"""
Tests for core/voting.py — Voting Engine (F-006).

Covers: Vote model, VoteRecord model, VoteTally model,
VotingEngine open/cast/tally/close/veto lifecycle,
quorum checks, approval threshold, weighted votes,
human veto power, edge cases, and exception hierarchy.
"""

import json
from pathlib import Path

import pytest

from core.voting import (
    Vote,
    VoteNotFoundError,
    VoteRecord,
    VoteTally,
    VotingEngine,
    VotingError,
    VotingStateError,
    VotingValidationError,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def votes_dir(tmp_path: Path) -> Path:
    """Return a fresh temp directory for vote record storage."""
    d = tmp_path / "votes"
    d.mkdir()
    return d


@pytest.fixture
def engine(votes_dir: Path) -> VotingEngine:
    """Return a VotingEngine wired to a temp directory."""
    return VotingEngine(votes_dir=votes_dir, quorum=3, threshold=0.60)


# ─── Vote Data Class ──────────────────────────────────────────


class TestVote:
    """Tests for the Vote frozen dataclass."""

    def test_fields(self):
        v = Vote(voter="Sage", choice="for", reason="Good idea", timestamp="2026-01-01", weight=1.5)
        assert v.voter == "Sage"
        assert v.choice == "for"
        assert v.reason == "Good idea"
        assert v.weight == 1.5

    def test_defaults(self):
        v = Vote(voter="Sage", choice="for")
        assert v.reason == ""
        assert v.timestamp == ""
        assert v.weight == 1.0

    def test_frozen(self):
        v = Vote(voter="Sage", choice="for")
        with pytest.raises(AttributeError):
            v.voter = "Logic"  # type: ignore[misc]

    def test_to_dict_roundtrip(self):
        v = Vote(voter="Sage", choice="for", reason="Well argued", timestamp="2026-01-01", weight=2.0)
        d = v.to_dict()
        v2 = Vote.from_dict(d)
        assert v == v2

    def test_create_factory(self):
        v = Vote.create("Sage", "for", reason="Good")
        assert v.voter == "Sage"
        assert v.choice == "for"
        assert v.reason == "Good"
        assert v.timestamp != ""
        assert v.weight == 1.0

    def test_create_invalid_choice(self):
        with pytest.raises(VotingValidationError, match="Invalid choice"):
            Vote.create("Sage", "maybe")

    def test_create_custom_weight(self):
        v = Vote.create("Sage", "for", weight=2.0)
        assert v.weight == 2.0

    def test_create_invalid_weight(self):
        with pytest.raises(VotingValidationError, match="positive"):
            Vote.create("Sage", "for", weight=0)

    def test_create_negative_weight(self):
        with pytest.raises(VotingValidationError, match="positive"):
            Vote.create("Sage", "for", weight=-1.0)


# ─── VoteRecord Data Class ────────────────────────────────────


class TestVoteRecord:
    """Tests for the VoteRecord frozen dataclass."""

    def test_fields(self):
        rec = VoteRecord(proposal_id="P-0001")
        assert rec.proposal_id == "P-0001"
        assert rec.status == "open"
        assert rec.votes == []
        assert rec.vetoed is False

    def test_frozen(self):
        rec = VoteRecord(proposal_id="P-0001")
        with pytest.raises(AttributeError):
            rec.status = "closed"  # type: ignore[misc]

    def test_to_dict_roundtrip(self):
        votes = [Vote(voter="Sage", choice="for", reason="Yes", timestamp="t1")]
        rec = VoteRecord(
            proposal_id="P-0001",
            status="open",
            votes=votes,
            vetoed=True,
            veto_reason="No way",
            veto_timestamp="t2",
            opened_at="t0",
            closed_at="",
            metadata={"key": "val"},
        )
        d = rec.to_dict()
        rec2 = VoteRecord.from_dict(d)
        assert rec == rec2

    def test_create_factory(self):
        rec = VoteRecord.create("P-0001", metadata={"source": "test"})
        assert rec.proposal_id == "P-0001"
        assert rec.status == "open"
        assert rec.votes == []
        assert rec.vetoed is False
        assert rec.opened_at != ""
        assert rec.metadata == {"source": "test"}

    def test_defaults(self):
        rec = VoteRecord.create("P-0001")
        assert rec.metadata == {}
        assert rec.veto_reason == ""
        assert rec.closed_at == ""


# ─── VoteTally Data Class ─────────────────────────────────────


class TestVoteTally:
    """Tests for the VoteTally frozen dataclass."""

    def test_to_dict(self):
        t = VoteTally(
            total_votes=5, votes_for=3, votes_against=1, votes_abstain=1,
            weighted_for=3.0, weighted_against=1.0, weighted_abstain=1.0,
            approval_rate=0.75, quorum_met=True, threshold_met=True,
            approved=True, vetoed=False,
        )
        d = t.to_dict()
        assert d["total_votes"] == 5
        assert d["approved"] is True

    def test_frozen(self):
        t = VoteTally(
            total_votes=0, votes_for=0, votes_against=0, votes_abstain=0,
            weighted_for=0, weighted_against=0, weighted_abstain=0,
            approval_rate=0, quorum_met=False, threshold_met=False,
            approved=False, vetoed=False,
        )
        with pytest.raises(AttributeError):
            t.approved = True  # type: ignore[misc]


# ─── VotingEngine Init ────────────────────────────────────────


class TestVotingEngineInit:
    """Tests for VotingEngine initialization."""

    def test_creates_directory(self, tmp_path: Path):
        d = tmp_path / "new_votes"
        engine = VotingEngine(votes_dir=d)
        assert d.exists()

    def test_existing_directory(self, votes_dir: Path):
        engine = VotingEngine(votes_dir=votes_dir)
        assert engine.directory == votes_dir

    def test_custom_quorum_and_threshold(self, votes_dir: Path):
        engine = VotingEngine(votes_dir=votes_dir, quorum=7, threshold=0.80)
        assert engine.quorum == 7
        assert engine.threshold == 0.80

    def test_repr(self, engine: VotingEngine):
        r = repr(engine)
        assert "VotingEngine" in r
        assert "records=0" in r
        assert "quorum=3" in r


# ─── Open Voting ──────────────────────────────────────────────


class TestOpenVoting:
    """Tests for opening voting on proposals."""

    def test_open_basic(self, engine: VotingEngine):
        rec = engine.open_voting("P-0001")
        assert rec.proposal_id == "P-0001"
        assert rec.status == "open"
        assert rec.opened_at != ""

    def test_open_creates_file(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        filepath = engine.directory / "V-P-0001.json"
        assert filepath.exists()

    def test_open_with_metadata(self, engine: VotingEngine):
        rec = engine.open_voting("P-0001", metadata={"session": "S-001"})
        assert rec.metadata == {"session": "S-001"}

    def test_open_duplicate_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        with pytest.raises(VotingStateError, match="already exists"):
            engine.open_voting("P-0001")

    def test_open_empty_id_raises(self, engine: VotingEngine):
        with pytest.raises(VotingValidationError, match="empty"):
            engine.open_voting("")

    def test_open_whitespace_id_raises(self, engine: VotingEngine):
        with pytest.raises(VotingValidationError, match="empty"):
            engine.open_voting("   ")


# ─── Cast Vote ────────────────────────────────────────────────


class TestCastVote:
    """Tests for casting votes."""

    def test_cast_basic(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        rec = engine.cast_vote("P-0001", Vote.create("Sage", "for", "Good idea"))
        assert len(rec.votes) == 1
        assert rec.votes[0].voter == "Sage"
        assert rec.votes[0].choice == "for"

    def test_cast_multiple(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "against"))
        rec = engine.cast_vote("P-0001", Vote.create("Spark", "abstain"))
        assert len(rec.votes) == 3

    def test_cast_persists(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        # Reload from disk
        rec = engine.get("P-0001")
        assert len(rec.votes) == 1
        assert rec.votes[0].voter == "Sage"

    def test_cast_duplicate_voter_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        with pytest.raises(VotingValidationError, match="already voted"):
            engine.cast_vote("P-0001", Vote.create("Sage", "against"))

    def test_cast_duplicate_case_insensitive(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        with pytest.raises(VotingValidationError, match="already voted"):
            engine.cast_vote("P-0001", Vote.create("sage", "against"))

    def test_cast_on_closed_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.close_voting("P-0001")
        with pytest.raises(VotingStateError, match="closed"):
            engine.cast_vote("P-0001", Vote.create("Sage", "for"))

    def test_cast_nonexistent_raises(self, engine: VotingEngine):
        with pytest.raises(VoteNotFoundError):
            engine.cast_vote("P-9999", Vote.create("Sage", "for"))


# ─── Tally ────────────────────────────────────────────────────


class TestTally:
    """Tests for vote tallying, quorum, and threshold logic."""

    def test_tally_empty(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        tally = engine.tally("P-0001")
        assert tally.total_votes == 0
        assert tally.votes_for == 0
        assert tally.votes_against == 0
        assert tally.votes_abstain == 0
        assert tally.approval_rate == 0.0
        assert tally.quorum_met is False
        assert tally.approved is False

    def test_tally_quorum_met(self, engine: VotingEngine):
        """With quorum=3, 3 votes should meet quorum."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "for"))
        engine.cast_vote("P-0001", Vote.create("Spark", "for"))
        tally = engine.tally("P-0001")
        assert tally.quorum_met is True

    def test_tally_quorum_not_met(self, engine: VotingEngine):
        """With quorum=3, 2 votes should not meet quorum."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "for"))
        tally = engine.tally("P-0001")
        assert tally.quorum_met is False
        assert tally.approved is False  # even with 100% for

    def test_tally_threshold_met(self, engine: VotingEngine):
        """60% threshold: 3 for, 1 against = 75% → approved."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "for"))
        engine.cast_vote("P-0001", Vote.create("Spark", "for"))
        engine.cast_vote("P-0001", Vote.create("Echo", "against"))
        tally = engine.tally("P-0001")
        assert tally.threshold_met is True
        assert tally.approval_rate == 0.75
        assert tally.approved is True

    def test_tally_threshold_not_met(self, engine: VotingEngine):
        """60% threshold: 1 for, 2 against = 33% → not approved."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "against"))
        engine.cast_vote("P-0001", Vote.create("Spark", "against"))
        tally = engine.tally("P-0001")
        assert tally.threshold_met is False
        assert tally.approved is False

    def test_tally_abstains_dont_count_for_threshold(self, engine: VotingEngine):
        """Abstains do not count toward approval rate (only for vs against)."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "abstain"))
        engine.cast_vote("P-0001", Vote.create("Spark", "abstain"))
        tally = engine.tally("P-0001")
        # 1 for, 0 against → 100% approval rate
        assert tally.approval_rate == 1.0
        assert tally.votes_abstain == 2
        assert tally.quorum_met is True
        assert tally.approved is True

    def test_tally_all_abstain(self, engine: VotingEngine):
        """All abstains: no decisive votes → 0% approval."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "abstain"))
        engine.cast_vote("P-0001", Vote.create("Logic", "abstain"))
        engine.cast_vote("P-0001", Vote.create("Spark", "abstain"))
        tally = engine.tally("P-0001")
        assert tally.approval_rate == 0.0
        assert tally.quorum_met is True
        assert tally.approved is False  # 0% < 60%

    def test_tally_weighted_votes(self, engine: VotingEngine):
        """Weighted votes: 1 for (weight=3) vs 2 against (weight=1 each)."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for", weight=3.0))
        engine.cast_vote("P-0001", Vote.create("Logic", "against", weight=1.0))
        engine.cast_vote("P-0001", Vote.create("Spark", "against", weight=1.0))
        tally = engine.tally("P-0001")
        assert tally.weighted_for == 3.0
        assert tally.weighted_against == 2.0
        # 3 / (3+2) = 0.60 — exactly at threshold
        assert tally.approval_rate == 0.6
        assert tally.threshold_met is True
        assert tally.approved is True

    def test_tally_nonexistent_raises(self, engine: VotingEngine):
        with pytest.raises(VoteNotFoundError):
            engine.tally("P-9999")


# ─── Close Voting ─────────────────────────────────────────────


class TestCloseVoting:
    """Tests for closing voting."""

    def test_close_basic(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        rec = engine.close_voting("P-0001")
        assert rec.status == "closed"
        assert rec.closed_at != ""

    def test_close_preserves_votes(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        rec = engine.close_voting("P-0001")
        assert len(rec.votes) == 1
        assert rec.votes[0].voter == "Sage"

    def test_close_already_closed_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.close_voting("P-0001")
        with pytest.raises(VotingStateError, match="already closed"):
            engine.close_voting("P-0001")

    def test_close_nonexistent_raises(self, engine: VotingEngine):
        with pytest.raises(VoteNotFoundError):
            engine.close_voting("P-9999")


# ─── Human Veto ───────────────────────────────────────────────


class TestHumanVeto:
    """Tests for human veto power."""

    def test_veto_basic(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        rec = engine.veto("P-0001", reason="Not appropriate")
        assert rec.vetoed is True
        assert rec.veto_reason == "Not appropriate"
        assert rec.veto_timestamp != ""

    def test_veto_overrides_approval(self, engine: VotingEngine):
        """Even with unanimous support and quorum, veto prevents approval."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "for"))
        engine.cast_vote("P-0001", Vote.create("Spark", "for"))
        engine.veto("P-0001", reason="I disagree")
        tally = engine.tally("P-0001")
        assert tally.quorum_met is True
        assert tally.threshold_met is True
        assert tally.vetoed is True
        assert tally.approved is False  # veto overrides

    def test_veto_already_vetoed_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.veto("P-0001")
        with pytest.raises(VotingStateError, match="already vetoed"):
            engine.veto("P-0001")

    def test_veto_nonexistent_raises(self, engine: VotingEngine):
        with pytest.raises(VoteNotFoundError):
            engine.veto("P-9999")

    def test_veto_without_reason(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        rec = engine.veto("P-0001")
        assert rec.vetoed is True
        assert rec.veto_reason == ""

    def test_veto_on_closed_voting(self, engine: VotingEngine):
        """Veto can be applied even after voting is closed."""
        engine.open_voting("P-0001")
        engine.close_voting("P-0001")
        rec = engine.veto("P-0001", reason="Changed my mind")
        assert rec.vetoed is True

    def test_lift_veto(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.veto("P-0001", reason="Testing")
        rec = engine.lift_veto("P-0001")
        assert rec.vetoed is False
        assert rec.veto_reason == ""
        assert rec.veto_timestamp == ""

    def test_lift_veto_not_vetoed_raises(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        with pytest.raises(VotingStateError, match="not vetoed"):
            engine.lift_veto("P-0001")

    def test_lift_veto_restores_approval(self, engine: VotingEngine):
        """After lifting veto, tally should reflect original vote outcome."""
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.cast_vote("P-0001", Vote.create("Logic", "for"))
        engine.cast_vote("P-0001", Vote.create("Spark", "for"))
        engine.veto("P-0001")
        assert engine.tally("P-0001").approved is False
        engine.lift_veto("P-0001")
        assert engine.tally("P-0001").approved is True


# ─── List Records ─────────────────────────────────────────────


class TestListRecords:
    """Tests for listing vote records."""

    def test_list_empty(self, engine: VotingEngine):
        assert engine.list_records() == []

    def test_list_all(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.open_voting("P-0002")
        records = engine.list_records()
        assert len(records) == 2
        ids = [r.proposal_id for r in records]
        assert "P-0001" in ids
        assert "P-0002" in ids

    def test_list_filter_status(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        engine.open_voting("P-0002")
        engine.close_voting("P-0002")
        assert len(engine.list_records(status="open")) == 1
        assert len(engine.list_records(status="closed")) == 1

    def test_has_record(self, engine: VotingEngine):
        assert engine.has_record("P-0001") is False
        engine.open_voting("P-0001")
        assert engine.has_record("P-0001") is True

    def test_corrupt_file_skipped(self, engine: VotingEngine):
        """Corrupt JSON files are silently skipped during listing."""
        engine.open_voting("P-0001")
        corrupt = engine.directory / "V-P-BAD.json"
        corrupt.write_text("{invalid json", encoding="utf-8")
        records = engine.list_records()
        assert len(records) == 1
        assert records[0].proposal_id == "P-0001"


# ─── Edge Cases ───────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unicode_voter_and_reason(self, engine: VotingEngine):
        engine.open_voting("P-0001")
        v = Vote.create("Sägé", "for", reason="Très bien! 🎉")
        rec = engine.cast_vote("P-0001", v)
        assert rec.votes[0].voter == "Sägé"
        assert "🎉" in rec.votes[0].reason

    def test_exact_threshold_boundary(self, votes_dir: Path):
        """Exactly at threshold (60%) should approve."""
        engine = VotingEngine(votes_dir=votes_dir, quorum=2, threshold=0.60)
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("A", "for", weight=3.0))
        engine.cast_vote("P-0001", Vote.create("B", "against", weight=2.0))
        tally = engine.tally("P-0001")
        assert tally.approval_rate == 0.6
        assert tally.threshold_met is True

    def test_just_below_threshold(self, votes_dir: Path):
        """Just below threshold should not approve."""
        engine = VotingEngine(votes_dir=votes_dir, quorum=2, threshold=0.60)
        engine.open_voting("P-0001")
        # 59/100 = 0.59 < 0.60
        engine.cast_vote("P-0001", Vote.create("A", "for", weight=59.0))
        engine.cast_vote("P-0001", Vote.create("B", "against", weight=41.0))
        tally = engine.tally("P-0001")
        assert tally.approval_rate == 0.59
        assert tally.threshold_met is False

    def test_large_number_of_votes(self, votes_dir: Path):
        """Engine handles many voters without issue."""
        engine = VotingEngine(votes_dir=votes_dir, quorum=5, threshold=0.50)
        engine.open_voting("P-0001")
        for i in range(50):
            choice = "for" if i % 2 == 0 else "against"
            engine.cast_vote("P-0001", Vote.create(f"Voter{i}", choice))
        tally = engine.tally("P-0001")
        assert tally.total_votes == 50
        assert tally.votes_for == 25
        assert tally.votes_against == 25

    def test_persistence_after_reopen(self, votes_dir: Path):
        """Data survives creating a new engine instance."""
        engine1 = VotingEngine(votes_dir=votes_dir, quorum=3, threshold=0.60)
        engine1.open_voting("P-0001")
        engine1.cast_vote("P-0001", Vote.create("Sage", "for"))

        engine2 = VotingEngine(votes_dir=votes_dir, quorum=3, threshold=0.60)
        rec = engine2.get("P-0001")
        assert len(rec.votes) == 1
        assert rec.votes[0].voter == "Sage"

    def test_voting_after_veto_then_lift(self, engine: VotingEngine):
        """Can still cast votes after veto is applied (voting is still open)."""
        engine.open_voting("P-0001")
        engine.veto("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for"))
        engine.lift_veto("P-0001")
        rec = engine.get("P-0001")
        assert len(rec.votes) == 1
        assert rec.vetoed is False


# ─── Exceptions ───────────────────────────────────────────────


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_voting_error_is_base(self):
        assert issubclass(VoteNotFoundError, VotingError)
        assert issubclass(VotingValidationError, VotingError)
        assert issubclass(VotingStateError, VotingError)

    def test_vote_not_found_fields(self):
        exc = VoteNotFoundError("P-0001")
        assert exc.proposal_id == "P-0001"
        assert "P-0001" in str(exc)

    def test_validation_error_fields(self):
        exc = VotingValidationError(["err1", "err2"])
        assert exc.errors == ["err1", "err2"]
        assert "err1" in str(exc)

    def test_state_error_fields(self):
        exc = VotingStateError("P-0001", "something wrong")
        assert exc.proposal_id == "P-0001"
        assert "something wrong" in str(exc)
