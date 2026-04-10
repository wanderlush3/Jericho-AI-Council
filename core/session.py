"""
Jericho — Council Session Orchestrator (F-007)

Full session lifecycle: context load, briefing, activity phase,
record, summary.  The orchestrator controls all I/O — council
members interact solely through LLM chat completions.

Session phases:
    1. CREATED   — session object constructed, not yet started
    2. BRIEFING  — context loaded, members receive opening brief
    3. ACTIVE    — main activity (discussion, voting, free-form)
    4. SUMMARY   — session winding down, collecting summaries
    5. CLOSED    — all artefacts persisted, session complete

Storage:
    Each session gets a JSON file in ``data/conversations/``
    named ``S-<session_id>.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import CONVERSATIONS_DIR
from core.api_client import APIClient, ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.memory_influence import MemoryInfluence
from core.registry import CouncilMember, CouncilRegistry
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class SessionError(Exception):
    """Base exception for session orchestrator errors."""


class SessionNotFoundError(SessionError):
    """Raised when a session record cannot be found."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: '{session_id}'")


class SessionStateError(SessionError):
    """Raised when an operation is invalid for the current session phase."""

    def __init__(self, session_id: str, message: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session '{session_id}': {message}")


class SessionValidationError(SessionError):
    """Raised when session data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Constants ─────────────────────────────────────────────────

SESSION_PHASES = ("created", "briefing", "active", "summary", "closed")

_VALID_TRANSITIONS: dict[str, list[str]] = {
    "created": ["briefing"],
    "briefing": ["active"],
    "active": ["summary"],
    "summary": ["closed"],
    "closed": [],
}

ACTIVITY_TYPES = ("discussion", "voting", "freeform", "review")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class SessionMessage:
    """A single message exchanged during a session."""

    speaker: str          # council member name, "orchestrator", or "human"
    content: str
    timestamp: str = ""
    phase: str = ""
    activity_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        return cls(
            speaker=data["speaker"],
            content=data["content"],
            timestamp=data.get("timestamp", ""),
            phase=data.get("phase", ""),
            activity_type=data.get("activity_type", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        speaker: str,
        content: str,
        phase: str = "",
        activity_type: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        """Factory that auto-fills the timestamp."""
        return cls(
            speaker=speaker,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            phase=phase,
            activity_type=activity_type,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class SessionRecord:
    """Persistent record of a council session."""

    session_id: str
    title: str
    phase: str = "created"
    activity_type: str = ""
    agenda: str = ""
    participants: list[str] = field(default_factory=list)
    messages: list[SessionMessage] = field(default_factory=list)
    summary: str = ""
    created_at: str = ""
    started_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["messages"] = [m.to_dict() for m in self.messages]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        messages = [
            SessionMessage.from_dict(m)
            for m in data.get("messages", [])
        ]
        return cls(
            session_id=data["session_id"],
            title=data["title"],
            phase=data.get("phase", "created"),
            activity_type=data.get("activity_type", ""),
            agenda=data.get("agenda", ""),
            participants=list(data.get("participants", [])),
            messages=messages,
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        session_id: str,
        title: str,
        activity_type: str = "freeform",
        agenda: str = "",
        participants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """Factory that auto-fills the created_at timestamp."""
        if not session_id.strip():
            raise SessionValidationError(["Session ID must not be empty"])
        if not title.strip():
            raise SessionValidationError(["Title must not be empty"])
        if activity_type and activity_type not in ACTIVITY_TYPES:
            raise SessionValidationError(
                [f"Invalid activity_type '{activity_type}' — "
                 f"must be one of {ACTIVITY_TYPES}"]
            )
        return cls(
            session_id=session_id.strip(),
            title=title.strip(),
            phase="created",
            activity_type=activity_type,
            agenda=agenda,
            participants=participants or [],
            messages=[],
            summary="",
            created_at=datetime.now(timezone.utc).isoformat(),
            started_at="",
            closed_at="",
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




def _build_briefing_prompt(
    record: SessionRecord,
    member: CouncilMember,
    recent_memories: list[MemoryEntry],
    memory_context_text: str = "",
) -> str:
    """Build the briefing message that introduces a member to the session."""
    parts = [
        f"## Council Session: {record.title}",
        f"**Session ID:** {record.session_id}",
        f"**Activity:** {record.activity_type}",
    ]
    if record.agenda:
        parts.append(f"\n### Agenda\n{record.agenda}")

    if record.participants:
        parts.append(
            f"\n### Participants\n"
            + ", ".join(record.participants)
        )

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")
    elif recent_memories:
        # Fallback: bare memory list when no scored context is available
        parts.append("\n### Your Recent Memories")
        for mem in recent_memories[:5]:
            parts.append(f"- [{mem.event_type}] {mem.content}")

    parts.append(
        f"\n---\n"
        f"You are **{member.name}** ({member.role}). "
        f"Please acknowledge the session briefing and indicate you are ready "
        f"to participate. Keep your response brief."
    )
    return "\n".join(parts)


def _build_discussion_prompt(
    topic: str,
    member: CouncilMember,
    prior_messages: list[SessionMessage],
    memory_context_text: str = "",
) -> str:
    """Build a prompt for a member to contribute to a discussion."""
    parts = [f"## Discussion Topic\n{topic}"]

    if prior_messages:
        parts.append("\n### Prior Contributions")
        for msg in prior_messages[-10:]:  # limit context window
            parts.append(f"**{msg.speaker}:** {msg.content}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), share your perspective on "
        f"this topic. Consider the prior contributions above. Be concise "
        f"but substantive."
    )
    return "\n".join(parts)


def _build_summary_prompt(
    record: SessionRecord,
    member: CouncilMember,
) -> str:
    """Build the prompt asking a member for their session summary."""
    parts = [
        f"## Session Summary Request",
        f"**Session:** {record.title} ({record.session_id})",
        f"**Messages exchanged:** {len(record.messages)}",
    ]

    # Include last few messages for context
    recent = record.messages[-5:] if record.messages else []
    if recent:
        parts.append("\n### Recent Activity")
        for msg in recent:
            parts.append(f"**{msg.speaker}:** {msg.content}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}**, provide a brief summary of what was discussed "
        f"and any key takeaways from your perspective. Keep it to 2-3 sentences."
    )
    return "\n".join(parts)


# ─── Session Orchestrator ─────────────────────────────────────


class SessionOrchestrator:
    """
    Orchestrates a full council session lifecycle.

    The orchestrator:
    - Manages session state transitions (created → briefing → active → summary → closed)
    - Loads member context (recent memories, core beliefs) before each interaction
    - Sends prompts to council members via the API client
    - Records all messages in the session transcript
    - Persists session events to per-agent memory
    - Records session summaries to shared council memory

    Usage::

        registry = CouncilRegistry().load()
        async with APIClient() as client:
            orch = SessionOrchestrator(
                registry=registry,
                api_client=client,
            )
            record = orch.create_session("S-001", "Ethics Review", activity_type="discussion")
            record = await orch.start_session(record.session_id)
            record = await orch.brief_member(record.session_id, "Sage")
            record = await orch.discuss(record.session_id, "Ethics of AI autonomy", ["Sage", "Logic"])
            record = await orch.close_session(record.session_id)
    """

    def __init__(
        self,
        *,
        registry: CouncilRegistry,
        api_client: APIClient,
        conversations_dir: Path | None = None,
        shared_memory: SharedMemory | None = None,
        memory_influence: MemoryInfluence | None = None,
    ) -> None:
        self._registry = registry
        self._api_client = api_client
        self._dir = conversations_dir or CONVERSATIONS_DIR
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

    # ── Session Lifecycle ─────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        title: str,
        *,
        activity_type: str = "freeform",
        agenda: str = "",
        participants: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """
        Create a new session record.

        Raises:
            SessionValidationError: if inputs are invalid.
            SessionStateError: if a session with this ID already exists.
        """
        filepath = self._filepath(session_id.strip())
        if filepath.exists():
            raise SessionStateError(
                session_id, "Session already exists"
            )

        # Validate participants are real members
        if participants:
            for name in participants:
                if name.lower() not in [n.lower() for n in self._registry.list_names()]:
                    raise SessionValidationError(
                        [f"Unknown council member: '{name}'"]
                    )

        record = SessionRecord.create(
            session_id=session_id,
            title=title,
            activity_type=activity_type,
            agenda=agenda,
            participants=participants,
            metadata=metadata,
        )
        self._save(record)
        return record

    async def start_session(self, session_id: str) -> SessionRecord:
        """
        Transition from 'created' to 'briefing' phase.

        Raises:
            SessionNotFoundError: if no session with this ID exists.
            SessionStateError: if the session is not in 'created' phase.
        """
        record = self.get(session_id)
        record = self._transition(record, "briefing")

        # Update started_at timestamp
        record = SessionRecord(
            session_id=record.session_id,
            title=record.title,
            phase=record.phase,
            activity_type=record.activity_type,
            agenda=record.agenda,
            participants=list(record.participants),
            messages=list(record.messages),
            summary=record.summary,
            created_at=record.created_at,
            started_at=datetime.now(timezone.utc).isoformat(),
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )
        self._save(record)
        return record

    async def brief_member(
        self,
        session_id: str,
        member_name: str,
        *,
        memory_limit: int = 5,
    ) -> SessionRecord:
        """
        Brief a single council member on the session context.

        Loads the member's recent memories and sends a briefing prompt
        via the API client. The member's acknowledgment is recorded.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'briefing' phase.
        """
        record = self.get(session_id)
        if record.phase != "briefing":
            raise SessionStateError(
                session_id,
                f"Cannot brief members during '{record.phase}' phase "
                f"(expected 'briefing')"
            )

        member = self._registry.get(member_name)
        agent_mem = AgentMemory(member.name)
        recent = agent_mem.get_recent_memories(limit=memory_limit)

        # Build memory context if influence engine is configured
        memory_text = ""
        if self._memory_influence is not None:
            keywords = MemoryInfluence.extract_keywords(
                f"{record.title} {record.agenda}"
            )
            ctx = self._memory_influence.build_context(member.name, keywords)
            memory_text = ctx.formatted_text

        # Build and send briefing
        prompt = _build_briefing_prompt(record, member, recent, memory_text)
        response = await self._api_client.chat(
            member,
            [ChatMessage(role="user", content=prompt)],
        )

        # Record the exchange
        orch_msg = SessionMessage.create(
            speaker="orchestrator",
            content=prompt,
            phase="briefing",
            activity_type=record.activity_type,
        )
        member_msg = SessionMessage.create(
            speaker=member.name,
            content=response.content,
            phase="briefing",
            activity_type=record.activity_type,
            metadata={"model": response.model, "provider": response.provider},
        )

        record = self._append_messages(record, [orch_msg, member_msg])

        # Record to agent memory
        agent_mem.append_session_event(
            MemoryEntry.create(
                session_id=session_id,
                event_type="briefing",
                content=f"Briefed on session '{record.title}'. "
                        f"Response: {response.content[:200]}",
                source="orchestrator",
            )
        )

        self._save(record)
        return record

    async def activate_session(self, session_id: str) -> SessionRecord:
        """
        Transition from 'briefing' to 'active' phase.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'briefing' phase.
        """
        record = self.get(session_id)
        record = self._transition(record, "active")
        self._save(record)
        return record

    async def discuss(
        self,
        session_id: str,
        topic: str,
        member_names: list[str],
    ) -> SessionRecord:
        """
        Run a discussion round where each listed member contributes.

        Each member sees the topic and all prior contributions before
        adding their own perspective.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'active' phase.
        """
        record = self.get(session_id)
        if record.phase != "active":
            raise SessionStateError(
                session_id,
                f"Cannot run discussion during '{record.phase}' phase "
                f"(expected 'active')"
            )

        # Post a topic announcement
        topic_msg = SessionMessage.create(
            speaker="orchestrator",
            content=f"**Discussion Topic:** {topic}",
            phase="active",
            activity_type="discussion",
        )
        record = self._append_messages(record, [topic_msg])

        # Collect discussion messages from this round
        discussion_msgs: list[SessionMessage] = []

        for name in member_names:
            member = self._registry.get(name)

            # Build memory context if influence engine is configured
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(topic)
                ctx = self._memory_influence.build_context(member.name, keywords)
                memory_text = ctx.formatted_text

            prompt = _build_discussion_prompt(topic, member, discussion_msgs, memory_text)

            response = await self._api_client.chat(
                member,
                [ChatMessage(role="user", content=prompt)],
            )

            msg = SessionMessage.create(
                speaker=member.name,
                content=response.content,
                phase="active",
                activity_type="discussion",
                metadata={"model": response.model, "provider": response.provider},
            )
            discussion_msgs.append(msg)

            # Record to agent memory
            agent_mem = AgentMemory(member.name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=session_id,
                    event_type="discussion",
                    content=f"Discussed '{topic}': {response.content[:200]}",
                    source="orchestrator",
                )
            )

        record = self._append_messages(record, discussion_msgs)
        self._save(record)
        return record

    async def send_to_member(
        self,
        session_id: str,
        member_name: str,
        prompt: str,
        *,
        activity_type: str = "freeform",
    ) -> tuple[SessionRecord, ChatResponse]:
        """
        Send an arbitrary prompt to a single member during the active phase.

        Returns the updated record and the raw ChatResponse.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'active' phase.
        """
        record = self.get(session_id)
        if record.phase != "active":
            raise SessionStateError(
                session_id,
                f"Cannot send messages during '{record.phase}' phase "
                f"(expected 'active')"
            )

        member = self._registry.get(member_name)
        response = await self._api_client.chat(
            member,
            [ChatMessage(role="user", content=prompt)],
        )

        orch_msg = SessionMessage.create(
            speaker="orchestrator",
            content=prompt,
            phase="active",
            activity_type=activity_type,
        )
        member_msg = SessionMessage.create(
            speaker=member.name,
            content=response.content,
            phase="active",
            activity_type=activity_type,
            metadata={"model": response.model, "provider": response.provider},
        )

        record = self._append_messages(record, [orch_msg, member_msg])

        # Record to agent memory
        agent_mem = AgentMemory(member.name)
        agent_mem.append_session_event(
            MemoryEntry.create(
                session_id=session_id,
                event_type=activity_type,
                content=f"Received prompt and responded: {response.content[:200]}",
                source="orchestrator",
            )
        )

        self._save(record)
        return record, response

    def add_human_message(
        self,
        session_id: str,
        content: str,
        *,
        activity_type: str = "freeform",
    ) -> SessionRecord:
        """
        Record a human message in the session transcript.

        The human can inject messages at any time during briefing or active phase.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'briefing' or 'active' phase.
        """
        record = self.get(session_id)
        if record.phase not in ("briefing", "active"):
            raise SessionStateError(
                session_id,
                f"Cannot add messages during '{record.phase}' phase "
                f"(expected 'briefing' or 'active')"
            )

        msg = SessionMessage.create(
            speaker="human",
            content=content,
            phase=record.phase,
            activity_type=activity_type,
        )
        record = self._append_messages(record, [msg])
        self._save(record)
        return record

    async def begin_summary(self, session_id: str) -> SessionRecord:
        """
        Transition from 'active' to 'summary' phase.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'active' phase.
        """
        record = self.get(session_id)
        record = self._transition(record, "summary")
        self._save(record)
        return record

    async def collect_summary(
        self,
        session_id: str,
        member_name: str,
    ) -> SessionRecord:
        """
        Ask a member for their session summary during the summary phase.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'summary' phase.
        """
        record = self.get(session_id)
        if record.phase != "summary":
            raise SessionStateError(
                session_id,
                f"Cannot collect summaries during '{record.phase}' phase "
                f"(expected 'summary')"
            )

        member = self._registry.get(member_name)
        prompt = _build_summary_prompt(record, member)

        response = await self._api_client.chat(
            member,
            [ChatMessage(role="user", content=prompt)],
        )

        msg = SessionMessage.create(
            speaker=member.name,
            content=response.content,
            phase="summary",
            activity_type="summary",
            metadata={"model": response.model, "provider": response.provider},
        )
        record = self._append_messages(record, [msg])
        self._save(record)
        return record

    async def close_session(
        self,
        session_id: str,
        summary: str = "",
    ) -> SessionRecord:
        """
        Transition from 'summary' to 'closed' phase.

        Persists the final summary to shared memory.

        Raises:
            SessionNotFoundError: if no session exists.
            SessionStateError: if session is not in 'summary' phase.
        """
        record = self.get(session_id)
        record = self._transition(record, "closed")

        # Set the summary and closed_at timestamp
        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)
        record = SessionRecord(
            session_id=record.session_id,
            title=record.title,
            phase=record.phase,
            activity_type=record.activity_type,
            agenda=record.agenda,
            participants=list(record.participants),
            messages=list(record.messages),
            summary=final_summary,
            created_at=record.created_at,
            started_at=record.started_at,
            closed_at=now,
            metadata=dict(record.metadata),
        )
        self._save(record)

        # Record decision to shared memory
        self._shared_memory.record_decision({
            "type": "session_closed",
            "session_id": record.session_id,
            "title": record.title,
            "activity_type": record.activity_type,
            "participants": record.participants,
            "message_count": len(record.messages),
            "summary": final_summary,
            "closed_at": now,
        })

        # Append to narrative history
        self._shared_memory.append_history(
            f"### Session: {record.title} ({record.session_id})\n"
            f"**Closed:** {now}\n"
            f"**Participants:** {', '.join(record.participants) or 'none'}\n\n"
            f"{final_summary}\n"
        )

        return record

    # ── Query ─────────────────────────────────────────────────

    def get(self, session_id: str) -> SessionRecord:
        """
        Load a session record by ID.

        Raises:
            SessionNotFoundError: if no session file exists.
        """
        filepath = self._filepath(session_id)
        if not filepath.exists():
            raise SessionNotFoundError(session_id)
        return self._load(filepath)

    def list_sessions(
        self,
        *,
        phase: str | None = None,
        activity_type: str | None = None,
    ) -> list[SessionRecord]:
        """
        Return all sessions, optionally filtered by phase or activity type.
        """
        records: list[SessionRecord] = []
        for filepath in sorted(self._dir.glob("S-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if phase is not None and rec.phase != phase:
                continue
            if activity_type is not None and rec.activity_type != activity_type:
                continue
            records.append(rec)
        return records

    def has_session(self, session_id: str) -> bool:
        """Check if a session record exists."""
        return self._filepath(session_id).exists()

    def get_transcript(
        self,
        session_id: str,
        *,
        speaker: str | None = None,
    ) -> list[SessionMessage]:
        """
        Get the session transcript, optionally filtered by speaker.

        Raises:
            SessionNotFoundError: if no session exists.
        """
        record = self.get(session_id)
        if speaker is not None:
            speaker_lower = speaker.lower()
            return [
                m for m in record.messages
                if m.speaker.lower() == speaker_lower
            ]
        return list(record.messages)

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, session_id: str) -> Path:
        return self._dir / f"S-{session_id}.json"

    def _save(self, record: SessionRecord) -> None:
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(record.session_id), payload + "\n")

    def _load(self, filepath: Path) -> SessionRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return SessionRecord.from_dict(data)

    def _transition(self, record: SessionRecord, target: str) -> SessionRecord:
        """
        Validate and perform a phase transition.

        Returns a new SessionRecord with the updated phase.

        Raises:
            SessionStateError: if the transition is invalid.
        """
        current = record.phase
        allowed = _VALID_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise SessionStateError(
                record.session_id,
                f"Cannot transition from '{current}' to '{target}' "
                f"(allowed: {allowed or 'none'})"
            )
        return SessionRecord(
            session_id=record.session_id,
            title=record.title,
            phase=target,
            activity_type=record.activity_type,
            agenda=record.agenda,
            participants=list(record.participants),
            messages=list(record.messages),
            summary=record.summary,
            created_at=record.created_at,
            started_at=record.started_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )

    def _append_messages(
        self,
        record: SessionRecord,
        new_messages: list[SessionMessage],
    ) -> SessionRecord:
        """Return a new SessionRecord with messages appended."""
        all_messages = list(record.messages) + new_messages
        return SessionRecord(
            session_id=record.session_id,
            title=record.title,
            phase=record.phase,
            activity_type=record.activity_type,
            agenda=record.agenda,
            participants=list(record.participants),
            messages=all_messages,
            summary=record.summary,
            created_at=record.created_at,
            started_at=record.started_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )

    def _generate_summary(self, record: SessionRecord) -> str:
        """Generate a default summary from session data."""
        participant_str = ", ".join(record.participants) or "no participants"
        msg_count = len(record.messages)
        member_msgs = [
            m for m in record.messages
            if m.speaker not in ("orchestrator", "human")
        ]
        unique_speakers = sorted(set(m.speaker for m in member_msgs))

        parts = [
            f"Session '{record.title}' ({record.activity_type}) "
            f"with {msg_count} messages.",
        ]
        if unique_speakers:
            parts.append(f"Active contributors: {', '.join(unique_speakers)}.")

        # Include summary-phase messages if any
        summary_msgs = [m for m in record.messages if m.phase == "summary"]
        if summary_msgs:
            parts.append("Member summaries:")
            for m in summary_msgs:
                parts.append(f"  - {m.speaker}: {m.content[:150]}")

        return " ".join(parts) if not summary_msgs else "\n".join(parts)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("S-*.json")))
        return f"SessionOrchestrator(sessions={count}, dir={self._dir})"
