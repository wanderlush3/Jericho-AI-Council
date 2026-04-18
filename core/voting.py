"""
Jericho — Voting Engine (F-006)

Cast votes, tally results, check quorum, apply approval threshold,
and enforce human veto power on council proposals.

Storage: one JSON file per vote record in ``data/votes/``, named
``V-<proposal_id>.json``  (e.g. ``V-P-0001.json``).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    APPROVAL_THRESHOLD,
    QUORUM_MINIMUM,
    VOTE_OPTIONS,
    VOTES_DIR,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class VotingError(Exception):
    """Base exception for voting-engine errors."""


class VoteNotFoundError(VotingError):
    """Raised when no vote record exists for a proposal."""

    def __init__(self, proposal_id: str) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"No vote record for proposal '{proposal_id}'")


class VotingValidationError(VotingError):
    """Raised when vote data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class VotingStateError(VotingError):
    """Raised when an operation conflicts with current voting state."""

    def __init__(self, proposal_id: str, message: str) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"Voting state error for '{proposal_id}': {message}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class Vote:
    """A single vote cast by a council member."""

    voter: str
    choice: str            # for / against / abstain
    reason: str = ""
    timestamp: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Vote:
        return cls(
            voter=data["voter"],
            choice=data["choice"],
            reason=data.get("reason", ""),
            timestamp=data.get("timestamp", ""),
            weight=data.get("weight", 1.0),
        )

    @classmethod
    def create(
        cls,
        voter: str,
        choice: str,
        reason: str = "",
        weight: float = 1.0,
    ) -> Vote:
        """Factory that auto-fills the timestamp and validates the choice."""
        if choice not in VOTE_OPTIONS:
            raise VotingValidationError(
                [f"Invalid choice '{choice}' — must be one of {VOTE_OPTIONS}"]
            )
        if weight <= 0:
            raise VotingValidationError(
                [f"Vote weight must be positive, got {weight}"]
            )
        return cls(
            voter=voter,
            choice=choice,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            weight=weight,
        )


@dataclass(frozen=True)
class VoteTally:
    """Immutable tally of votes on a proposal."""

    total_votes: int
    votes_for: int
    votes_against: int
    votes_abstain: int
    weighted_for: float
    weighted_against: float
    weighted_abstain: float
    approval_rate: float         # weighted_for / (weighted_for + weighted_against)
    quorum_met: bool
    threshold_met: bool
    approved: bool               # quorum_met AND threshold_met AND not vetoed
    vetoed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VoteRecord:
    """
    Full vote record for a single proposal.

    Stored as one JSON file per proposal in the votes directory.
    """

    proposal_id: str
    status: str = "open"          # open / closed
    votes: list[Vote] = field(default_factory=list)
    vetoed: bool = False
    veto_reason: str = ""
    veto_timestamp: str = ""
    opened_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoteRecord:
        votes = [Vote.from_dict(v) for v in data.get("votes", [])]
        return cls(
            proposal_id=data["proposal_id"],
            status=data.get("status", "open"),
            votes=votes,
            vetoed=data.get("vetoed", False),
            veto_reason=data.get("veto_reason", ""),
            veto_timestamp=data.get("veto_timestamp", ""),
            opened_at=data.get("opened_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        proposal_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> VoteRecord:
        """Factory that auto-fills the opened_at timestamp."""
        return cls(
            proposal_id=proposal_id,
            status="open",
            votes=[],
            vetoed=False,
            veto_reason="",
            veto_timestamp="",
            opened_at=datetime.now(timezone.utc).isoformat(),
            closed_at="",
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




# ─── Voting Engine ─────────────────────────────────────────────


class VotingEngine:
    """
    Filesystem-backed voting engine for council proposals.

    Each proposal's votes are stored as ``V-<proposal_id>.json`` in the
    votes directory (e.g. ``V-P-0001.json``).

    Usage::

        engine = VotingEngine()
        engine.open_voting("P-0001")
        engine.cast_vote("P-0001", Vote.create("Sage", "for", "Well argued"))
        engine.cast_vote("P-0001", Vote.create("Logic", "against", "Needs work"))
        tally = engine.tally("P-0001")
        result = engine.close_voting("P-0001")
    """

    def __init__(
        self,
        votes_dir: Path | None = None,
        quorum: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self._dir = votes_dir or VOTES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._quorum = quorum if quorum is not None else QUORUM_MINIMUM
        self._threshold = threshold if threshold is not None else APPROVAL_THRESHOLD

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def quorum(self) -> int:
        return self._quorum

    @property
    def threshold(self) -> float:
        return self._threshold

    # ── Open Voting ───────────────────────────────────────────

    def open_voting(
        self,
        proposal_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> VoteRecord:
        """
        Open voting on a proposal.

        Creates a new vote record file.

        Raises:
            VotingValidationError: if proposal_id is empty.
            VotingStateError: if voting is already open/closed for this proposal.
        """
        if not proposal_id.strip():
            raise VotingValidationError(["Proposal ID must not be empty"])

        filepath = self._filepath(proposal_id)
        if filepath.exists():
            existing = self._load(filepath)
            raise VotingStateError(
                proposal_id,
                f"Voting already exists with status '{existing.status}'",
            )

        record = VoteRecord.create(proposal_id, metadata=metadata)
        self._save(record)
        return record

    # ── Cast Vote ─────────────────────────────────────────────

    def cast_vote(self, proposal_id: str, vote: Vote) -> VoteRecord:
        """
        Cast a vote on a proposal.

        Raises:
            VoteNotFoundError: if no vote record exists for the proposal.
            VotingStateError: if voting is closed.
            VotingValidationError: if the voter has already voted.
        """
        record = self.get(proposal_id)

        if record.status != "open":
            raise VotingStateError(
                proposal_id, "Voting is closed — cannot cast new votes"
            )

        existing_voters = {v.voter.lower() for v in record.votes}
        if vote.voter.lower() in existing_voters:
            raise VotingValidationError(
                [f"'{vote.voter}' has already voted on proposal '{proposal_id}'"]
            )

        new_votes = list(record.votes) + [vote]
        updated = dataclasses.replace(record, votes=new_votes)
        self._save(updated)
        return updated

    # ── Tally ─────────────────────────────────────────────────

    def tally(self, proposal_id: str) -> VoteTally:
        """
        Compute the current vote tally for a proposal.

        Raises:
            VoteNotFoundError: if no vote record exists for the proposal.
        """
        record = self.get(proposal_id)
        return self._compute_tally(record)

    def _compute_tally(self, record: VoteRecord) -> VoteTally:
        """Internal tally computation from a VoteRecord."""
        votes_for = sum(1 for v in record.votes if v.choice == "for")
        votes_against = sum(1 for v in record.votes if v.choice == "against")
        votes_abstain = sum(1 for v in record.votes if v.choice == "abstain")

        weighted_for = sum(v.weight for v in record.votes if v.choice == "for")
        weighted_against = sum(v.weight for v in record.votes if v.choice == "against")
        weighted_abstain = sum(v.weight for v in record.votes if v.choice == "abstain")

        total_decisive = weighted_for + weighted_against
        approval_rate = (weighted_for / total_decisive) if total_decisive > 0 else 0.0

        quorum_met = len(record.votes) >= self._quorum
        threshold_met = approval_rate >= self._threshold
        approved = quorum_met and threshold_met and not record.vetoed

        return VoteTally(
            total_votes=len(record.votes),
            votes_for=votes_for,
            votes_against=votes_against,
            votes_abstain=votes_abstain,
            weighted_for=weighted_for,
            weighted_against=weighted_against,
            weighted_abstain=weighted_abstain,
            approval_rate=round(approval_rate, 4),
            quorum_met=quorum_met,
            threshold_met=threshold_met,
            approved=approved,
            vetoed=record.vetoed,
        )

    # ── Close Voting ──────────────────────────────────────────

    def close_voting(self, proposal_id: str) -> VoteRecord:
        """
        Close voting on a proposal.

        Raises:
            VoteNotFoundError: if no vote record exists for the proposal.
            VotingStateError: if voting is already closed.
        """
        record = self.get(proposal_id)

        if record.status != "open":
            raise VotingStateError(
                proposal_id, "Voting is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            record, status="closed", closed_at=now,
        )
        self._save(updated)
        return updated

    # ── Human Veto ────────────────────────────────────────────

    def veto(self, proposal_id: str, reason: str = "") -> VoteRecord:
        """
        Apply a human veto to a proposal's vote.

        The human veto overrides all votes — a vetoed proposal cannot be
        approved regardless of vote tallies.

        Raises:
            VoteNotFoundError: if no vote record exists for the proposal.
            VotingStateError: if the proposal is already vetoed.
        """
        record = self.get(proposal_id)

        if record.vetoed:
            raise VotingStateError(
                proposal_id, "Proposal is already vetoed"
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            record, vetoed=True, veto_reason=reason, veto_timestamp=now,
        )
        self._save(updated)
        return updated

    def lift_veto(self, proposal_id: str) -> VoteRecord:
        """
        Remove a human veto from a proposal's vote.

        Raises:
            VoteNotFoundError: if no vote record exists for the proposal.
            VotingStateError: if the proposal is not vetoed.
        """
        record = self.get(proposal_id)

        if not record.vetoed:
            raise VotingStateError(
                proposal_id, "Proposal is not vetoed"
            )

        updated = dataclasses.replace(
            record, vetoed=False, veto_reason="", veto_timestamp="",
        )
        self._save(updated)
        return updated

    # ── Read ──────────────────────────────────────────────────

    def get(self, proposal_id: str) -> VoteRecord:
        """
        Load a vote record by proposal ID.

        Raises:
            VoteNotFoundError: if no record exists.
        """
        filepath = self._filepath(proposal_id)
        if not filepath.exists():
            raise VoteNotFoundError(proposal_id)
        return self._load(filepath)

    def list_records(
        self,
        *,
        status: str | None = None,
    ) -> list[VoteRecord]:
        """
        Return all vote records, optionally filtered by status.
        """
        records: list[VoteRecord] = []
        for filepath in sorted(self._dir.glob("V-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and rec.status != status:
                continue
            records.append(rec)
        return records

    def has_record(self, proposal_id: str) -> bool:
        """Check if a vote record exists for the given proposal."""
        return self._filepath(proposal_id).exists()

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, proposal_id: str) -> Path:
        return self._dir / f"V-{proposal_id}.json"

    def _save(self, record: VoteRecord) -> None:
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(record.proposal_id), payload + "\n")

    def _load(self, filepath: Path) -> VoteRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return VoteRecord.from_dict(data)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("V-*.json")))
        return f"VotingEngine(records={count}, quorum={self._quorum}, threshold={self._threshold}, dir={self._dir})"


# ─── Vote Prompt Builder / Parser (F-064) ──────────────────────
# Extracted from core/routes/proposals.py — pure business logic for
# formatting LLM vote prompts and parsing structured vote responses.


def build_vote_prompt(
    proposal,
    member,
    discussion_context: str = "",
    memory_block: str = "",
) -> str:
    """Build an LLM vote prompt for a council member.

    Args:
        proposal: The proposal being voted on (needs .title, .id,
            .category, .author, .description).
        member: The council member casting the vote (needs .name, .role).
        discussion_context: Pre-formatted discussion summary text.
        memory_block: Pre-formatted memory context text.

    Returns:
        Formatted prompt string.
    """
    return (
        f"## Vote Required: {proposal.title}\n"
        f"**Proposal ID:** {proposal.id}\n"
        f"**Category:** {proposal.category}\n"
        f"**Author:** {proposal.author}\n"
        f"**Description:** {proposal.description}\n"
        f"{discussion_context}"
        f"{memory_block}\n\n"
        f"---\n"
        f"You are **{member.name}** ({member.role}). "
        f"You must now vote on this proposal.\n\n"
        f"Respond with EXACTLY this format (first line is your vote, "
        f"rest is your reasoning):\n"
        f"VOTE: for\n"
        f"or\n"
        f"VOTE: against\n"
        f"or\n"
        f"VOTE: abstain\n\n"
        f"Then explain your reasoning briefly."
    )


def parse_vote_response(content: str) -> tuple[str, str]:
    """Parse a structured vote response from an LLM.

    Expects the response to contain ``VOTE: for|against|abstain``
    followed by reasoning text.

    Args:
        content: Raw LLM response text.

    Returns:
        Tuple of ``(choice, reason)`` where choice is one of
        ``"for"``, ``"against"``, or ``"abstain"``.
    """
    import re

    choice = "abstain"  # default
    reason = content
    content_lower = content.lower()

    if "vote: for" in content_lower or "vote:for" in content_lower:
        choice = "for"
    elif "vote: against" in content_lower or "vote:against" in content_lower:
        choice = "against"
    elif "vote: abstain" in content_lower or "vote:abstain" in content_lower:
        choice = "abstain"

    # Extract reason (everything after the VOTE: line)
    reason_match = re.split(
        r"VOTE:\s*\w+\s*\n?", content, flags=re.IGNORECASE,
    )
    if len(reason_match) > 1:
        reason = reason_match[-1].strip()

    return choice, reason
