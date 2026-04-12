"""
Jericho — Council Session Tests (F-045)

Comprehensive unit tests for core/council_session.py covering:
- CouncilSessionRecord dataclass (fields, frozen, roundtrip, factory)
- CouncilSessionManager lifecycle (create, close, list, get)
- Proposal handoff via build_proposal_data
- Exception hierarchy and edge cases
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.council_session import (
    CouncilSessionError,
    CouncilSessionManager,
    CouncilSessionNotFoundError,
    CouncilSessionRecord,
    CouncilSessionStateError,
    CouncilSessionValidationError,
)
from core.discussion import DiscussionContribution


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    """Create a temporary sessions directory."""
    d = tmp_path / "council_sessions"
    d.mkdir()
    return d


@pytest.fixture
def mgr(sessions_dir: Path) -> CouncilSessionManager:
    """CouncilSessionManager backed by tmp directory."""
    return CouncilSessionManager(sessions_dir=sessions_dir)


# ─── CouncilSessionRecord ─────────────────────────────────────


class TestCouncilSessionRecord:
    """Test the frozen dataclass."""

    def test_fields(self):
        rec = CouncilSessionRecord(
            session_id="CS-0001",
            title="Test Session",
            topic="Test topic",
        )
        assert rec.session_id == "CS-0001"
        assert rec.title == "Test Session"
        assert rec.topic == "Test topic"
        assert rec.status == "open"
        assert rec.round_count == 5
        assert rec.current_round == 0
        assert rec.contributions == []
        assert rec.participants == []
        assert rec.agenda == ""
        assert rec.summary == ""
        assert rec.created_at == ""
        assert rec.closed_at == ""
        assert rec.proposed_category == "governance"
        assert rec.proposed_title == ""
        assert rec.proposed_description == ""
        assert rec.metadata == {}

    def test_frozen(self):
        rec = CouncilSessionRecord(
            session_id="CS-0001",
            title="Test",
            topic="Topic",
        )
        with pytest.raises(AttributeError):
            rec.title = "Modified"  # type: ignore[misc]

    def test_to_dict_roundtrip(self):
        contrib = DiscussionContribution(
            speaker="Sage",
            content="I think this is important.",
            round_number=1,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        rec = CouncilSessionRecord(
            session_id="CS-0002",
            title="Roundtrip Test",
            topic="Testing roundtrip",
            agenda="Review topics",
            participants=["Sage", "Logic"],
            contributions=[contrib],
            round_count=3,
            current_round=1,
            status="open",
            summary="",
            created_at="2026-01-01T00:00:00+00:00",
            closed_at="",
            proposed_category="world",
            proposed_title="Custom Title",
            proposed_description="Custom Desc",
            metadata={"key": "value"},
        )
        d = rec.to_dict()
        restored = CouncilSessionRecord.from_dict(d)
        assert restored.session_id == rec.session_id
        assert restored.title == rec.title
        assert restored.topic == rec.topic
        assert restored.agenda == rec.agenda
        assert restored.participants == rec.participants
        assert len(restored.contributions) == 1
        assert restored.contributions[0].speaker == "Sage"
        assert restored.round_count == 3
        assert restored.current_round == 1
        assert restored.proposed_category == "world"
        assert restored.proposed_title == "Custom Title"
        assert restored.proposed_description == "Custom Desc"
        assert restored.metadata == {"key": "value"}

    def test_from_dict_missing_optionals(self):
        """from_dict should fill missing optional fields with defaults."""
        data = {
            "session_id": "CS-0003",
            "title": "Minimal",
            "topic": "Minimal topic",
        }
        rec = CouncilSessionRecord.from_dict(data)
        assert rec.agenda == ""
        assert rec.participants == []
        assert rec.contributions == []
        assert rec.round_count == 5
        assert rec.current_round == 0
        assert rec.status == "open"
        assert rec.proposed_category == "governance"

    def test_create_factory(self):
        rec = CouncilSessionRecord.create(
            session_id="CS-0010",
            title="Factory Session",
            topic="Factory topic",
            agenda="Do things",
            participants=["Sage"],
            round_count=3,
            proposed_category="world",
            metadata={"source": "test"},
        )
        assert rec.session_id == "CS-0010"
        assert rec.title == "Factory Session"
        assert rec.topic == "Factory topic"
        assert rec.agenda == "Do things"
        assert rec.participants == ["Sage"]
        assert rec.round_count == 3
        assert rec.current_round == 0
        assert rec.status == "open"
        assert rec.created_at  # auto-filled
        assert rec.closed_at == ""
        assert rec.proposed_category == "world"
        # Factory auto-populates proposed_title/description from title/topic
        assert rec.proposed_title == "Factory Session"
        assert rec.proposed_description == "Factory topic"
        assert rec.metadata == {"source": "test"}

    def test_create_empty_session_id_raises(self):
        with pytest.raises(CouncilSessionValidationError) as exc_info:
            CouncilSessionRecord.create(
                session_id="   ",
                title="Title",
                topic="Topic",
            )
        assert "Session ID" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(CouncilSessionValidationError) as exc_info:
            CouncilSessionRecord.create(
                session_id="CS-0001",
                title="   ",
                topic="Topic",
            )
        assert "Title" in str(exc_info.value)

    def test_create_empty_topic_raises(self):
        with pytest.raises(CouncilSessionValidationError) as exc_info:
            CouncilSessionRecord.create(
                session_id="CS-0001",
                title="Title",
                topic="  ",
            )
        assert "Topic" in str(exc_info.value)

    def test_create_whitespace_stripping(self):
        rec = CouncilSessionRecord.create(
            session_id="  CS-0099  ",
            title="  Spaces  ",
            topic="  Topic  ",
            agenda="  Agenda  ",
        )
        assert rec.session_id == "CS-0099"
        assert rec.title == "Spaces"
        assert rec.topic == "Topic"
        assert rec.agenda == "Agenda"

    def test_create_default_participants(self):
        rec = CouncilSessionRecord.create(
            session_id="CS-0001",
            title="Title",
            topic="Topic",
        )
        assert rec.participants == []

    def test_create_default_metadata(self):
        rec = CouncilSessionRecord.create(
            session_id="CS-0001",
            title="Title",
            topic="Topic",
        )
        assert rec.metadata == {}


# ─── CouncilSessionManager Init ───────────────────────────────


class TestCouncilSessionManagerInit:
    def test_creates_dir(self, tmp_path: Path):
        d = tmp_path / "new_sessions"
        assert not d.exists()
        mgr = CouncilSessionManager(sessions_dir=d)
        assert d.exists()
        assert mgr.directory == d

    def test_existing_dir(self, sessions_dir: Path):
        mgr = CouncilSessionManager(sessions_dir=sessions_dir)
        assert mgr.directory == sessions_dir

    def test_repr(self, mgr: CouncilSessionManager):
        r = repr(mgr)
        assert "CouncilSessionManager" in r
        assert "sessions=0" in r


# ─── Create Session ───────────────────────────────────────────


class TestCreateSession:
    def test_basic_creation(self, mgr: CouncilSessionManager):
        session = mgr.create_session("Ethics Discussion", "Discuss AI ethics")
        assert session.session_id == "CS-0001"
        assert session.title == "Ethics Discussion"
        assert session.topic == "Discuss AI ethics"
        assert session.status == "open"
        assert session.created_at

    def test_with_options(self, mgr: CouncilSessionManager):
        session = mgr.create_session(
            "Advanced Topic",
            "Deep discussion",
            agenda="1. Intro 2. Debate",
            participants=["Sage", "Logic"],
            round_count=10,
            proposed_category="world",
            metadata={"custom": True},
        )
        assert session.agenda == "1. Intro 2. Debate"
        assert session.participants == ["Sage", "Logic"]
        assert session.round_count == 10
        assert session.proposed_category == "world"
        assert session.metadata == {"custom": True}

    def test_persistence(self, mgr: CouncilSessionManager, sessions_dir: Path):
        mgr.create_session("Persistent", "Test persistence")
        filepath = sessions_dir / "CS-0001.json"
        assert filepath.exists()

        # Verify JSON is well-formed
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["session_id"] == "CS-0001"
        assert data["title"] == "Persistent"

    def test_sequential_ids(self, mgr: CouncilSessionManager):
        s1 = mgr.create_session("First", "Topic A")
        s2 = mgr.create_session("Second", "Topic B")
        s3 = mgr.create_session("Third", "Topic C")
        assert s1.session_id == "CS-0001"
        assert s2.session_id == "CS-0002"
        assert s3.session_id == "CS-0003"

    def test_empty_title_raises(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionValidationError):
            mgr.create_session("  ", "Topic")

    def test_empty_topic_raises(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionValidationError):
            mgr.create_session("Title", "  ")

    def test_both_empty_raises(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionValidationError) as exc_info:
            mgr.create_session("  ", "  ")
        assert len(exc_info.value.errors) == 2

    def test_id_gap_sequencing(self, mgr: CouncilSessionManager, sessions_dir: Path):
        """IDs should sequence from the highest existing file number."""
        mgr.create_session("First", "Topic")
        # Manually inject a gap by writing CS-0010
        s10 = CouncilSessionRecord.create(
            session_id="CS-0010",
            title="Jump",
            topic="Jumped topic",
        )
        filepath = sessions_dir / "CS-0010.json"
        filepath.write_text(
            json.dumps(s10.to_dict(), indent=2), encoding="utf-8"
        )
        # Next ID should be CS-0011
        s_next = mgr.create_session("After Gap", "Topic after gap")
        assert s_next.session_id == "CS-0011"


# ─── Read / Get ────────────────────────────────────────────────


class TestGetSession:
    def test_get_existing(self, mgr: CouncilSessionManager):
        created = mgr.create_session("Findable", "Topic")
        found = mgr.get(created.session_id)
        assert found.session_id == created.session_id
        assert found.title == created.title

    def test_get_not_found(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionNotFoundError) as exc_info:
            mgr.get("CS-9999")
        assert exc_info.value.session_id == "CS-9999"

    def test_get_preserves_contributions(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        """Verify contributions survive save/load cycle."""
        session = mgr.create_session("With Contrib", "Topic")
        # Manually add a contribution by updating the file
        data = json.loads(
            (sessions_dir / f"{session.session_id}.json").read_text(
                encoding="utf-8"
            )
        )
        data["contributions"].append({
            "speaker": "Sage",
            "content": "I agree.",
            "round_number": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })
        (sessions_dir / f"{session.session_id}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        reloaded = mgr.get(session.session_id)
        assert len(reloaded.contributions) == 1
        assert reloaded.contributions[0].speaker == "Sage"


# ─── List Sessions ────────────────────────────────────────────


class TestListSessions:
    def test_list_all(self, mgr: CouncilSessionManager):
        mgr.create_session("A", "Topic A")
        mgr.create_session("B", "Topic B")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_empty(self, mgr: CouncilSessionManager):
        assert mgr.list_sessions() == []

    def test_list_filter_status(self, mgr: CouncilSessionManager):
        mgr.create_session("Open1", "Topic")
        mgr.create_session("Open2", "Topic")
        mgr.close_session("CS-0001", summary="Done")

        open_sessions = mgr.list_sessions(status="open")
        assert len(open_sessions) == 1
        assert open_sessions[0].session_id == "CS-0002"

        closed_sessions = mgr.list_sessions(status="closed")
        assert len(closed_sessions) == 1
        assert closed_sessions[0].session_id == "CS-0001"

    def test_list_sorted_by_filename(self, mgr: CouncilSessionManager):
        mgr.create_session("First", "T")
        mgr.create_session("Second", "T")
        mgr.create_session("Third", "T")
        sessions = mgr.list_sessions()
        ids = [s.session_id for s in sessions]
        assert ids == ["CS-0001", "CS-0002", "CS-0003"]

    def test_corrupt_file_skipped(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        mgr.create_session("Good", "Topic")
        # Write a corrupt JSON file
        (sessions_dir / "CS-0099.json").write_text(
            "{not json!", encoding="utf-8"
        )
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].title == "Good"


# ─── Close Session ────────────────────────────────────────────


class TestCloseSession:
    def test_close_with_summary(self, mgr: CouncilSessionManager):
        mgr.create_session("Closeable", "Topic")
        closed = mgr.close_session("CS-0001", summary="Concluded.")
        assert closed.status == "closed"
        assert closed.summary == "Concluded."
        assert closed.closed_at

    def test_close_auto_summary(self, mgr: CouncilSessionManager):
        mgr.create_session(
            "AutoSum",
            "Topic for auto-summary",
            participants=["Sage", "Logic"],
        )
        closed = mgr.close_session("CS-0001")
        assert closed.status == "closed"
        assert "AutoSum" in closed.summary
        assert "Topic for auto-summary" in closed.summary

    def test_close_already_closed_raises(self, mgr: CouncilSessionManager):
        mgr.create_session("Once", "Topic")
        mgr.close_session("CS-0001")
        with pytest.raises(CouncilSessionStateError):
            mgr.close_session("CS-0001")

    def test_close_not_found_raises(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionNotFoundError):
            mgr.close_session("CS-9999")

    def test_close_preserves_all_fields(self, mgr: CouncilSessionManager):
        session = mgr.create_session(
            "Full Session",
            "Detailed topic",
            agenda="Full agenda",
            participants=["Sage", "Logic"],
            proposed_category="world",
            metadata={"test": True},
        )
        closed = mgr.close_session(session.session_id, summary="Done.")

        assert closed.title == "Full Session"
        assert closed.topic == "Detailed topic"
        assert closed.agenda == "Full agenda"
        assert closed.participants == ["Sage", "Logic"]
        assert closed.proposed_category == "world"
        assert closed.metadata == {"test": True}
        assert closed.created_at == session.created_at

    def test_close_persists(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        mgr.create_session("Persist Close", "Topic")
        mgr.close_session("CS-0001", summary="Persisted.")

        data = json.loads(
            (sessions_dir / "CS-0001.json").read_text(encoding="utf-8")
        )
        assert data["status"] == "closed"
        assert data["summary"] == "Persisted."
        assert data["closed_at"]


# ─── Save (public) ────────────────────────────────────────────


class TestSavePublic:
    def test_save_updates_record(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        session = mgr.create_session("Saveable", "Topic")
        contrib = DiscussionContribution.create(
            speaker="Sage",
            content="Important point.",
            round_number=1,
        )
        # Rebuild with contribution
        updated = CouncilSessionRecord(
            session_id=session.session_id,
            title=session.title,
            topic=session.topic,
            agenda=session.agenda,
            participants=session.participants,
            contributions=[contrib],
            round_count=session.round_count,
            current_round=1,
            status=session.status,
            summary=session.summary,
            created_at=session.created_at,
            closed_at=session.closed_at,
            proposed_category=session.proposed_category,
            proposed_title=session.proposed_title,
            proposed_description=session.proposed_description,
            metadata=dict(session.metadata),
        )
        mgr.save(updated)

        reloaded = mgr.get(session.session_id)
        assert len(reloaded.contributions) == 1
        assert reloaded.current_round == 1


# ─── Proposal Handoff ─────────────────────────────────────────


class TestBuildProposalData:
    def test_basic_handoff(self, mgr: CouncilSessionManager):
        mgr.create_session("Ethics Review", "Should we allow X?")
        mgr.close_session("CS-0001", summary="We decided yes.")
        data = mgr.build_proposal_data("CS-0001")

        assert data["title"] == "Ethics Review"
        assert data["description"] == "Should we allow X?"
        assert data["category"] == "governance"
        assert "Council Session" in data["body"]
        assert data["metadata"]["source_session"] == "CS-0001"

    def test_handoff_custom_overrides(self, mgr: CouncilSessionManager):
        mgr.create_session(
            "Override Test",
            "Default desc",
            proposed_category="world",
        )
        mgr.close_session("CS-0001")
        data = mgr.build_proposal_data(
            "CS-0001",
            title="Custom Title",
            description="Custom Desc",
            category="culture",
        )
        assert data["title"] == "Custom Title"
        assert data["description"] == "Custom Desc"
        assert data["category"] == "culture"

    def test_handoff_not_closed_raises(self, mgr: CouncilSessionManager):
        mgr.create_session("Open Session", "Topic")
        with pytest.raises(CouncilSessionStateError) as exc_info:
            mgr.build_proposal_data("CS-0001")
        assert "closed" in str(exc_info.value).lower()

    def test_handoff_not_found_raises(self, mgr: CouncilSessionManager):
        with pytest.raises(CouncilSessionNotFoundError):
            mgr.build_proposal_data("CS-9999")

    def test_handoff_includes_summary(self, mgr: CouncilSessionManager):
        mgr.create_session("Summary Handoff", "Topic")
        mgr.close_session("CS-0001", summary="Key decision: yes to X.")
        data = mgr.build_proposal_data("CS-0001")
        assert "Key decision" in data["body"]

    def test_handoff_includes_contributions(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        session = mgr.create_session(
            "Contrib Handoff",
            "Topic",
            participants=["Sage"],
        )
        # Add contributions manually
        rec_data = json.loads(
            (sessions_dir / f"{session.session_id}.json").read_text(
                encoding="utf-8"
            )
        )
        rec_data["contributions"] = [
            {
                "speaker": "Sage",
                "content": "I strongly support this.",
                "round_number": 1,
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
        ]
        (sessions_dir / f"{session.session_id}.json").write_text(
            json.dumps(rec_data, indent=2), encoding="utf-8"
        )
        # Close it
        mgr.close_session(session.session_id, summary="Supported.")
        data = mgr.build_proposal_data(session.session_id)
        assert "Sage" in data["body"]
        assert "strongly support" in data["body"]

    def test_handoff_body_includes_agenda(self, mgr: CouncilSessionManager):
        mgr.create_session(
            "Agenda Handoff",
            "Topic with agenda",
            agenda="Step 1: review, Step 2: decide",
        )
        mgr.close_session("CS-0001")
        data = mgr.build_proposal_data("CS-0001")
        assert "Step 1" in data["body"]


# ─── Auto-Generated Summary ──────────────────────────────────


class TestAutoSummary:
    def test_summary_contains_title(self, mgr: CouncilSessionManager):
        mgr.create_session("Important Meeting", "The topic")
        closed = mgr.close_session("CS-0001")
        assert "Important Meeting" in closed.summary

    def test_summary_contains_topic(self, mgr: CouncilSessionManager):
        mgr.create_session("Meeting", "Discussion about governance")
        closed = mgr.close_session("CS-0001")
        assert "Discussion about governance" in closed.summary

    def test_summary_contains_participants(self, mgr: CouncilSessionManager):
        mgr.create_session(
            "Participant Test",
            "Topic",
            participants=["Sage", "Logic"],
        )
        closed = mgr.close_session("CS-0001")
        assert "Sage" in closed.summary
        assert "Logic" in closed.summary

    def test_summary_with_contributions(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        session = mgr.create_session(
            "With Contrib Summary",
            "Topic",
            participants=["Sage"],
        )
        rec_data = json.loads(
            (sessions_dir / f"{session.session_id}.json").read_text(
                encoding="utf-8"
            )
        )
        rec_data["contributions"] = [
            {
                "speaker": "Sage",
                "content": "My contribution.",
                "round_number": 1,
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
        ]
        rec_data["current_round"] = 1
        (sessions_dir / f"{session.session_id}.json").write_text(
            json.dumps(rec_data, indent=2), encoding="utf-8"
        )
        closed = mgr.close_session(session.session_id)
        assert "1 contribution" in closed.summary
        assert "Sage" in closed.summary

    def test_summary_no_participants(self, mgr: CouncilSessionManager):
        mgr.create_session("No Participants", "Topic")
        closed = mgr.close_session("CS-0001")
        # Should still produce something valid
        assert "No Participants" in closed.summary
        assert "0 contributions" in closed.summary


# ─── Exceptions ────────────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(CouncilSessionNotFoundError, CouncilSessionError)
        assert issubclass(CouncilSessionValidationError, CouncilSessionError)
        assert issubclass(CouncilSessionStateError, CouncilSessionError)
        assert issubclass(CouncilSessionError, Exception)

    def test_not_found_fields(self):
        err = CouncilSessionNotFoundError("CS-5555")
        assert err.session_id == "CS-5555"
        assert "CS-5555" in str(err)

    def test_validation_fields(self):
        err = CouncilSessionValidationError(["Error 1", "Error 2"])
        assert err.errors == ["Error 1", "Error 2"]
        assert "Error 1" in str(err)
        assert "Error 2" in str(err)

    def test_state_error_fields(self):
        err = CouncilSessionStateError("CS-0001", "Already closed")
        assert err.session_id == "CS-0001"
        assert "Already closed" in str(err)
        assert "CS-0001" in str(err)


# ─── Edge Cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, mgr: CouncilSessionManager):
        session = mgr.create_session(
            "日本語セッション",
            "こんにちは世界",
            agenda="議題: 倫理的AI",
            participants=["Ärch", "Ñoño"],
        )
        reloaded = mgr.get(session.session_id)
        assert reloaded.title == "日本語セッション"
        assert reloaded.topic == "こんにちは世界"
        assert reloaded.agenda == "議題: 倫理的AI"
        assert "Ärch" in reloaded.participants

    def test_long_agenda(self, mgr: CouncilSessionManager):
        long_agenda = "A" * 5000
        session = mgr.create_session("Long", "Topic", agenda=long_agenda)
        reloaded = mgr.get(session.session_id)
        assert len(reloaded.agenda) == 5000

    def test_many_participants(self, mgr: CouncilSessionManager):
        participants = [f"Member_{i}" for i in range(50)]
        session = mgr.create_session(
            "Crowded",
            "Topic",
            participants=participants,
        )
        reloaded = mgr.get(session.session_id)
        assert len(reloaded.participants) == 50

    def test_persistence_roundtrip(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        """Full create → close → reload roundtrip."""
        session = mgr.create_session(
            "Roundtrip",
            "Roundtrip topic",
            agenda="Full agenda",
            participants=["Alpha", "Beta"],
            round_count=7,
            proposed_category="culture",
            metadata={"v": 1},
        )
        closed = mgr.close_session(session.session_id, summary="All done.")
        # Create a new manager to force fresh reads
        mgr2 = CouncilSessionManager(sessions_dir=sessions_dir)
        reloaded = mgr2.get(closed.session_id)
        assert reloaded.status == "closed"
        assert reloaded.summary == "All done."
        assert reloaded.round_count == 7
        assert reloaded.proposed_category == "culture"
        assert reloaded.metadata == {"v": 1}
        assert reloaded.participants == ["Alpha", "Beta"]

    def test_full_lifecycle(self, mgr: CouncilSessionManager, sessions_dir: Path):
        """Create → add contributions → close → handoff."""
        session = mgr.create_session(
            "Lifecycle Test",
            "End-to-end lifecycle",
            participants=["Sage", "Logic"],
        )
        # Add contributions
        rec_data = json.loads(
            (sessions_dir / f"{session.session_id}.json").read_text(
                encoding="utf-8"
            )
        )
        for i in range(3):
            rec_data["contributions"].append({
                "speaker": "Sage" if i % 2 == 0 else "Logic",
                "content": f"Contribution number {i + 1}",
                "round_number": (i // 2) + 1,
                "timestamp": f"2026-01-01T0{i}:00:00+00:00",
            })
        rec_data["current_round"] = 2
        (sessions_dir / f"{session.session_id}.json").write_text(
            json.dumps(rec_data, indent=2), encoding="utf-8"
        )
        # Verify get works with contributions
        loaded = mgr.get(session.session_id)
        assert len(loaded.contributions) == 3

        # Close
        closed = mgr.close_session(session.session_id, summary="Lifecycle done.")
        assert closed.status == "closed"
        assert len(closed.contributions) == 3

        # Build proposal data
        proposal_data = mgr.build_proposal_data(session.session_id)
        assert "Lifecycle Test" in proposal_data["body"]
        assert "Sage" in proposal_data["body"]

    def test_repr_counts_sessions(self, mgr: CouncilSessionManager):
        assert "sessions=0" in repr(mgr)
        mgr.create_session("A", "T")
        mgr.create_session("B", "T")
        assert "sessions=2" in repr(mgr)

    def test_metadata_with_nested_objects(self, mgr: CouncilSessionManager):
        meta = {
            "tags": ["ethics", "governance"],
            "config": {"max_depth": 5, "enabled": True},
        }
        session = mgr.create_session("Meta", "Topic", metadata=meta)
        reloaded = mgr.get(session.session_id)
        assert reloaded.metadata == meta
        assert reloaded.metadata["tags"] == ["ethics", "governance"]
        assert reloaded.metadata["config"]["max_depth"] == 5

    def test_contribution_limit_in_handoff(
        self, mgr: CouncilSessionManager, sessions_dir: Path
    ):
        """Handoff body only includes the last 20 contributions."""
        session = mgr.create_session("Many Contrib", "Topic")
        rec_data = json.loads(
            (sessions_dir / f"{session.session_id}.json").read_text(
                encoding="utf-8"
            )
        )
        # Add 30 contributions
        for i in range(30):
            rec_data["contributions"].append({
                "speaker": f"Member{i}",
                "content": f"Content from member {i}",
                "round_number": 1,
                "timestamp": f"2026-01-01T00:{i:02d}:00+00:00",
            })
        rec_data["current_round"] = 1
        (sessions_dir / f"{session.session_id}.json").write_text(
            json.dumps(rec_data, indent=2), encoding="utf-8"
        )

        mgr.close_session(session.session_id, summary="Done.")
        data = mgr.build_proposal_data(session.session_id)
        # The body should contain "30 contributions" in the header
        assert "30 contributions" in data["body"]
        # But only the last 20 members should have their content shown
        # Member0 through Member9 should NOT appear in the actual
        # contribution list (only last 20: Member10-Member29)
        assert "Member29" in data["body"]
        assert "Member10" in data["body"]
