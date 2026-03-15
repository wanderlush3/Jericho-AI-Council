"""
Jericho — Memory System Tests (F-004)

Comprehensive tests for AgentMemory, SharedMemory, and data models.
All tests use tmp_path — no real data/memories/ directory is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory import (
    AgentMemory,
    CoreBelief,
    MemoryCorruptionError,
    MemoryEntry,
    SharedMemory,
    _atomic_write,
)


# ═══════════════════════════════════════════════════════════════
#  MemoryEntry
# ═══════════════════════════════════════════════════════════════


class TestMemoryEntry:
    """Tests for the MemoryEntry frozen dataclass."""

    def test_fields(self):
        entry = MemoryEntry(
            timestamp="2026-01-01T00:00:00Z",
            session_id="S-001",
            event_type="discussion",
            content="Sage spoke about ethics",
            source="sage",
            metadata={"topic": "ethics"},
        )
        assert entry.timestamp == "2026-01-01T00:00:00Z"
        assert entry.session_id == "S-001"
        assert entry.event_type == "discussion"
        assert entry.content == "Sage spoke about ethics"
        assert entry.source == "sage"
        assert entry.metadata == {"topic": "ethics"}

    def test_defaults(self):
        entry = MemoryEntry(
            timestamp="t", session_id="s", event_type="e", content="c"
        )
        assert entry.source == ""
        assert entry.metadata == {}

    def test_frozen(self):
        entry = MemoryEntry(
            timestamp="t", session_id="s", event_type="e", content="c"
        )
        with pytest.raises(AttributeError):
            entry.content = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        entry = MemoryEntry(
            timestamp="t", session_id="s", event_type="e", content="c",
            source="src", metadata={"k": "v"},
        )
        d = entry.to_dict()
        assert d == {
            "timestamp": "t",
            "session_id": "s",
            "event_type": "e",
            "content": "c",
            "source": "src",
            "metadata": {"k": "v"},
        }

    def test_from_dict_roundtrip(self):
        original = MemoryEntry(
            timestamp="t", session_id="s", event_type="e", content="c",
            source="src", metadata={"k": "v"},
        )
        rebuilt = MemoryEntry.from_dict(original.to_dict())
        assert rebuilt == original

    def test_from_dict_missing_optionals(self):
        data = {"timestamp": "t", "session_id": "s", "event_type": "e", "content": "c"}
        entry = MemoryEntry.from_dict(data)
        assert entry.source == ""
        assert entry.metadata == {}

    def test_create_factory(self):
        entry = MemoryEntry.create(
            session_id="S-001", event_type="vote", content="Voted for",
        )
        assert entry.session_id == "S-001"
        assert entry.event_type == "vote"
        assert entry.content == "Voted for"
        assert entry.timestamp  # non-empty ISO string


# ═══════════════════════════════════════════════════════════════
#  CoreBelief
# ═══════════════════════════════════════════════════════════════


class TestCoreBelief:
    """Tests for the CoreBelief frozen dataclass."""

    def test_fields(self):
        b = CoreBelief(topic="safety", content="Safety first", added_timestamp="t", source="sage")
        assert b.topic == "safety"
        assert b.content == "Safety first"
        assert b.added_timestamp == "t"
        assert b.source == "sage"

    def test_defaults(self):
        b = CoreBelief(topic="t", content="c")
        assert b.added_timestamp == ""
        assert b.source == ""

    def test_frozen(self):
        b = CoreBelief(topic="t", content="c")
        with pytest.raises(AttributeError):
            b.topic = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        b = CoreBelief(topic="t", content="c", added_timestamp="ts", source="s")
        assert b.to_dict() == {
            "topic": "t", "content": "c", "added_timestamp": "ts", "source": "s",
        }

    def test_from_dict_roundtrip(self):
        original = CoreBelief(topic="t", content="c", added_timestamp="ts", source="s")
        assert CoreBelief.from_dict(original.to_dict()) == original

    def test_create_factory(self):
        b = CoreBelief.create(topic="ethics", content="Do no harm", source="sage")
        assert b.topic == "ethics"
        assert b.content == "Do no harm"
        assert b.source == "sage"
        assert b.added_timestamp  # non-empty


# ═══════════════════════════════════════════════════════════════
#  AgentMemory — Init
# ═══════════════════════════════════════════════════════════════


class TestAgentMemoryInit:
    """Tests for AgentMemory construction and directory setup."""

    def test_creates_directory(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.directory.exists()
        assert mem.directory == tmp_path / "sage"

    def test_case_insensitive_name(self, tmp_path: Path):
        mem = AgentMemory("SAGE", memories_dir=tmp_path)
        assert mem.name == "sage"
        assert mem.directory == tmp_path / "sage"

    def test_whitespace_stripped(self, tmp_path: Path):
        mem = AgentMemory("  Sage  ", memories_dir=tmp_path)
        assert mem.name == "sage"

    def test_existing_directory_ok(self, tmp_path: Path):
        (tmp_path / "sage").mkdir()
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.directory.exists()

    def test_paths(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.beliefs_path == tmp_path / "sage" / "core_beliefs.json"
        assert mem.session_log_path == tmp_path / "sage" / "session_log.jsonl"


# ═══════════════════════════════════════════════════════════════
#  AgentMemory — Core Beliefs
# ═══════════════════════════════════════════════════════════════


class TestCoreBeliefs:
    """Tests for core belief read / write / remove."""

    def test_read_empty(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.read_core_beliefs() == []

    def test_write_one(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        belief = CoreBelief(topic="safety", content="Safety first")
        mem.write_core_belief(belief)
        beliefs = mem.read_core_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0].topic == "safety"
        assert beliefs[0].content == "Safety first"

    def test_write_multiple(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.write_core_belief(CoreBelief(topic="safety", content="Safety first"))
        mem.write_core_belief(CoreBelief(topic="honesty", content="Always be honest"))
        beliefs = mem.read_core_beliefs()
        assert len(beliefs) == 2
        topics = {b.topic for b in beliefs}
        assert topics == {"safety", "honesty"}

    def test_write_same_topic_replaces(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.write_core_belief(CoreBelief(topic="safety", content="Version 1"))
        mem.write_core_belief(CoreBelief(topic="safety", content="Version 2"))
        beliefs = mem.read_core_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0].content == "Version 2"

    def test_remove_existing(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.write_core_belief(CoreBelief(topic="safety", content="Safety first"))
        mem.write_core_belief(CoreBelief(topic="honesty", content="Be honest"))
        removed = mem.remove_core_belief("safety")
        assert removed is True
        beliefs = mem.read_core_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0].topic == "honesty"

    def test_remove_nonexistent(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.write_core_belief(CoreBelief(topic="safety", content="Safety first"))
        removed = mem.remove_core_belief("nosuch")
        assert removed is False
        assert len(mem.read_core_beliefs()) == 1

    def test_persistence_roundtrip(self, tmp_path: Path):
        mem1 = AgentMemory("sage", memories_dir=tmp_path)
        mem1.write_core_belief(CoreBelief(topic="t", content="c", added_timestamp="ts", source="s"))
        # New instance, same directory
        mem2 = AgentMemory("sage", memories_dir=tmp_path)
        beliefs = mem2.read_core_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0] == CoreBelief(topic="t", content="c", added_timestamp="ts", source="s")

    def test_corrupt_json_raises(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.beliefs_path.write_text("NOT VALID JSON", encoding="utf-8")
        with pytest.raises(MemoryCorruptionError, match="Corrupt memory file"):
            mem.read_core_beliefs()

    def test_wrong_type_raises(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.beliefs_path.write_text('"just a string"', encoding="utf-8")
        with pytest.raises(MemoryCorruptionError, match="Expected JSON array"):
            mem.read_core_beliefs()


# ═══════════════════════════════════════════════════════════════
#  AgentMemory — Session Log
# ═══════════════════════════════════════════════════════════════


class TestSessionLog:
    """Tests for session log read / append."""

    def _make_entry(self, session_id: str = "S-001", event_type: str = "chat", content: str = "hello") -> MemoryEntry:
        return MemoryEntry(
            timestamp="2026-01-01T00:00:00Z",
            session_id=session_id,
            event_type=event_type,
            content=content,
        )

    def test_read_empty(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.read_session_log() == []

    def test_append_one(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = self._make_entry()
        mem.append_session_event(entry)
        log = mem.read_session_log()
        assert len(log) == 1
        assert log[0].content == "hello"

    def test_append_multiple(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.append_session_event(self._make_entry(content="first"))
        mem.append_session_event(self._make_entry(content="second"))
        mem.append_session_event(self._make_entry(content="third"))
        log = mem.read_session_log()
        assert len(log) == 3
        assert [e.content for e in log] == ["first", "second", "third"]

    def test_filter_by_session_id(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.append_session_event(self._make_entry(session_id="S-001", content="a"))
        mem.append_session_event(self._make_entry(session_id="S-002", content="b"))
        mem.append_session_event(self._make_entry(session_id="S-001", content="c"))
        log = mem.read_session_log(session_id="S-001")
        assert len(log) == 2
        assert [e.content for e in log] == ["a", "c"]

    def test_jsonl_format(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.append_session_event(self._make_entry(content="line1"))
        mem.append_session_event(self._make_entry(content="line2"))
        raw = mem.session_log_path.read_text(encoding="utf-8")
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "content" in parsed

    def test_corrupt_line_raises(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.session_log_path.write_text("NOT JSON\n", encoding="utf-8")
        with pytest.raises(MemoryCorruptionError, match="Line 1"):
            mem.read_session_log()

    def test_persistence_across_instances(self, tmp_path: Path):
        mem1 = AgentMemory("sage", memories_dir=tmp_path)
        mem1.append_session_event(self._make_entry(content="from_mem1"))
        mem2 = AgentMemory("sage", memories_dir=tmp_path)
        log = mem2.read_session_log()
        assert len(log) == 1
        assert log[0].content == "from_mem1"


# ═══════════════════════════════════════════════════════════════
#  AgentMemory — Recent Memories
# ═══════════════════════════════════════════════════════════════


class TestRecentMemories:
    """Tests for get_recent_memories()."""

    def test_empty(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        assert mem.get_recent_memories() == []

    def test_limit(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(5):
            mem.append_session_event(
                MemoryEntry(
                    timestamp=f"2026-01-01T00:0{i}:00Z",
                    session_id="S-001",
                    event_type="chat",
                    content=f"msg-{i}",
                )
            )
        recent = mem.get_recent_memories(limit=3)
        assert len(recent) == 3

    def test_newest_first_ordering(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        for i in range(3):
            mem.append_session_event(
                MemoryEntry(
                    timestamp=f"2026-01-01T00:0{i}:00Z",
                    session_id="S-001",
                    event_type="chat",
                    content=f"msg-{i}",
                )
            )
        recent = mem.get_recent_memories(limit=3)
        # Most recent (last appended) comes first
        assert recent[0].content == "msg-2"
        assert recent[2].content == "msg-0"

    def test_across_sessions(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.append_session_event(
            MemoryEntry(timestamp="t1", session_id="S-001", event_type="e", content="a")
        )
        mem.append_session_event(
            MemoryEntry(timestamp="t2", session_id="S-002", event_type="e", content="b")
        )
        recent = mem.get_recent_memories(limit=10)
        assert len(recent) == 2
        assert recent[0].session_id == "S-002"


# ═══════════════════════════════════════════════════════════════
#  SharedMemory
# ═══════════════════════════════════════════════════════════════


class TestSharedMemory:
    """Tests for council-wide shared memory."""

    def test_creates_directory(self, tmp_path: Path):
        shared_dir = tmp_path / "shared"
        mem = SharedMemory(shared_dir=shared_dir)
        assert mem.directory.exists()

    def test_read_decisions_empty(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        assert mem.read_decisions() == []

    def test_record_and_read_decision(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        decision = {
            "timestamp": "2026-01-01T00:00:00Z",
            "proposal_id": "P-001",
            "result": "approved",
            "votes_for": 7,
            "votes_against": 2,
            "summary": "First decision",
        }
        mem.record_decision(decision)
        decisions = mem.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["proposal_id"] == "P-001"
        assert decisions[0]["votes_for"] == 7

    def test_record_multiple_decisions(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        for i in range(3):
            mem.record_decision({"id": f"P-{i}", "result": "approved"})
        decisions = mem.read_decisions()
        assert len(decisions) == 3

    def test_decisions_skips_comments(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        # Write a file with comment lines (like the existing stub)
        mem.decisions_path.write_text(
            '# Comment line\n{"id": "P-001"}\n# Another comment\n{"id": "P-002"}\n',
            encoding="utf-8",
        )
        decisions = mem.read_decisions()
        assert len(decisions) == 2

    def test_read_history_empty(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        assert mem.read_history() == ""

    def test_read_history_existing(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        mem.history_path.write_text("# History\n\nSome content\n", encoding="utf-8")
        assert "Some content" in mem.read_history()

    def test_append_history(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        mem.history_path.write_text("# History\n", encoding="utf-8")
        mem.append_history("## Session 1\n\nStuff happened.\n")
        text = mem.read_history()
        assert "# History" in text
        assert "## Session 1" in text
        assert "Stuff happened." in text

    def test_decisions_corrupt_raises(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        mem.decisions_path.write_text("NOT JSON\n", encoding="utf-8")
        with pytest.raises(MemoryCorruptionError, match="Line 1"):
            mem.read_decisions()

    def test_decisions_jsonl_format(self, tmp_path: Path):
        mem = SharedMemory(shared_dir=tmp_path / "shared")
        mem.record_decision({"id": "P-001"})
        mem.record_decision({"id": "P-002"})
        raw = mem.decisions_path.read_text(encoding="utf-8")
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "id" in parsed


# ═══════════════════════════════════════════════════════════════
#  Atomic Writes
# ═══════════════════════════════════════════════════════════════


class TestAtomicWrites:
    """Tests for the _atomic_write helper."""

    def test_creates_file(self, tmp_path: Path):
        target = tmp_path / "test.json"
        _atomic_write(target, '{"key": "value"}\n')
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == {"key": "value"}

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "test.json"
        target.write_text("old content", encoding="utf-8")
        _atomic_write(target, "new content")
        assert target.read_text(encoding="utf-8") == "new content"

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c.txt"
        _atomic_write(target, "deep file")
        assert target.read_text(encoding="utf-8") == "deep file"

    def test_no_leftover_tmp_files(self, tmp_path: Path):
        target = tmp_path / "test.txt"
        _atomic_write(target, "content")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


# ═══════════════════════════════════════════════════════════════
#  Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge-case tests for the memory system."""

    def test_unicode_content(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        belief = CoreBelief(topic="多样性", content="多样性是力量 🌍")
        mem.write_core_belief(belief)
        beliefs = mem.read_core_beliefs()
        assert beliefs[0].topic == "多样性"
        assert beliefs[0].content == "多样性是力量 🌍"

    def test_unicode_session_log(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry = MemoryEntry(
            timestamp="t", session_id="s", event_type="e",
            content="Ñoño said 日本語 テスト 🎉",
        )
        mem.append_session_event(entry)
        log = mem.read_session_log()
        assert log[0].content == "Ñoño said 日本語 テスト 🎉"

    def test_empty_beliefs_file(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        mem.beliefs_path.write_text("", encoding="utf-8")
        assert mem.read_core_beliefs() == []

    def test_blank_lines_in_session_log(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        entry_json = json.dumps(
            MemoryEntry(timestamp="t", session_id="s", event_type="e", content="c").to_dict()
        )
        mem.session_log_path.write_text(
            f"\n{entry_json}\n\n{entry_json}\n\n", encoding="utf-8"
        )
        log = mem.read_session_log()
        assert len(log) == 2

    def test_multiple_members_isolated(self, tmp_path: Path):
        sage = AgentMemory("sage", memories_dir=tmp_path)
        spark = AgentMemory("spark", memories_dir=tmp_path)
        sage.write_core_belief(CoreBelief(topic="ethics", content="Safety first"))
        spark.write_core_belief(CoreBelief(topic="creativity", content="Bold ideas"))
        assert len(sage.read_core_beliefs()) == 1
        assert len(spark.read_core_beliefs()) == 1
        assert sage.read_core_beliefs()[0].topic == "ethics"
        assert spark.read_core_beliefs()[0].topic == "creativity"

    def test_large_entry(self, tmp_path: Path):
        mem = AgentMemory("sage", memories_dir=tmp_path)
        big_content = "x" * 50_000
        mem.append_session_event(
            MemoryEntry(timestamp="t", session_id="s", event_type="e", content=big_content)
        )
        log = mem.read_session_log()
        assert len(log[0].content) == 50_000
