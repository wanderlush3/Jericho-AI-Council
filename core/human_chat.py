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

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import CONVERSATIONS_DIR, MULTI_AI_RESPONSE_DELAY
from core.api_client import APIClient, ChatMessage, ChatResponse
from core.characters import CharacterManager, CharacterTemplate
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.memory_influence import MemoryInfluence
from core.registry import CouncilMember, CouncilRegistry
from core.utils import atomic_write


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
    council_members: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    paused: bool = False

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
        # Backward compat: derive council_members from member_name if absent
        council_members = list(data.get("council_members", []))
        if not council_members and data.get("member_name"):
            council_members = [data["member_name"]]
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
            council_members=council_members,
            characters=list(data.get("characters", [])),
            paused=data.get("paused", False),
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
        initial_members = [member_name.strip()] if member_name.strip() else []
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
            council_members=initial_members,
            characters=[],
            paused=False,
        )


# ─── Helpers ───────────────────────────────────────────────────




def _build_human_chat_prompt(
    member: CouncilMember,
    messages: list[HumanChatMessage],
    topic: str,
    memory_context_text: str = "",
    council_members: list[str] | None = None,
    user_description: str = "",
    character_names: list[str] | None = None,
    user_name: str = "",
) -> str:
    """Build a prompt for the council member to respond to the human."""
    parts = ["## Direct Conversation with Human Operator"]

    if user_description or user_name:
        label = "About the Human Operator"
        if user_name:
            label += f" ({user_name})"
        desc = user_description or "No further details provided."
        parts.append(f"\n**{label}:** {desc}")

    if topic:
        parts.append(f"**Topic:** {topic}")

    if messages:
        parts.append("\n### Conversation So Far")
        for msg in messages[-10:]:  # limit context window
            label = "Human" if msg.role == "human" else msg.speaker
            parts.append(f"**{label}:** {msg.content}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    # Multi-member context — combine council members and characters
    all_participants = list(council_members or []) + list(character_names or [])
    other_members = [
        m for m in all_participants
        if m.lower() != member.name.lower()
    ]

    parts.append(f"\n---\n")
    if other_members:
        others_str = ", ".join(f"**{m}**" for m in other_members)
        parts.append(
            f"You are **{member.name}** ({member.role}). You are in a "
            f"group conversation with the human operator and {others_str}. "
            f"Read everyone's messages carefully and respond to the latest "
            f"points raised. Be concise but substantive."
        )
    else:
        parts.append(
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

    # ── Character Helpers ─────────────────────────────────────

    @staticmethod
    def _character_to_member(char: CharacterTemplate) -> CouncilMember:
        """Convert a CharacterTemplate to a CouncilMember for API calls.

        Uses the character's own api_provider/model (model defaults to
        'Default' which makes APIClient fall back to the Settings default).
        The character's traits, backstory, and personality fields are woven
        into the system prompt so the LLM receives the full character context.
        """
        # Build a rich system prompt from all character fields
        prompt_parts: list[str] = []
        if char.system_prompt:
            prompt_parts.append(char.system_prompt)

        if char.backstory:
            prompt_parts.append(f"\n## Backstory\n{char.backstory}")

        if char.traits:
            traits_text = "\n".join(
                f"- **{t.name}** ({t.trait_type}, intensity {t.intensity}): {t.description}"
                for t in char.traits
            )
            prompt_parts.append(f"\n## Character Traits\n{traits_text}")

        if char.greeting:
            prompt_parts.append(
                f"\n## Greeting\nWhen starting a conversation, greet with: {char.greeting}"
            )

        if char.example_messages:
            examples = "\n".join(f"- {ex}" for ex in char.example_messages)
            prompt_parts.append(f"\n## Example Messages\n{examples}")

        full_prompt = "\n".join(prompt_parts) if prompt_parts else f"You are {char.name}."

        return CouncilMember(
            name=char.name,
            role=char.description,
            description=char.description,
            personality={},
            api_provider=char.api_provider,
            model=char.model,
            vote_weight=1.0,
            specialties=list(char.tags),
            system_prompt=full_prompt,
        )

    @staticmethod
    def _character_memory_name(char_name: str) -> str:
        """Return the memory directory name for a character."""
        return f"{char_name.strip().lower().replace(' ', '_')}_memory"

    # ── Chat Lifecycle ────────────────────────────────────────

    def create_chat(
        self,
        chat_id: str,
        title: str,
        *,
        member_name: str = "",
        character_id: str = "",
        topic: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> HumanChatRecord:
        """
        Create a new human-to-agent chat record.

        Either ``member_name`` or ``character_id`` (or both) must be provided.
        When using a character, the character must be in 'active' status and
        a memory directory ``charactername_memory`` is created.

        Raises:
            HumanChatValidationError: if inputs are invalid.
            HumanChatError: if a chat with this ID already exists.
        """
        filepath = self._filepath(chat_id.strip())
        if filepath.exists():
            raise HumanChatError(f"Chat already exists: '{chat_id}'")

        if not member_name.strip() and not character_id.strip():
            raise HumanChatValidationError(
                ["Either 'member_name' or 'character_id' is required"]
            )

        initial_members: list[str] = []
        initial_characters: list[str] = []
        effective_member_name = member_name.strip()

        # Validate council member if provided
        if member_name.strip():
            known_names = [n.lower() for n in self._registry.list_names()]
            if member_name.lower() not in known_names:
                raise HumanChatValidationError(
                    [f"Unknown council member: '{member_name}'"]
                )
            initial_members = [member_name.strip()]

        # Validate and set up character if provided
        if character_id.strip():
            from core.characters import CharacterManager, CharacterNotFoundError
            cmgr = CharacterManager()
            try:
                char = cmgr.get(character_id.strip())
            except CharacterNotFoundError:
                raise HumanChatValidationError(
                    [f"Character not found: '{character_id}'"]
                )
            if char.status != "active":
                raise HumanChatValidationError(
                    [f"Character '{char.name}' is not active (status: {char.status})"]
                )
            initial_characters = [character_id.strip()]

            # Create the character memory directory
            mem_name = self._character_memory_name(char.name)
            AgentMemory(mem_name)  # Creates the directory

            # Use character name as member_name if no council member provided
            if not effective_member_name:
                effective_member_name = char.name

        record = HumanChatRecord.create(
            chat_id=chat_id,
            title=title,
            member_name=effective_member_name,
            topic=topic,
            metadata=metadata,
        )
        # Set initial council_members and characters
        record = self._replace_record(
            record,
            council_members=initial_members,
            characters=initial_characters,
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
        Get council member and/or character response(s) to the conversation.

        When multiple participants are active, each responds in turn.
        After all respond, the chat is auto-paused to prevent
        endless AI-to-AI loops (user must resume or send a new message).

        Returns:
            Tuple of (updated record, last ChatResponse).

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or paused.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        if record.paused:
            raise HumanChatError(f"Chat '{chat_id}' is paused")

        effective_topic = record.topic
        last_response = None

        # Load user profile for prompt context
        from core.api_keys import APIKeyManager
        _mgr = APIKeyManager()
        _user_desc = _mgr.get_user_description()
        _user_name = _mgr.get_user_name()

        # Resolve character names for prompt context
        char_names = self._resolve_character_names(record)

        # Build response queue: council members first, then characters
        respondents: list[tuple[CouncilMember, str]] = []  # (member, memory_name)

        # Council members
        members_to_respond = list(record.council_members)
        if not members_to_respond and not record.characters:
            # Backward compat: fall back to member_name
            members_to_respond = [record.member_name]

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        # Characters
        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = self._character_to_member(char)
                mem_name = self._character_memory_name(char.name)
                respondents.append((member, mem_name))

        for idx, (member, mem_name) in enumerate(respondents):
            # Build prompt from conversation history
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(member.name, keywords)
                memory_text = ctx.formatted_text

            prompt = _build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
                user_name=_user_name,
            )

            # Build API messages
            api_messages = self._build_api_messages(record, member, prompt)

            response = await self._api_client.chat(member, api_messages)
            last_response = response

            # Guard against None content from API
            content_text = response.content or ""

            # Record the agent message
            msg = HumanChatMessage.create(
                role="agent",
                speaker=member.name,
                content=content_text,
                metadata={"model": response.model, "provider": response.provider},
            )
            record = self._append_messages(record, [msg])

            # Record to agent/character memory
            agent_mem = AgentMemory(mem_name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=chat_id,
                    event_type="human_chat",
                    content=f"Spoke with human operator about "
                            f"'{effective_topic or record.title}': "
                            f"{content_text[:200]}",
                    source="human_chat",
                )
            )

            # Save incrementally so next member sees this message
            self._save(record)

            # Inter-AI pacing delay (skip after the last respondent)
            if idx < len(respondents) - 1:
                await asyncio.sleep(MULTI_AI_RESPONSE_DELAY)

        # Auto-pause when multiple participants are active
        if len(respondents) > 1:
            record = self._set_paused(record, True)

        self._save(record)
        return record, last_response

    def add_council_member(
        self,
        chat_id: str,
        member_name: str,
    ) -> HumanChatRecord:
        """
        Add a council member to an active chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed.
            HumanChatValidationError: if the member is unknown or already present.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        # Validate member
        known = [n.lower() for n in self._registry.list_names()]
        if member_name.lower() not in known:
            raise HumanChatValidationError(
                [f"Unknown council member: '{member_name}'"]
            )

        current = [m.lower() for m in record.council_members]
        if member_name.lower() in current:
            raise HumanChatValidationError(
                [f"'{member_name}' is already in this chat"]
            )

        new_members = list(record.council_members) + [member_name]
        record = self._replace_record(record, council_members=new_members)
        self._save(record)
        return record

    def remove_council_member(
        self,
        chat_id: str,
        member_name: str,
    ) -> HumanChatRecord:
        """
        Remove a council member from an active chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or this is the last member.
            HumanChatValidationError: if the member is not in the chat.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        current_lower = [m.lower() for m in record.council_members]
        if member_name.lower() not in current_lower:
            raise HumanChatValidationError(
                [f"'{member_name}' is not in this chat"]
            )

        total_participants = len(record.council_members) + len(record.characters)
        if total_participants <= 1:
            raise HumanChatError("Cannot remove the last participant")

        new_members = [
            m for m in record.council_members
            if m.lower() != member_name.lower()
        ]
        # If removing leaves only 1 member, auto-unpause
        total = len(new_members) + len(record.characters)
        paused = record.paused if total > 1 else False
        record = self._replace_record(
            record, council_members=new_members, paused=paused,
        )
        self._save(record)
        return record

    def add_character(
        self,
        chat_id: str,
        character_id: str,
    ) -> HumanChatRecord:
        """
        Add a character to an active chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed.
            HumanChatValidationError: if the character is unknown, inactive, or duplicate.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        # Validate character
        from core.characters import CharacterNotFoundError
        cmgr = CharacterManager()
        try:
            char = cmgr.get(character_id)
        except CharacterNotFoundError:
            raise HumanChatValidationError(
                [f"Character not found: '{character_id}'"]
            )

        if char.status != "active":
            raise HumanChatValidationError(
                [f"Character '{char.name}' is not active (status: {char.status})"]
            )

        if character_id in record.characters:
            raise HumanChatValidationError(
                [f"Character '{char.name}' is already in this chat"]
            )

        # Create character memory directory
        mem_name = self._character_memory_name(char.name)
        AgentMemory(mem_name)

        new_characters = list(record.characters) + [character_id]
        record = self._replace_record(record, characters=new_characters)
        self._save(record)
        return record

    def remove_character(
        self,
        chat_id: str,
        character_id: str,
    ) -> HumanChatRecord:
        """
        Remove a character from an active chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or this is the last participant.
            HumanChatValidationError: if the character is not in the chat.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        if character_id not in record.characters:
            raise HumanChatValidationError(
                [f"Character '{character_id}' is not in this chat"]
            )

        total_participants = len(record.council_members) + len(record.characters)
        if total_participants <= 1:
            raise HumanChatError("Cannot remove the last participant")

        new_characters = [c for c in record.characters if c != character_id]
        total = len(record.council_members) + len(new_characters)
        paused = record.paused if total > 1 else False
        record = self._replace_record(
            record, characters=new_characters, paused=paused,
        )
        self._save(record)
        return record

    def pause_chat(self, chat_id: str) -> HumanChatRecord:
        """
        Pause a chat to prevent further agent responses.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or already paused.
        """
        record = self.get(chat_id)
        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")
        if record.paused:
            raise HumanChatError(f"Chat '{chat_id}' is already paused")
        record = self._set_paused(record, True)
        self._save(record)
        return record

    def resume_chat(self, chat_id: str) -> HumanChatRecord:
        """
        Resume a paused chat.

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or not paused.
        """
        record = self.get(chat_id)
        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")
        if not record.paused:
            raise HumanChatError(f"Chat '{chat_id}' is not paused")
        record = self._set_paused(record, False)
        self._save(record)
        return record

    async def continue_conversation(
        self,
        chat_id: str,
    ) -> tuple[HumanChatRecord, list[ChatResponse]]:
        """
        Run one round of AI-to-AI conversation.

        Each participant responds in turn, seeing all prior messages
        (including other AIs' messages with speaker attribution).
        The chat is auto-paused after the round completes.

        Requires 2+ participants (council members + characters).

        Returns:
            Tuple of (updated record, list of ChatResponses).

        Raises:
            HumanChatNotFoundError: if the chat doesn't exist.
            HumanChatError: if the chat is closed or has < 2 participants.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        # Build respondent list
        respondents: list[tuple[CouncilMember, str]] = []
        char_names = self._resolve_character_names(record)

        members_to_respond = list(record.council_members)
        if not members_to_respond and not record.characters:
            members_to_respond = [record.member_name]

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = self._character_to_member(char)
                mem_name = self._character_memory_name(char.name)
                respondents.append((member, mem_name))

        if len(respondents) < 2:
            raise HumanChatError(
                "continue_conversation requires 2+ participants"
            )

        # Auto-resume if paused
        if record.paused:
            record = self._set_paused(record, False)
            self._save(record)

        effective_topic = record.topic
        responses: list[ChatResponse] = []

        # Load user description for prompt context
        from core.api_keys import APIKeyManager
        _user_desc = APIKeyManager().get_user_description()

        for idx, (member, mem_name) in enumerate(respondents):
            # Build prompt from conversation history
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(
                    member.name, keywords
                )
                memory_text = ctx.formatted_text

            prompt = _build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
            )

            # Build API messages
            api_messages = self._build_api_messages(
                record, member, prompt
            )

            response = await self._api_client.chat(member, api_messages)
            responses.append(response)

            # Guard against None content from API
            content_text = response.content or ""

            # Record the agent message
            msg = HumanChatMessage.create(
                role="agent",
                speaker=member.name,
                content=content_text,
                metadata={
                    "model": response.model,
                    "provider": response.provider,
                },
            )
            record = self._append_messages(record, [msg])

            # Record to agent/character memory
            agent_mem = AgentMemory(mem_name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=chat_id,
                    event_type="human_chat",
                    content=f"Spoke in group conversation about "
                            f"'{effective_topic or record.title}': "
                            f"{content_text[:200]}",
                    source="human_chat",
                )
            )

            # Re-load record so next member sees this message
            self._save(record)

            # Inter-AI pacing delay (skip after the last respondent)
            if idx < len(respondents) - 1:
                await asyncio.sleep(MULTI_AI_RESPONSE_DELAY)

        # Auto-pause after round
        record = self._set_paused(record, True)
        self._save(record)
        return record, responses

    async def get_agent_response_streaming(
        self,
        chat_id: str,
    ) -> AsyncIterator[tuple[str, ChatResponse, HumanChatRecord]]:
        """
        Stream council member responses one at a time.

        Same logic as ``get_agent_response`` but yields after each
        member responds so the caller can forward results immediately
        (e.g. via SSE).

        Yields:
            ``(member_name, ChatResponse, updated_record)`` per member.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        if record.paused:
            raise HumanChatError(f"Chat '{chat_id}' is paused")

        members_to_respond = list(record.council_members)
        if not members_to_respond and not record.characters:
            members_to_respond = [record.member_name]

        effective_topic = record.topic

        # Load user profile for prompt context
        from core.api_keys import APIKeyManager
        _mgr = APIKeyManager()
        _user_desc = _mgr.get_user_description()
        _user_name = _mgr.get_user_name()

        # Resolve character names for prompt context
        char_names = self._resolve_character_names(record)

        # Build response queue: council members first, then characters
        respondents: list[tuple[CouncilMember, str]] = []  # (member, memory_name)

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = self._character_to_member(char)
                mem_name = self._character_memory_name(char.name)
                respondents.append((member, mem_name))

        for idx, (member, mem_name) in enumerate(respondents):
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(member.name, keywords)
                memory_text = ctx.formatted_text

            prompt = _build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
                user_name=_user_name,
            )
            api_messages = self._build_api_messages(record, member, prompt)

            response = await self._api_client.chat(member, api_messages)
            content_text = response.content or ""

            msg = HumanChatMessage.create(
                role="agent",
                speaker=member.name,
                content=content_text,
                metadata={"model": response.model, "provider": response.provider},
            )
            record = self._append_messages(record, [msg])

            agent_mem = AgentMemory(mem_name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=chat_id,
                    event_type="human_chat",
                    content=f"Spoke with human operator about "
                            f"'{effective_topic or record.title}': "
                            f"{content_text[:200]}",
                    source="human_chat",
                )
            )

            self._save(record)
            yield member.name, response, record

            # Inter-AI pacing delay (skip after the last respondent)
            if idx < len(respondents) - 1:
                await asyncio.sleep(MULTI_AI_RESPONSE_DELAY)

        # Auto-pause when multiple participants are active
        if len(respondents) > 1:
            record = self._set_paused(record, True)
            self._save(record)


    async def continue_conversation_streaming(
        self,
        chat_id: str,
    ) -> AsyncIterator[tuple[str, ChatResponse, HumanChatRecord]]:
        """
        Stream one round of AI-to-AI conversation responses.

        Same logic as ``continue_conversation`` but yields after each
        member responds.

        Yields:
            ``(member_name, ChatResponse, updated_record)`` per member.
        """
        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        members_to_respond = list(record.council_members)
        if not members_to_respond and not record.characters:
            members_to_respond = [record.member_name]

        # Resolve character names for prompt context
        char_names = self._resolve_character_names(record)

        # Build response queue: council members first, then characters
        respondents: list[tuple[CouncilMember, str]] = []  # (member, memory_name)

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = self._character_to_member(char)
                mem_name = self._character_memory_name(char.name)
                respondents.append((member, mem_name))

        if len(respondents) < 2:
            raise HumanChatError(
                "continue_conversation requires 2+ participants"
            )

        # Auto-resume if paused
        if record.paused:
            record = self._set_paused(record, False)
            self._save(record)

        effective_topic = record.topic

        # Load user profile for prompt context
        from core.api_keys import APIKeyManager
        _mgr = APIKeyManager()
        _user_desc = _mgr.get_user_description()
        _user_name = _mgr.get_user_name()

        for idx, (member, mem_name) in enumerate(respondents):
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(
                    member.name, keywords
                )
                memory_text = ctx.formatted_text

            prompt = _build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
                user_name=_user_name,
            )
            api_messages = self._build_api_messages(record, member, prompt)

            response = await self._api_client.chat(member, api_messages)
            content_text = response.content or ""

            msg = HumanChatMessage.create(
                role="agent",
                speaker=member.name,
                content=content_text,
                metadata={
                    "model": response.model,
                    "provider": response.provider,
                },
            )
            record = self._append_messages(record, [msg])

            agent_mem = AgentMemory(mem_name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=chat_id,
                    event_type="human_chat",
                    content=f"Spoke in group conversation about "
                            f"'{effective_topic or record.title}': "
                            f"{content_text[:200]}",
                    source="human_chat",
                )
            )

            self._save(record)
            yield member.name, response, record

            # Inter-AI pacing delay (skip after the last respondent)
            if idx < len(respondents) - 1:
                await asyncio.sleep(MULTI_AI_RESPONSE_DELAY)

        # Auto-pause after round
        record = self._set_paused(record, True)
        self._save(record)

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

        record = self._replace_record(
            record, summary=final_summary, closed_at=now, paused=False,
        )
        self._save(record)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "human_chat_closed",
            "chat_id": record.chat_id,
            "title": record.title,
            "member": record.member_name,
            "council_members": record.council_members,
            "message_count": len(record.messages),
            "summary": final_summary,
            "closed_at": now,
        })

        members_str = ", ".join(record.council_members) or record.member_name
        self._shared_memory.append_history(
            f"### Human Chat: {record.title} ({record.chat_id})\n"
            f"**Closed:** {now}\n"
            f"**Members:** {members_str}\n\n"
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
        atomic_write(self._filepath(record.chat_id), payload + "\n")

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
        return self._replace_record(record, messages=all_messages)

    def _set_paused(
        self,
        record: HumanChatRecord,
        paused: bool,
    ) -> HumanChatRecord:
        """Return a new HumanChatRecord with paused state changed."""
        return self._replace_record(record, paused=paused)

    def _replace_record(
        self,
        record: HumanChatRecord,
        **overrides: Any,
    ) -> HumanChatRecord:
        """Return a new HumanChatRecord with specified fields replaced."""
        defaults = {
            "chat_id": record.chat_id,
            "title": record.title,
            "member_name": record.member_name,
            "topic": record.topic,
            "messages": list(record.messages),
            "summary": record.summary,
            "created_at": record.created_at,
            "closed_at": record.closed_at,
            "metadata": dict(record.metadata),
            "council_members": list(record.council_members),
            "characters": list(record.characters),
            "paused": record.paused,
        }
        defaults.update(overrides)
        return HumanChatRecord(**defaults)

    def _build_api_messages(
        self,
        record: HumanChatRecord,
        member: CouncilMember,
        prompt: str,
    ) -> list[ChatMessage]:
        """
        Build the API message list for the agent's turn.

        Human messages become "user" role.  The current member's own
        prior messages become "assistant" role.  Other council members'
        messages become "user" role with a ``[Speaker]:`` prefix so the
        LLM can distinguish who said what.
        """
        messages: list[ChatMessage] = []
        total_participants = len(record.council_members) + len(record.characters)
        is_multi = total_participants > 1

        for msg in record.messages[-10:]:  # limit context
            if msg.role == "human":
                if is_multi:
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=f"[Human]: {msg.content}",
                        )
                    )
                else:
                    messages.append(
                        ChatMessage(role="user", content=msg.content)
                    )
            elif msg.speaker.lower() == member.name.lower():
                messages.append(
                    ChatMessage(role="assistant", content=msg.content)
                )
            else:
                messages.append(
                    ChatMessage(
                        role="user",
                        content=f"[{msg.speaker}]: {msg.content}",
                    )
                )

        # Append the new prompt
        messages.append(ChatMessage(role="user", content=prompt))
        return messages

    def _generate_summary(self, record: HumanChatRecord) -> str:
        """Generate a default summary from chat data."""
        msg_count = len(record.messages)
        human_count = sum(1 for m in record.messages if m.role == "human")
        agent_count = sum(1 for m in record.messages if m.role == "agent")

        members_str = ", ".join(record.council_members) or record.member_name
        char_names = self._resolve_character_names(record)
        if char_names:
            all_parts = ([members_str] if members_str else []) + char_names
            members_str = ", ".join(all_parts)
        parts = [
            f"Chat '{record.title}' between human and {members_str} "
            f"with {msg_count} messages ({human_count} human, {agent_count} agent).",
        ]
        if record.topic:
            parts.append(f"Topic: {record.topic}.")
        return " ".join(parts)

    def _resolve_character_names(self, record: HumanChatRecord) -> list[str]:
        """Resolve character IDs to display names."""
        names: list[str] = []
        for char_id in record.characters:
            char = self._load_character(char_id)
            if char:
                names.append(char.name)
        return names

    def _load_character(self, character_id: str) -> CharacterTemplate | None:
        """Load a character template by ID, returning None if not found."""
        try:
            cmgr = CharacterManager()
            return cmgr.get(character_id)
        except Exception:
            return None

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("H-*.json")))
        return f"HumanChat(chats={count}, dir={self._dir})"
