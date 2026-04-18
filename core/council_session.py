"""
Jericho — Council Session Orchestrator

Open-ended council deliberation sessions that can optionally be
handed off to the Proposal system with auto-populated fields.

Storage:
    Each session gets a JSON file in ``data/council_sessions/``
    named ``CS-XXXX.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import COUNCIL_SESSIONS_DIR
from core.discussion import DiscussionContribution
from core.utils import atomic_write, make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class CouncilSessionError(Exception):
    """Base exception for council-session errors."""


class CouncilSessionNotFoundError(CouncilSessionError):
    """Raised when a session record cannot be found."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Council session not found: '{session_id}'")


class CouncilSessionValidationError(CouncilSessionError):
    """Raised when session data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class CouncilSessionStateError(CouncilSessionError):
    """Raised when an operation conflicts with current session state."""

    def __init__(self, session_id: str, message: str) -> None:
        self.session_id = session_id
        super().__init__(
            f"Session state error for '{session_id}': {message}"
        )


# ─── Data Model ────────────────────────────────────────────────


@dataclass(frozen=True)
class CouncilSessionRecord:
    """Persistent record of a council deliberation session."""

    session_id: str
    title: str
    topic: str
    agenda: str = ""
    participants: list[str] = field(default_factory=list)
    contributions: list[DiscussionContribution] = field(default_factory=list)
    round_count: int = 5
    current_round: int = 0
    status: str = "open"  # open / closed
    summary: str = ""
    created_at: str = ""
    closed_at: str = ""
    proposed_category: str = "governance"
    proposed_title: str = ""
    proposed_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["contributions"] = [c.to_dict() for c in self.contributions]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CouncilSessionRecord:
        contributions = [
            DiscussionContribution.from_dict(c)
            for c in data.get("contributions", [])
        ]
        return cls(
            session_id=data["session_id"],
            title=data["title"],
            topic=data["topic"],
            agenda=data.get("agenda", ""),
            participants=list(data.get("participants", [])),
            contributions=contributions,
            round_count=data.get("round_count", 5),
            current_round=data.get("current_round", 0),
            status=data.get("status", "open"),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            closed_at=data.get("closed_at", ""),
            proposed_category=data.get("proposed_category", "governance"),
            proposed_title=data.get("proposed_title", ""),
            proposed_description=data.get("proposed_description", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        session_id: str,
        title: str,
        topic: str,
        *,
        agenda: str = "",
        participants: list[str] | None = None,
        round_count: int = 5,
        proposed_category: str = "governance",
        metadata: dict[str, Any] | None = None,
    ) -> CouncilSessionRecord:
        """Factory that auto-fills created_at."""
        if not session_id.strip():
            raise CouncilSessionValidationError(
                ["Session ID must not be empty"]
            )
        if not title.strip():
            raise CouncilSessionValidationError(["Title must not be empty"])
        if not topic.strip():
            raise CouncilSessionValidationError(["Topic must not be empty"])
        return cls(
            session_id=session_id.strip(),
            title=title.strip(),
            topic=topic.strip(),
            agenda=agenda.strip(),
            participants=participants or [],
            contributions=[],
            round_count=round_count,
            current_round=0,
            status="open",
            summary="",
            created_at=datetime.now(timezone.utc).isoformat(),
            closed_at="",
            proposed_category=proposed_category,
            proposed_title=title.strip(),
            proposed_description=topic.strip(),
            metadata=metadata or {},
        )


# ─── Session Manager ──────────────────────────────────────────


class CouncilSessionManager:
    """
    Filesystem-backed council session store.

    Each session is stored as ``CS-XXXX.json`` in the sessions directory.

    Usage::

        mgr = CouncilSessionManager()
        session = mgr.create_session("Ethics Discussion", "Discuss ethical AI boundaries")
        session = mgr.get("CS-0001")
        mgr.close_session("CS-0001")
        proposal_data = mgr.build_proposal_data("CS-0001")
    """

    _ID_PATTERN = re.compile(r"^CS-(\d{4})\.json$")

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._dir = sessions_dir or COUNCIL_SESSIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Create ────────────────────────────────────────────────

    def create_session(
        self,
        title: str,
        topic: str,
        *,
        agenda: str = "",
        participants: list[str] | None = None,
        round_count: int = 5,
        proposed_category: str = "governance",
        metadata: dict[str, Any] | None = None,
    ) -> CouncilSessionRecord:
        """Create a new council session in 'open' status."""
        errors: list[str] = []
        if not title.strip():
            errors.append("Title must not be empty")
        if not topic.strip():
            errors.append("Topic must not be empty")
        if errors:
            raise CouncilSessionValidationError(errors)

        with self._id_lock:
            next_id = self._next_id()
            session = CouncilSessionRecord.create(
                session_id=next_id,
                title=title,
                topic=topic,
                agenda=agenda,
                participants=participants,
                round_count=round_count,
                proposed_category=proposed_category,
                metadata=metadata,
            )
            self._save(session)
        return session

    # ── Read ──────────────────────────────────────────────────

    def get(self, session_id: str) -> CouncilSessionRecord:
        """Load a session by ID."""
        filepath = self._filepath(session_id)
        if not filepath.exists():
            raise CouncilSessionNotFoundError(session_id)
        return self._load(filepath)

    def list_sessions(
        self,
        *,
        status: str | None = None,
    ) -> list[CouncilSessionRecord]:
        """Return all sessions, optionally filtered by status."""
        records: list[CouncilSessionRecord] = []
        for filepath in sorted(self._dir.glob("CS-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            if status is not None and rec.status != status:
                continue
            records.append(rec)
        return records

    # ── Close ─────────────────────────────────────────────────

    def close_session(
        self,
        session_id: str,
        summary: str = "",
    ) -> CouncilSessionRecord:
        """Close a session and persist summary."""
        record = self.get(session_id)

        if record.status != "open":
            raise CouncilSessionStateError(
                session_id, "Session is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)

        record = CouncilSessionRecord(
            session_id=record.session_id,
            title=record.title,
            topic=record.topic,
            agenda=record.agenda,
            participants=list(record.participants),
            contributions=list(record.contributions),
            round_count=record.round_count,
            current_round=record.current_round,
            status="closed",
            summary=final_summary,
            created_at=record.created_at,
            closed_at=now,
            proposed_category=record.proposed_category,
            proposed_title=record.proposed_title,
            proposed_description=record.proposed_description,
            metadata=dict(record.metadata),
        )
        self._save(record)
        return record

    # ── Update (for adding contributions) ─────────────────────

    def save(self, record: CouncilSessionRecord) -> None:
        """Public save method for external callers (SSE handler)."""
        self._save(record)

    # ── Proposal Handoff ──────────────────────────────────────

    def build_proposal_data(
        self,
        session_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """
        Build data for creating a proposal from this session.

        Returns a dict suitable for passing to ProposalManager.create().
        """
        record = self.get(session_id)

        if record.status != "closed":
            raise CouncilSessionStateError(
                session_id,
                "Session must be closed before handoff to proposal",
            )

        # Build body from contributions
        body_parts = [f"## Council Session: {record.title}\n"]
        body_parts.append(f"**Topic:** {record.topic}\n")
        if record.agenda:
            body_parts.append(f"**Agenda:** {record.agenda}\n")
        if record.summary:
            body_parts.append(f"\n### Summary\n{record.summary}\n")
        if record.contributions:
            body_parts.append(f"\n### Discussion ({len(record.contributions)} contributions)\n")
            for c in record.contributions[-20:]:
                body_parts.append(
                    f"**{c.speaker}** (round {c.round_number}): "
                    f"{c.content[:300]}\n"
                )

        return {
            "title": title or record.proposed_title or record.title,
            "description": description or record.proposed_description or record.topic,
            "category": category or record.proposed_category,
            "body": "\n".join(body_parts),
            "metadata": {
                "source_session": session_id,
            },
        }

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _save(self, record: CouncilSessionRecord) -> None:
        payload = json.dumps(
            record.to_dict(), indent=2, ensure_ascii=False
        )
        atomic_write(self._filepath(record.session_id), payload + "\n")

    def _load(self, filepath: Path) -> CouncilSessionRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return CouncilSessionRecord.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential CS-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("CS-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"CS-{max_num + 1:04d}"

    def _generate_summary(self, record: CouncilSessionRecord) -> str:
        """Generate a default summary from session data."""
        participant_str = ", ".join(record.participants)
        contrib_count = len(record.contributions)
        unique_speakers = sorted(
            set(c.speaker for c in record.contributions)
        )

        parts = [
            f"Council session '{record.title}' on topic '{record.topic}' "
            f"with {contrib_count} contributions across "
            f"{record.current_round} round(s).",
        ]
        if participant_str:
            parts.append(f"Participants: {participant_str}.")
        if unique_speakers:
            parts.append(
                f"Active speakers: {', '.join(unique_speakers)}."
            )
        return " ".join(parts)

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("CS-*.json")))
        return f"CouncilSessionManager(sessions={count}, dir={self._dir})"
