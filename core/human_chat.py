"""
Jericho — Human-to-Agent Chat (F-009)

Direct conversation between the human operator and individual council
members with automatic memory recording.  Unlike agent-to-agent chat
(F-008), this module is one-on-one: one human, one council member.

Storage:
    Each chat gets a JSON file in ``data/conversations/``
    named ``H-<chat_id>.json``.
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


class HumanChatError(Exception):
    """Base exception for human-to-agent chat errors."""


class HumanChatNotFoundError(HumanChatError):
    """Raised when a chat record cannot be found."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        super().__init__(f"Chat not found: '{chat_id}'")


class HumanChatValidationError(HumanChatError):
    """Raised when chat data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class HumanChatMessage:
    """A single message in a human-to-agent conversation."""

    role: str  # "human" or "agent"
    speaker: str
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanChatMessage:
        return cls(
            role=data["role"],
            speaker=data["speaker"],
            content=data["content"],
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        role: str,
        speaker: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> HumanChatMessage:
        """Factory that auto-fills the timestamp."""
        if role not in ("human", "agent"):
            raise HumanChatValidationError(
                [f"Invalid role '{role}': must be 'human' or 'agent'"]
            )
        return cls(
            role=role,
            speaker=speaker,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class HumanChatRecord:
    """Persistent record of a human-to-agent conversation."""

    chat_id: str
    title: str
    member_name: str = ""
    topic: str = ""
    messages: list[HumanChatMessage] = field(default_factory=list)
    summary: str = ""
    created_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["messages"] = [m.to_dict() for m in self.messages]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanChatRecord:
        messages = [
            HumanChatMessage.from_dict(m)
            for m in data.get("messages", [])
        ]
        return cls(
            chat_id=data["chat_id"],
            title=data["title"],
            member_name=data.get("member_name", ""),
            topic=data.get("topic", ""),
            messages=messages,
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        chat_id: str,
        title: str,
        member_name: str = "",
        topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> HumanChatRecord:
        """Factory that auto-fills the created_at timestamp."""
        if not chat_id.strip():
            raise HumanChatValidationError(["Chat ID must not be empty"])
        if not title.strip():
            raise HumanChatValidationError(["Title must not be empty"])
        return cls(
            chat_id=chat_id.strip(),
            title=title.strip(),
            member_name=member_name.strip(),
            topic=topic,
            messages=[],
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


def _build_human_chat_prompt(
    member: CouncilMember,
    messages: list[HumanChatMessage],
    topic: str,
    memory_context_text: str = "",
) -> str:
    """Build a prompt for the council member to respond to the human."""
    parts = ["## Direct Conversation with Human Operator"]
    if topic:
        parts.append(f"**Topic:** {topic}")

    if messages:
        parts.append("\n### Conversation So Far")
        for msg in messages[-10:]:  # limit context window
            label = "Human" if msg.role == "human" else member.name
            parts.append(f"**{label}:** {msg.content}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    parts.append(
        f"\n---\n"
        f"You are **{member.name}** ({member.role}). You are speaking "
        f"directly with the human operator of the Jericho AI Council. "
        f"Respond to their latest message. Be concise but substantive."
    )
    return "\n".join(parts)


# ─── Human Chat ────────────────────────────────────────────────


class HumanChat:
    """
    Direct human-to-agent conversations.

    Provides lightweight, one-on-one conversations between the human
    operator and a single council member.  All agent responses are
    recorded to per-agent memory automatically.

    Usage::

        registry = CouncilRegistry().load()
        async with APIClient() as client:
            chat = HumanChat(registry=registry, api_client=client)
            rec = chat.create_chat("H-001", "Ethics Q&A", member_name="Sage")
            rec = chat.send_human_message("H-001", "What are your core beliefs?")
            rec, resp = await chat.get_agent_response("H-001")
            rec = chat.close_chat("H-001")
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

    # ── Chat Lifecycle ────────────────────────────────────────

    def create_chat(
        self,
        chat_id: str,
        title: str,
        *,
        member_name: str,
        topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> HumanChatRecord:
        """
        Create a new human-to-agent chat record.

        Raises:
            HumanChatValidationError: if inputs are invalid or member unknown.
            HumanChatError: if a chat with this ID already exists.
        """
        filepath = self._filepath(chat_id.strip())
        if filepath.exists():
            raise HumanChatError(f"Chat already exists: '{chat_id}'")

        # Validate member is a real council member
        known_names = [n.lower() for n in self._registry.list_names()]
        if member_name.lower() not in known_names:
            raise HumanChatValidationError(
                [f"Unknown council member: '{member_name}'"]
            )

        record = HumanChatRecord.create(
            chat_id=chat_id,
            title=title,
            member_name=member_name,
            topic=topic,
            metadata=metadata,
        )
        self._save(record)
        return record

    def send_human_message(
        self,
        chat_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> HumanChatRecord:
        """
        Record a human message in the chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        msg = HumanChatMessage.create(
            role="human",
            speaker="Human",
            content=content,
            metadata=metadata,
        )
        record = self._append_messages(record, [msg])
        self._save(record)
        return record

    async def get_agent_response(
        self,
        chat_id: str,
    ) -> tuple[HumanChatRecord, ChatResponse]:
        """
        Get the council member's response to the conversation so far.

        Sends the conversation history to the API and records the
        agent's response in both the chat file and agent memory.

        Returns:
            Tuple of (updated record, raw ChatResponse).

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        member = self._registry.get(record.member_name)
        effective_topic = record.topic

        # Build prompt from conversation history
        memory_text = ""
        if self._memory_influence is not None:
            keywords = MemoryInfluence.extract_keywords(
                effective_topic or record.title
            )
            ctx = self._memory_influence.build_context(member.name, keywords)
            memory_text = ctx.formatted_text

        prompt = _build_human_chat_prompt(
            member, record.messages, effective_topic, memory_text
        )

        # Build API messages
        api_messages = self._build_api_messages(record, member, prompt)

        response = await self._api_client.chat(member, api_messages)

        # Record the agent message
        msg = HumanChatMessage.create(
            role="agent",
            speaker=member.name,
            content=response.content,
            metadata={"model": response.model, "provider": response.provider},
        )
        record = self._append_messages(record, [msg])

        # Record to agent memory
        agent_mem = AgentMemory(member.name)
        agent_mem.append_session_event(
            MemoryEntry.create(
                session_id=chat_id,
                event_type="human_chat",
                content=f"Spoke with human operator about "
                        f"'{effective_topic or record.title}': "
                        f"{response.content[:200]}",
                source="human_chat",
            )
        )

        self._save(record)
        return record, response

    def close_chat(
        self,
        chat_id: str,
        summary: str = "",
    ) -> HumanChatRecord:
        """
        Close a chat and persist summary to shared memory.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is already closed.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(
                f"Chat '{chat_id}' is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)

        record = HumanChatRecord(
            chat_id=record.chat_id,
            title=record.title,
            member_name=record.member_name,
            topic=record.topic,
            messages=list(record.messages),
            summary=final_summary,
            created_at=record.created_at,
            closed_at=now,
            metadata=dict(record.metadata),
        )
        self._save(record)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "human_chat_closed",
            "chat_id": record.chat_id,
            "title": record.title,
            "member": record.member_name,
            "message_count": len(record.messages),
            "summary": final_summary,
            "closed_at": now,
        })

        self._shared_memory.append_history(
            f"### Human Chat: {record.title} ({record.chat_id})\n"
            f"**Closed:** {now}\n"
            f"**Member:** {record.member_name}\n\n"
            f"{final_summary}\n"
        )

        return record

    # ── Query ─────────────────────────────────────────────────

    def get(self, chat_id: str) -> HumanChatRecord:
        """
        Load a chat record by ID.

        Raises:
            HumanChatNotFoundError: if no chat file exists.
        """
        filepath = self._filepath(chat_id)
        if not filepath.exists():
            raise HumanChatNotFoundError(chat_id)
        return self._load(filepath)

    def list_chats(
        self,
        *,
        member: str | None = None,
        closed: bool | None = None,
    ) -> list[HumanChatRecord]:
        """
        Return all human chats, optionally filtered.

        Args:
            member: Filter to chats with this council member.
            closed: If True, only closed; if False, only open; if None, all.
        """
        records: list[HumanChatRecord] = []
        for filepath in sorted(self._dir.glob("H-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if member is not None:
                if rec.member_name.lower() != member.lower():
                    continue
            if closed is not None:
                is_closed = bool(rec.closed_at)
                if is_closed != closed:
                    continue
            records.append(rec)
        return records

    def has_chat(self, chat_id: str) -> bool:
        """Check if a chat record exists."""
        return self._filepath(chat_id).exists()

    def get_messages(
        self,
        chat_id: str,
        *,
        role: str | None = None,
    ) -> list[HumanChatMessage]:
        """
        Get chat messages, optionally filtered by role.

        Raises:
            HumanChatNotFoundError: if no chat exists.
        """
        record = self.get(chat_id)
        if role is not None:
            return [m for m in record.messages if m.role == role]
        return list(record.messages)

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, chat_id: str) -> Path:
        return self._dir / f"H-{chat_id}.json"

    def _save(self, record: HumanChatRecord) -> None:
        payload = json.dumps(
            record.to_dict(), indent=2, ensure_ascii=False
        )
        _atomic_write(self._filepath(record.chat_id), payload + "\n")

    def _load(self, filepath: Path) -> HumanChatRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return HumanChatRecord.from_dict(data)

    def _append_messages(
        self,
        record: HumanChatRecord,
        new_messages: list[HumanChatMessage],
    ) -> HumanChatRecord:
        """Return a new HumanChatRecord with messages appended."""
        all_messages = list(record.messages) + new_messages
        return HumanChatRecord(
            chat_id=record.chat_id,
            title=record.title,
            member_name=record.member_name,
            topic=record.topic,
            messages=all_messages,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )

    def _build_api_messages(
        self,
        record: HumanChatRecord,
        member: CouncilMember,
        prompt: str,
    ) -> list[ChatMessage]:
        """
        Build the API message list for the agent's turn.

        Human messages become "user" role, agent messages become
        "assistant" role, then the new prompt is appended as "user".
        """
        messages: list[ChatMessage] = []

        for msg in record.messages[-10:]:  # limit context
            if msg.role == "human":
                messages.append(ChatMessage(role="user", content=msg.content))
            else:
                messages.append(
                    ChatMessage(role="assistant", content=msg.content)
                )

        # Append the new prompt
        messages.append(ChatMessage(role="user", content=prompt))
        return messages

    def _generate_summary(self, record: HumanChatRecord) -> str:
        """Generate a default summary from chat data."""
        msg_count = len(record.messages)
        human_count = sum(1 for m in record.messages if m.role == "human")
        agent_count = sum(1 for m in record.messages if m.role == "agent")

        parts = [
            f"Chat '{record.title}' between human and {record.member_name} "
            f"with {msg_count} messages ({human_count} human, {agent_count} agent).",
        ]
        if record.topic:
            parts.append(f"Topic: {record.topic}.")
        return " ".join(parts)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("H-*.json")))
        return f"HumanChat(chats={count}, dir={self._dir})"
