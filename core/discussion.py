"""
Jericho — Discussion Rounds (F-010)

Structured multi-agent discussion on a proposal before voting.
Each discussion round bundles a proposal with participants, runs
multiple rounds of deliberation, and produces a structured outcome
(summary + per-member contributions) that feeds into voting.

Storage:
    Each discussion gets a JSON file in ``data/discussions/``
    named ``D-<discussion_id>.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    DEFAULT_DISCUSSION_ROUNDS,
    DISCUSSIONS_DIR,
    MAX_DISCUSSION_ROUNDS,
)
from core.api_client import APIClient, ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.memory_influence import MemoryInfluence
from core.proposals import Proposal, ProposalManager
from core.registry import CouncilMember, CouncilRegistry
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class DiscussionError(Exception):
    """Base exception for discussion-round errors."""


class DiscussionNotFoundError(DiscussionError):
    """Raised when a discussion record cannot be found."""

    def __init__(self, discussion_id: str) -> None:
        self.discussion_id = discussion_id
        super().__init__(f"Discussion not found: '{discussion_id}'")


class DiscussionValidationError(DiscussionError):
    """Raised when discussion data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class DiscussionStateError(DiscussionError):
    """Raised when an operation conflicts with current discussion state."""

    def __init__(self, discussion_id: str, message: str) -> None:
        self.discussion_id = discussion_id
        super().__init__(
            f"Discussion state error for '{discussion_id}': {message}"
        )


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class DiscussionContribution:
    """A single contribution from a council member in a discussion round."""

    speaker: str
    content: str
    round_number: int = 0
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscussionContribution:
        return cls(
            speaker=data["speaker"],
            content=data["content"],
            round_number=data.get("round_number", 0),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        speaker: str,
        content: str,
        round_number: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> DiscussionContribution:
        """Factory that auto-fills the timestamp."""
        return cls(
            speaker=speaker,
            content=content,
            round_number=round_number,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class DiscussionRecord:
    """Persistent record of a structured discussion round on a proposal."""

    discussion_id: str
    proposal_id: str
    title: str
    participants: list[str] = field(default_factory=list)
    contributions: list[DiscussionContribution] = field(default_factory=list)
    round_count: int = 0
    current_round: int = 0
    status: str = "open"  # open / closed
    summary: str = ""
    created_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["contributions"] = [c.to_dict() for c in self.contributions]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscussionRecord:
        contributions = [
            DiscussionContribution.from_dict(c)
            for c in data.get("contributions", [])
        ]
        return cls(
            discussion_id=data["discussion_id"],
            proposal_id=data["proposal_id"],
            title=data["title"],
            participants=list(data.get("participants", [])),
            contributions=contributions,
            round_count=data.get("round_count", 0),
            current_round=data.get("current_round", 0),
            status=data.get("status", "open"),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        discussion_id: str,
        proposal_id: str,
        title: str,
        participants: list[str] | None = None,
        round_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> DiscussionRecord:
        """Factory that auto-fills the created_at timestamp."""
        if not discussion_id.strip():
            raise DiscussionValidationError(
                ["Discussion ID must not be empty"]
            )
        if not title.strip():
            raise DiscussionValidationError(["Title must not be empty"])
        if not proposal_id.strip():
            raise DiscussionValidationError(
                ["Proposal ID must not be empty"]
            )
        return cls(
            discussion_id=discussion_id.strip(),
            proposal_id=proposal_id.strip(),
            title=title.strip(),
            participants=participants or [],
            contributions=[],
            round_count=round_count,
            current_round=0,
            status="open",
            summary="",
            created_at=datetime.now(timezone.utc).isoformat(),
            closed_at="",
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────

# _atomic_write is imported from core.utils


def _build_discussion_prompt(
    member: CouncilMember,
    proposal: Proposal,
    contributions: list[DiscussionContribution],
    round_number: int,
    memory_context_text: str = "",
) -> str:
    """Build a discussion prompt that includes proposal details and history."""
    parts = [
        f"## Discussion: {proposal.title}",
        f"**Proposal ID:** {proposal.id}",
        f"**Category:** {proposal.category}",
        f"**Author:** {proposal.author}",
        f"\n**Description:** {proposal.description}",
    ]
    if proposal.body:
        parts.append(f"\n**Details:**\n{proposal.body}")

    if contributions:
        parts.append("\n### Discussion So Far")
        for c in contributions[-10:]:  # limit context window
            parts.append(
                f"**{c.speaker}** (round {c.round_number}): {c.content}"
            )

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    parts.append(
        f"\n---\n"
        f"You are **{member.name}** ({member.role}). This is round "
        f"{round_number} of the discussion.\n"
        f"Share your perspective on this proposal. Consider its merits, "
        f"potential issues, and how it aligns with your area of expertise. "
        f"Be concise but substantive."
    )
    return "\n".join(parts)


# ─── Discussion Manager ───────────────────────────────────────


class DiscussionManager:
    """
    Orchestrates structured multi-agent discussions on proposals.

    Each discussion ties to a specific proposal and runs through
    configured rounds where each participant contributes their
    perspective.  Contributions are recorded to per-agent memory.

    Usage::

        registry = CouncilRegistry().load()
        proposals = ProposalManager()
        async with APIClient() as client:
            mgr = DiscussionManager(
                registry=registry,
                api_client=client,
                proposal_manager=proposals,
            )
            rec = mgr.create_discussion(
                "D-001", "P-0001", "Ethics Review",
                participants=["Sage", "Logic", "Drift"],
            )
            rec = await mgr.run_all_rounds("D-001")
            rec = mgr.close_discussion("D-001")
    """

    def __init__(
        self,
        *,
        registry: CouncilRegistry,
        api_client: APIClient,
        proposal_manager: ProposalManager,
        discussions_dir: Path | None = None,
        shared_memory: SharedMemory | None = None,
        memory_influence: MemoryInfluence | None = None,
    ) -> None:
        self._registry = registry
        self._api_client = api_client
        self._proposal_manager = proposal_manager
        self._dir = discussions_dir or DISCUSSIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._shared_memory = shared_memory or SharedMemory()
        self._memory_influence = memory_influence

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def registry(self) -> CouncilRegistry:
        return self._registry

    @property
    def proposal_manager(self) -> ProposalManager:
        return self._proposal_manager

    # ── Discussion Lifecycle ──────────────────────────────────

    def create_discussion(
        self,
        discussion_id: str,
        proposal_id: str,
        title: str,
        *,
        participants: list[str] | None = None,
        round_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DiscussionRecord:
        """
        Create a new discussion round for a proposal.

        Validates proposal exists and participants are real council members.
        Requires at least 2 participants.

        Raises:
            DiscussionValidationError: if inputs are invalid.
            DiscussionError: if a discussion with this ID already exists.
        """
        filepath = self._filepath(discussion_id.strip())
        if filepath.exists():
            raise DiscussionError(
                f"Discussion already exists: '{discussion_id}'"
            )

        participants = participants or []

        # Validate minimum participants
        if len(participants) < 2:
            raise DiscussionValidationError(
                ["At least 2 participants are required for a discussion"]
            )

        # Validate all participants are real members
        known_names = [n.lower() for n in self._registry.list_names()]
        for name in participants:
            if name.lower() not in known_names:
                raise DiscussionValidationError(
                    [f"Unknown council member: '{name}'"]
                )

        # Validate proposal exists
        self._proposal_manager.get(proposal_id)

        effective_rounds = round_count or DEFAULT_DISCUSSION_ROUNDS
        if effective_rounds > MAX_DISCUSSION_ROUNDS:
            raise DiscussionValidationError(
                [
                    f"Round count {effective_rounds} exceeds maximum "
                    f"of {MAX_DISCUSSION_ROUNDS}"
                ]
            )

        record = DiscussionRecord.create(
            discussion_id=discussion_id,
            proposal_id=proposal_id,
            title=title,
            participants=participants,
            round_count=effective_rounds,
            metadata=metadata,
        )
        self._save(record)
        return record

    async def run_round(
        self,
        discussion_id: str,
    ) -> DiscussionRecord:
        """
        Run one discussion round where each participant speaks.

        Each participant sees the proposal details and all prior
        contributions, then adds their perspective.

        Raises:
            DiscussionNotFoundError: if the discussion doesn't exist.
            DiscussionStateError: if the discussion is closed or all
                rounds are complete.
        """
        record = self.get(discussion_id)

        if record.status != "open":
            raise DiscussionStateError(
                discussion_id, "Discussion is closed"
            )

        if record.current_round >= record.round_count:
            raise DiscussionStateError(
                discussion_id,
                f"All {record.round_count} rounds are complete",
            )

        # Load the proposal
        proposal = self._proposal_manager.get(record.proposal_id)

        round_number = record.current_round + 1
        new_contributions: list[DiscussionContribution] = []

        for name in record.participants:
            member = self._registry.get(name)

            # Build prompt with all prior contributions + new ones
            all_contributions = (
                list(record.contributions) + new_contributions
            )
            prompt = _build_discussion_prompt(
                member, proposal, all_contributions, round_number,
            )

            # Inject memory context if influence engine is configured
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    f"{proposal.title} {proposal.description}"
                )
                ctx = self._memory_influence.build_context(member.name, keywords)
                if ctx.formatted_text:
                    prompt = _build_discussion_prompt(
                        member, proposal, all_contributions, round_number,
                        memory_context_text=ctx.formatted_text,
                    )

            # Build API messages
            messages = [ChatMessage(role="user", content=prompt)]

            response = await self._api_client.chat(member, messages)

            contribution = DiscussionContribution.create(
                speaker=member.name,
                content=response.content,
                round_number=round_number,
                metadata={
                    "model": response.model,
                    "provider": response.provider,
                },
            )
            new_contributions.append(contribution)

            # Record to agent memory
            agent_mem = AgentMemory(member.name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=discussion_id,
                    event_type="discussion",
                    content=(
                        f"Discussed proposal '{proposal.title}' "
                        f"({proposal.id}) round {round_number}: "
                        f"{response.content[:200]}"
                    ),
                    source="discussion",
                )
            )

        # Update record with new contributions and incremented round
        all_contributions = list(record.contributions) + new_contributions
        record = DiscussionRecord(
            discussion_id=record.discussion_id,
            proposal_id=record.proposal_id,
            title=record.title,
            participants=list(record.participants),
            contributions=all_contributions,
            round_count=record.round_count,
            current_round=round_number,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )
        self._save(record)
        return record

    async def run_all_rounds(
        self,
        discussion_id: str,
        rounds: int | None = None,
    ) -> DiscussionRecord:
        """
        Run all remaining discussion rounds (or a custom number).

        Args:
            discussion_id: The discussion to run.
            rounds: Override the number of rounds to run. If None, runs
                all remaining rounds up to the configured round_count.

        Returns:
            The final DiscussionRecord with all contributions.

        Raises:
            DiscussionNotFoundError: if the discussion doesn't exist.
            DiscussionStateError: if the discussion is closed.
        """
        record = self.get(discussion_id)

        if record.status != "open":
            raise DiscussionStateError(
                discussion_id, "Discussion is closed"
            )

        remaining = record.round_count - record.current_round
        to_run = min(rounds, remaining) if rounds is not None else remaining

        for _ in range(to_run):
            record = await self.run_round(discussion_id)

        return record

    def close_discussion(
        self,
        discussion_id: str,
        summary: str = "",
    ) -> DiscussionRecord:
        """
        Close a discussion and persist summary to shared memory.

        Raises:
            DiscussionNotFoundError: if the discussion doesn't exist.
            DiscussionStateError: if the discussion is already closed.
        """
        record = self.get(discussion_id)

        if record.status != "open":
            raise DiscussionStateError(
                discussion_id, "Discussion is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)

        record = DiscussionRecord(
            discussion_id=record.discussion_id,
            proposal_id=record.proposal_id,
            title=record.title,
            participants=list(record.participants),
            contributions=list(record.contributions),
            round_count=record.round_count,
            current_round=record.current_round,
            status="closed",
            summary=final_summary,
            created_at=record.created_at,
            closed_at=now,
            metadata=dict(record.metadata),
        )
        self._save(record)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "discussion_closed",
            "discussion_id": record.discussion_id,
            "proposal_id": record.proposal_id,
            "title": record.title,
            "participants": record.participants,
            "rounds_completed": record.current_round,
            "contribution_count": len(record.contributions),
            "summary": final_summary,
            "closed_at": now,
        })

        self._shared_memory.append_history(
            f"### Discussion: {record.title} ({record.discussion_id})\n"
            f"**Proposal:** {record.proposal_id}\n"
            f"**Closed:** {now}\n"
            f"**Participants:** {', '.join(record.participants)}\n"
            f"**Rounds:** {record.current_round}/{record.round_count}\n\n"
            f"{final_summary}\n"
        )

        return record

    # ── Query ─────────────────────────────────────────────────

    def get(self, discussion_id: str) -> DiscussionRecord:
        """
        Load a discussion record by ID.

        Raises:
            DiscussionNotFoundError: if no discussion file exists.
        """
        filepath = self._filepath(discussion_id)
        if not filepath.exists():
            raise DiscussionNotFoundError(discussion_id)
        return self._load(filepath)

    def list_discussions(
        self,
        *,
        proposal_id: str | None = None,
        status: str | None = None,
        participant: str | None = None,
    ) -> list[DiscussionRecord]:
        """
        Return all discussions, optionally filtered.

        Args:
            proposal_id: Filter to discussions for this proposal.
            status: Filter by status (open/closed).
            participant: Filter to discussions including this member.
        """
        records: list[DiscussionRecord] = []
        for filepath in sorted(self._dir.glob("D-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if proposal_id is not None and rec.proposal_id != proposal_id:
                continue
            if status is not None and rec.status != status:
                continue
            if participant is not None:
                if participant.lower() not in [
                    p.lower() for p in rec.participants
                ]:
                    continue
            records.append(rec)
        return records

    def has_discussion(self, discussion_id: str) -> bool:
        """Check if a discussion record exists."""
        return self._filepath(discussion_id).exists()

    def get_contributions(
        self,
        discussion_id: str,
        *,
        speaker: str | None = None,
        round_number: int | None = None,
    ) -> list[DiscussionContribution]:
        """
        Get discussion contributions, optionally filtered.

        Raises:
            DiscussionNotFoundError: if no discussion exists.
        """
        record = self.get(discussion_id)
        results = list(record.contributions)
        if speaker is not None:
            speaker_lower = speaker.lower()
            results = [
                c for c in results if c.speaker.lower() == speaker_lower
            ]
        if round_number is not None:
            results = [
                c for c in results if c.round_number == round_number
            ]
        return results

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, discussion_id: str) -> Path:
        return self._dir / f"D-{discussion_id}.json"

    def _save(self, record: DiscussionRecord) -> None:
        payload = json.dumps(
            record.to_dict(), indent=2, ensure_ascii=False
        )
        atomic_write(self._filepath(record.discussion_id), payload + "\n")

    def _load(self, filepath: Path) -> DiscussionRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return DiscussionRecord.from_dict(data)

    def _generate_summary(self, record: DiscussionRecord) -> str:
        """Generate a default summary from discussion data."""
        participant_str = ", ".join(record.participants)
        contrib_count = len(record.contributions)
        unique_speakers = sorted(
            set(c.speaker for c in record.contributions)
        )

        parts = [
            f"Discussion '{record.title}' on proposal {record.proposal_id} "
            f"with {contrib_count} contributions across "
            f"{record.current_round} round(s).",
        ]
        parts.append(f"Participants: {participant_str}.")
        if unique_speakers:
            parts.append(
                f"Active speakers: {', '.join(unique_speakers)}."
            )
        return " ".join(parts)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("D-*.json")))
        return f"DiscussionManager(discussions={count}, dir={self._dir})"
