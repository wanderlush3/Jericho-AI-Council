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
    unanimous_count: int = 0

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
            unanimous_count=data.get("unanimous_count", 0),
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
class WorldBuildingStats:
    """World-building entity statistics."""

    total_characters: int = 0
    characters_by_status: dict[str, int] = field(default_factory=dict)
    total_locations: int = 0
    locations_by_status: dict[str, int] = field(default_factory=dict)
    total_items: int = 0
    items_by_status: dict[str, int] = field(default_factory=dict)
    total_stores: int = 0
    active_stores: int = 0
    total_inventory_slots: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldBuildingStats:
        return cls(
            total_characters=data.get("total_characters", 0),
            characters_by_status=dict(data.get("characters_by_status", {})),
            total_locations=data.get("total_locations", 0),
            locations_by_status=dict(data.get("locations_by_status", {})),
            total_items=data.get("total_items", 0),
            items_by_status=dict(data.get("items_by_status", {})),
            total_stores=data.get("total_stores", 0),
            active_stores=data.get("active_stores", 0),
            total_inventory_slots=data.get("total_inventory_slots", 0),
        )


@dataclass(frozen=True)
class EconomyStats:
    """Economy and treasury statistics."""

    total_accounts: int = 0
    total_circulation_gold: str = "0.00"
    government_balance: dict[str, int] = field(default_factory=dict)
    total_tax_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EconomyStats:
        return cls(
            total_accounts=data.get("total_accounts", 0),
            total_circulation_gold=data.get("total_circulation_gold", "0.00"),
            government_balance=dict(data.get("government_balance", {})),
            total_tax_events=data.get("total_tax_events", 0),
        )


@dataclass(frozen=True)
class ContentStats:
    """Story and content statistics."""

    total_stories: int = 0
    stories_by_status: dict[str, int] = field(default_factory=dict)
    total_chapters: int = 0
    total_scenes: int = 0
    illustrated_scenes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentStats:
        return cls(
            total_stories=data.get("total_stories", 0),
            stories_by_status=dict(data.get("stories_by_status", {})),
            total_chapters=data.get("total_chapters", 0),
            total_scenes=data.get("total_scenes", 0),
            illustrated_scenes=data.get("illustrated_scenes", 0),
        )


@dataclass(frozen=True)
class ImageStats:
    """Image generation statistics."""

    total_images: int = 0
    images_by_entity_type: dict[str, int] = field(default_factory=dict)
    total_storage_bytes: int = 0
    total_templates: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageStats:
        return cls(
            total_images=data.get("total_images", 0),
            images_by_entity_type=dict(data.get("images_by_entity_type", {})),
            total_storage_bytes=data.get("total_storage_bytes", 0),
            total_templates=data.get("total_templates", 0),
        )


@dataclass(frozen=True)
class MemoryKnowledgeStats:
    """Memory and knowledge base statistics."""

    total_beliefs: int = 0
    total_session_events: int = 0
    total_shared_decisions: int = 0
    total_laws: int = 0
    laws_by_status: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryKnowledgeStats:
        return cls(
            total_beliefs=data.get("total_beliefs", 0),
            total_session_events=data.get("total_session_events", 0),
            total_shared_decisions=data.get("total_shared_decisions", 0),
            total_laws=data.get("total_laws", 0),
            laws_by_status=dict(data.get("laws_by_status", {})),
        )


@dataclass(frozen=True)
class AnalyticsReport:
    """Full analytics bundle across all subsystems."""

    member_stats: dict[str, MemberStats] = field(default_factory=dict)
    proposal_stats: ProposalStats = field(default_factory=ProposalStats)
    voting_stats: VotingStats = field(default_factory=VotingStats)
    session_stats: SessionStats = field(default_factory=SessionStats)
    top_participants: list[tuple[str, int]] = field(default_factory=list)
    world_building_stats: WorldBuildingStats = field(default_factory=WorldBuildingStats)
    economy_stats: EconomyStats = field(default_factory=EconomyStats)
    content_stats: ContentStats = field(default_factory=ContentStats)
    image_stats: ImageStats = field(default_factory=ImageStats)
    memory_knowledge_stats: MemoryKnowledgeStats = field(default_factory=MemoryKnowledgeStats)
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
            "world_building_stats": self.world_building_stats.to_dict(),
            "economy_stats": self.economy_stats.to_dict(),
            "content_stats": self.content_stats.to_dict(),
            "image_stats": self.image_stats.to_dict(),
            "memory_knowledge_stats": self.memory_knowledge_stats.to_dict(),
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
        character_manager: Any | None = None,
        location_manager: Any | None = None,
        item_manager: Any | None = None,
        store_manager: Any | None = None,
        treasury_manager: Any | None = None,
        taxation_manager: Any | None = None,
        story_manager: Any | None = None,
        image_manager: Any | None = None,
        template_manager: Any | None = None,
        law_manager: Any | None = None,
        registry: Any | None = None,
    ) -> None:
        self._proposals = proposal_manager
        self._voting = voting_engine
        self._sessions = session_orchestrator
        self._discussions = discussion_manager
        self._characters = character_manager
        self._locations = location_manager
        self._items = item_manager
        self._stores = store_manager
        self._treasury = treasury_manager
        self._taxation = taxation_manager
        self._stories = story_manager
        self._images = image_manager
        self._templates = template_manager
        self._laws = law_manager
        self._registry = registry

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
        unanimous_count = 0

        for r in records:
            tally = self._voting._compute_tally(r)
            if tally.quorum_met:
                quorum_met_count += 1
            if r.status == "closed":
                closed_count += 1
                if tally.approved:
                    approved_count += 1
            # Unanimous: all votes are "for" and at least 1 vote
            if r.votes and all(v.choice == "for" for v in r.votes):
                unanimous_count += 1

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
            unanimous_count=unanimous_count,
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

    # ── World Building Stats ───────────────────────────────────

    def world_building_stats(self) -> WorldBuildingStats:
        """Compute world-building entity statistics."""
        total_characters = 0
        characters_by_status: dict[str, int] = {}
        total_locations = 0
        locations_by_status: dict[str, int] = {}
        total_items = 0
        items_by_status: dict[str, int] = {}
        total_stores = 0
        active_stores = 0
        total_inventory_slots = 0

        if self._characters is not None:
            try:
                chars = self._characters.list_characters()
                total_characters = len(chars)
                for c in chars:
                    characters_by_status[c.status] = (
                        characters_by_status.get(c.status, 0) + 1
                    )
            except Exception:
                pass

        if self._locations is not None:
            try:
                locs = self._locations.list_locations()
                total_locations = len(locs)
                for loc in locs:
                    locations_by_status[loc.status] = (
                        locations_by_status.get(loc.status, 0) + 1
                    )
            except Exception:
                pass

        if self._items is not None:
            try:
                items = self._items.list_items()
                total_items = len(items)
                for item in items:
                    items_by_status[item.status] = (
                        items_by_status.get(item.status, 0) + 1
                    )
            except Exception:
                pass

        if self._stores is not None:
            try:
                stores = self._stores.list_stores()
                total_stores = len(stores)
                for store in stores:
                    if store.status == "active":
                        active_stores += 1
                    total_inventory_slots += len(
                        getattr(store, "inventory", []) or []
                    )
            except Exception:
                pass

        return WorldBuildingStats(
            total_characters=total_characters,
            characters_by_status=characters_by_status,
            total_locations=total_locations,
            locations_by_status=locations_by_status,
            total_items=total_items,
            items_by_status=items_by_status,
            total_stores=total_stores,
            active_stores=active_stores,
            total_inventory_slots=total_inventory_slots,
        )

    # ── Economy Stats ────────────────────────────────────────

    def economy_stats(self) -> EconomyStats:
        """Compute economy and treasury statistics."""
        total_accounts = 0
        total_bronze = 0
        government_balance: dict[str, int] = {}
        total_tax_events = 0

        if self._treasury is not None:
            try:
                accounts = self._treasury.list_accounts()
                total_accounts = len(accounts)
                for acct in accounts:
                    total_bronze += acct.balance.total_in_bronze()
                    if acct.account_type == "government":
                        government_balance = acct.balance.to_dict()
            except Exception:
                pass

        if self._taxation is not None:
            try:
                events = self._taxation.list_events()
                total_tax_events = len(events)
            except Exception:
                pass

        # Convert total bronze to gold display string
        from config.settings import OBELISK_CONVERSION_RATE
        rate = OBELISK_CONVERSION_RATE
        gold_equiv = total_bronze / (rate * rate) if rate > 0 else 0.0
        circulation_display = f"{gold_equiv:.2f}"

        return EconomyStats(
            total_accounts=total_accounts,
            total_circulation_gold=circulation_display,
            government_balance=government_balance,
            total_tax_events=total_tax_events,
        )

    # ── Content Stats ────────────────────────────────────────

    def content_stats(self) -> ContentStats:
        """Compute story and content statistics."""
        total_stories = 0
        stories_by_status: dict[str, int] = {}
        total_chapters = 0
        total_scenes = 0
        illustrated_scenes = 0

        if self._stories is not None:
            try:
                stories = self._stories.list_stories()
                total_stories = len(stories)
                for story in stories:
                    stories_by_status[story.status] = (
                        stories_by_status.get(story.status, 0) + 1
                    )
                    total_chapters += len(story.chapters)
                    for chapter in story.chapters:
                        total_scenes += len(chapter.scenes)
                        for scene in chapter.scenes:
                            if scene.image_id:
                                illustrated_scenes += 1
            except Exception:
                pass

        return ContentStats(
            total_stories=total_stories,
            stories_by_status=stories_by_status,
            total_chapters=total_chapters,
            total_scenes=total_scenes,
            illustrated_scenes=illustrated_scenes,
        )

    # ── Image Stats ──────────────────────────────────────────

    def image_stats(self) -> ImageStats:
        """Compute image generation statistics."""
        total_images = 0
        images_by_entity_type: dict[str, int] = {}
        total_storage_bytes = 0
        total_templates = 0

        if self._images is not None:
            try:
                images_dir = self._images.directory
                for entity_type_dir in images_dir.iterdir():
                    if not entity_type_dir.is_dir() or entity_type_dir.name.startswith("."):
                        continue
                    entity_type = entity_type_dir.name
                    for entity_dir in entity_type_dir.iterdir():
                        if not entity_dir.is_dir():
                            continue
                        imgs = self._images.list_images(
                            entity_type, entity_dir.name,
                        )
                        count = len(imgs)
                        total_images += count
                        images_by_entity_type[entity_type] = (
                            images_by_entity_type.get(entity_type, 0) + count
                        )
                        for img in imgs:
                            total_storage_bytes += img.file_size
            except Exception:
                pass

        if self._templates is not None:
            try:
                total_templates = len(self._templates.list_templates())
            except Exception:
                pass

        return ImageStats(
            total_images=total_images,
            images_by_entity_type=images_by_entity_type,
            total_storage_bytes=total_storage_bytes,
            total_templates=total_templates,
        )

    # ── Memory & Knowledge Stats ─────────────────────────────

    def memory_knowledge_stats(self) -> MemoryKnowledgeStats:
        """Compute memory and knowledge base statistics."""
        total_beliefs = 0
        total_session_events = 0
        total_shared_decisions = 0
        total_laws = 0
        laws_by_status: dict[str, int] = {}

        # Gather member names for memory scanning
        member_names: list[str] = []
        if self._registry is not None:
            try:
                member_names = self._registry.list_names()
            except Exception:
                pass

        if member_names:
            try:
                from core.memory import AgentMemory, SharedMemory
                for mname in member_names:
                    amem = AgentMemory(mname)
                    total_beliefs += len(amem.read_core_beliefs())
                    total_session_events += len(amem.read_session_log())
                shared = SharedMemory()
                total_shared_decisions = len(shared.read_decisions())
            except Exception:
                pass

        if self._laws is not None:
            try:
                laws = self._laws.list_laws()
                total_laws = len(laws)
                for law in laws:
                    laws_by_status[law.status] = (
                        laws_by_status.get(law.status, 0) + 1
                    )
            except Exception:
                pass

        return MemoryKnowledgeStats(
            total_beliefs=total_beliefs,
            total_session_events=total_session_events,
            total_shared_decisions=total_shared_decisions,
            total_laws=total_laws,
            laws_by_status=laws_by_status,
        )

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
        world = self.world_building_stats()
        economy = self.economy_stats()
        content = self.content_stats()
        images = self.image_stats()
        memory_knowledge = self.memory_knowledge_stats()

        return AnalyticsReport(
            member_stats=members,
            proposal_stats=proposals,
            voting_stats=voting,
            session_stats=sessions,
            top_participants=top,
            world_building_stats=world,
            economy_stats=economy,
            content_stats=content,
            image_stats=images,
            memory_knowledge_stats=memory_knowledge,
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
        if self._characters is not None:
            sources.append("characters")
        if self._locations is not None:
            sources.append("locations")
        if self._items is not None:
            sources.append("items")
        if self._stores is not None:
            sources.append("stores")
        if self._treasury is not None:
            sources.append("treasury")
        if self._stories is not None:
            sources.append("stories")
        if self._images is not None:
            sources.append("images")
        if self._laws is not None:
            sources.append("laws")
        return f"SessionAnalytics(sources=[{', '.join(sources)}])"
