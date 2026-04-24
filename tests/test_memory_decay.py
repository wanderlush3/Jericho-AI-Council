"""
Jericho — Memory Decay, Summarization & Contested Memories Tests

Comprehensive tests for:
  - Time-weighted memory decay scoring
  - Memory summarization (session grouping, summarized log I/O)
  - Contested memories (recording, reading, prompt formatting)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory import AgentMemory, CoreBelief, MemoryEntry
from core.memory_influence import (
    MemoryContext,
    MemoryInfluence,
    ScoredBelief,
    ScoredMemory,
    _tokenise,
)


# ─── Helpers ───────────────────────────────────────────────────


def _make_entry(
    content: str = "test content",
    event_type: str = "discussion",
    session_id: str = "S-001",
    source: str = "orchestrator",
    timestamp: str | None = None,
) -> MemoryEntry:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return MemoryEntry(
        timestamp=timestamp,
        session_id=session_id,
        event_type=event_type,
        content=content,
        source=source,
    )


def _make_aged_entry(
    days_old: float,
    content: str = "test content",
    session_id: str = "S-001",
) -> MemoryEntry:
    """Create a MemoryEntry with a timestamp *days_old* days in the past."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_old)
    return _make_entry(
        content=content,
        session_id=session_id,
        timestamp=ts.isoformat(),
    )


def _make_belief(
    topic: str = "safety",
    content: str = "Safety is paramount in AI design",
) -> CoreBelief:
    return CoreBelief(
        topic=topic,
        content=content,
        added_timestamp="2026-01-01T00:00:00",
        source="session",
    )


# ═══════════════════════════════════════════════════════════════
# MEMORY DECAY TESTS
# ═══════════════════════════════════════════════════════════════


class TestDecayFactor:
    """Tests for MemoryInfluence._compute_decay_factor."""

    def test_recent_memory_no_decay(self):
        """A fresh memory should have a factor near 1.0."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        ts = datetime.now(timezone.utc).isoformat()
        factor = mi._compute_decay_factor(ts)
        assert factor >= 0.99

    def test_half_life_decay(self):
        """A memory exactly one half-life old should have factor ≈ 0.5."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        factor = mi._compute_decay_factor(ts)
        assert abs(factor - 0.5) < 0.05

    def test_double_half_life(self):
        """A memory two half-lives old should have factor ≈ 0.25."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        factor = mi._compute_decay_factor(ts)
        assert abs(factor - 0.25) < 0.05

    def test_very_old_memory_clamped(self):
        """Very old memory should be clamped to decay_min_factor."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        ts = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        factor = mi._compute_decay_factor(ts)
        assert factor == pytest.approx(0.1)

    def test_decay_disabled_returns_1(self):
        """With decay disabled, factor should be 1.0 regardless of age."""
        mi = MemoryInfluence(
            decay_enabled=False,
            embedding_provider=None,
        )
        ts = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        factor = mi._compute_decay_factor(ts)
        assert factor == 1.0

    def test_invalid_timestamp(self):
        """Invalid timestamp should return 1.0 (no penalty)."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        factor = mi._compute_decay_factor("not-a-timestamp")
        assert factor == 1.0

    def test_naive_timestamp_treated_as_utc(self):
        """Naive timestamps (no tz) should be treated as UTC."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        factor = mi._compute_decay_factor(ts)
        assert 0.95 < factor < 1.0  # 1 day old, very mild decay


class TestDecayInScoring:
    """Tests that decay affects score_memories output."""

    def test_recent_beats_old_with_same_content(self):
        """Same content but different ages — recent should score higher."""
        mi = MemoryInfluence(
            min_relevance=0.0,
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        old = _make_aged_entry(60, content="ethics safety discussion")
        new = _make_aged_entry(1, content="ethics safety discussion")
        result = mi.score_memories([old, new], ["ethics", "safety"])
        assert len(result) >= 2
        # Newer entry should have higher score
        assert result[0].entry.timestamp > result[1].entry.timestamp
        assert result[0].relevance_score > result[1].relevance_score

    def test_decay_reason_annotation(self):
        """Decayed scores should include freshness annotation in reason."""
        mi = MemoryInfluence(
            min_relevance=0.0,
            decay_enabled=True,
            decay_half_life_days=30,
            decay_min_factor=0.1,
            embedding_provider=None,
        )
        old = _make_aged_entry(60, content="ethics safety discussion")
        result = mi.score_memories([old], ["ethics", "safety"])
        if result:
            assert "freshness" in result[0].reason.lower()

    def test_no_freshness_annotation_when_disabled(self):
        """With decay disabled, no freshness annotation should appear."""
        mi = MemoryInfluence(
            min_relevance=0.0,
            decay_enabled=False,
            embedding_provider=None,
        )
        old = _make_aged_entry(60, content="ethics safety discussion")
        result = mi.score_memories([old], ["ethics", "safety"])
        if result:
            assert "freshness" not in result[0].reason.lower()

    def test_decay_properties_accessible(self):
        """Decay settings should be exposed via properties."""
        mi = MemoryInfluence(
            decay_enabled=True,
            decay_half_life_days=15,
            decay_min_factor=0.2,
            embedding_provider=None,
        )
        assert mi.decay_enabled is True
        assert mi.decay_half_life == 15
        assert mi.decay_min_factor == 0.2


# ═══════════════════════════════════════════════════════════════
# MEMORY SUMMARIZATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestSessionIds:
    """Tests for AgentMemory.get_unique_session_ids."""

    def test_empty_log(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.get_unique_session_ids() == []

    def test_single_session(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "hello")
        )
        mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "world")
        )
        ids = mem.get_unique_session_ids()
        assert ids == ["S-001"]

    def test_multiple_sessions_ordered(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for sid in ["S-001", "S-002", "S-003", "S-001"]:
            mem.append_session_event(
                MemoryEntry.create(sid, "chat", f"content {sid}")
            )
        ids = mem.get_unique_session_ids()
        assert ids == ["S-001", "S-002", "S-003"]


class TestSessionsNeedingSummary:
    """Tests for AgentMemory.get_sessions_needing_summary."""

    def test_not_enough_sessions(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for sid in ["S-001", "S-002"]:
            mem.append_session_event(
                MemoryEntry.create(sid, "chat", f"content {sid}")
            )
        groups = mem.get_sessions_needing_summary(keep_recent=3)
        assert groups == []

    def test_old_sessions_returned(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(7):
            mem.append_session_event(
                MemoryEntry.create(
                    f"S-{i:03d}", "chat", f"content for session {i}"
                )
            )
        groups = mem.get_sessions_needing_summary(keep_recent=3)
        # 7 sessions, keep 3 recent → 4 old sessions
        assert len(groups) == 4
        # Check they're the oldest sessions
        session_ids = [g[0].session_id for g in groups]
        assert "S-000" in session_ids
        assert "S-003" in session_ids
        # Recent sessions not included
        assert "S-004" not in session_ids
        assert "S-006" not in session_ids

    def test_already_summarized_excluded(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(7):
            mem.append_session_event(
                MemoryEntry.create(
                    f"S-{i:03d}", "chat", f"content for session {i}"
                )
            )
        # Mark S-000 as already summarized
        mem.write_summarized_entry(
            MemoryEntry.create("S-000", "summary", "summary of S-000")
        )
        groups = mem.get_sessions_needing_summary(keep_recent=3)
        session_ids = [g[0].session_id for g in groups]
        assert "S-000" not in session_ids
        assert len(groups) == 3  # S-001, S-002, S-003


class TestSummarizedLog:
    """Tests for summarized log I/O."""

    def test_read_empty(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.read_summarized_log() == []

    def test_write_and_read(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = MemoryEntry.create("S-001", "summary", "Condensed summary")
        mem.write_summarized_entry(entry)

        result = mem.read_summarized_log()
        assert len(result) == 1
        assert result[0].event_type == "summary"
        assert result[0].content == "Condensed summary"

    def test_multiple_summaries(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(3):
            entry = MemoryEntry.create(
                f"S-{i:03d}", "summary", f"Summary {i}"
            )
            mem.write_summarized_entry(entry)

        result = mem.read_summarized_log()
        assert len(result) == 3


class TestSummarizationInBuildContext:
    """Tests that build_context includes summarized entries."""

    def test_summarized_entries_included(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        # Write a summarized entry with matching keywords
        agent_mem.write_summarized_entry(
            MemoryEntry.create(
                "S-OLD", "summary",
                "Summary: discussed ethics and safety protocols extensively",
            )
        )

        mi = MemoryInfluence(
            min_relevance=0.0,
            summarization_enabled=True,
            decay_enabled=False,
            embedding_provider=None,
        )
        ctx = mi.build_context(
            "sage", ["ethics", "safety"], memories_dir=mem_dir,
        )
        # The summarized entry should appear in scored memories
        assert any(
            "summary" in m.entry.event_type.lower()
            for m in ctx.memories
        )

    def test_summarization_disabled_excludes_summaries(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        agent_mem.write_summarized_entry(
            MemoryEntry.create(
                "S-OLD", "summary",
                "Summary: discussed ethics and safety protocols",
            )
        )

        mi = MemoryInfluence(
            min_relevance=0.0,
            summarization_enabled=False,
            decay_enabled=False,
            embedding_provider=None,
        )
        ctx = mi.build_context(
            "sage", ["ethics", "safety"], memories_dir=mem_dir,
        )
        # No summarized entries should be present
        assert all(
            m.entry.event_type != "summary"
            for m in ctx.memories
        )


# ═══════════════════════════════════════════════════════════════
# CONTESTED MEMORIES TESTS
# ═══════════════════════════════════════════════════════════════


class TestContestedMemories:
    """Tests for contested memory recording and reading."""

    def test_record_and_read(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        record = mem.record_contested_memory(
            event_id="S-001:2026-01-01T00:00:00",
            member_name="sage",
            content="I recall we discussed safety more harshly",
            original_content="Discussed safety protocols",
        )
        assert record["event_id"] == "S-001:2026-01-01T00:00:00"
        assert record["member_name"] == "sage"

        all_records = mem.read_contested_memories()
        assert len(all_records) == 1
        assert all_records[0]["content"] == "I recall we discussed safety more harshly"

    def test_multiple_contested_for_event(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        event_id = "S-001:2026-01-01T00:00:00"
        mem.record_contested_memory(
            event_id=event_id,
            member_name="sage",
            content="Version A",
            original_content="Original",
        )
        mem.record_contested_memory(
            event_id=event_id,
            member_name="spark",
            content="Version B",
            original_content="Original",
        )

        results = mem.get_contested_for_event(event_id)
        assert len(results) == 2

    def test_empty_contested(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.read_contested_memories() == []
        assert mem.get_contested_for_event("X") == []


class TestContestedInFormatPrompt:
    """Tests for contested memory rendering in format_for_prompt."""

    def test_contested_appears_as_sub_bullet(self):
        memories = [
            ScoredMemory(
                entry=_make_entry(
                    content="Discussed safety protocols",
                    session_id="S-001",
                    timestamp="2026-01-01T00:00:00",
                ),
                relevance_score=0.8,
            ),
        ]
        contested = {
            "S-001:2026-01-01T00:00:00": [
                {
                    "member_name": "spark",
                    "content": "I remember it being about creativity",
                },
            ],
        }
        result = MemoryInfluence.format_for_prompt(
            [], memories, contested=contested,
        )
        assert "spark's recollection" in result
        assert "creativity" in result

    def test_no_contested_no_sub_bullets(self):
        memories = [
            ScoredMemory(
                entry=_make_entry(
                    content="Normal memory",
                    session_id="S-001",
                    timestamp="2026-01-01T00:00:00",
                ),
                relevance_score=0.7,
            ),
        ]
        result = MemoryInfluence.format_for_prompt([], memories)
        assert "recollection" not in result


class TestContestedInBuildContext:
    """Tests for contested memory loading in build_context."""

    def test_contested_loaded_in_context(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        # Write a session event
        entry = MemoryEntry.create(
            "S-001", "discussion", "Discussed ethics"
        )
        agent_mem.append_session_event(entry)

        # Record a contested memory for it
        event_id = f"{entry.session_id}:{entry.timestamp}"
        agent_mem.record_contested_memory(
            event_id=event_id,
            member_name="spark",
            content="I thought we discussed creativity, not ethics",
            original_content=entry.content,
        )

        mi = MemoryInfluence(
            min_relevance=0.0,
            contested_enabled=True,
            decay_enabled=False,
            embedding_provider=None,
        )
        ctx = mi.build_context(
            "sage", ["ethics", "discussion"], memories_dir=mem_dir,
        )
        assert ctx.has_content
        # Should appear in formatted text
        assert "spark's recollection" in ctx.formatted_text

    def test_contested_disabled_no_rendering(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        entry = MemoryEntry.create(
            "S-001", "discussion", "Discussed ethics"
        )
        agent_mem.append_session_event(entry)

        event_id = f"{entry.session_id}:{entry.timestamp}"
        agent_mem.record_contested_memory(
            event_id=event_id,
            member_name="spark",
            content="Different recollection",
            original_content=entry.content,
        )

        mi = MemoryInfluence(
            min_relevance=0.0,
            contested_enabled=False,
            decay_enabled=False,
            embedding_provider=None,
        )
        ctx = mi.build_context(
            "sage", ["ethics", "discussion"], memories_dir=mem_dir,
        )
        # Should NOT appear when contested is disabled
        assert "recollection" not in ctx.formatted_text


# ═══════════════════════════════════════════════════════════════
# PROPERTY TESTS
# ═══════════════════════════════════════════════════════════════


class TestNewProperties:
    """Tests for new properties on MemoryInfluence."""

    def test_default_properties(self):
        mi = MemoryInfluence(embedding_provider=None)
        assert mi.decay_enabled is True
        assert mi.decay_half_life == 30
        assert mi.decay_min_factor == 0.1
        assert mi.summarization_enabled is True
        assert mi.contested_enabled is True
        assert mi.contested_probability == 0.03

    def test_custom_properties(self):
        mi = MemoryInfluence(
            decay_enabled=False,
            decay_half_life_days=15,
            decay_min_factor=0.2,
            summarization_enabled=False,
            contested_enabled=False,
            contested_probability=0.01,
            embedding_provider=None,
        )
        assert mi.decay_enabled is False
        assert mi.decay_half_life == 15
        assert mi.decay_min_factor == 0.2
        assert mi.summarization_enabled is False
        assert mi.contested_enabled is False
        assert mi.contested_probability == 0.01

    def test_repr_includes_new_flags(self):
        mi = MemoryInfluence(embedding_provider=None)
        r = repr(mi)
        assert "decay=" in r
        assert "summarization=" in r


# ═══════════════════════════════════════════════════════════════
# LLM SUMMARIZATION TESTS (mocked)
# ═══════════════════════════════════════════════════════════════


class TestSummarizeSessionsLLM:
    """Tests for MemoryInfluence.summarize_sessions_llm with mocked LLM."""

    @pytest.mark.asyncio
    async def test_summarize_calls_llm(self, tmp_path: Path):
        """When threshold is met, LLM should be called."""
        mem = AgentMemory("sage", memories_dir=tmp_path)
        # Create 7 sessions (threshold is 6)
        for i in range(7):
            mem.append_session_event(
                MemoryEntry.create(
                    f"S-{i:03d}", "chat", f"content for session {i}"
                )
            )

        with patch.object(
            MemoryInfluence, "_call_llm",
            new_callable=AsyncMock,
            return_value="Condensed summary of the session.",
        ) as mock_llm:
            summaries = await MemoryInfluence.summarize_sessions_llm(
                mem, keep_recent=3,
            )
            assert len(summaries) == 4  # 7 - 3 recent = 4 old
            assert mock_llm.call_count == 4

            # Each summary should be written to summarized log
            saved = mem.read_summarized_log()
            assert len(saved) == 4

    @pytest.mark.asyncio
    async def test_below_threshold_no_call(self, tmp_path: Path):
        """When below threshold, LLM should not be called."""
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(3):
            mem.append_session_event(
                MemoryEntry.create(f"S-{i:03d}", "chat", f"content {i}")
            )

        with patch.object(
            MemoryInfluence, "_call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            summaries = await MemoryInfluence.summarize_sessions_llm(
                mem, keep_recent=3,
            )
            assert summaries == []
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure_continues(self, tmp_path: Path):
        """If LLM fails for one session, others should still be summarized."""
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(7):
            mem.append_session_event(
                MemoryEntry.create(
                    f"S-{i:03d}", "chat", f"content for session {i}"
                )
            )

        call_count = 0

        async def flaky_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM error")
            return "Summary text."

        with patch.object(
            MemoryInfluence, "_call_llm",
            side_effect=flaky_llm,
        ):
            summaries = await MemoryInfluence.summarize_sessions_llm(
                mem, keep_recent=3,
            )
            # 4 old sessions, 1 failed → 3 summaries
            assert len(summaries) == 3


class TestMaybeGenerateContested:
    """Tests for MemoryInfluence.maybe_generate_contested_memory."""

    @pytest.mark.asyncio
    async def test_probability_zero_no_call(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = MemoryEntry.create("S-001", "chat", "Something happened")

        result = await MemoryInfluence.maybe_generate_contested_memory(
            mem, "sage", entry, probability=0.0,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_probability_one_always_calls(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = MemoryEntry.create("S-001", "chat", "Something happened")

        with patch.object(
            MemoryInfluence, "_call_llm",
            new_callable=AsyncMock,
            return_value="My version of events.",
        ):
            result = await MemoryInfluence.maybe_generate_contested_memory(
                mem, "sage", entry, probability=1.0,
            )
            assert result is not None
            assert result["member_name"] == "sage"
            assert result["content"] == "My version of events."

            # Should be persisted
            records = mem.read_contested_memories()
            assert len(records) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = MemoryEntry.create("S-001", "chat", "Something")

        with patch.object(
            MemoryInfluence, "_call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            result = await MemoryInfluence.maybe_generate_contested_memory(
                mem, "sage", entry, probability=1.0,
            )
            assert result is None
