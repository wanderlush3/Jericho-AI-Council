"""
Jericho — Session Analytics (F-016)

Read-only analytics engine that aggregates data from existing managers
to produce participation rates, voting patterns, proposal success rates,
and member activity metrics.

This module performs **no filesystem writes** — it reads from
``ProposalManager``, ``VotingEngine``, ``SessionOrchestrator``,
and ``DiscussionManager`` and returns frozen data-class reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


# ─── Exceptions ────────────────────────────────────────────────


class AnalyticsError(Exception):
    """Base exception for analytics errors."""


class AnalyticsValidationError(AnalyticsError):
    """Raised when analytics input data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class MemberStats:
    """Per-member activity statistics."""

    name: str
    sessions_participated: int = 0
    votes_cast: int = 0
    proposals_authored: int = 0
    discussions_participated: int = 0
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    total_activity: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemberStats:
        return cls(
            name=data["name"],
            sessions_participated=data.get("sessions_participated", 0),
            votes_cast=data.get("votes_cast", 0),
            proposals_authored=data.get("proposals_authored", 0),
            discussions_participated=data.get("discussions_participated", 0),
            votes_for=data.get("votes_for", 0),
            votes_against=data.get("votes_against", 0),
            votes_abstain=data.get("votes_abstain", 0),
            total_activity=data.get("total_activity", 0),
        )


@dataclass(frozen=True)
class ProposalStats:
    """Aggregate proposal statistics."""

    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    approval_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposalStats:
        return cls(
            total=data.get("total", 0),
            by_status=dict(data.get("by_status", {})),
            by_category=dict(data.get("by_category", {})),
            approval_rate=data.get("approval_rate", 0.0),
        )


@dataclass(frozen=True)
class VotingStats:
    """Aggregate voting statistics."""

    total_records: int = 0
    total_votes_cast: int = 0
    avg_votes_per_record: float = 0.0
    quorum_achievement_rate: float = 0.0
    approval_rate: float = 0.0
    veto_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VotingStats:
        return cls(
            total_records=data.get("total_records", 0),
            total_votes_cast=data.get("total_votes_cast", 0),
            avg_votes_per_record=data.get("avg_votes_per_record", 0.0),
            quorum_achievement_rate=data.get("quorum_achievement_rate", 0.0),
            approval_rate=data.get("approval_rate", 0.0),
            veto_count=data.get("veto_count", 0),
        )


@dataclass(frozen=True)
class SessionStats:
    """Aggregate session statistics."""

    total_sessions: int = 0
    by_phase: dict[str, int] = field(default_factory=dict)
    by_activity: dict[str, int] = field(default_factory=dict)
    avg_messages_per_session: float = 0.0
    avg_participants: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionStats:
        return cls(
            total_sessions=data.get("total_sessions", 0),
            by_phase=dict(data.get("by_phase", {})),
            by_activity=dict(data.get("by_activity", {})),
            avg_messages_per_session=data.get("avg_messages_per_session", 0.0),
            avg_participants=data.get("avg_participants", 0.0),
        )


@dataclass(frozen=True)
class AnalyticsReport:
    """Full analytics bundle across all subsystems."""

    member_stats: dict[str, MemberStats] = field(default_factory=dict)
    proposal_stats: ProposalStats = field(default_factory=ProposalStats)
    voting_stats: VotingStats = field(default_factory=VotingStats)
    session_stats: SessionStats = field(default_factory=SessionStats)
    top_participants: list[tuple[str, int]] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_stats": {
                k: v.to_dict() for k, v in self.member_stats.items()
            },
            "proposal_stats": self.proposal_stats.to_dict(),
            "voting_stats": self.voting_stats.to_dict(),
            "session_stats": self.session_stats.to_dict(),
            "top_participants": list(self.top_participants),
            "generated_at": self.generated_at,
        }


# ─── Session Analytics ────────────────────────────────────────


class SessionAnalytics:
    """
    Read-only analytics engine for the Jericho AI Council.

    Aggregates data from existing managers to compute participation
    rates, voting patterns, proposal success rates, and member
    activity metrics.

    All methods are read-only — no data is written to disk.

    Usage::

        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.session import SessionOrchestrator
        from core.discussion import DiscussionManager

        analytics = SessionAnalytics(
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
        report = analytics.full_report()
        stats = analytics.member_stats("Sage")
    """

    def __init__(
        self,
        *,
        proposal_manager: Any | None = None,
        voting_engine: Any | None = None,
        session_orchestrator: Any | None = None,
        discussion_manager: Any | None = None,
    ) -> None:
        self._proposals = proposal_manager
        self._voting = voting_engine
        self._sessions = session_orchestrator
        self._discussions = discussion_manager

    # ── Properties ────────────────────────────────────────────

    @property
    def proposal_manager(self) -> Any | None:
        return self._proposals

    @property
    def voting_engine(self) -> Any | None:
        return self._voting

    @property
    def session_orchestrator(self) -> Any | None:
        return self._sessions

    @property
    def discussion_manager(self) -> Any | None:
        return self._discussions

    # ── Member Stats ──────────────────────────────────────────

    def member_stats(self, member_name: str) -> MemberStats:
        """
        Compute activity statistics for a single member.

        Scans proposals, votes, sessions, and discussions for
        the given member name (case-insensitive).
        """
        name_lower = member_name.strip().lower()

        # ── Proposals ────────────────────────────────────────
        proposals_authored = 0
        if self._proposals is not None:
            for p in self._proposals.list_proposals():
                if p.author.lower() == name_lower:
                    proposals_authored += 1

        # ── Votes ────────────────────────────────────────────
        votes_cast = 0
        votes_for = 0
        votes_against = 0
        votes_abstain = 0
        if self._voting is not None:
            for record in self._voting.list_records():
                for vote in record.votes:
                    if vote.voter.lower() == name_lower:
                        votes_cast += 1
                        if vote.choice == "for":
                            votes_for += 1
                        elif vote.choice == "against":
                            votes_against += 1
                        elif vote.choice == "abstain":
                            votes_abstain += 1

        # ── Sessions ─────────────────────────────────────────
        sessions_participated = 0
        if self._sessions is not None:
            for session in self._sessions.list_sessions():
                if name_lower in [
                    p.lower() for p in session.participants
                ]:
                    sessions_participated += 1

        # ── Discussions ──────────────────────────────────────
        discussions_participated = 0
        if self._discussions is not None:
            for discussion in self._discussions.list_discussions():
                if name_lower in [
                    p.lower() for p in discussion.participants
                ]:
                    discussions_participated += 1

        total_activity = (
            sessions_participated
            + votes_cast
            + proposals_authored
            + discussions_participated
        )

        return MemberStats(
            name=member_name.strip(),
            sessions_participated=sessions_participated,
            votes_cast=votes_cast,
            proposals_authored=proposals_authored,
            discussions_participated=discussions_participated,
            votes_for=votes_for,
            votes_against=votes_against,
            votes_abstain=votes_abstain,
            total_activity=total_activity,
        )

    def all_member_stats(
        self,
        member_names: list[str] | None = None,
    ) -> dict[str, MemberStats]:
        """
        Compute stats for all members (or a provided list).

        If no member_names list is given, collects unique names
        from all data sources.
        """
        if member_names is not None:
            names = [n.strip() for n in member_names]
        else:
            names = sorted(self._collect_member_names())

        return {name: self.member_stats(name) for name in names}

    def _collect_member_names(self) -> set[str]:
        """Gather unique member names from all data sources."""
        names: set[str] = set()

        if self._proposals is not None:
            for p in self._proposals.list_proposals():
                names.add(p.author)

        if self._voting is not None:
            for record in self._voting.list_records():
                for vote in record.votes:
                    names.add(vote.voter)

        if self._sessions is not None:
            for session in self._sessions.list_sessions():
                for participant in session.participants:
                    names.add(participant)

        if self._discussions is not None:
            for discussion in self._discussions.list_discussions():
                for participant in discussion.participants:
                    names.add(participant)

        return names

    # ── Proposal Stats ────────────────────────────────────────

    def proposal_stats(self) -> ProposalStats:
        """Compute aggregate proposal statistics."""
        if self._proposals is None:
            return ProposalStats()

        proposals = self._proposals.list_proposals()
        if not proposals:
            return ProposalStats()

        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        decided_count = 0
        approved_count = 0

        for p in proposals:
            by_status[p.status] = by_status.get(p.status, 0) + 1
            by_category[p.category] = by_category.get(p.category, 0) + 1

            # Track approval rate for decided proposals
            if p.status == "decided" and self._voting is not None:
                decided_count += 1
                try:
                    tally = self._voting.tally(p.id)
                    if tally.approved:
                        approved_count += 1
                except Exception:
                    pass  # vote record may not exist

        approval_rate = (
            round(approved_count / decided_count, 4)
            if decided_count > 0
            else 0.0
        )

        return ProposalStats(
            total=len(proposals),
            by_status=by_status,
            by_category=by_category,
            approval_rate=approval_rate,
        )

    # ── Voting Stats ──────────────────────────────────────────

    def voting_stats(self) -> VotingStats:
        """Compute aggregate voting statistics."""
        if self._voting is None:
            return VotingStats()

        records = self._voting.list_records()
        if not records:
            return VotingStats()

        total_records = len(records)
        total_votes = sum(len(r.votes) for r in records)
        veto_count = sum(1 for r in records if r.vetoed)

        avg_votes = (
            round(total_votes / total_records, 2)
            if total_records > 0
            else 0.0
        )

        # Quorum achievement: how many records had quorum met
        quorum_met_count = 0
        approved_count = 0
        closed_count = 0

        for r in records:
            tally = self._voting._compute_tally(r)
            if tally.quorum_met:
                quorum_met_count += 1
            if r.status == "closed":
                closed_count += 1
                if tally.approved:
                    approved_count += 1

        quorum_rate = (
            round(quorum_met_count / total_records, 4)
            if total_records > 0
            else 0.0
        )

        approval_rate = (
            round(approved_count / closed_count, 4)
            if closed_count > 0
            else 0.0
        )

        return VotingStats(
            total_records=total_records,
            total_votes_cast=total_votes,
            avg_votes_per_record=avg_votes,
            quorum_achievement_rate=quorum_rate,
            approval_rate=approval_rate,
            veto_count=veto_count,
        )

    # ── Session Stats ─────────────────────────────────────────

    def session_stats(self) -> SessionStats:
        """Compute aggregate session statistics."""
        if self._sessions is None:
            return SessionStats()

        sessions = self._sessions.list_sessions()
        if not sessions:
            return SessionStats()

        total = len(sessions)
        by_phase: dict[str, int] = {}
        by_activity: dict[str, int] = {}
        total_messages = 0
        total_participants = 0

        for s in sessions:
            by_phase[s.phase] = by_phase.get(s.phase, 0) + 1
            if s.activity_type:
                by_activity[s.activity_type] = (
                    by_activity.get(s.activity_type, 0) + 1
                )
            total_messages += len(s.messages)
            total_participants += len(s.participants)

        avg_messages = round(total_messages / total, 2) if total > 0 else 0.0
        avg_participants = (
            round(total_participants / total, 2) if total > 0 else 0.0
        )

        return SessionStats(
            total_sessions=total,
            by_phase=by_phase,
            by_activity=by_activity,
            avg_messages_per_session=avg_messages,
            avg_participants=avg_participants,
        )

    # ── Top Participants ──────────────────────────────────────

    def top_participants(
        self,
        limit: int = 5,
        member_names: list[str] | None = None,
    ) -> list[tuple[str, int]]:
        """
        Return members ranked by total activity count.

        Args:
            limit: Max number of results to return.
            member_names: Optional list of names to rank. If None,
                discovers names from data sources.
        """
        all_stats = self.all_member_stats(member_names=member_names)
        ranked = sorted(
            all_stats.items(),
            key=lambda item: item[1].total_activity,
            reverse=True,
        )
        return [(name, stats.total_activity) for name, stats in ranked[:limit]]

    # ── Full Report ───────────────────────────────────────────

    def full_report(
        self,
        member_names: list[str] | None = None,
    ) -> AnalyticsReport:
        """
        Generate a comprehensive analytics report.

        Args:
            member_names: Optional list of members to include.
                If None, discovers names from data sources.
        """
        members = self.all_member_stats(member_names=member_names)
        proposals = self.proposal_stats()
        voting = self.voting_stats()
        sessions = self.session_stats()
        top = self.top_participants(member_names=member_names)

        return AnalyticsReport(
            member_stats=members,
            proposal_stats=proposals,
            voting_stats=voting,
            session_stats=sessions,
            top_participants=top,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        sources = []
        if self._proposals is not None:
            sources.append("proposals")
        if self._voting is not None:
            sources.append("voting")
        if self._sessions is not None:
            sources.append("sessions")
        if self._discussions is not None:
            sources.append("discussions")
        return f"SessionAnalytics(sources=[{', '.join(sources)}])"
