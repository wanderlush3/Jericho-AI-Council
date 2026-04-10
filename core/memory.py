"""
Jericho — Memory System (F-004)

Per-agent read/write memory with core beliefs, session logs (JSONL),
and shared council memory for decisions and narrative history.

Architecture rule: the orchestrator writes files; agents respond with
structured text.  All I/O is synchronous — filesystem ops don't need async.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import MEMORIES_DIR
from core.utils import atomic_append, atomic_write


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
        atomic_write(self.beliefs_path, payload + "\n")

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
        atomic_append(self.session_log_path, line)

    # ── Convenience ───────────────────────────────────────────

    def get_recent_memories(self, limit: int = 10) -> list[MemoryEntry]:
        """Return the *limit* most recent session events (newest first)."""
        all_entries = self.read_session_log()
        return list(reversed(all_entries[-limit:]))

    # ── Session IDs ──────────────────────────────────────────

    def get_unique_session_ids(self) -> list[str]:
        """Return a chronologically-ordered list of unique session IDs."""
        seen: dict[str, None] = {}
        for entry in self.read_session_log():
            if entry.session_id not in seen:
                seen[entry.session_id] = None
        return list(seen.keys())

    # ── Memory Summarization ─────────────────────────────────

    SUMMARIZED_LOG_FILE = "session_log_summarized.jsonl"

    @property
    def summarized_log_path(self) -> Path:
        return self._dir / self.SUMMARIZED_LOG_FILE

    def read_summarized_log(self) -> list[MemoryEntry]:
        """Read previously-condensed summary entries."""
        if not self.summarized_log_path.exists():
            return []
        entries: list[MemoryEntry] = []
        for lineno, line in enumerate(
            self.summarized_log_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    self.summarized_log_path,
                    f"Line {lineno}: {exc}",
                ) from exc
            entries.append(MemoryEntry.from_dict(data))
        return entries

    def write_summarized_entry(self, entry: MemoryEntry) -> None:
        """Append a single condensed summary to the summarised log."""
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        atomic_append(self.summarized_log_path, line)

    def get_sessions_needing_summary(
        self, keep_recent: int = 3,
    ) -> list[list[MemoryEntry]]:
        """
        Group session-log entries by session ID and return groups
        eligible for summarization (all except the *keep_recent* most
        recent sessions and any already-summarized session IDs).
        """
        session_ids = self.get_unique_session_ids()
        if len(session_ids) <= keep_recent:
            return []

        already_summarized: set[str] = {
            e.session_id for e in self.read_summarized_log()
        }
        old_ids = [
            sid for sid in session_ids[:-keep_recent]
            if sid not in already_summarized
        ]
        if not old_ids:
            return []

        # Group entries by session ID
        all_entries = self.read_session_log()
        groups: list[list[MemoryEntry]] = []
        for sid in old_ids:
            group = [e for e in all_entries if e.session_id == sid]
            if group:
                groups.append(group)
        return groups

    # ── Contested Memories ────────────────────────────────────

    CONTESTED_FILE = "contested_memories.jsonl"

    @property
    def contested_path(self) -> Path:
        return self._dir / self.CONTESTED_FILE

    def read_contested_memories(self) -> list[dict[str, Any]]:
        """Read all contested memory records."""
        if not self.contested_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for lineno, line in enumerate(
            self.contested_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    self.contested_path,
                    f"Line {lineno}: {exc}",
                ) from exc
        return records

    def record_contested_memory(
        self,
        event_id: str,
        member_name: str,
        content: str,
        original_content: str,
    ) -> dict[str, Any]:
        """
        Record a divergent recollection of an event.

        Args:
            event_id: Identifier linking to the original memory
                      (typically session_id + timestamp).
            member_name: The agent recording the divergent memory.
            content: The agent's subjective recollection.
            original_content: What actually happened (for reference).

        Returns:
            The contested memory record dict.
        """
        record = {
            "event_id": event_id,
            "member_name": member_name,
            "content": content,
            "original_content": original_content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        line = json.dumps(record, ensure_ascii=False)
        atomic_append(self.contested_path, line)
        return record

    def get_contested_for_event(self, event_id: str) -> list[dict[str, Any]]:
        """Return contested memory records for a specific event."""
        return [
            r for r in self.read_contested_memories()
            if r.get("event_id") == event_id
        ]



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
        atomic_append(self.decisions_path, line)

    def remove_decision(self, index: int) -> dict[str, Any]:
        """Remove a decision by 0-based index.

        Args:
            index: Position of the decision to remove.

        Returns:
            The removed decision dict.

        Raises:
            IndexError: If the index is out of range.
        """
        decisions = self.read_decisions()
        if index < 0 or index >= len(decisions):
            raise IndexError(
                f"Decision index {index} out of range (0–{len(decisions) - 1})."
            )
        removed = decisions.pop(index)
        # Rewrite the entire file
        lines = [json.dumps(d, ensure_ascii=False) for d in decisions]
        content = "\n".join(lines) + "\n" if lines else ""
        atomic_write(self.decisions_path, content)
        return removed

    # ── History ───────────────────────────────────────────────

    def read_history(self) -> str:
        """Return the full narrative history as a string."""
        if not self.history_path.exists():
            return ""
        return self.history_path.read_text(encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """Append a markdown section to the history file."""
        text = entry if entry.endswith("\n") else entry + "\n"
        atomic_append(self.history_path, "\n" + text)


# ─── Law Shared Memory ────────────────────────────────────────────


class LawSharedMemory:
    """
    Shared memory for active laws — accessible to the LLM.

    Separate from SharedMemory because laws can be toggled on/off
    (active ↔ archived) and need independent management.

    File layout inside ``data/memories/law_shared/``::

        active_laws.jsonl  — one JSON object per active law

    Usage::

        lsm = LawSharedMemory()
        lsm.sync_active_laws([law1.to_dict(), law2.to_dict()])
        laws = lsm.read_active_laws()
        context = lsm.get_law_context()
    """

    ACTIVE_LAWS_FILE = "active_laws.jsonl"

    def __init__(self, shared_dir: Path | None = None) -> None:
        from config.settings import LAW_SHARED_MEMORIES_DIR
        base = shared_dir or LAW_SHARED_MEMORIES_DIR
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def active_laws_path(self) -> Path:
        return self._dir / self.ACTIVE_LAWS_FILE

    # ── Active Laws ───────────────────────────────────────────

    def read_active_laws(self) -> list[dict[str, Any]]:
        """Return all active law records."""
        if not self.active_laws_path.exists():
            return []
        laws: list[dict[str, Any]] = []
        for lineno, line in enumerate(
            self.active_laws_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                laws.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    self.active_laws_path,
                    f"Line {lineno}: {exc}",
                ) from exc
        return laws

    def sync_active_laws(self, laws: list[dict[str, Any]]) -> None:
        """Rewrite the active laws file with the given list.

        Call this whenever a law transitions to/from 'active' status.
        """
        lines = [json.dumps(law, ensure_ascii=False) for law in laws]
        content = "\n".join(lines) + "\n" if lines else ""
        atomic_write(self.active_laws_path, content)

    def get_law_context(self) -> str:
        """Return formatted text of all active laws for LLM injection."""
        laws = self.read_active_laws()
        if not laws:
            return ""

        parts = ["## Active Laws\n"]
        for i, law in enumerate(laws, 1):
            title = law.get("title", "Untitled Law")
            desc = law.get("description", "")
            body = law.get("body", "")
            parts.append(f"### {i}. {title}")
            if desc:
                parts.append(f"{desc}")
            if body:
                parts.append(f"{body}")
            parts.append("")  # blank line separator

        return "\n".join(parts)

