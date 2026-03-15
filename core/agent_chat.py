"""
Jericho — Agent-to-Agent Chat (F-008)

Orchestrator-mediated conversations between council members with
automatic memory recording.  Unlike the session orchestrator (F-007),
this module provides lightweight, standalone conversations that don't
require a full session lifecycle.

Storage:
    Each conversation gets a JSON file in ``data/conversations/``
    named ``C-<conversation_id>.json``.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import CONVERSATIONS_DIR
from core.api_client import APIClient, ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.memory_influence import MemoryInfluence
from core.registry import CouncilMember, CouncilRegistry


# ─── Exceptions ────────────────────────────────────────────────


class ChatError(Exception):
    """Base exception for agent chat errors."""


class ChatNotFoundError(ChatError):
    """Raised when a conversation record cannot be found."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation not found: '{conversation_id}'")


class ChatValidationError(ChatError):
    """Raised when conversation data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ChatExchange:
    """A single exchange in an agent-to-agent conversation."""

    speaker: str
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatExchange:
        return cls(
            speaker=data["speaker"],
            content=data["content"],
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        speaker: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatExchange:
        """Factory that auto-fills the timestamp."""
        return cls(
            speaker=speaker,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class ConversationRecord:
    """Persistent record of an agent-to-agent conversation."""

    conversation_id: str
    title: str
    participants: list[str] = field(default_factory=list)
    topic: str = ""
    exchanges: list[ChatExchange] = field(default_factory=list)
    summary: str = ""
    created_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["exchanges"] = [e.to_dict() for e in self.exchanges]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationRecord:
        exchanges = [
            ChatExchange.from_dict(e)
            for e in data.get("exchanges", [])
        ]
        return cls(
            conversation_id=data["conversation_id"],
            title=data["title"],
            participants=list(data.get("participants", [])),
            topic=data.get("topic", ""),
            exchanges=exchanges,
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        conversation_id: str,
        title: str,
        participants: list[str] | None = None,
        topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConversationRecord:
        """Factory that auto-fills the created_at timestamp."""
        if not conversation_id.strip():
            raise ChatValidationError(["Conversation ID must not be empty"])
        if not title.strip():
            raise ChatValidationError(["Title must not be empty"])
        return cls(
            conversation_id=conversation_id.strip(),
            title=title.strip(),
            participants=participants or [],
            topic=topic,
            exchanges=[],
            summary="",
            created_at=datetime.now(timezone.utc).isoformat(),
            closed_at="",
            metadata=metadata or {},
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
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _build_opening_prompt(
    member: CouncilMember,
    partner_name: str,
    topic: str,
    memory_context_text: str = "",
) -> str:
    """Build the opening prompt for a conversation."""
    parts = [
        f"## Conversation with {partner_name}",
    ]
    if topic:
        parts.append(f"\n**Topic:** {topic}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    parts.append(
        f"\n---\n"
        f"You are **{member.name}** ({member.role}). You are starting a "
        f"conversation with **{partner_name}**. "
    )
    if topic:
        parts.append(f"The topic is: {topic}. ")
    parts.append(
        "Share your opening thoughts. Be concise but substantive."
    )
    return "\n".join(parts)


def _build_chat_prompt(
    member: CouncilMember,
    partner_name: str,
    exchanges: list[ChatExchange],
    topic: str,
    memory_context_text: str = "",
) -> str:
    """Build a continuation prompt with conversation history."""
    parts = [f"## Conversation with {partner_name}"]
    if topic:
        parts.append(f"**Topic:** {topic}")

    if exchanges:
        parts.append("\n### Conversation So Far")
        for ex in exchanges[-10:]:  # limit context window
            parts.append(f"**{ex.speaker}:** {ex.content}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), continue this conversation. "
        f"Respond to the latest message above. Be concise but substantive."
    )
    return "\n".join(parts)


# ─── Agent Chat ────────────────────────────────────────────────


class AgentChat:
    """
    Orchestrator-mediated agent-to-agent conversations.

    Provides lightweight, standalone conversations between council
    members without requiring a full session lifecycle.  All exchanges
    are recorded to per-agent memory automatically.

    Usage::

        registry = CouncilRegistry().load()
        async with APIClient() as client:
            chat = AgentChat(registry=registry, api_client=client)
            rec = chat.create_conversation(
                "C-001", "Ethics Debate",
                participants=["Sage", "Logic"],
                topic="AI autonomy",
            )
            rec = await chat.converse("C-001", ["Sage", "Logic"], "AI autonomy", rounds=2)
            rec = chat.close_conversation("C-001")
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

    # ── Conversation Lifecycle ────────────────────────────────

    def create_conversation(
        self,
        conversation_id: str,
        title: str,
        *,
        participants: list[str] | None = None,
        topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConversationRecord:
        """
        Create a new conversation record.

        Requires at least 2 participants.

        Raises:
            ChatValidationError: if inputs are invalid or < 2 participants.
            ChatError: if a conversation with this ID already exists.
        """
        filepath = self._filepath(conversation_id.strip())
        if filepath.exists():
            raise ChatError(
                f"Conversation already exists: '{conversation_id}'"
            )

        participants = participants or []

        # Validate minimum participants
        if len(participants) < 2:
            raise ChatValidationError(
                ["At least 2 participants are required for a conversation"]
            )

        # Validate all participants are real members
        known_names = [n.lower() for n in self._registry.list_names()]
        for name in participants:
            if name.lower() not in known_names:
                raise ChatValidationError(
                    [f"Unknown council member: '{name}'"]
                )

        record = ConversationRecord.create(
            conversation_id=conversation_id,
            title=title,
            participants=participants,
            topic=topic,
            metadata=metadata,
        )
        self._save(record)
        return record

    async def exchange(
        self,
        conversation_id: str,
        speaker_name: str,
        *,
        addressee_name: str | None = None,
        topic: str = "",
    ) -> tuple[ConversationRecord, ChatResponse]:
        """
        Have one member speak in the conversation.

        The speaker sees the full conversation history and generates
        a response via the API client.  The exchange is recorded in
        both the conversation file and the speaker's agent memory.

        Args:
            conversation_id: The conversation to speak in.
            speaker_name: The member who is speaking.
            addressee_name: Optional specific addressee (for prompt context).
            topic: Optional topic override for the prompt.

        Returns:
            Tuple of (updated record, raw ChatResponse).

        Raises:
            ChatNotFoundError: if the conversation doesn't exist.
            ChatValidationError: if speaker is not a participant.
            ChatError: if the conversation is closed.
        """
        record = self.get(conversation_id)

        if record.closed_at:
            raise ChatError(
                f"Conversation '{conversation_id}' is closed"
            )

        # Validate speaker is a participant
        if speaker_name.lower() not in [
            p.lower() for p in record.participants
        ]:
            raise ChatValidationError(
                [f"'{speaker_name}' is not a participant in this conversation"]
            )

        member = self._registry.get(speaker_name)
        effective_topic = topic or record.topic

        # Determine partner for prompt context
        partner = addressee_name
        if not partner:
            others = [
                p for p in record.participants
                if p.lower() != speaker_name.lower()
            ]
            partner = others[0] if others else "the group"

        # Build prompt
        memory_text = ""
        if self._memory_influence is not None:
            keywords = MemoryInfluence.extract_keywords(
                effective_topic or record.title
            )
            ctx = self._memory_influence.build_context(member.name, keywords)
            memory_text = ctx.formatted_text

        if not record.exchanges:
            prompt = _build_opening_prompt(member, partner, effective_topic, memory_text)
        else:
            prompt = _build_chat_prompt(
                member, partner, record.exchanges, effective_topic, memory_text
            )

        # Build multi-turn message history for the API
        api_messages = self._build_api_messages(record, member, prompt)

        response = await self._api_client.chat(member, api_messages)

        # Record the exchange
        ex = ChatExchange.create(
            speaker=member.name,
            content=response.content,
            metadata={"model": response.model, "provider": response.provider},
        )
        record = self._append_exchanges(record, [ex])

        # Record to agent memory
        agent_mem = AgentMemory(member.name)
        agent_mem.append_session_event(
            MemoryEntry.create(
                session_id=conversation_id,
                event_type="agent_chat",
                content=f"Spoke with {partner} about "
                        f"'{effective_topic or record.title}': "
                        f"{response.content[:200]}",
                source="agent_chat",
            )
        )

        self._save(record)
        return record, response

    async def converse(
        self,
        conversation_id: str,
        member_names: list[str],
        topic: str = "",
        *,
        rounds: int = 1,
    ) -> ConversationRecord:
        """
        Run an orchestrated multi-turn conversation.

        Each member takes a turn per round, seeing all prior exchanges.

        Args:
            conversation_id: The conversation to run.
            member_names: Ordered list of members to speak each round.
            topic: Topic for the conversation prompts.
            rounds: Number of full rounds (each member speaks once per round).

        Returns:
            The final ConversationRecord with all exchanges.

        Raises:
            ChatNotFoundError: if the conversation doesn't exist.
            ChatValidationError: if any member is not a participant.
            ChatError: if the conversation is closed.
        """
        record = self.get(conversation_id)

        if record.closed_at:
            raise ChatError(
                f"Conversation '{conversation_id}' is closed"
            )

        if not member_names:
            raise ChatValidationError(
                ["At least one member name is required"]
            )

        effective_topic = topic or record.topic

        for _round in range(rounds):
            for name in member_names:
                record, _ = await self.exchange(
                    conversation_id,
                    name,
                    topic=effective_topic,
                )

        return record

    def close_conversation(
        self,
        conversation_id: str,
        summary: str = "",
    ) -> ConversationRecord:
        """
        Close a conversation and persist summary to shared memory.

        Raises:
            ChatNotFoundError: if the conversation doesn't exist.
            ChatError: if the conversation is already closed.
        """
        record = self.get(conversation_id)

        if record.closed_at:
            raise ChatError(
                f"Conversation '{conversation_id}' is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)

        record = ConversationRecord(
            conversation_id=record.conversation_id,
            title=record.title,
            participants=list(record.participants),
            topic=record.topic,
            exchanges=list(record.exchanges),
            summary=final_summary,
            created_at=record.created_at,
            closed_at=now,
            metadata=dict(record.metadata),
        )
        self._save(record)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "conversation_closed",
            "conversation_id": record.conversation_id,
            "title": record.title,
            "participants": record.participants,
            "exchange_count": len(record.exchanges),
            "summary": final_summary,
            "closed_at": now,
        })

        self._shared_memory.append_history(
            f"### Conversation: {record.title} ({record.conversation_id})\n"
            f"**Closed:** {now}\n"
            f"**Participants:** {', '.join(record.participants)}\n\n"
            f"{final_summary}\n"
        )

        return record

    # ── Query ─────────────────────────────────────────────────

    def get(self, conversation_id: str) -> ConversationRecord:
        """
        Load a conversation record by ID.

        Raises:
            ChatNotFoundError: if no conversation file exists.
        """
        filepath = self._filepath(conversation_id)
        if not filepath.exists():
            raise ChatNotFoundError(conversation_id)
        return self._load(filepath)

    def list_conversations(
        self,
        *,
        participant: str | None = None,
        closed: bool | None = None,
    ) -> list[ConversationRecord]:
        """
        Return all conversations, optionally filtered.

        Args:
            participant: Filter to conversations including this member.
            closed: If True, only closed; if False, only open; if None, all.
        """
        records: list[ConversationRecord] = []
        for filepath in sorted(self._dir.glob("C-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if participant is not None:
                if participant.lower() not in [
                    p.lower() for p in rec.participants
                ]:
                    continue
            if closed is not None:
                is_closed = bool(rec.closed_at)
                if is_closed != closed:
                    continue
            records.append(rec)
        return records

    def has_conversation(self, conversation_id: str) -> bool:
        """Check if a conversation record exists."""
        return self._filepath(conversation_id).exists()

    def get_exchanges(
        self,
        conversation_id: str,
        *,
        speaker: str | None = None,
    ) -> list[ChatExchange]:
        """
        Get conversation exchanges, optionally filtered by speaker.

        Raises:
            ChatNotFoundError: if no conversation exists.
        """
        record = self.get(conversation_id)
        if speaker is not None:
            speaker_lower = speaker.lower()
            return [
                e for e in record.exchanges
                if e.speaker.lower() == speaker_lower
            ]
        return list(record.exchanges)

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, conversation_id: str) -> Path:
        return self._dir / f"C-{conversation_id}.json"

    def _save(self, record: ConversationRecord) -> None:
        payload = json.dumps(
            record.to_dict(), indent=2, ensure_ascii=False
        )
        _atomic_write(self._filepath(record.conversation_id), payload + "\n")

    def _load(self, filepath: Path) -> ConversationRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return ConversationRecord.from_dict(data)

    def _append_exchanges(
        self,
        record: ConversationRecord,
        new_exchanges: list[ChatExchange],
    ) -> ConversationRecord:
        """Return a new ConversationRecord with exchanges appended."""
        all_exchanges = list(record.exchanges) + new_exchanges
        return ConversationRecord(
            conversation_id=record.conversation_id,
            title=record.title,
            participants=list(record.participants),
            topic=record.topic,
            exchanges=all_exchanges,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )

    def _build_api_messages(
        self,
        record: ConversationRecord,
        member: CouncilMember,
        prompt: str,
    ) -> list[ChatMessage]:
        """
        Build the API message list for a member's turn.

        Converts prior exchanges into alternating user/assistant messages
        from the speaker's perspective, then appends the new prompt.
        """
        messages: list[ChatMessage] = []

        # Convert history: speaker's messages are "assistant",
        # others' messages are "user"
        for ex in record.exchanges[-10:]:  # limit context
            if ex.speaker.lower() == member.name.lower():
                messages.append(ChatMessage(role="assistant", content=ex.content))
            else:
                messages.append(
                    ChatMessage(
                        role="user",
                        content=f"**{ex.speaker}:** {ex.content}",
                    )
                )

        # Append the new prompt
        messages.append(ChatMessage(role="user", content=prompt))
        return messages

    def _generate_summary(self, record: ConversationRecord) -> str:
        """Generate a default summary from conversation data."""
        participant_str = ", ".join(record.participants)
        ex_count = len(record.exchanges)
        unique_speakers = sorted(set(e.speaker for e in record.exchanges))

        parts = [
            f"Conversation '{record.title}' between {participant_str} "
            f"with {ex_count} exchanges.",
        ]
        if record.topic:
            parts.append(f"Topic: {record.topic}.")
        if unique_speakers:
            parts.append(
                f"Active speakers: {', '.join(unique_speakers)}."
            )
        return " ".join(parts)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("C-*.json")))
        return f"AgentChat(conversations={count}, dir={self._dir})"
