"""
Jericho — Tests for Session Analytics (F-016)

Tests for core/analytics.py: MemberStats, ProposalStats, VotingStats,
SessionStats, AnalyticsReport, SessionAnalytics engine, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.analytics import (
    AnalyticsError,
    AnalyticsReport,
    AnalyticsValidationError,
    MemberStats,
    ProposalStats,
    SessionAnalytics,
    SessionStats,
    VotingStats,
)
from core.proposals import Proposal, ProposalManager
from core.voting import Vote, VoteRecord, VotingEngine
from core.session import SessionOrchestrator, SessionRecord, SessionMessage
from core.discussion import DiscussionManager, DiscussionRecord, DiscussionContribution


# ─── Helpers ──────────────────────────────────────────────────


def _make_proposal_manager(tmp_path: Path) -> ProposalManager:
    """Create a ProposalManager with a temp directory."""
    return ProposalManager(proposals_dir=tmp_path / "proposals")


def _make_voting_engine(tmp_path: Path) -> VotingEngine:
    """Create a VotingEngine with a temp directory."""
    return VotingEngine(votes_dir=tmp_path / "votes", quorum=2, threshold=0.6)


def _seed_proposals(mgr: ProposalManager, count: int = 3) -> list[Proposal]:
    """Create sample proposals."""
    proposals = []
    categories = ["ethics", "governance", "character"]
    for i in range(count):
        p = mgr.create(
            f"Proposal {i + 1}",
            f"Description {i + 1}",
            author=["Sage", "Logic", "Spark"][i % 3],
            category=categories[i % len(categories)],
        )
        proposals.append(p)
    return proposals


def _seed_votes(
    engine: VotingEngine,
    proposal_ids: list[str],
    voters: list[str] | None = None,
) -> None:
    """Open voting and cast votes for proposals."""
    voters = voters or ["Sage", "Logic", "Spark", "Echo", "Forge"]
    choices = ["for", "against", "abstain"]
    for pid in proposal_ids:
        engine.open_voting(pid)
        for i, voter in enumerate(voters):
            engine.cast_vote(
                pid,
                Vote.create(voter, choices[i % len(choices)]),
            )


def _make_session_record(
    session_id: str,
    participants: list[str],
    phase: str = "closed",
    activity_type: str = "discussion",
    message_count: int = 5,
) -> SessionRecord:
    """Create a SessionRecord for testing (without orchestrator)."""
    messages = [
        SessionMessage.create(
            speaker=participants[i % len(participants)],
            content=f"Message {i}",
            phase="active",
        )
        for i in range(message_count)
    ]
    return SessionRecord(
        session_id=session_id,
        title=f"Session {session_id}",
        phase=phase,
        activity_type=activity_type,
        participants=participants,
        messages=messages,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _make_discussion_record(
    discussion_id: str,
    proposal_id: str,
    participants: list[str],
    status: str = "closed",
    contribution_count: int = 4,
) -> DiscussionRecord:
    """Create a DiscussionRecord for testing (without manager)."""
    contributions = [
        DiscussionContribution.create(
            speaker=participants[i % len(participants)],
            content=f"Contribution {i}",
            round_number=(i // len(participants)) + 1,
        )
        for i in range(contribution_count)
    ]
    return DiscussionRecord(
        discussion_id=discussion_id,
        proposal_id=proposal_id,
        title=f"Discussion {discussion_id}",
        participants=participants,
        contributions=contributions,
        round_count=2,
        current_round=2,
        status=status,
        created_at="2026-01-01T00:00:00+00:00",
    )


class _FakeSessionOrchestrator:
    """Minimal mock that mimics SessionOrchestrator.list_sessions()."""

    def __init__(self, sessions: list[SessionRecord]) -> None:
        self._sessions = sessions

    def list_sessions(self, **kwargs) -> list[SessionRecord]:
        return list(self._sessions)


class _FakeDiscussionManager:
    """Minimal mock that mimics DiscussionManager.list_discussions()."""

    def __init__(self, discussions: list[DiscussionRecord]) -> None:
        self._discussions = discussions

    def list_discussions(self, **kwargs) -> list[DiscussionRecord]:
        return list(self._discussions)


# ═══════════════════════════════════════════════════════════════
# MemberStats
# ═══════════════════════════════════════════════════════════════


class TestMemberStats:
    def test_fields(self):
        s = MemberStats(name="Sage", votes_cast=3, proposals_authored=1)
        assert s.name == "Sage"
        assert s.votes_cast == 3
        assert s.proposals_authored == 1
        assert s.sessions_participated == 0

    def test_frozen(self):
        s = MemberStats(name="Sage")
        with pytest.raises(AttributeError):
            s.name = "Changed"  # type: ignore[misc]

    def test_to_dict(self):
        s = MemberStats(name="Sage", votes_cast=5, total_activity=5)
        d = s.to_dict()
        assert d["name"] == "Sage"
        assert d["votes_cast"] == 5
        assert d["total_activity"] == 5

    def test_roundtrip(self):
        s = MemberStats(
            name="Sage",
            sessions_participated=2,
            votes_cast=5,
            proposals_authored=1,
            discussions_participated=3,
            votes_for=3,
            votes_against=1,
            votes_abstain=1,
            total_activity=11,
        )
        d = s.to_dict()
        s2 = MemberStats.from_dict(d)
        assert s == s2

    def test_defaults(self):
        s = MemberStats(name="Sage")
        assert s.sessions_participated == 0
        assert s.votes_cast == 0
        assert s.proposals_authored == 0
        assert s.discussions_participated == 0
        assert s.votes_for == 0
        assert s.votes_against == 0
        assert s.votes_abstain == 0
        assert s.total_activity == 0


# ═══════════════════════════════════════════════════════════════
# ProposalStats
# ═══════════════════════════════════════════════════════════════


class TestProposalStats:
    def test_fields(self):
        s = ProposalStats(total=10, approval_rate=0.75)
        assert s.total == 10
        assert s.approval_rate == 0.75

    def test_frozen(self):
        s = ProposalStats()
        with pytest.raises(AttributeError):
            s.total = 5  # type: ignore[misc]

    def test_defaults(self):
        s = ProposalStats()
        assert s.total == 0
        assert s.by_status == {}
        assert s.by_category == {}
        assert s.approval_rate == 0.0

    def test_roundtrip(self):
        s = ProposalStats(
            total=5,
            by_status={"draft": 2, "decided": 3},
            by_category={"ethics": 3, "governance": 2},
            approval_rate=0.6667,
        )
        d = s.to_dict()
        s2 = ProposalStats.from_dict(d)
        assert s == s2

    def test_to_dict(self):
        s = ProposalStats(total=3, by_status={"draft": 3})
        d = s.to_dict()
        assert d["total"] == 3
        assert d["by_status"] == {"draft": 3}


# ═══════════════════════════════════════════════════════════════
# VotingStats
# ═══════════════════════════════════════════════════════════════


class TestVotingStats:
    def test_fields(self):
        s = VotingStats(total_records=5, total_votes_cast=25)
        assert s.total_records == 5
        assert s.total_votes_cast == 25

    def test_frozen(self):
        s = VotingStats()
        with pytest.raises(AttributeError):
            s.total_records = 10  # type: ignore[misc]

    def test_defaults(self):
        s = VotingStats()
        assert s.total_records == 0
        assert s.total_votes_cast == 0
        assert s.avg_votes_per_record == 0.0
        assert s.quorum_achievement_rate == 0.0
        assert s.approval_rate == 0.0
        assert s.veto_count == 0

    def test_roundtrip(self):
        s = VotingStats(
            total_records=3,
            total_votes_cast=15,
            avg_votes_per_record=5.0,
            quorum_achievement_rate=1.0,
            approval_rate=0.6667,
            veto_count=1,
        )
        d = s.to_dict()
        s2 = VotingStats.from_dict(d)
        assert s == s2

    def test_to_dict(self):
        s = VotingStats(total_records=2, veto_count=1)
        d = s.to_dict()
        assert d["total_records"] == 2
        assert d["veto_count"] == 1


# ═══════════════════════════════════════════════════════════════
# SessionStats
# ═══════════════════════════════════════════════════════════════


class TestSessionStats:
    def test_fields(self):
        s = SessionStats(total_sessions=10, avg_messages_per_session=8.5)
        assert s.total_sessions == 10
        assert s.avg_messages_per_session == 8.5

    def test_frozen(self):
        s = SessionStats()
        with pytest.raises(AttributeError):
            s.total_sessions = 5  # type: ignore[misc]

    def test_defaults(self):
        s = SessionStats()
        assert s.total_sessions == 0
        assert s.by_phase == {}
        assert s.by_activity == {}
        assert s.avg_messages_per_session == 0.0
        assert s.avg_participants == 0.0

    def test_roundtrip(self):
        s = SessionStats(
            total_sessions=5,
            by_phase={"closed": 3, "active": 2},
            by_activity={"discussion": 4, "voting": 1},
            avg_messages_per_session=12.5,
            avg_participants=3.2,
        )
        d = s.to_dict()
        s2 = SessionStats.from_dict(d)
        assert s == s2

    def test_to_dict(self):
        s = SessionStats(total_sessions=3, by_phase={"closed": 3})
        d = s.to_dict()
        assert d["total_sessions"] == 3
        assert d["by_phase"] == {"closed": 3}


# ═══════════════════════════════════════════════════════════════
# AnalyticsReport
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsReport:
    def test_fields(self):
        r = AnalyticsReport(generated_at="2026-01-01T00:00:00+00:00")
        assert r.generated_at != ""
        assert r.member_stats == {}
        assert isinstance(r.proposal_stats, ProposalStats)
        assert isinstance(r.voting_stats, VotingStats)
        assert isinstance(r.session_stats, SessionStats)

    def test_frozen(self):
        r = AnalyticsReport()
        with pytest.raises(AttributeError):
            r.generated_at = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        stats = MemberStats(name="Sage", total_activity=5)
        r = AnalyticsReport(
            member_stats={"Sage": stats},
            top_participants=[("Sage", 5)],
            generated_at="2026-01-01",
        )
        d = r.to_dict()
        assert d["member_stats"]["Sage"]["name"] == "Sage"
        assert d["top_participants"] == [("Sage", 5)]
        assert d["generated_at"] == "2026-01-01"


# ═══════════════════════════════════════════════════════════════
# SessionAnalytics Init
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsInit:
    def test_with_all_managers(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        ve = _make_voting_engine(tmp_path)
        fake_so = _FakeSessionOrchestrator([])
        fake_dm = _FakeDiscussionManager([])
        sa = SessionAnalytics(
            proposal_manager=pm,
            voting_engine=ve,
            session_orchestrator=fake_so,
            discussion_manager=fake_dm,
        )
        assert sa.proposal_manager is pm
        assert sa.voting_engine is ve
        assert sa.session_orchestrator is fake_so
        assert sa.discussion_manager is fake_dm

    def test_with_none_managers(self):
        sa = SessionAnalytics()
        assert sa.proposal_manager is None
        assert sa.voting_engine is None
        assert sa.session_orchestrator is None
        assert sa.discussion_manager is None

    def test_repr(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        sa = SessionAnalytics(proposal_manager=pm)
        r = repr(sa)
        assert "SessionAnalytics" in r
        assert "proposals" in r
        assert "voting" not in r


# ═══════════════════════════════════════════════════════════════
# Member Stats Computation
# ═══════════════════════════════════════════════════════════════


class TestMemberStatsComputation:
    def test_votes_counted(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "against"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.member_stats("Sage")
        assert stats.votes_cast == 1
        assert stats.votes_for == 1
        assert stats.votes_against == 0

    def test_proposals_counted(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")
        pm.create("Test 2", "Desc 2", author="Sage", category="governance")
        pm.create("Test 3", "Desc 3", author="Logic", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("Sage")
        assert stats.proposals_authored == 2

    def test_sessions_counted(self):
        sessions = [
            _make_session_record("S-001", ["Sage", "Logic"]),
            _make_session_record("S-002", ["Sage", "Spark"]),
            _make_session_record("S-003", ["Logic", "Spark"]),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.member_stats("Sage")
        assert stats.sessions_participated == 2

    def test_discussions_counted(self):
        discussions = [
            _make_discussion_record("D-001", "P-0001", ["Sage", "Logic"]),
            _make_discussion_record("D-002", "P-0002", ["Sage", "Spark"]),
        ]
        sa = SessionAnalytics(
            discussion_manager=_FakeDiscussionManager(discussions)
        )
        stats = sa.member_stats("Sage")
        assert stats.discussions_participated == 2

    def test_vote_breakdown(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "against"))
        ve.open_voting("P-0003")
        ve.cast_vote("P-0003", Vote.create("Sage", "abstain"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.member_stats("Sage")
        assert stats.votes_for == 1
        assert stats.votes_against == 1
        assert stats.votes_abstain == 1
        assert stats.votes_cast == 3

    def test_unknown_member_returns_zeros(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm)
        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("UnknownMember")
        assert stats.total_activity == 0
        assert stats.proposals_authored == 0

    def test_case_insensitive(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")
        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("sage")  # lowercase
        assert stats.proposals_authored == 1

    def test_no_data_sources(self):
        sa = SessionAnalytics()
        stats = sa.member_stats("Sage")
        assert stats.total_activity == 0

    def test_total_activity(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")

        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))

        sessions = [_make_session_record("S-001", ["Sage"])]
        discussions = [
            _make_discussion_record("D-001", "P-0001", ["Sage", "Logic"])
        ]

        sa = SessionAnalytics(
            proposal_manager=pm,
            voting_engine=ve,
            session_orchestrator=_FakeSessionOrchestrator(sessions),
            discussion_manager=_FakeDiscussionManager(discussions),
        )
        stats = sa.member_stats("Sage")
        # 1 proposal + 1 vote + 1 session + 1 discussion = 4
        assert stats.total_activity == 4


# ═══════════════════════════════════════════════════════════════
# All Member Stats
# ═══════════════════════════════════════════════════════════════


class TestAllMemberStats:
    def test_with_explicit_names(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        all_stats = sa.all_member_stats(member_names=["Sage", "Logic"])
        assert "Sage" in all_stats
        assert "Logic" in all_stats
        assert all_stats["Sage"].proposals_authored == 1
        assert all_stats["Logic"].proposals_authored == 0

    def test_auto_discovers_names(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")
        pm.create("Test 2", "Desc 2", author="Logic", category="governance")

        sa = SessionAnalytics(proposal_manager=pm)
        all_stats = sa.all_member_stats()
        assert "Sage" in all_stats
        assert "Logic" in all_stats
        assert len(all_stats) == 2

    def test_empty(self):
        sa = SessionAnalytics()
        all_stats = sa.all_member_stats()
        assert all_stats == {}


# ═══════════════════════════════════════════════════════════════
# Proposal Stats Computation
# ═══════════════════════════════════════════════════════════════


class TestProposalStatsComputation:
    def test_by_status(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 3)
        pm.update_status("P-0001", "open")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.total == 3
        assert stats.by_status["draft"] == 2
        assert stats.by_status["open"] == 1

    def test_by_category(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("E1", "Desc", author="Sage", category="ethics")
        pm.create("E2", "Desc", author="Sage", category="ethics")
        pm.create("G1", "Desc", author="Logic", category="governance")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.by_category["ethics"] == 2
        assert stats.by_category["governance"] == 1

    def test_approval_rate_with_voting(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        p1 = pm.create("P1", "Desc", author="Sage", category="ethics")
        p2 = pm.create("P2", "Desc", author="Sage", category="ethics")

        # Move both to decided
        pm.update_status(p1.id, "open")
        pm.update_status(p1.id, "under_review")
        pm.update_status(p1.id, "decided")
        pm.update_status(p2.id, "open")
        pm.update_status(p2.id, "under_review")
        pm.update_status(p2.id, "decided")

        # Only approve p1
        ve = _make_voting_engine(tmp_path)
        ve.open_voting(p1.id)
        ve.cast_vote(p1.id, Vote.create("A", "for"))
        ve.cast_vote(p1.id, Vote.create("B", "for"))

        ve.open_voting(p2.id)
        ve.cast_vote(p2.id, Vote.create("A", "against"))
        ve.cast_vote(p2.id, Vote.create("B", "against"))

        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        stats = sa.proposal_stats()
        assert stats.approval_rate == 0.5  # 1 of 2 approved

    def test_no_proposals(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.total == 0
        assert stats.approval_rate == 0.0

    def test_no_proposal_manager(self):
        sa = SessionAnalytics()
        stats = sa.proposal_stats()
        assert stats.total == 0

    def test_mixed_statuses(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        p1 = pm.create("P1", "D", author="Sage", category="ethics")
        p2 = pm.create("P2", "D", author="Logic", category="governance")
        p3 = pm.create("P3", "D", author="Spark", category="character")
        pm.update_status(p1.id, "open")
        pm.update_status(p2.id, "open")
        pm.update_status(p2.id, "under_review")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.by_status == {"open": 1, "under_review": 1, "draft": 1}


# ═══════════════════════════════════════════════════════════════
# Voting Stats Computation
# ═══════════════════════════════════════════════════════════════


class TestVotingStatsComputation:
    def test_total_records(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.open_voting("P-0002")

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.total_records == 2

    def test_total_votes(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "against"))
        ve.cast_vote("P-0001", Vote.create("Spark", "abstain"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.total_votes_cast == 3

    def test_avg_votes(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "for"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.avg_votes_per_record == 1.5  # 3 votes / 2 records

    def test_quorum_rate(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        # Record 1: 2 votes (quorum=2 met)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        # Record 2: 1 vote (quorum not met)
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "for"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.quorum_achievement_rate == 0.5  # 1 of 2

    def test_veto_count(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.veto("P-0001", "Overruled")
        ve.open_voting("P-0002")

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.veto_count == 1

    def test_no_records(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.total_records == 0
        assert stats.avg_votes_per_record == 0.0

    def test_no_voting_engine(self):
        sa = SessionAnalytics()
        stats = sa.voting_stats()
        assert stats.total_records == 0

    def test_approval_rate_closed(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        # Approved: quorum met, threshold met
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        ve.close_voting("P-0001")
        # Not approved: all against
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "against"))
        ve.cast_vote("P-0002", Vote.create("Logic", "against"))
        ve.close_voting("P-0002")

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.approval_rate == 0.5  # 1 of 2 closed approved


# ═══════════════════════════════════════════════════════════════
# Session Stats Computation
# ═══════════════════════════════════════════════════════════════


class TestSessionStatsComputation:
    def test_total_sessions(self):
        sessions = [
            _make_session_record("S-001", ["Sage", "Logic"]),
            _make_session_record("S-002", ["Sage", "Spark"]),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.session_stats()
        assert stats.total_sessions == 2

    def test_by_phase(self):
        sessions = [
            _make_session_record("S-001", ["Sage"], phase="closed"),
            _make_session_record("S-002", ["Sage"], phase="closed"),
            _make_session_record("S-003", ["Logic"], phase="active"),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.session_stats()
        assert stats.by_phase == {"closed": 2, "active": 1}

    def test_by_activity(self):
        sessions = [
            _make_session_record("S-001", ["Sage"], activity_type="discussion"),
            _make_session_record("S-002", ["Sage"], activity_type="voting"),
            _make_session_record(
                "S-003", ["Logic"], activity_type="discussion"
            ),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.session_stats()
        assert stats.by_activity == {"discussion": 2, "voting": 1}

    def test_avg_messages(self):
        sessions = [
            _make_session_record(
                "S-001", ["Sage"], message_count=10
            ),
            _make_session_record(
                "S-002", ["Sage"], message_count=6
            ),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.session_stats()
        assert stats.avg_messages_per_session == 8.0

    def test_avg_participants(self):
        sessions = [
            _make_session_record("S-001", ["Sage", "Logic"]),
            _make_session_record("S-002", ["Sage", "Logic", "Spark", "Echo"]),
        ]
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator(sessions)
        )
        stats = sa.session_stats()
        assert stats.avg_participants == 3.0  # (2+4)/2

    def test_no_sessions(self):
        sa = SessionAnalytics(
            session_orchestrator=_FakeSessionOrchestrator([])
        )
        stats = sa.session_stats()
        assert stats.total_sessions == 0
        assert stats.avg_messages_per_session == 0.0

    def test_no_orchestrator(self):
        sa = SessionAnalytics()
        stats = sa.session_stats()
        assert stats.total_sessions == 0


# ═══════════════════════════════════════════════════════════════
# Full Report
# ═══════════════════════════════════════════════════════════════


class TestFullReport:
    def test_includes_all(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")

        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))

        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        report = sa.full_report()

        assert report.proposal_stats.total == 1
        assert report.voting_stats.total_records == 1
        assert report.generated_at != ""
        assert "Sage" in report.member_stats

    def test_timestamp_set(self):
        sa = SessionAnalytics()
        report = sa.full_report()
        assert report.generated_at != ""

    def test_empty_data(self):
        sa = SessionAnalytics()
        report = sa.full_report()
        assert report.proposal_stats.total == 0
        assert report.voting_stats.total_records == 0
        assert report.session_stats.total_sessions == 0
        assert report.member_stats == {}
        assert report.top_participants == []


# ═══════════════════════════════════════════════════════════════
# Top Participants
# ═══════════════════════════════════════════════════════════════


class TestTopParticipants:
    def test_ranking(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("T1", "D", author="Sage", category="ethics")
        pm.create("T2", "D", author="Sage", category="ethics")
        pm.create("T3", "D", author="Logic", category="governance")

        sa = SessionAnalytics(proposal_manager=pm)
        top = sa.top_participants(member_names=["Sage", "Logic"])
        assert top[0] == ("Sage", 2)
        assert top[1] == ("Logic", 1)

    def test_limit(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("T1", "D", author="Sage", category="ethics")
        pm.create("T2", "D", author="Logic", category="ethics")
        pm.create("T3", "D", author="Spark", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        top = sa.top_participants(limit=2)
        assert len(top) == 2

    def test_no_data(self):
        sa = SessionAnalytics()
        top = sa.top_participants()
        assert top == []

    def test_with_mixed_activity(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("T1", "D", author="Sage", category="ethics")

        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        ve.cast_vote("P-0001", Vote.create("Spark", "against"))

        sessions = [_make_session_record("S-001", ["Logic", "Spark"])]

        sa = SessionAnalytics(
            proposal_manager=pm,
            voting_engine=ve,
            session_orchestrator=_FakeSessionOrchestrator(sessions),
        )
        top = sa.top_participants(limit=3)
        # Logic: 1 vote + 1 session = 2
        # Spark: 1 vote + 1 session = 2
        # Sage: 1 proposal = 1
        assert len(top) == 3
        assert top[0][1] >= top[1][1]  # sorted descending


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode_names(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Tëst", "Dësc", author="Sàge", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("Sàge")
        assert stats.proposals_authored == 1
        assert stats.name == "Sàge"

    def test_whitespace_stripping(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("  Sage  ")
        assert stats.proposals_authored == 1
        assert stats.name == "Sage"

    def test_large_dataset(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        for i in range(50):
            pm.create(
                f"Proposal {i}",
                f"Description {i}",
                author=f"Member-{i % 5}",
                category="ethics",
            )

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.total == 50
        assert stats.by_category["ethics"] == 50

    def test_empty_managers(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        ve = _make_voting_engine(tmp_path)
        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        report = sa.full_report()
        assert report.proposal_stats.total == 0
        assert report.voting_stats.total_records == 0

    def test_mixed_none_managers(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Test", "Desc", author="Sage", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.member_stats("Sage")
        assert stats.proposals_authored == 1
        assert stats.sessions_participated == 0  # no session orchestrator


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(AnalyticsValidationError, AnalyticsError)
        assert issubclass(AnalyticsError, Exception)

    def test_validation_fields(self):
        e = AnalyticsValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)
