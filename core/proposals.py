"""
Jericho — Proposal System (F-005)

Create, list, review proposals with structured format and lifecycle tracking.

Lifecycle:  draft → open → under_review → decided
            (any non-decided status may also → withdrawn)

Storage: one JSON file per proposal in ``data/proposals/``, named ``P-XXXX.json``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    PROPOSALS_DIR,
    PROPOSAL_CATEGORIES,
    PROPOSAL_STATUSES,
    REVIEW_STANCES,
)
from core.utils import atomic_write, make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class ProposalError(Exception):
    """Base exception for proposal-system errors."""


class ProposalNotFoundError(ProposalError):
    """Raised when a proposal ID is not found on disk."""

    def __init__(self, proposal_id: str) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"Proposal not found: '{proposal_id}'")


class ProposalValidationError(ProposalError):
    """Raised when proposal data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class ProposalLifecycleError(ProposalError):
    """Raised when a status transition is not allowed."""

    def __init__(self, proposal_id: str, current: str, requested: str) -> None:
        self.proposal_id = proposal_id
        self.current_status = current
        self.requested_status = requested
        super().__init__(
            f"Cannot transition '{proposal_id}' from '{current}' to '{requested}'"
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"open", "withdrawn"},
    "open": {"under_review", "open_to_review", "withdrawn"},
    "open_to_review": {"under_review", "decided", "withdrawn"},
    "under_review": {"decided", "withdrawn"},
    "decided": set(),       # terminal
    "withdrawn": set(),     # terminal
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class Review:
    """A single review left by a council member on a proposal."""

    reviewer: str
    stance: str          # support / oppose / neutral
    comment: str
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Review:
        return cls(
            reviewer=data["reviewer"],
            stance=data["stance"],
            comment=data["comment"],
            timestamp=data.get("timestamp", ""),
        )

    @classmethod
    def create(
        cls,
        reviewer: str,
        stance: str,
        comment: str,
    ) -> Review:
        """Factory that auto-fills the timestamp."""
        if stance not in REVIEW_STANCES:
            raise ProposalValidationError(
                [f"Invalid stance '{stance}' — must be one of {REVIEW_STANCES}"]
            )
        return cls(
            reviewer=reviewer,
            stance=stance,
            comment=comment,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True)
class Proposal:
    """Immutable snapshot of a proposal loaded from (or about to be saved to) disk."""

    id: str
    title: str
    description: str
    author: str
    category: str
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""
    body: str = ""
    reviews: list[Review] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Reviews are already dicts via asdict; just keep the structure.
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Proposal:
        reviews = [Review.from_dict(r) for r in data.get("reviews", [])]
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            author=data["author"],
            category=data["category"],
            status=data.get("status", "draft"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            body=data.get("body", ""),
            reviews=reviews,
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        title: str,
        description: str,
        author: str,
        category: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Proposal:
        """Factory that auto-fills timestamps and validates category."""
        if category not in PROPOSAL_CATEGORIES:
            raise ProposalValidationError(
                [f"Invalid category '{category}' — must be one of {PROPOSAL_CATEGORIES}"]
            )
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            title=title,
            description=description,
            author=author,
            category=category,
            status="draft",
            created_at=now,
            updated_at=now,
            body=body,
            reviews=[],
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




# ─── Proposal Manager ─────────────────────────────────────────


class ProposalManager:
    """
    Filesystem-backed proposal store.

    Each proposal is stored as ``P-XXXX.json`` in the proposals directory.

    Usage::

        mgr = ProposalManager()
        proposal = mgr.create("Ethics Update", "Expand ethical constraints",
                              author="Sage", category="ethics")
        mgr.update_status(proposal.id, "open")
        mgr.add_review(proposal.id, Review.create("Logic", "support", "Well reasoned"))
    """

    _ID_PATTERN = re.compile(r"^P-(\d{4})\.json$")

    def __init__(self, proposals_dir: Path | None = None) -> None:
        self._dir = proposals_dir or PROPOSALS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Create ────────────────────────────────────────────────

    def create(
        self,
        title: str,
        description: str,
        *,
        author: str,
        category: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Proposal:
        """
        Create a new proposal in *draft* status.

        Auto-generates a sequential ``P-XXXX`` ID.

        Raises:
            ProposalValidationError: if required fields are empty or category invalid.
        """
        errors: list[str] = []
        if not title.strip():
            errors.append("Title must not be empty")
        if not description.strip():
            errors.append("Description must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")
        if errors:
            raise ProposalValidationError(errors)

        with self._id_lock:
            next_id = self._next_id()
            proposal = Proposal.create(
                id=next_id,
                title=title.strip(),
                description=description.strip(),
                author=author.strip(),
                category=category,
                body=body,
                metadata=metadata,
            )
            self._save(proposal)
        return proposal

    # ── Read ──────────────────────────────────────────────────

    def get(self, proposal_id: str) -> Proposal:
        """
        Load a proposal by ID.

        Raises:
            ProposalNotFoundError: if no file exists for that ID.
        """
        filepath = self._filepath(proposal_id)
        if not filepath.exists():
            raise ProposalNotFoundError(proposal_id)
        return self._load(filepath)

    def list_proposals(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        author: str | None = None,
    ) -> list[Proposal]:
        """
        Return proposals sorted by ID, with optional filters.
        """
        proposals: list[Proposal] = []
        for filepath in sorted(self._dir.glob("P-*.json")):
            try:
                p = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and p.status != status:
                continue
            if category is not None and p.category != category:
                continue
            if author is not None and p.author.lower() != author.strip().lower():
                continue
            proposals.append(p)
        return proposals

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, proposal_id: str, new_status: str) -> Proposal:
        """
        Transition a proposal to *new_status*.

        Raises:
            ProposalNotFoundError: if proposal does not exist.
            ProposalLifecycleError: if the transition is invalid.
            ProposalValidationError: if *new_status* is not a known status.
        """
        if new_status not in PROPOSAL_STATUSES:
            raise ProposalValidationError(
                [f"Unknown status '{new_status}' — must be one of {PROPOSAL_STATUSES}"]
            )

        proposal = self.get(proposal_id)
        allowed = _VALID_TRANSITIONS.get(proposal.status, set())

        if new_status not in allowed:
            raise ProposalLifecycleError(proposal_id, proposal.status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            proposal, status=new_status, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Reviews ───────────────────────────────────────────────

    def add_review(self, proposal_id: str, review: Review) -> Proposal:
        """
        Append a review to a proposal.

        Raises:
            ProposalNotFoundError: if proposal does not exist.
            ProposalLifecycleError: if proposal is not in 'open' or 'under_review' status.
            ProposalValidationError: if reviewer has already reviewed.
        """
        proposal = self.get(proposal_id)

        if proposal.status not in ("open", "under_review"):
            raise ProposalLifecycleError(
                proposal_id, proposal.status, f"add_review (requires open/under_review)"
            )

        existing_reviewers = {r.reviewer.lower() for r in proposal.reviews}
        if review.reviewer.lower() in existing_reviewers:
            raise ProposalValidationError(
                [f"'{review.reviewer}' has already reviewed proposal '{proposal_id}'"]
            )

        now = datetime.now(timezone.utc).isoformat()
        new_reviews = list(proposal.reviews) + [review]
        updated = dataclasses.replace(
            proposal, reviews=new_reviews, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Update Fields ─────────────────────────────────────────

    _MUTABLE_FIELDS = {"title", "description", "body", "category", "metadata"}

    def update(self, proposal_id: str, **fields: Any) -> Proposal:
        """
        Update mutable fields on a proposal.

        Only ``title``, ``description``, ``body``, ``category``, and
        ``metadata`` may be changed.  Bumps ``updated_at``.

        Raises:
            ProposalNotFoundError: if proposal does not exist.
            ProposalValidationError: if an immutable field is specified
                or category is invalid.
        """
        invalid = set(fields) - self._MUTABLE_FIELDS
        if invalid:
            raise ProposalValidationError(
                [f"Cannot update immutable field(s): {', '.join(sorted(invalid))}"]
            )

        proposal = self.get(proposal_id)

        if "category" in fields and fields["category"] not in PROPOSAL_CATEGORIES:
            raise ProposalValidationError(
                [f"Invalid category '{fields['category']}' — must be one of {PROPOSAL_CATEGORIES}"]
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(proposal, updated_at=now, **fields)
        self._save(updated)
        return updated

    # ── Withdraw ──────────────────────────────────────────────

    def withdraw(self, proposal_id: str, author: str) -> Proposal:
        """
        Withdraw a proposal.  Only the original author may withdraw.

        Raises:
            ProposalNotFoundError: if proposal does not exist.
            ProposalValidationError: if requester is not the author.
            ProposalLifecycleError: if proposal is in a terminal state.
        """
        proposal = self.get(proposal_id)

        if proposal.author.lower() != author.strip().lower():
            raise ProposalValidationError(
                [f"Only the author ('{proposal.author}') can withdraw this proposal"]
            )

        return self.update_status(proposal_id, "withdrawn")

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, proposal_id: str) -> Path:
        return self._dir / f"{proposal_id}.json"

    def _save(self, proposal: Proposal) -> None:
        payload = json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(proposal.id), payload + "\n")

    def _load(self, filepath: Path) -> Proposal:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return Proposal.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential P-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("P-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"P-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("P-*.json")))
        return f"ProposalManager(proposals={count}, dir={self._dir})"
