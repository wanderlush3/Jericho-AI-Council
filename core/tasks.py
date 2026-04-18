"""
Jericho — Task Manager

Filesystem-backed task system where council members and characters
are assigned tasks with a name, description, and reason.  Tasks
follow a simple lifecycle: draft → active → completed.

When executed ("Do Tasks"), each assignee receives an additive prompt
injection layered on top of existing memory/context injections and
narrates themselves completing the task over up to 5 message rounds.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import TASKS_DIR, TASK_STATUSES, TASK_MAX_ROUNDS
from core.utils import make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class TaskError(Exception):
    """Base exception for task errors."""


class TaskNotFoundError(TaskError):
    """Raised when a task is not found."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task '{task_id}' not found.")


class TaskValidationError(TaskError):
    """Raised when task data is invalid."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class TaskLifecycleError(TaskError):
    """Raised when a lifecycle transition is invalid."""

    def __init__(
        self, task_id: str, current_status: str, requested_status: str,
    ) -> None:
        self.task_id = task_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Cannot transition task '{task_id}' from "
            f"'{current_status}' to '{requested_status}'."
        )


# ─── Lifecycle ─────────────────────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"draft", "completed"},
    "completed": set(),  # terminal
}


# ─── Data Model ────────────────────────────────────────────────


@dataclass(frozen=True)
class TaskMessage:
    """A single narration message from an assignee during task execution."""

    speaker: str
    content: str
    round_number: int
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskMessage:
        return cls(
            speaker=data.get("speaker", ""),
            content=data.get("content", ""),
            round_number=data.get("round_number", 0),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        speaker: str,
        content: str,
        round_number: int,
        **metadata: Any,
    ) -> TaskMessage:
        return cls(
            speaker=speaker,
            content=content,
            round_number=round_number,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )


@dataclass(frozen=True)
class Task:
    """A task assigned to council members and/or characters."""

    id: str
    name: str
    description: str
    reason: str
    assignees: list[str]
    status: str = "draft"
    current_round: int = 0
    messages: list[TaskMessage] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["messages"] = [m.to_dict() for m in self.messages]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        messages = [
            TaskMessage.from_dict(m)
            for m in data.get("messages", [])
        ]
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            reason=data.get("reason", ""),
            assignees=data.get("assignees", []),
            status=data.get("status", "draft"),
            current_round=data.get("current_round", 0),
            messages=messages,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        task_id: str,
        name: str,
        description: str,
        reason: str,
        assignees: list[str],
        **metadata: Any,
    ) -> Task:
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=task_id,
            name=name.strip(),
            description=description.strip(),
            reason=reason.strip(),
            assignees=list(assignees),
            status="draft",
            current_round=0,
            messages=[],
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )


# ─── Task Manager ──────────────────────────────────────────────


class TaskManager:
    """Filesystem-backed task manager.

    Each task is stored as ``TK-XXXX.json`` in the tasks directory.
    """

    def __init__(self, tasks_dir: Path | None = None) -> None:
        self._dir = tasks_dir or TASKS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()

    def __repr__(self) -> str:
        return f"TaskManager(dir='{self._dir}')"

    # ── CRUD ─────────────────────────────────────────────────

    def create(
        self,
        name: str,
        description: str,
        reason: str,
        assignees: list[str],
        **metadata: Any,
    ) -> Task:
        """Create a new task in draft status."""
        errors: list[str] = []
        if not name or not name.strip():
            errors.append("Task name is required.")
        if not description or not description.strip():
            errors.append("Task description is required.")
        if not reason or not reason.strip():
            errors.append("Task reason is required.")
        if not assignees:
            errors.append("At least one assignee is required.")
        if errors:
            raise TaskValidationError(errors)

        with self._id_lock:
            task_id = self._next_id()
            task = Task.create(task_id, name, description, reason, assignees, **metadata)
            self._save(task)
        return task

    def get(self, task_id: str) -> Task:
        """Load a task by ID."""
        path = self._dir / f"{task_id}.json"
        if not path.exists():
            raise TaskNotFoundError(task_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Task.from_dict(data)

    def list_tasks(
        self,
        *,
        status: str | None = None,
        assignee: str | None = None,
    ) -> list[Task]:
        """List tasks with optional filters."""
        tasks: list[Task] = []
        for path in sorted(self._dir.glob("TK-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                task = Task.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue
            if status and task.status != status:
                continue
            if assignee:
                assignee_lower = assignee.lower()
                if not any(
                    a.lower() == assignee_lower for a in task.assignees
                ):
                    continue
            tasks.append(task)
        return tasks

    def update(self, task_id: str, **fields: Any) -> Task:
        """Update mutable fields of a task."""
        task = self.get(task_id)

        # Reject immutable fields
        immutables = {"id", "created_at"}
        bad = set(fields.keys()) & immutables
        if bad:
            raise TaskValidationError(
                f"Cannot update immutable field(s): {', '.join(bad)}"
            )

        d = task.to_dict()
        for key, value in fields.items():
            if key in d:
                d[key] = value
        d["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = Task.from_dict(d)
        self._save(updated)
        return updated

    def update_status(self, task_id: str, new_status: str) -> Task:
        """Transition a task to a new status."""
        task = self.get(task_id)

        if new_status not in TASK_STATUSES:
            raise TaskValidationError(f"Unknown status: '{new_status}'")

        valid = _VALID_TRANSITIONS.get(task.status, set())
        if new_status not in valid:
            raise TaskLifecycleError(task_id, task.status, new_status)

        d = task.to_dict()
        d["status"] = new_status
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = Task.from_dict(d)
        self._save(updated)
        return updated

    # ── Internal Helpers ─────────────────────────────────────

    def _save(self, task: Task) -> None:
        """Persist a task to disk."""
        path = self._dir / f"{task.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _next_id(self) -> str:
        """Generate the next sequential task ID (TK-0001, TK-0002, …)."""
        existing = sorted(self._dir.glob("TK-*.json"))
        if not existing:
            return "TK-0001"
        last = existing[-1].stem  # e.g. "TK-0042"
        try:
            num = int(last.split("-", 1)[1]) + 1
        except (IndexError, ValueError):
            num = len(existing) + 1
        return f"TK-{num:04d}"
