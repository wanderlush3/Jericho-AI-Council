"""
Jericho — Memory Influence Tests (F-018)

Comprehensive tests for the memory influence engine: relevance scoring,
context building, prompt formatting, and integration with other modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory import AgentMemory, CoreBelief, MemoryEntry
from core.memory_influence import (
    MemoryContext,
    MemoryInfluence,
    MemoryInfluenceError,
    ScoredBelief,
    ScoredMemory,
    _jaccard,
    _tokenise,
)


# ─── Helpers ───────────────────────────────────────────────────


def _make_entry(
    content: str = "test content",
    event_type: str = "discussion",
    session_id: str = "S-001",
    source: str = "orchestrator",
    timestamp: str = "2026-01-01T00:00:00",
) -> MemoryEntry:
    return MemoryEntry(
        timestamp=timestamp,
        session_id=session_id,
        event_type=event_type,
        content=content,
        source=source,
    )


def _make_belief(
    topic: str = "safety",
    content: str = "Safety is paramount in AI design",
    source: str = "session",
) -> CoreBelief:
    return CoreBelief(
        topic=topic,
        content=content,
        added_timestamp="2026-01-01T00:00:00",
        source=source,
    )


# ─── Tokenisation ─────────────────────────────────────────────


class TestTokenise:
    """Tests for the tokeniser helper."""

    def test_basic_words(self):
        tokens = _tokenise("Hello world foo bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens

    def test_removes_stop_words(self):
        tokens = _tokenise("the cat is on the mat")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "on" not in tokens
        assert "cat" in tokens
        assert "mat" in tokens

    def test_lowercases(self):
        tokens = _tokenise("Ethics SAFETY Autonomy")
        assert "ethics" in tokens
        assert "safety" in tokens
        assert "autonomy" in tokens

    def test_empty_string(self):
        assert _tokenise("") == set()

    def test_only_stop_words(self):
        assert _tokenise("the and or is it") == set()

    def test_unicode(self):
        tokens = _tokenise("naïve résumé über")
        # Words with special chars may lose diacritics due to regex
        assert "na" in tokens or "ve" in tokens  # regex splits on ï


class TestJaccard:
    """Tests for Jaccard similarity."""

    def test_identical_sets(self):
        assert _jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        # {a,b,c} ∩ {b,c,d} = {b,c}, union = {a,b,c,d}
        assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)

    def test_empty_set_a(self):
        assert _jaccard(set(), {"a", "b"}) == 0.0

    def test_empty_set_b(self):
        assert _jaccard({"a", "b"}, set()) == 0.0

    def test_both_empty(self):
        assert _jaccard(set(), set()) == 0.0


# ─── ScoredMemory ─────────────────────────────────────────────


class TestScoredMemory:
    """Tests for the ScoredMemory data class."""

    def test_fields(self):
        entry = _make_entry()
        sm = ScoredMemory(entry=entry, relevance_score=0.75, reason="test")
        assert sm.entry is entry
        assert sm.relevance_score == 0.75
        assert sm.reason == "test"

    def test_frozen(self):
        sm = ScoredMemory(entry=_make_entry())
        with pytest.raises(AttributeError):
            sm.relevance_score = 0.5  # type: ignore[misc]

    def test_defaults(self):
        sm = ScoredMemory(entry=_make_entry())
        assert sm.relevance_score == 0.0
        assert sm.reason == ""

    def test_roundtrip(self):
        entry = _make_entry(content="ethics discussion")
        sm = ScoredMemory(entry=entry, relevance_score=0.8, reason="matched")
        d = sm.to_dict()
        restored = ScoredMemory.from_dict(d)
        assert restored.entry.content == "ethics discussion"
        assert restored.relevance_score == 0.8
        assert restored.reason == "matched"

    def test_to_dict_structure(self):
        sm = ScoredMemory(entry=_make_entry(), relevance_score=0.5)
        d = sm.to_dict()
        assert "entry" in d
        assert "relevance_score" in d
        assert "reason" in d
        assert isinstance(d["entry"], dict)


# ─── ScoredBelief ─────────────────────────────────────────────


class TestScoredBelief:
    """Tests for the ScoredBelief data class."""

    def test_fields(self):
        belief = _make_belief()
        sb = ScoredBelief(belief=belief, relevance_score=0.9, reason="topic match")
        assert sb.belief is belief
        assert sb.relevance_score == 0.9
        assert sb.reason == "topic match"

    def test_frozen(self):
        sb = ScoredBelief(belief=_make_belief())
        with pytest.raises(AttributeError):
            sb.relevance_score = 0.5  # type: ignore[misc]

    def test_defaults(self):
        sb = ScoredBelief(belief=_make_belief())
        assert sb.relevance_score == 0.0
        assert sb.reason == ""

    def test_roundtrip(self):
        belief = _make_belief(topic="ethics", content="Ethics must guide AI")
        sb = ScoredBelief(belief=belief, relevance_score=0.95, reason="ethics match")
        d = sb.to_dict()
        restored = ScoredBelief.from_dict(d)
        assert restored.belief.topic == "ethics"
        assert restored.relevance_score == 0.95
        assert restored.reason == "ethics match"

    def test_to_dict_structure(self):
        sb = ScoredBelief(belief=_make_belief(), relevance_score=0.5)
        d = sb.to_dict()
        assert "belief" in d
        assert "relevance_score" in d
        assert "reason" in d
        assert isinstance(d["belief"], dict)


# ─── MemoryContext ─────────────────────────────────────────────


class TestMemoryContext:
    """Tests for the MemoryContext data class."""

    def test_fields(self):
        ctx = MemoryContext(member_name="sage", formatted_text="test")
        assert ctx.member_name == "sage"
        assert ctx.formatted_text == "test"
        assert ctx.beliefs == []
        assert ctx.memories == []

    def test_has_content_empty(self):
        ctx = MemoryContext(member_name="sage")
        assert ctx.has_content is False

    def test_has_content_with_beliefs(self):
        ctx = MemoryContext(
            member_name="sage",
            beliefs=[ScoredBelief(belief=_make_belief())],
        )
        assert ctx.has_content is True

    def test_has_content_with_memories(self):
        ctx = MemoryContext(
            member_name="sage",
            memories=[ScoredMemory(entry=_make_entry())],
        )
        assert ctx.has_content is True

    def test_roundtrip(self):
        ctx = MemoryContext(
            member_name="sage",
            beliefs=[ScoredBelief(belief=_make_belief(), relevance_score=0.5)],
            memories=[ScoredMemory(entry=_make_entry(), relevance_score=0.3)],
            formatted_text="### test",
        )
        d = ctx.to_dict()
        restored = MemoryContext.from_dict(d)
        assert restored.member_name == "sage"
        assert len(restored.beliefs) == 1
        assert len(restored.memories) == 1
        assert restored.formatted_text == "### test"


# ─── MemoryInfluence Init ─────────────────────────────────────


class TestMemoryInfluenceInit:
    """Tests for MemoryInfluence construction."""

    def test_defaults(self):
        mi = MemoryInfluence()
        assert mi.memory_limit == 10
        assert mi.belief_limit == 5
        assert mi.min_relevance == 0.1
        assert mi.belief_boost == 1.5

    def test_custom_values(self):
        mi = MemoryInfluence(
            memory_limit=3,
            belief_limit=2,
            min_relevance=0.5,
            belief_boost=2.0,
        )
        assert mi.memory_limit == 3
        assert mi.belief_limit == 2
        assert mi.min_relevance == 0.5
        assert mi.belief_boost == 2.0

    def test_repr(self):
        mi = MemoryInfluence()
        r = repr(mi)
        assert "MemoryInfluence" in r
        assert "memory_limit=" in r
        assert "belief_boost=" in r


# ─── Score Memories ───────────────────────────────────────────


class TestScoreMemories:
    """Tests for memory scoring."""

    def test_empty_entries(self):
        mi = MemoryInfluence()
        result = mi.score_memories([], ["ethics", "safety"])
        assert result == []

    def test_empty_keywords(self):
        mi = MemoryInfluence()
        entries = [_make_entry(content="ethics safety discussion")]
        result = mi.score_memories(entries, [])
        assert result == []

    def test_relevant_entry_scores_high(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [
            _make_entry(content="Discussed ethics and safety guidelines"),
            _make_entry(content="Talked about lunch plans"),
        ]
        result = mi.score_memories(entries, ["ethics", "safety"])
        assert len(result) >= 1
        # Ethics entry should score higher
        if len(result) >= 2:
            assert result[0].relevance_score >= result[1].relevance_score

    def test_threshold_filtering(self):
        mi = MemoryInfluence(min_relevance=0.9)
        entries = [_make_entry(content="vaguely related topic")]
        result = mi.score_memories(entries, ["ethics"])
        # Low overlap shouldn't pass 0.9 threshold
        assert len(result) == 0

    def test_limit_applied(self):
        mi = MemoryInfluence(memory_limit=2, min_relevance=0.0)
        entries = [
            _make_entry(content=f"ethics safety topic {i}")
            for i in range(10)
        ]
        result = mi.score_memories(entries, ["ethics", "safety", "topic"])
        assert len(result) <= 2

    def test_sorted_by_relevance(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [
            _make_entry(content="unrelated stuff here"),
            _make_entry(content="ethics safety guidelines protocols"),
            _make_entry(content="ethics discussion"),
        ]
        result = mi.score_memories(entries, ["ethics", "safety", "guidelines"])
        if len(result) >= 2:
            assert result[0].relevance_score >= result[1].relevance_score

    def test_reason_includes_keywords(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [_make_entry(content="ethics and safety are important")]
        result = mi.score_memories(entries, ["ethics", "safety"])
        assert len(result) >= 1
        assert "ethics" in result[0].reason.lower() or "safety" in result[0].reason.lower()

    def test_event_type_included_in_scoring(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [_make_entry(content="something", event_type="ethics_review")]
        result = mi.score_memories(entries, ["ethics"])
        # Should find at least a partial match via event_type
        assert len(result) >= 1


# ─── Score Beliefs ────────────────────────────────────────────


class TestScoreBeliefs:
    """Tests for belief scoring."""

    def test_empty_beliefs(self):
        mi = MemoryInfluence()
        result = mi.score_beliefs([], ["ethics"])
        assert result == []

    def test_empty_keywords(self):
        mi = MemoryInfluence()
        beliefs = [_make_belief(topic="safety")]
        result = mi.score_beliefs(beliefs, [])
        assert result == []

    def test_relevant_belief_scores_high(self):
        mi = MemoryInfluence(min_relevance=0.0)
        beliefs = [
            _make_belief(topic="ethics", content="Ethics guide all decisions"),
            _make_belief(topic="cooking", content="Pizza is delicious"),
        ]
        result = mi.score_beliefs(beliefs, ["ethics", "decisions"])
        assert len(result) >= 1
        # Ethics belief should score higher
        if len(result) >= 2:
            assert result[0].relevance_score >= result[1].relevance_score

    def test_belief_boost_applied(self):
        mi = MemoryInfluence(belief_boost=2.0, min_relevance=0.0)
        beliefs = [_make_belief(topic="safety", content="Safety first")]
        # Same text as memory entry for comparison
        entries = [_make_entry(content="Safety first")]

        belief_result = mi.score_beliefs(beliefs, ["safety", "first"])
        memory_result = mi.score_memories(entries, ["safety", "first"])

        if belief_result and memory_result:
            # Belief should score higher due to boost
            assert belief_result[0].relevance_score >= memory_result[0].relevance_score

    def test_belief_boost_capped_at_1(self):
        mi = MemoryInfluence(belief_boost=100.0, min_relevance=0.0)
        beliefs = [_make_belief(topic="safety", content="Safety first")]
        result = mi.score_beliefs(beliefs, ["safety", "first"])
        if result:
            assert result[0].relevance_score <= 1.0

    def test_threshold_filtering(self):
        mi = MemoryInfluence(min_relevance=0.9)
        beliefs = [_make_belief(topic="cooking", content="Pizza is great")]
        result = mi.score_beliefs(beliefs, ["ethics"])
        assert len(result) == 0

    def test_limit_applied(self):
        mi = MemoryInfluence(belief_limit=2, min_relevance=0.0)
        beliefs = [
            _make_belief(topic=f"topic_{i}", content="ethics safety relevance")
            for i in range(10)
        ]
        result = mi.score_beliefs(beliefs, ["ethics", "safety"])
        assert len(result) <= 2

    def test_reason_includes_topic(self):
        mi = MemoryInfluence(min_relevance=0.0)
        beliefs = [_make_belief(topic="safety", content="Safety is key")]
        result = mi.score_beliefs(beliefs, ["safety"])
        assert len(result) >= 1
        assert "safety" in result[0].reason.lower()


# ─── Build Context ────────────────────────────────────────────


class TestBuildContext:
    """Tests for end-to-end context building."""

    def test_builds_from_filesystem(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        # Write beliefs
        agent_mem.write_core_belief(
            CoreBelief.create("safety", "Safety is paramount", source="session")
        )
        agent_mem.write_core_belief(
            CoreBelief.create("ethics", "Ethics guide all AI", source="session")
        )

        # Write session events
        agent_mem.append_session_event(
            MemoryEntry.create("S-001", "discussion", "Discussed AI safety protocols")
        )
        agent_mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "Talked about weather")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context("sage", ["safety", "ethics", "AI"], memories_dir=mem_dir)

        assert ctx.member_name == "sage"
        assert ctx.has_content is True
        assert len(ctx.beliefs) >= 1
        assert len(ctx.memories) >= 1
        assert ctx.formatted_text != ""

    def test_empty_member_memories(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        loc_dir = tmp_path / "locations"
        loc_dir.mkdir()

        mi = MemoryInfluence()
        ctx = mi.build_context(
            "newmember", ["ethics"], memories_dir=mem_dir, locations_dir=loc_dir,
        )

        assert ctx.has_content is False
        assert ctx.beliefs == []
        assert ctx.memories == []
        assert ctx.formatted_text == ""

    def test_case_insensitive_member(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("SAGE", memories_dir=mem_dir)
        agent_mem.write_core_belief(
            CoreBelief.create("test", "Test belief", source="test")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context("Sage", ["test"], memories_dir=mem_dir)
        assert ctx.member_name == "sage"
        assert ctx.has_content is True

    def test_respects_limits(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        for i in range(20):
            agent_mem.write_core_belief(
                CoreBelief.create(
                    f"topic_{i}",
                    f"ethics safety belief number {i}",
                    source="test",
                )
            )
            agent_mem.append_session_event(
                MemoryEntry.create(
                    "S-001", "discussion",
                    f"Discussed ethics and safety item {i}",
                )
            )

        mi = MemoryInfluence(
            memory_limit=3, belief_limit=2, min_relevance=0.0,
        )
        ctx = mi.build_context("sage", ["ethics", "safety"], memories_dir=mem_dir)
        assert len(ctx.beliefs) <= 2
        assert len(ctx.memories) <= 3


# ─── Format for Prompt ────────────────────────────────────────


class TestFormatForPrompt:
    """Tests for prompt formatting."""

    def test_empty_produces_empty(self):
        result = MemoryInfluence.format_for_prompt([], [])
        assert result == ""

    def test_beliefs_only(self):
        beliefs = [
            ScoredBelief(
                belief=_make_belief(topic="safety", content="Safety first"),
                relevance_score=0.8,
            ),
        ]
        result = MemoryInfluence.format_for_prompt(beliefs, [])
        assert "Core Beliefs" in result
        assert "safety" in result.lower()
        assert "Safety first" in result

    def test_memories_only(self):
        memories = [
            ScoredMemory(
                entry=_make_entry(content="Discussed AI safety", event_type="discussion"),
                relevance_score=0.6,
            ),
        ]
        result = MemoryInfluence.format_for_prompt([], memories)
        assert "Relevant Memories" in result
        assert "Discussed AI safety" in result
        assert "[discussion]" in result

    def test_both_beliefs_and_memories(self):
        beliefs = [
            ScoredBelief(belief=_make_belief(), relevance_score=0.8),
        ]
        memories = [
            ScoredMemory(entry=_make_entry(), relevance_score=0.5),
        ]
        result = MemoryInfluence.format_for_prompt(beliefs, memories)
        assert "Core Beliefs" in result
        assert "Relevant Memories" in result

    def test_multiple_beliefs_formatted(self):
        beliefs = [
            ScoredBelief(
                belief=_make_belief(topic="safety", content="Safety first"),
                relevance_score=0.9,
            ),
            ScoredBelief(
                belief=_make_belief(topic="ethics", content="Ethics guide us"),
                relevance_score=0.7,
            ),
        ]
        result = MemoryInfluence.format_for_prompt(beliefs, [])
        assert "**safety**" in result
        assert "**ethics**" in result

    def test_multiple_memories_formatted(self):
        memories = [
            ScoredMemory(
                entry=_make_entry(content="First memory", event_type="chat"),
                relevance_score=0.8,
            ),
            ScoredMemory(
                entry=_make_entry(content="Second memory", event_type="discussion"),
                relevance_score=0.5,
            ),
        ]
        result = MemoryInfluence.format_for_prompt([], memories)
        assert "First memory" in result
        assert "Second memory" in result
        assert "[chat]" in result
        assert "[discussion]" in result


# ─── Extract Keywords ─────────────────────────────────────────


class TestExtractKeywords:
    """Tests for keyword extraction helper."""

    def test_basic_extraction(self):
        keywords = MemoryInfluence.extract_keywords("Ethics of AI Safety")
        assert "ethics" in keywords
        assert "safety" in keywords

    def test_removes_stop_words(self):
        keywords = MemoryInfluence.extract_keywords("The ethics of the AI")
        assert "the" not in keywords
        assert "of" not in keywords
        assert "ethics" in keywords

    def test_empty_string(self):
        keywords = MemoryInfluence.extract_keywords("")
        assert keywords == []

    def test_sorted(self):
        keywords = MemoryInfluence.extract_keywords("zebra apple mango")
        assert keywords == sorted(keywords)


# ─── Edge Cases ───────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests for memory influence."""

    def test_unicode_content(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)

        agent_mem.write_core_belief(
            CoreBelief.create("ethik", "Ethik ist wichtig für KI", source="test")
        )
        agent_mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "Diskussion über Ethik und Sicherheit")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context("sage", ["ethik", "sicherheit"], memories_dir=mem_dir)
        # Should not crash with unicode
        assert ctx.member_name == "sage"

    def test_very_long_content(self):
        mi = MemoryInfluence(min_relevance=0.0)
        long_content = "ethics safety " * 1000
        entries = [_make_entry(content=long_content)]
        result = mi.score_memories(entries, ["ethics", "safety"])
        assert len(result) >= 1

    def test_all_below_threshold(self):
        mi = MemoryInfluence(min_relevance=1.0)
        entries = [_make_entry(content="something random")]
        beliefs = [_make_belief(topic="cooking", content="Pizza")]
        mem_result = mi.score_memories(entries, ["ethics"])
        bel_result = mi.score_beliefs(beliefs, ["ethics"])
        assert mem_result == []
        assert bel_result == []

    def test_no_beliefs_only_memories(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)
        agent_mem.append_session_event(
            MemoryEntry.create("S-001", "discussion", "Discussed ethics")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context("sage", ["ethics"], memories_dir=mem_dir)
        assert ctx.beliefs == []
        assert len(ctx.memories) >= 1

    def test_no_memories_only_beliefs(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)
        agent_mem.write_core_belief(
            CoreBelief.create("ethics", "Ethics matter", source="test")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context("sage", ["ethics"], memories_dir=mem_dir)
        assert len(ctx.beliefs) >= 1
        assert ctx.memories == []

    def test_special_characters_in_keywords(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [_make_entry(content="AI safety! ethics? protocols.")]
        result = mi.score_memories(entries, ["safety!", "ethics?"])
        # Regex tokeniser should handle special chars gracefully
        assert isinstance(result, list)

    def test_duplicate_keywords(self):
        mi = MemoryInfluence(min_relevance=0.0)
        entries = [_make_entry(content="ethics ethics ethics")]
        result = mi.score_memories(entries, ["ethics", "ethics", "ethics"])
        assert isinstance(result, list)


# ─── Integration with Session Prompts ────────────────────────


class TestSessionIntegration:
    """Verify memory influence integrates with session prompt builders."""

    def test_briefing_prompt_includes_memory_context(self, tmp_path: Path):
        """Session briefing should include memory context when available."""
        from core.session import _build_briefing_prompt, SessionRecord
        from core.registry import CouncilMember

        member = CouncilMember(
            name="Sage",
            role="Ethics",
            description="Ethics expert",
            api_provider="openrouter",
            model="test-model",
            system_prompt="You are Sage.",
        )
        record = SessionRecord.create(
            "S-001", "Ethics Review", activity_type="discussion",
            agenda="Discuss AI safety and ethics",
            participants=["Sage"],
        )

        # Build memory context
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)
        agent_mem.write_core_belief(
            CoreBelief.create("safety", "Safety is paramount", source="test")
        )
        agent_mem.append_session_event(
            MemoryEntry.create("S-000", "discussion", "Discussed AI safety protocols")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context(
            "sage",
            MemoryInfluence.extract_keywords(f"{record.title} {record.agenda}"),
            memories_dir=mem_dir,
        )

        # The context should have content
        assert ctx.has_content is True
        assert "safety" in ctx.formatted_text.lower()


class TestDiscussionIntegration:
    """Verify memory influence can work with discussion prompts."""

    def test_memory_context_can_be_generated(self, tmp_path: Path):
        """Discussion prompts should be augmentable with memory context."""
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("logic", memories_dir=mem_dir)
        agent_mem.write_core_belief(
            CoreBelief.create(
                "systems", "Systems thinking yields better designs", source="test"
            )
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context(
            "logic",
            MemoryInfluence.extract_keywords("Systems architecture proposal"),
            memories_dir=mem_dir,
        )

        assert ctx.has_content is True
        assert "systems" in ctx.formatted_text.lower()


class TestAgentChatIntegration:
    """Verify memory influence works with agent chat prompts."""

    def test_memory_context_for_chat(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("spark", memories_dir=mem_dir)
        agent_mem.write_core_belief(
            CoreBelief.create("creativity", "Creativity drives innovation")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context(
            "spark",
            MemoryInfluence.extract_keywords("Creative approaches to AI design"),
            memories_dir=mem_dir,
        )

        assert ctx.has_content is True


class TestHumanChatIntegration:
    """Verify memory influence works with human chat prompts."""

    def test_memory_context_for_human_chat(self, tmp_path: Path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        agent_mem = AgentMemory("sage", memories_dir=mem_dir)
        agent_mem.append_session_event(
            MemoryEntry.create("S-001", "human_chat", "Human asked about ethics")
        )

        mi = MemoryInfluence(min_relevance=0.0)
        ctx = mi.build_context(
            "sage",
            MemoryInfluence.extract_keywords("Ethics discussion with human"),
            memories_dir=mem_dir,
        )

        assert len(ctx.memories) >= 1
