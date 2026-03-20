"""
Tests for Jericho — Council Session Orchestrator (F-007)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_member
from core.session import (
    ACTIVITY_TYPES,
    SESSION_PHASES,
    SessionError,
    SessionMessage,
    SessionNotFoundError,
    SessionOrchestrator,
    SessionRecord,
    SessionStateError,
    SessionValidationError,
    _build_briefing_prompt,
    _build_discussion_prompt,
    _build_summary_prompt,
    _VALID_TRANSITIONS,
)
from core.api_client import ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.registry import CouncilMember, CouncilRegistry


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def orchestrator(registry, api_client, tmp_dirs):
    shared = SharedMemory(shared_dir=tmp_dirs["shared"])
    return SessionOrchestrator(
        registry=registry,
        api_client=api_client,
        conversations_dir=tmp_dirs["conversations"],
        shared_memory=shared,
    )


# ─── SessionMessage Tests ─────────────────────────────────────


class TestSessionMessage:
    def test_fields(self):
        msg = SessionMessage(speaker="Sage", content="Hello")
        assert msg.speaker == "Sage"
        assert msg.content == "Hello"
        assert msg.timestamp == ""
        assert msg.phase == ""
        assert msg.activity_type == ""
        assert msg.metadata == {}

    def test_frozen(self):
        msg = SessionMessage(speaker="Sage", content="Hello")
        with pytest.raises(AttributeError):
            msg.speaker = "Logic"  # type: ignore

    def test_to_dict_roundtrip(self):
        msg = SessionMessage.create(
            "Sage", "Hello", phase="active", activity_type="discussion"
        )
        d = msg.to_dict()
        restored = SessionMessage.from_dict(d)
        assert restored.speaker == msg.speaker
        assert restored.content == msg.content
        assert restored.phase == msg.phase
        assert restored.activity_type == msg.activity_type

    def test_create_factory(self):
        msg = SessionMessage.create("orchestrator", "Briefing starts")
        assert msg.speaker == "orchestrator"
        assert msg.timestamp != ""

    def test_metadata_preserved(self):
        msg = SessionMessage.create(
            "Sage", "test", metadata={"model": "test-model"}
        )
        assert msg.metadata["model"] == "test-model"


# ─── SessionRecord Tests ──────────────────────────────────────


class TestSessionRecord:
    def test_fields(self):
        rec = SessionRecord(session_id="S-001", title="Test")
        assert rec.session_id == "S-001"
        assert rec.title == "Test"
        assert rec.phase == "created"
        assert rec.messages == []
        assert rec.participants == []

    def test_frozen(self):
        rec = SessionRecord(session_id="S-001", title="Test")
        with pytest.raises(AttributeError):
            rec.phase = "active"  # type: ignore

    def test_to_dict_roundtrip(self):
        msg = SessionMessage.create("Sage", "Hello", phase="active")
        rec = SessionRecord(
            session_id="S-001",
            title="Roundtrip Test",
            phase="active",
            activity_type="discussion",
            agenda="Discuss ethics",
            participants=["Sage", "Logic"],
            messages=[msg],
            metadata={"key": "value"},
        )
        d = rec.to_dict()
        restored = SessionRecord.from_dict(d)
        assert restored.session_id == rec.session_id
        assert restored.title == rec.title
        assert restored.phase == rec.phase
        assert len(restored.messages) == 1
        assert restored.messages[0].speaker == "Sage"
        assert restored.participants == ["Sage", "Logic"]
        assert restored.metadata == {"key": "value"}

    def test_create_factory(self):
        rec = SessionRecord.create(
            "S-001", "Ethics Session",
            activity_type="discussion",
            agenda="Ethics of AI",
            participants=["Sage"],
        )
        assert rec.session_id == "S-001"
        assert rec.phase == "created"
        assert rec.activity_type == "discussion"
        assert rec.created_at != ""

    def test_create_empty_id_raises(self):
        with pytest.raises(SessionValidationError) as exc_info:
            SessionRecord.create("", "Title")
        assert "Session ID" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(SessionValidationError) as exc_info:
            SessionRecord.create("S-001", "   ")
        assert "Title" in str(exc_info.value)

    def test_create_invalid_activity_type(self):
        with pytest.raises(SessionValidationError) as exc_info:
            SessionRecord.create("S-001", "Test", activity_type="invalid")
        assert "activity_type" in str(exc_info.value)

    def test_create_whitespace_strip(self):
        rec = SessionRecord.create("  S-001  ", "  Test  ")
        assert rec.session_id == "S-001"
        assert rec.title == "Test"


# ─── Constants Tests ──────────────────────────────────────────


class TestConstants:
    def test_session_phases(self):
        assert SESSION_PHASES == ("created", "briefing", "active", "summary", "closed")

    def test_activity_types(self):
        assert "discussion" in ACTIVITY_TYPES
        assert "voting" in ACTIVITY_TYPES
        assert "freeform" in ACTIVITY_TYPES
        assert "review" in ACTIVITY_TYPES

    def test_valid_transitions(self):
        assert _VALID_TRANSITIONS["created"] == ["briefing"]
        assert _VALID_TRANSITIONS["briefing"] == ["active"]
        assert _VALID_TRANSITIONS["active"] == ["summary"]
        assert _VALID_TRANSITIONS["summary"] == ["closed"]
        assert _VALID_TRANSITIONS["closed"] == []


# ─── SessionOrchestrator Init Tests ───────────────────────────


class TestOrchestratorInit:
    def test_creates_dir(self, orchestrator, tmp_dirs):
        assert tmp_dirs["conversations"].exists()

    def test_properties(self, orchestrator, tmp_dirs, registry):
        assert orchestrator.directory == tmp_dirs["conversations"]
        assert orchestrator.registry is registry

    def test_repr(self, orchestrator):
        r = repr(orchestrator)
        assert "SessionOrchestrator" in r
        assert "sessions=0" in r


# ─── Session Creation Tests ───────────────────────────────────


class TestCreateSession:
    def test_basic_creation(self, orchestrator):
        rec = orchestrator.create_session("S-001", "Test Session")
        assert rec.session_id == "S-001"
        assert rec.title == "Test Session"
        assert rec.phase == "created"
        assert rec.activity_type == "freeform"

    def test_with_options(self, orchestrator):
        rec = orchestrator.create_session(
            "S-002", "Ethics Review",
            activity_type="discussion",
            agenda="Review ethical guidelines",
            participants=["Sage", "Logic"],
            metadata={"priority": "high"},
        )
        assert rec.activity_type == "discussion"
        assert rec.agenda == "Review ethical guidelines"
        assert rec.participants == ["Sage", "Logic"]
        assert rec.metadata["priority"] == "high"

    def test_persistence(self, orchestrator, tmp_dirs):
        orchestrator.create_session("S-001", "Persist Test")
        filepath = tmp_dirs["conversations"] / "S-S-001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["session_id"] == "S-001"

    def test_duplicate_raises(self, orchestrator):
        orchestrator.create_session("S-001", "First")
        with pytest.raises(SessionStateError) as exc_info:
            orchestrator.create_session("S-001", "Second")
        assert "already exists" in str(exc_info.value)

    def test_unknown_participant_raises(self, orchestrator):
        with pytest.raises(SessionValidationError) as exc_info:
            orchestrator.create_session(
                "S-001", "Test",
                participants=["UnknownMember"],
            )
        assert "Unknown council member" in str(exc_info.value)

    def test_sequential_ids(self, orchestrator):
        orchestrator.create_session("S-001", "First")
        orchestrator.create_session("S-002", "Second")
        assert orchestrator.has_session("S-001")
        assert orchestrator.has_session("S-002")


# ─── Phase Transition Tests ──────────────────────────────────


class TestPhaseTransitions:
    def test_created_to_briefing(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        rec = asyncio.get_event_loop().run_until_complete(
            orchestrator.start_session("S-001")
        )
        assert rec.phase == "briefing"
        assert rec.started_at != ""

    def test_briefing_to_active(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        asyncio.get_event_loop().run_until_complete(
            orchestrator.start_session("S-001")
        )
        rec = asyncio.get_event_loop().run_until_complete(
            orchestrator.activate_session("S-001")
        )
        assert rec.phase == "active"

    def test_active_to_summary(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        rec = loop.run_until_complete(orchestrator.begin_summary("S-001"))
        assert rec.phase == "summary"

    def test_summary_to_closed(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        loop.run_until_complete(orchestrator.begin_summary("S-001"))
        rec = loop.run_until_complete(orchestrator.close_session("S-001"))
        assert rec.phase == "closed"
        assert rec.closed_at != ""

    def test_skip_phase_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        with pytest.raises(SessionStateError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                orchestrator.activate_session("S-001")
            )
        assert "Cannot transition" in str(exc_info.value)

    def test_closed_transition_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        loop.run_until_complete(orchestrator.begin_summary("S-001"))
        loop.run_until_complete(orchestrator.close_session("S-001"))
        with pytest.raises(SessionStateError):
            loop.run_until_complete(orchestrator.start_session("S-001"))

    def test_not_found_raises(self, orchestrator):
        with pytest.raises(SessionNotFoundError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                orchestrator.start_session("MISSING")
            )
        assert "MISSING" in str(exc_info.value)

    def test_backward_transition_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        with pytest.raises(SessionStateError):
            loop.run_until_complete(orchestrator.start_session("S-001"))


# ─── Brief Member Tests ──────────────────────────────────────


class TestBriefMember:
    def test_brief_records_messages(self, orchestrator, tmp_dirs):
        orchestrator.create_session(
            "S-001", "Briefing Test", participants=["Sage"]
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        rec = loop.run_until_complete(
            orchestrator.brief_member("S-001", "Sage")
        )
        # Should have 2 messages: orchestrator prompt + member response
        assert len(rec.messages) == 2
        assert rec.messages[0].speaker == "orchestrator"
        assert rec.messages[1].speaker == "Sage"
        assert rec.messages[1].content == "Acknowledged."

    def test_brief_calls_api(self, orchestrator, api_client):
        orchestrator.create_session(
            "S-001", "API Test", participants=["Sage"]
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.brief_member("S-001", "Sage"))
        api_client.chat.assert_called_once()

    def test_brief_wrong_phase_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        with pytest.raises(SessionStateError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                orchestrator.brief_member("S-001", "Sage")
            )
        assert "briefing" in str(exc_info.value)

    def test_brief_records_memory(self, orchestrator, tmp_dirs):
        orchestrator.create_session(
            "S-001", "Memory Test", participants=["Sage"]
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))

        with patch("core.session.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            mock_mem_instance.get_recent_memories.return_value = []
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                orchestrator.brief_member("S-001", "Sage")
            )
            mock_mem_instance.append_session_event.assert_called_once()


# ─── Discussion Tests ─────────────────────────────────────────


class TestDiscussion:
    def test_discuss_records_messages(self, orchestrator):
        orchestrator.create_session(
            "S-001", "Discussion Test",
            activity_type="discussion",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))

        rec = loop.run_until_complete(
            orchestrator.discuss("S-001", "Ethics of AI", ["Sage", "Logic"])
        )
        # 1 topic announcement + 2 member messages
        assert len(rec.messages) == 3
        assert rec.messages[0].speaker == "orchestrator"
        assert "Ethics of AI" in rec.messages[0].content
        assert rec.messages[1].speaker == "Sage"
        assert rec.messages[2].speaker == "Logic"

    def test_discuss_calls_api_per_member(self, orchestrator, api_client):
        orchestrator.create_session(
            "S-001", "API Test",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))

        loop.run_until_complete(
            orchestrator.discuss("S-001", "Topic", ["Sage", "Logic"])
        )
        assert api_client.chat.call_count == 2

    def test_discuss_wrong_phase_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        with pytest.raises(SessionStateError):
            loop.run_until_complete(
                orchestrator.discuss("S-001", "Topic", ["Sage"])
            )

    def test_discuss_multiple_rounds(self, orchestrator):
        orchestrator.create_session(
            "S-001", "Multi-Round",
            participants=["Sage"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))

        loop.run_until_complete(
            orchestrator.discuss("S-001", "Round 1", ["Sage"])
        )
        rec = loop.run_until_complete(
            orchestrator.discuss("S-001", "Round 2", ["Sage"])
        )
        # 2 topic announcements + 2 member messages
        assert len(rec.messages) == 4


# ─── Send to Member Tests ────────────────────────────────────


class TestSendToMember:
    def test_send_records_exchange(self, orchestrator):
        orchestrator.create_session(
            "S-001", "Send Test", participants=["Sage"]
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))

        rec, response = loop.run_until_complete(
            orchestrator.send_to_member("S-001", "Sage", "What do you think?")
        )
        assert len(rec.messages) == 2
        assert rec.messages[0].speaker == "orchestrator"
        assert rec.messages[1].speaker == "Sage"
        assert response.content == "Acknowledged."

    def test_send_wrong_phase_raises(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        with pytest.raises(SessionStateError):
            asyncio.get_event_loop().run_until_complete(
                orchestrator.send_to_member("S-001", "Sage", "Hi")
            )


# ─── Human Message Tests ─────────────────────────────────────


class TestHumanMessage:
    def test_add_human_message_briefing(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        rec = orchestrator.add_human_message("S-001", "I have a question")
        assert len(rec.messages) == 1
        assert rec.messages[0].speaker == "human"
        assert rec.messages[0].content == "I have a question"

    def test_add_human_message_active(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        rec = orchestrator.add_human_message("S-001", "Comment")
        assert rec.messages[0].speaker == "human"

    def test_add_human_message_wrong_phase(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        with pytest.raises(SessionStateError) as exc_info:
            orchestrator.add_human_message("S-001", "Hi")
        assert "created" in str(exc_info.value)


# ─── Summary & Close Tests ───────────────────────────────────


class TestSummaryAndClose:
    def _prepare_summary_phase(self, orchestrator):
        orchestrator.create_session("S-001", "Summary Test", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        loop.run_until_complete(orchestrator.begin_summary("S-001"))
        return loop

    def test_collect_summary(self, orchestrator):
        loop = self._prepare_summary_phase(orchestrator)
        rec = loop.run_until_complete(
            orchestrator.collect_summary("S-001", "Sage")
        )
        summary_msgs = [m for m in rec.messages if m.phase == "summary"]
        assert len(summary_msgs) == 1
        assert summary_msgs[0].speaker == "Sage"

    def test_collect_summary_wrong_phase(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        with pytest.raises(SessionStateError):
            loop.run_until_complete(
                orchestrator.collect_summary("S-001", "Sage")
            )

    def test_close_with_summary(self, orchestrator):
        loop = self._prepare_summary_phase(orchestrator)
        rec = loop.run_until_complete(
            orchestrator.close_session("S-001", summary="Session complete.")
        )
        assert rec.phase == "closed"
        assert rec.summary == "Session complete."
        assert rec.closed_at != ""

    def test_close_auto_summary(self, orchestrator):
        loop = self._prepare_summary_phase(orchestrator)
        rec = loop.run_until_complete(orchestrator.close_session("S-001"))
        assert rec.summary != ""

    def test_close_records_shared_memory(self, orchestrator, tmp_dirs):
        loop = self._prepare_summary_phase(orchestrator)
        loop.run_until_complete(
            orchestrator.close_session("S-001", summary="Done.")
        )
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["type"] == "session_closed"
        assert decisions[0]["session_id"] == "S-001"

    def test_close_records_history(self, orchestrator, tmp_dirs):
        loop = self._prepare_summary_phase(orchestrator)
        loop.run_until_complete(
            orchestrator.close_session("S-001", summary="Session done.")
        )
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        history = shared.read_history()
        assert "Summary Test" in history
        assert "Session done." in history


# ─── Query Tests ──────────────────────────────────────────────


class TestQueryMethods:
    def test_get_existing(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        rec = orchestrator.get("S-001")
        assert rec.session_id == "S-001"

    def test_get_not_found(self, orchestrator):
        with pytest.raises(SessionNotFoundError):
            orchestrator.get("MISSING")

    def test_list_sessions(self, orchestrator):
        orchestrator.create_session("S-001", "First")
        orchestrator.create_session("S-002", "Second")
        sessions = orchestrator.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_filter_phase(self, orchestrator):
        orchestrator.create_session("S-001", "First")
        orchestrator.create_session("S-002", "Second")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-002"))
        created = orchestrator.list_sessions(phase="created")
        briefing = orchestrator.list_sessions(phase="briefing")
        assert len(created) == 1
        assert len(briefing) == 1

    def test_list_sessions_filter_activity(self, orchestrator):
        orchestrator.create_session("S-001", "First", activity_type="discussion")
        orchestrator.create_session("S-002", "Second", activity_type="voting")
        discussion = orchestrator.list_sessions(activity_type="discussion")
        assert len(discussion) == 1
        assert discussion[0].activity_type == "discussion"

    def test_has_session(self, orchestrator):
        assert not orchestrator.has_session("S-001")
        orchestrator.create_session("S-001", "Test")
        assert orchestrator.has_session("S-001")

    def test_get_transcript(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        orchestrator.add_human_message("S-001", "Hello")
        transcript = orchestrator.get_transcript("S-001")
        assert len(transcript) == 1

    def test_get_transcript_filter_speaker(self, orchestrator):
        orchestrator.create_session("S-001", "Test")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        loop.run_until_complete(
            orchestrator.send_to_member("S-001", "Sage", "Hi")
        )
        orch_msgs = orchestrator.get_transcript("S-001", speaker="orchestrator")
        sage_msgs = orchestrator.get_transcript("S-001", speaker="Sage")
        assert len(orch_msgs) == 1
        assert len(sage_msgs) == 1

    def test_corrupt_file_skipped(self, orchestrator, tmp_dirs):
        # Write a corrupt file
        corrupt = tmp_dirs["conversations"] / "S-CORRUPT.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("not json!", encoding="utf-8")
        orchestrator.create_session("S-001", "Good Session")
        sessions = orchestrator.list_sessions()
        assert len(sessions) == 1


# ─── Prompt Builder Tests ────────────────────────────────────


class TestPromptBuilders:
    def test_briefing_prompt_contains_title(self):
        rec = SessionRecord.create("S-001", "Ethics Review", activity_type="discussion")
        member = make_member("Sage")
        prompt = _build_briefing_prompt(rec, member, [])
        assert "Ethics Review" in prompt
        assert "Sage" in prompt
        assert "Ethics" in prompt

    def test_briefing_prompt_with_agenda(self):
        rec = SessionRecord.create(
            "S-001", "Test", agenda="Discuss AI autonomy"
        )
        member = make_member("Sage")
        prompt = _build_briefing_prompt(rec, member, [])
        assert "Discuss AI autonomy" in prompt

    def test_briefing_prompt_with_memories(self):
        rec = SessionRecord.create("S-001", "Test")
        member = make_member("Sage")
        memories = [
            MemoryEntry.create("S-000", "chat", "Previous discussion"),
        ]
        prompt = _build_briefing_prompt(rec, member, memories)
        assert "Previous discussion" in prompt

    def test_discussion_prompt_contains_topic(self):
        member = make_member("Sage")
        prompt = _build_discussion_prompt("Ethics of AI", member, [])
        assert "Ethics of AI" in prompt
        assert "Sage" in prompt

    def test_discussion_prompt_with_prior_messages(self):
        member = make_member("Logic")
        prior = [
            SessionMessage.create("Sage", "I think ethics matter."),
        ]
        prompt = _build_discussion_prompt("Ethics", member, prior)
        assert "Sage" in prompt
        assert "ethics matter" in prompt

    def test_summary_prompt_contains_session(self):
        rec = SessionRecord(
            session_id="S-001",
            title="Test Session",
            messages=[SessionMessage.create("Sage", "Hello")],
        )
        member = make_member("Sage")
        prompt = _build_summary_prompt(rec, member)
        assert "Test Session" in prompt
        assert "Sage" in prompt


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    def test_session_error_hierarchy(self):
        assert issubclass(SessionNotFoundError, SessionError)
        assert issubclass(SessionStateError, SessionError)
        assert issubclass(SessionValidationError, SessionError)

    def test_not_found_fields(self):
        err = SessionNotFoundError("S-999")
        assert err.session_id == "S-999"
        assert "S-999" in str(err)

    def test_state_error_fields(self):
        err = SessionStateError("S-001", "bad transition")
        assert err.session_id == "S-001"
        assert "bad transition" in str(err)

    def test_validation_error_fields(self):
        err = SessionValidationError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)


# ─── Edge Case Tests ─────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, orchestrator):
        orchestrator.create_session("S-001", "Ünïcödé Sëssïön")
        rec = orchestrator.get("S-001")
        assert rec.title == "Ünïcödé Sëssïön"

    def test_long_agenda(self, orchestrator):
        long_agenda = "A" * 10000
        orchestrator.create_session(
            "S-001", "Long Agenda", agenda=long_agenda
        )
        rec = orchestrator.get("S-001")
        assert len(rec.agenda) == 10000

    def test_empty_participants(self, orchestrator):
        rec = orchestrator.create_session("S-001", "No Participants")
        assert rec.participants == []

    def test_full_lifecycle(self, orchestrator, api_client):
        """End-to-end: create → brief → discuss → summary → close."""
        orchestrator.create_session(
            "S-001", "Full Lifecycle",
            activity_type="discussion",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()

        # Phase 1: Briefing
        loop.run_until_complete(orchestrator.start_session("S-001"))
        loop.run_until_complete(orchestrator.brief_member("S-001", "Sage"))
        loop.run_until_complete(orchestrator.brief_member("S-001", "Logic"))

        # Phase 2: Active
        loop.run_until_complete(orchestrator.activate_session("S-001"))
        orchestrator.add_human_message("S-001", "Let's discuss ethics.")
        loop.run_until_complete(
            orchestrator.discuss("S-001", "AI Ethics", ["Sage", "Logic"])
        )

        # Phase 3: Summary
        loop.run_until_complete(orchestrator.begin_summary("S-001"))
        loop.run_until_complete(orchestrator.collect_summary("S-001", "Sage"))

        # Phase 4: Close
        rec = loop.run_until_complete(
            orchestrator.close_session("S-001", summary="Ethics discussed.")
        )

        assert rec.phase == "closed"
        assert rec.summary == "Ethics discussed."
        # Briefing (2*2=4) + human (1) + topic (1) + discussion (2) + summary (1) = 9
        assert len(rec.messages) == 9
        assert api_client.chat.call_count == 5  # 2 brief + 2 discuss + 1 summary

    def test_persistence_roundtrip(self, orchestrator):
        orchestrator.create_session(
            "S-001", "Persistence",
            activity_type="discussion",
            participants=["Sage"],
            metadata={"key": "value"},
        )
        # Re-load from disk
        rec = orchestrator.get("S-001")
        assert rec.session_id == "S-001"
        assert rec.title == "Persistence"
        assert rec.metadata == {"key": "value"}
