"""
Jericho — Memory System (F-004)

Per-agent read/write memory with core beliefs, session logs (JSONL),
and shared council memory for decisions and narrative history.

Architecture rule: the orchestrator writes files; agents respond with
structured text.  All I/O is synchronous — filesystem ops don't need async.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import MEMORIES_DIR


# ─── Exceptions ────────────────────────────────────────────────


class MemoryError(Exception):
    """Base exception for memory-system errors."""


class MemoryCorruptionError(MemoryError):
    """Raised when a memory file contains invalid data."""

    def __init__(self, filepath: Path, reason: str) -> None:
        self.filepath = filepath
        self.reason = reason
        super().__init__(f"Corrupt memory file {filepath.name}: {reason}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class MemoryEntry:
    """A single event recorded during a council session."""

    timestamp: str
    session_id: str
    event_type: str
    content: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            timestamp=data["timestamp"],
            session_id=data["session_id"],
            event_type=data["event_type"],
            content=data["content"],
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        session_id: str,
        event_type: str,
        content: str,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Factory that auto-fills the timestamp."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            event_type=event_type,
            content=content,
            source=source,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class CoreBelief:
    """A persistent value or stance held by a council member."""

    topic: str
    content: str
    added_timestamp: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> CoreBelief:
        return cls(
            topic=data["topic"],
            content=data["content"],
            added_timestamp=data.get("added_timestamp", ""),
            source=data.get("source", ""),
        )

    @classmethod
    def create(
        cls,
        topic: str,
        content: str,
        source: str = "",
    ) -> CoreBelief:
        """Factory that auto-fills the timestamp."""
        return cls(
            topic=topic,
            content=content,
            added_timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
        )


# ─── Helpers ───────────────────────────────────────────────────


def _atomic_write(filepath: Path, content: str) -> None:
    """Write *content* to *filepath* atomically via temp-file + rename."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent, suffix=".tmp", prefix=filepath.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # On Windows, os.replace handles cross-device atomicity.
        os.replace(tmp_path, filepath)
    except BaseException:
        # Clean up the temp file on failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_append(filepath: Path, line: str) -> None:
    """Append a single line to *filepath* (creates file if missing)."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line if line.endswith("\n") else line + "\n")


# ─── Agent Memory ─────────────────────────────────────────────


class AgentMemory:
    """
    Per-member memory store.

    File layout inside ``data/memories/<member_name>/``::

        core_beliefs.json   — JSON list of CoreBelief dicts
        session_log.jsonl   — one MemoryEntry JSON-object per line, append-only

    Usage::

        mem = AgentMemory("sage")
        mem.write_core_belief(CoreBelief.create("safety", "Safety is paramount"))
        beliefs = mem.read_core_beliefs()
    """

    BELIEFS_FILE = "core_beliefs.json"
    SESSION_LOG_FILE = "session_log.jsonl"

    def __init__(
        self,
        member_name: str,
        memories_dir: Path | None = None,
    ) -> None:
        self._name = member_name.strip().lower()
        base = memories_dir or MEMORIES_DIR
        self._dir = base / self._name
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def beliefs_path(self) -> Path:
        return self._dir / self.BELIEFS_FILE

    @property
    def session_log_path(self) -> Path:
        return self._dir / self.SESSION_LOG_FILE

    # ── Core Beliefs ──────────────────────────────────────────

    def read_core_beliefs(self) -> list[CoreBelief]:
        """Return all core beliefs.  Empty list if file is missing or empty."""
        if not self.beliefs_path.exists():
            return []
        text = self.beliefs_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MemoryCorruptionError(self.beliefs_path, str(exc)) from exc
        if not isinstance(raw, list):
            raise MemoryCorruptionError(
                self.beliefs_path, f"Expected JSON array, got {type(raw).__name__}"
            )
        return [CoreBelief.from_dict(item) for item in raw]

    def write_core_belief(self, belief: CoreBelief) -> None:
        """Append a core belief (or overwrite if same topic exists)."""
        beliefs = self.read_core_beliefs()
        # Replace existing belief with same topic.
        beliefs = [b for b in beliefs if b.topic != belief.topic]
        beliefs.append(belief)
        self._save_beliefs(beliefs)

    def remove_core_belief(self, topic: str) -> bool:
        """Remove a belief by topic.  Returns True if removed, False if not found."""
        beliefs = self.read_core_beliefs()
        filtered = [b for b in beliefs if b.topic != topic]
        if len(filtered) == len(beliefs):
            return False
        self._save_beliefs(filtered)
        return True

    def _save_beliefs(self, beliefs: list[CoreBelief]) -> None:
        payload = json.dumps(
            [b.to_dict() for b in beliefs], indent=2, ensure_ascii=False
        )
        _atomic_write(self.beliefs_path, payload + "\n")

    # ── Session Log ───────────────────────────────────────────

    def read_session_log(
        self, session_id: str | None = None
    ) -> list[MemoryEntry]:
        """
        Read stored session events.

        Args:
            session_id: If provided, return only entries for that session.
        """
        if not self.session_log_path.exists():
            return []
        entries: list[MemoryEntry] = []
        for lineno, line in enumerate(
            self.session_log_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    self.session_log_path,
                    f"Line {lineno}: {exc}",
                ) from exc
            entry = MemoryEntry.from_dict(data)
            if session_id is None or entry.session_id == session_id:
                entries.append(entry)
        return entries

    def append_session_event(self, entry: MemoryEntry) -> None:
        """Append a single event to the session log (JSONL)."""
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        _atomic_append(self.session_log_path, line)

    # ── Convenience ───────────────────────────────────────────

    def get_recent_memories(self, limit: int = 10) -> list[MemoryEntry]:
        """Return the *limit* most recent session events (newest first)."""
        all_entries = self.read_session_log()
        return list(reversed(all_entries[-limit:]))


# ─── Shared Memory ─────────────────────────────────────────────


class SharedMemory:
    """
    Council-wide memory shared across all members.

    File layout inside ``data/memories/shared/``::

        decisions.jsonl  — one JSON object per council decision
        history.md       — narrative markdown history

    Usage::

        shared = SharedMemory()
        shared.record_decision({...})
        decisions = shared.read_decisions()
    """

    DECISIONS_FILE = "decisions.jsonl"
    HISTORY_FILE = "history.md"

    def __init__(self, shared_dir: Path | None = None) -> None:
        base = shared_dir or (MEMORIES_DIR / "shared")
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def decisions_path(self) -> Path:
        return self._dir / self.DECISIONS_FILE

    @property
    def history_path(self) -> Path:
        return self._dir / self.HISTORY_FILE

    # ── Decisions ─────────────────────────────────────────────

    def read_decisions(self) -> list[dict[str, Any]]:
        """Return all recorded decisions.  Skips comment lines (``#``)."""
        if not self.decisions_path.exists():
            return []
        decisions: list[dict[str, Any]] = []
        for lineno, line in enumerate(
            self.decisions_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                decisions.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    self.decisions_path,
                    f"Line {lineno}: {exc}",
                ) from exc
        return decisions

    def record_decision(self, decision: dict[str, Any]) -> None:
        """Append a decision record (one JSON line)."""
        line = json.dumps(decision, ensure_ascii=False)
        _atomic_append(self.decisions_path, line)

    # ── History ───────────────────────────────────────────────

    def read_history(self) -> str:
        """Return the full narrative history as a string."""
        if not self.history_path.exists():
            return ""
        return self.history_path.read_text(encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """Append a markdown section to the history file."""
        text = entry if entry.endswith("\n") else entry + "\n"
        _atomic_append(self.history_path, "\n" + text)
