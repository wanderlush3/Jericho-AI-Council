"""
Jericho — Law System

Structured JSON format for world laws with lifecycle tracking.
Laws passed through the proposal/voting system are auto-created as drafts,
then activated to become part of the active legal framework.

Lifecycle:  draft → active ↔ archived
            (active and archived can toggle — laws may be reinstated)

Storage: one JSON file per law in ``data/laws/``, named ``LAW-XXXX.json``.
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
    LAWS_DIR,
    LAW_STATUSES,
)
from core.utils import atomic_write, make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class LawError(Exception):
    """Base exception for law-system errors."""


class LawNotFoundError(LawError):
    """Raised when a law ID is not found on disk."""

    def __init__(self, law_id: str) -> None:
        self.law_id = law_id
        super().__init__(f"Law not found: '{law_id}'")


class LawValidationError(LawError):
    """Raised when law data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class LawLifecycleError(LawError):
    """Raised when a status transition is not allowed."""

    def __init__(self, law_id: str, current: str, requested: str) -> None:
        self.law_id = law_id
        self.current_status = current
        self.requested_status = requested
        super().__init__(
            f"Cannot transition '{law_id}' from '{current}' to '{requested}'"
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived"},
    "archived": {"active"},  # laws can be reactivated
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class Law:
    """Immutable snapshot of a law loaded from (or about to be saved to) disk."""

    id: str
    title: str
    description: str
    author: str
    status: str = "draft"
    body: str = ""
    source_proposal_id: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Law:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            author=data["author"],
            status=data.get("status", "draft"),
            body=data.get("body", ""),
            source_proposal_id=data.get("source_proposal_id", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
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
        body: str = "",
        source_proposal_id: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Law:
        """Factory that auto-fills timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            title=title,
            description=description,
            author=author,
            status="draft",
            body=body,
            source_proposal_id=source_proposal_id,
            tags=tags or [],
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Law Manager ──────────────────────────────────────────────


class LawManager:
    """
    Filesystem-backed law store.

    Each law is stored as ``LAW-XXXX.json`` in the laws directory.

    Usage::

        mgr = LawManager()
        law = mgr.create("Trade Regulation Act", "Regulates inter-city trade",
                          author="Council")
        mgr.update_status(law.id, "active")
    """

    _ID_PATTERN = re.compile(r"^LAW-(\d{4})\.json$")

    def __init__(self, laws_dir: Path | None = None) -> None:
        self._dir = laws_dir or LAWS_DIR
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
        body: str = "",
        source_proposal_id: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Law:
        """
        Create a new law in *draft* status.

        Auto-generates a sequential ``LAW-XXXX`` ID.

        Raises:
            LawValidationError: if required fields are empty.
        """
        errors: list[str] = []
        if not title.strip():
            errors.append("Title must not be empty")
        if not description.strip():
            errors.append("Description must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")
        if errors:
            raise LawValidationError(errors)

        with self._id_lock:
            next_id = self._next_id()
            law = Law.create(
                id=next_id,
                title=title.strip(),
                description=description.strip(),
                author=author.strip(),
                body=body,
                source_proposal_id=source_proposal_id,
                tags=tags or [],
                metadata=metadata,
            )
            self._save(law)
        return law

    # ── Read ──────────────────────────────────────────────────

    def get(self, law_id: str) -> Law:
        """
        Load a law by ID.

        Raises:
            LawNotFoundError: if no file exists for that ID.
        """
        filepath = self._filepath(law_id)
        if not filepath.exists():
            raise LawNotFoundError(law_id)
        return self._load(filepath)

    def list_laws(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
        tag: str | None = None,
    ) -> list[Law]:
        """
        Return laws sorted by ID, with optional filters.
        """
        laws: list[Law] = []
        for filepath in sorted(self._dir.glob("LAW-*.json")):
            try:
                law = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and law.status != status:
                continue
            if author is not None and law.author.lower() != author.strip().lower():
                continue
            if tag is not None and tag.lower() not in [t.lower() for t in law.tags]:
                continue
            laws.append(law)
        return laws

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, law_id: str, new_status: str) -> Law:
        """
        Transition a law to *new_status*.

        Raises:
            LawNotFoundError: if law does not exist.
            LawLifecycleError: if the transition is invalid.
            LawValidationError: if *new_status* is not a known status.
        """
        if new_status not in LAW_STATUSES:
            raise LawValidationError(
                [f"Unknown status '{new_status}' — must be one of {LAW_STATUSES}"]
            )

        law = self.get(law_id)
        allowed = _VALID_TRANSITIONS.get(law.status, set())

        if new_status not in allowed:
            raise LawLifecycleError(law_id, law.status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            law, status=new_status, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Update Fields ─────────────────────────────────────────

    _MUTABLE_FIELDS = {
        "title", "description", "body", "tags", "metadata",
    }

    def update(self, law_id: str, **fields: Any) -> Law:
        """
        Update mutable fields on a law.

        Only ``title``, ``description``, ``body``, ``tags``, and
        ``metadata`` may be changed.  Bumps ``updated_at``.

        Raises:
            LawNotFoundError: if law does not exist.
            LawValidationError: if an immutable field is specified.
        """
        invalid = set(fields) - self._MUTABLE_FIELDS
        if invalid:
            raise LawValidationError(
                [f"Cannot update immutable field(s): {', '.join(sorted(invalid))}"]
            )

        law = self.get(law_id)

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(law, updated_at=now, **fields)
        self._save(updated)
        return updated

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, law_id: str) -> Path:
        return self._dir / f"{law_id}.json"

    def _save(self, law: Law) -> None:
        payload = json.dumps(law.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(law.id), payload + "\n")

    def _load(self, filepath: Path) -> Law:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return Law.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential LAW-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("LAW-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"LAW-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("LAW-*.json")))
        return f"LawManager(laws={count}, dir={self._dir})"
