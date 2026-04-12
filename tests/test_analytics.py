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
    ContentStats,
    EconomyStats,
    ImageStats,
    MemberStats,
    MemoryKnowledgeStats,
    ProposalStats,
    SessionAnalytics,
    SessionStats,
    VotingStats,
    WorldBuildingStats,
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


# ═══════════════════════════════════════════════════════════════
# New Dataclass Tests (F-050)
# ═══════════════════════════════════════════════════════════════


class TestWorldBuildingStats:
    def test_defaults(self):
        s = WorldBuildingStats()
        assert s.total_characters == 0
        assert s.characters_by_status == {}
        assert s.total_stores == 0

    def test_roundtrip(self):
        s = WorldBuildingStats(
            total_characters=5,
            characters_by_status={"active": 3, "draft": 2},
            total_locations=8,
            locations_by_status={"active": 8},
            total_items=12,
            items_by_status={"active": 10, "draft": 2},
            total_stores=3,
            active_stores=2,
            total_inventory_slots=15,
        )
        d = s.to_dict()
        s2 = WorldBuildingStats.from_dict(d)
        assert s2.total_characters == 5
        assert s2.total_inventory_slots == 15


class TestEconomyStats:
    def test_defaults(self):
        s = EconomyStats()
        assert s.total_accounts == 0
        assert s.total_circulation_gold == "0.00"

    def test_roundtrip(self):
        s = EconomyStats(
            total_accounts=10,
            total_circulation_gold="2400.00",
            government_balance={"gold": 1000, "silver": 0, "bronze": 0},
            total_tax_events=5,
        )
        d = s.to_dict()
        s2 = EconomyStats.from_dict(d)
        assert s2.total_accounts == 10
        assert s2.government_balance["gold"] == 1000


class TestContentStats:
    def test_defaults(self):
        s = ContentStats()
        assert s.total_stories == 0
        assert s.illustrated_scenes == 0

    def test_roundtrip(self):
        s = ContentStats(
            total_stories=3,
            stories_by_status={"active": 2, "draft": 1},
            total_chapters=7,
            total_scenes=15,
            illustrated_scenes=8,
        )
        d = s.to_dict()
        s2 = ContentStats.from_dict(d)
        assert s2.total_scenes == 15
        assert s2.illustrated_scenes == 8


class TestImageStats:
    def test_defaults(self):
        s = ImageStats()
        assert s.total_images == 0
        assert s.total_storage_bytes == 0

    def test_roundtrip(self):
        s = ImageStats(
            total_images=42,
            images_by_entity_type={"character": 20, "location": 22},
            total_storage_bytes=10485760,
            total_templates=3,
        )
        d = s.to_dict()
        s2 = ImageStats.from_dict(d)
        assert s2.total_images == 42
        assert s2.images_by_entity_type["character"] == 20


class TestMemoryKnowledgeStats:
    def test_defaults(self):
        s = MemoryKnowledgeStats()
        assert s.total_beliefs == 0
        assert s.total_laws == 0

    def test_roundtrip(self):
        s = MemoryKnowledgeStats(
            total_beliefs=45,
            total_session_events=120,
            total_shared_decisions=10,
            total_laws=8,
            laws_by_status={"active": 6, "draft": 2},
        )
        d = s.to_dict()
        s2 = MemoryKnowledgeStats.from_dict(d)
        assert s2.total_beliefs == 45
        assert s2.laws_by_status["active"] == 6


# ═══════════════════════════════════════════════════════════════
# World Building Stats Computation (F-050)
# ═══════════════════════════════════════════════════════════════


class _FakeCharacterManager:
    def __init__(self, chars):
        self._chars = chars
    def list_characters(self, **kw):
        return list(self._chars)


class _FakeLocationManager:
    def __init__(self, locs):
        self._locs = locs
    def list_locations(self, **kw):
        return list(self._locs)


class _FakeItemManager:
    def __init__(self, items):
        self._items = items
    def list_items(self, **kw):
        return list(self._items)


class _FakeStoreManager:
    def __init__(self, stores):
        self._stores = stores
    def list_stores(self, **kw):
        return list(self._stores)


class _FakeEntity:
    """Minimal entity stub with status and optional inventory."""
    def __init__(self, status="active", inventory=None):
        self.status = status
        self.inventory = inventory or []


class TestWorldBuildingComputation:
    def test_all_counts(self):
        chars = [_FakeEntity("active"), _FakeEntity("draft"), _FakeEntity("active")]
        locs = [_FakeEntity("active"), _FakeEntity("active")]
        items = [_FakeEntity("active"), _FakeEntity("draft")]
        stores = [
            _FakeEntity("active", inventory=["a", "b"]),
            _FakeEntity("draft", inventory=["c"]),
        ]
        sa = SessionAnalytics(
            character_manager=_FakeCharacterManager(chars),
            location_manager=_FakeLocationManager(locs),
            item_manager=_FakeItemManager(items),
            store_manager=_FakeStoreManager(stores),
        )
        wb = sa.world_building_stats()
        assert wb.total_characters == 3
        assert wb.characters_by_status == {"active": 2, "draft": 1}
        assert wb.total_locations == 2
        assert wb.total_items == 2
        assert wb.total_stores == 2
        assert wb.active_stores == 1
        assert wb.total_inventory_slots == 3

    def test_no_managers(self):
        sa = SessionAnalytics()
        wb = sa.world_building_stats()
        assert wb.total_characters == 0
        assert wb.total_locations == 0


# ═══════════════════════════════════════════════════════════════
# Economy Stats Computation (F-050)
# ═══════════════════════════════════════════════════════════════


class _FakeTreasuryAccount:
    def __init__(self, account_type="personal", gold=0, silver=0, bronze=0):
        self.account_type = account_type
        self.balance = _FakeBalance(gold, silver, bronze)


class _FakeBalance:
    def __init__(self, gold, silver, bronze):
        self.gold = gold
        self.silver = silver
        self.bronze = bronze
    def total_in_bronze(self):
        return (self.gold * 10000) + (self.silver * 100) + self.bronze
    def to_dict(self):
        return {"gold": self.gold, "silver": self.silver, "bronze": self.bronze}


class _FakeTreasuryManager:
    def __init__(self, accounts):
        self._accounts = accounts
    def list_accounts(self):
        return list(self._accounts)


class _FakeTaxationManager:
    def __init__(self, events):
        self._events = events
    def list_events(self, **kw):
        return list(self._events)


class TestEconomyComputation:
    def test_basic(self):
        accounts = [
            _FakeTreasuryAccount("government", gold=1000),
            _FakeTreasuryAccount("personal", gold=200),
        ]
        sa = SessionAnalytics(
            treasury_manager=_FakeTreasuryManager(accounts),
            taxation_manager=_FakeTaxationManager(["e1", "e2"]),
        )
        ec = sa.economy_stats()
        assert ec.total_accounts == 2
        assert ec.government_balance == {"gold": 1000, "silver": 0, "bronze": 0}
        assert ec.total_tax_events == 2
        assert ec.total_circulation_gold != "0.00"

    def test_no_managers(self):
        sa = SessionAnalytics()
        ec = sa.economy_stats()
        assert ec.total_accounts == 0
        assert ec.total_circulation_gold == "0.00"


# ═══════════════════════════════════════════════════════════════
# Content Stats Computation (F-050)
# ═══════════════════════════════════════════════════════════════


class _FakeScene:
    def __init__(self, image_id=""):
        self.image_id = image_id


class _FakeChapter:
    def __init__(self, scenes=None):
        self.scenes = scenes or []


class _FakeStory:
    def __init__(self, status="active", chapters=None):
        self.status = status
        self.chapters = chapters or []


class _FakeStoryManager:
    def __init__(self, stories):
        self._stories = stories
    def list_stories(self, **kw):
        return list(self._stories)


class TestContentComputation:
    def test_basic(self):
        stories = [
            _FakeStory("active", [
                _FakeChapter([_FakeScene("IMG-0001"), _FakeScene("")]),
                _FakeChapter([_FakeScene("IMG-0002")]),
            ]),
            _FakeStory("draft"),
        ]
        sa = SessionAnalytics(story_manager=_FakeStoryManager(stories))
        cs = sa.content_stats()
        assert cs.total_stories == 2
        assert cs.stories_by_status == {"active": 1, "draft": 1}
        assert cs.total_chapters == 2
        assert cs.total_scenes == 3
        assert cs.illustrated_scenes == 2

    def test_no_manager(self):
        sa = SessionAnalytics()
        cs = sa.content_stats()
        assert cs.total_stories == 0


# ═══════════════════════════════════════════════════════════════
# Image Stats Computation (F-050)
# ═══════════════════════════════════════════════════════════════


class TestImageComputation:
    def test_basic(self, tmp_path):
        # Build a fake images directory structure
        images_dir = tmp_path / "images"
        char_dir = images_dir / "character" / "CH-0001"
        char_dir.mkdir(parents=True)
        # Write a metadata file
        import json as _json
        metadata = [
            {"id": "IMG-0001", "entity_type": "character", "entity_id": "CH-0001",
             "filename": "img_0001.png", "is_primary": True, "file_size": 1024,
             "width": 512, "height": 512, "created_at": "", "original_filename": "",
             "prompt": "", "negative_prompt": "", "template_id": "",
             "generation_job_id": "", "metadata": {}},
        ]
        (char_dir / "images.json").write_text(
            _json.dumps(metadata), encoding="utf-8"
        )

        from core.image_manager import ImageManager
        img_mgr = ImageManager(images_dir=images_dir)

        sa = SessionAnalytics(image_manager=img_mgr)
        im = sa.image_stats()
        assert im.total_images == 1
        assert im.images_by_entity_type == {"character": 1}
        assert im.total_storage_bytes == 1024

    def test_no_manager(self):
        sa = SessionAnalytics()
        im = sa.image_stats()
        assert im.total_images == 0


# ═══════════════════════════════════════════════════════════════
# Memory & Knowledge Stats Computation (F-050)
# ═══════════════════════════════════════════════════════════════


class _FakeRegistry:
    def __init__(self, names):
        self._names = names
    def list_names(self):
        return list(self._names)


class _FakeLawManager:
    def __init__(self, laws):
        self._laws = laws
    def list_laws(self, **kw):
        return list(self._laws)


class _FakeLaw:
    def __init__(self, status="active"):
        self.status = status


class TestMemoryKnowledgeComputation:
    def test_laws(self):
        laws = [_FakeLaw("active"), _FakeLaw("active"), _FakeLaw("draft")]
        sa = SessionAnalytics(law_manager=_FakeLawManager(laws))
        mk = sa.memory_knowledge_stats()
        assert mk.total_laws == 3
        assert mk.laws_by_status == {"active": 2, "draft": 1}

    def test_no_managers(self):
        sa = SessionAnalytics()
        mk = sa.memory_knowledge_stats()
        assert mk.total_laws == 0
        assert mk.total_beliefs == 0


# ═══════════════════════════════════════════════════════════════
# Unanimous Vote Tracking (F-050)
# ═══════════════════════════════════════════════════════════════


class TestUnanimousVotes:
    def test_unanimous(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        # Record 1: all "for" — unanimous
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        # Record 2: mixed — not unanimous
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "for"))
        ve.cast_vote("P-0002", Vote.create("Logic", "against"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.unanimous_count == 1

    def test_no_votes(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.unanimous_count == 0

    def test_all_unanimous(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("A", "for"))
        ve.cast_vote("P-0001", Vote.create("B", "for"))
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("A", "for"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.unanimous_count == 2


# ═══════════════════════════════════════════════════════════════
# Full Report with Expanded Stats (F-050)
# ═══════════════════════════════════════════════════════════════


class TestFullReportExpanded:
    def test_includes_new_sections(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        ve = _make_voting_engine(tmp_path)
        chars = [_FakeEntity("active")]
        sa = SessionAnalytics(
            proposal_manager=pm,
            voting_engine=ve,
            character_manager=_FakeCharacterManager(chars),
            law_manager=_FakeLawManager([_FakeLaw("active")]),
        )
        report = sa.full_report()

        assert isinstance(report.world_building_stats, WorldBuildingStats)
        assert isinstance(report.economy_stats, EconomyStats)
        assert isinstance(report.content_stats, ContentStats)
        assert isinstance(report.image_stats, ImageStats)
        assert isinstance(report.memory_knowledge_stats, MemoryKnowledgeStats)
        assert report.world_building_stats.total_characters == 1
        assert report.memory_knowledge_stats.total_laws == 1

    def test_to_dict_includes_new_sections(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        ve = _make_voting_engine(tmp_path)
        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        report = sa.full_report()
        d = report.to_dict()

        assert "world_building_stats" in d
        assert "economy_stats" in d
        assert "content_stats" in d
        assert "image_stats" in d
        assert "memory_knowledge_stats" in d
