"""
Jericho — Chat Streaming Mixin (F-063)

Streaming async generators for the human-to-agent chat system.
Extracted from ``core/human_chat.py`` to keep the main module
focused on lifecycle management.

The ``ChatStreamingMixin`` is mixed into ``HumanChat`` so that
callers see the streaming methods as ordinary instance methods.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from config.settings import MULTI_AI_RESPONSE_DELAY
from core.api_client import ChatResponse
from core.chat_helpers import build_human_chat_prompt, character_memory_name, character_to_member
from core.memory import AgentMemory, MemoryEntry
from core.memory_influence import MemoryInfluence


class ChatStreamingMixin:
    """Mixin providing streaming response methods for ``HumanChat``.

    This mixin depends on attributes and methods defined by the
    ``HumanChat`` class:

    - ``self.get(chat_id)``
    - ``self._registry``
    - ``self._api_client``
    - ``self._memory_influence``
    - ``self._summarizer``
    - ``self._load_character(char_id)``
    - ``self._resolve_character_names(record)``
    - ``self._append_messages(record, messages)``
    - ``self._set_paused(record, paused)``
    - ``self._save(record)``
    - ``self._build_api_messages(record, member, prompt, ...)``
    - ``self._should_skip_world_entities(record)``
    """

    async def get_agent_response_streaming(
        self,
        chat_id: str,
    ) -> AsyncIterator[tuple[str, ChatResponse, "HumanChatRecord"]]:  # noqa: F821
        """Stream council member responses one at a time.

        Same logic as ``get_agent_response`` but yields after each
        member responds so the caller can forward results immediately
        (e.g. via SSE).

        Yields:
            ``(member_name, ChatResponse, updated_record)`` per member.
        """
        from core.human_chat import HumanChatError, HumanChatMessage

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
        respondents: list[tuple] = []  # (member, memory_name)

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = character_to_member(char)
                mem_name = character_memory_name(char.name)
                respondents.append((member, mem_name))

        # F-058: get rolling summary if available
        summary_result = None
        if self._summarizer is not None:
            try:
                summary_result = await self._summarizer.get_summary(
                    chat_id, record.messages,
                )
            except Exception:
                summary_result = None  # graceful fallback

        for idx, (member, mem_name) in enumerate(respondents):
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(
                    member.name, keywords,
                    skip_world_entities=self._should_skip_world_entities(record),
                )
                memory_text = ctx.formatted_text

            prompt = build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
                user_name=_user_name,
                summary_result=summary_result,
            )
            api_messages = self._build_api_messages(
                record, member, prompt, summary_result=summary_result,
            )

            try:
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
            except Exception:
                # API call failed — record an absent message and continue
                content_text = "[absent] Was unavailable to respond at this time. [/absent]"
                msg = HumanChatMessage.create(
                    role="agent",
                    speaker=member.name,
                    content=content_text,
                    metadata={"absent": True},
                )
                record = self._append_messages(record, [msg])
                # Build a stub response for the SSE layer
                response = ChatResponse(
                    content=content_text,
                    model="",
                    provider="",
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
    ) -> AsyncIterator[tuple[str, ChatResponse, "HumanChatRecord"]]:  # noqa: F821
        """Stream one round of AI-to-AI conversation responses.

        Same logic as ``continue_conversation`` but yields after each
        member responds.

        Yields:
            ``(member_name, ChatResponse, updated_record)`` per member.
        """
        from core.human_chat import HumanChatError, HumanChatMessage

        record = self.get(chat_id)

        if record.closed_at:
            raise HumanChatError(f"Chat '{chat_id}' is closed")

        members_to_respond = list(record.council_members)
        if not members_to_respond and not record.characters:
            members_to_respond = [record.member_name]

        # Resolve character names for prompt context
        char_names = self._resolve_character_names(record)

        # Build response queue: council members first, then characters
        respondents: list[tuple] = []  # (member, memory_name)

        for member_name in members_to_respond:
            if member_name not in self._registry:
                continue  # skip non-registry names (e.g. characters)
            member = self._registry.get(member_name)
            respondents.append((member, member.name))

        for char_id in record.characters:
            char = self._load_character(char_id)
            if char is not None:
                member = character_to_member(char)
                mem_name = character_memory_name(char.name)
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

        # F-058: get rolling summary if available
        summary_result = None
        if self._summarizer is not None:
            try:
                summary_result = await self._summarizer.get_summary(
                    chat_id, record.messages,
                )
            except Exception:
                summary_result = None  # graceful fallback

        for idx, (member, mem_name) in enumerate(respondents):
            memory_text = ""
            if self._memory_influence is not None:
                keywords = MemoryInfluence.extract_keywords(
                    effective_topic or record.title
                )
                ctx = self._memory_influence.build_context(
                    member.name, keywords,
                    skip_world_entities=self._should_skip_world_entities(record),
                )
                memory_text = ctx.formatted_text

            prompt = build_human_chat_prompt(
                member, record.messages, effective_topic, memory_text,
                council_members=list(record.council_members),
                user_description=_user_desc,
                character_names=char_names,
                user_name=_user_name,
                summary_result=summary_result,
            )
            api_messages = self._build_api_messages(
                record, member, prompt, summary_result=summary_result,
            )

            try:
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
            except Exception:
                # API call failed — record an absent message and continue
                content_text = "[absent] Was unavailable to respond at this time. [/absent]"
                msg = HumanChatMessage.create(
                    role="agent",
                    speaker=member.name,
                    content=content_text,
                    metadata={"absent": True},
                )
                record = self._append_messages(record, [msg])
                # Build a stub response for the SSE layer
                response = ChatResponse(
                    content=content_text,
                    model="",
                    provider="",
                )

            self._save(record)
            yield member.name, response, record

            # Inter-AI pacing delay (skip after the last respondent)
            if idx < len(respondents) - 1:
                await asyncio.sleep(MULTI_AI_RESPONSE_DELAY)

        # Auto-pause after round
        record = self._set_paused(record, True)
        self._save(record)
