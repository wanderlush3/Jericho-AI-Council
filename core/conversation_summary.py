"""
Jericho — Rolling Conversation Summary (F-058)

Generates and caches LLM-based rolling summaries for long conversations.
When a conversation exceeds a configurable threshold (default 10 messages),
the summarizer compresses older messages into a short summary and returns
it alongside the most recent messages.  This preserves context continuity
while dramatically reducing token usage in long conversations.

The summary is cached by content hash so that unchanged conversation
prefixes are never re-summarized.  If the LLM call fails, the system
falls back to the legacy behavior (raw last N messages).

Usage::

    summarizer = ConversationSummarizer(api_client=client)
    result = await summarizer.get_summary("H-001", messages)
    if result is not None:
        # Use result.summary_text + result.recent_messages
    else:
        # Short conversation, use raw messages[-10:]
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from config.settings import (
    DEFAULT_SUMMARIZATION_MODEL,
    DEFAULT_SUMMARIZATION_PROVIDER,
    ROLLING_SUMMARY_ENABLED,
    ROLLING_SUMMARY_MAX_TOKENS,
    ROLLING_SUMMARY_RECENT_MESSAGES,
    ROLLING_SUMMARY_THRESHOLD,
    SUMMARIZATION_MODEL_ENV,
    SUMMARIZATION_PROVIDER_ENV,
)

if TYPE_CHECKING:
    from core.api_client import APIClient
    from core.human_chat import HumanChatMessage


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class CachedSummary:
    """In-memory cache entry for a conversation summary."""

    content_hash: str
    summary_text: str
    message_count: int


@dataclass(frozen=True)
class RollingSummaryResult:
    """Result of a rolling summary request.

    Attributes:
        summary_text: LLM-generated summary of older messages.
        recent_messages: The most recent raw messages to keep.
        summarized_count: How many messages were compressed.
        token_estimate: Estimated tokens in the summary text.
    """

    summary_text: str
    recent_messages: list[HumanChatMessage]
    summarized_count: int = 0
    token_estimate: int = 0


# ─── Summarizer ───────────────────────────────────────────────


class ConversationSummarizer:
    """Generates and caches rolling summaries of long conversations.

    Args:
        api_client: The LLM API client for generating summaries.
        threshold: Message count that triggers summarization.
        recent_count: How many recent messages to keep raw.
        max_summary_tokens: Max tokens for the generated summary.
        enabled: Whether summarization is active.
    """

    def __init__(
        self,
        *,
        api_client: APIClient,
        threshold: int | None = None,
        recent_count: int | None = None,
        max_summary_tokens: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._api_client = api_client
        self._threshold = (
            threshold if threshold is not None else ROLLING_SUMMARY_THRESHOLD
        )
        self._recent_count = (
            recent_count
            if recent_count is not None
            else ROLLING_SUMMARY_RECENT_MESSAGES
        )
        self._max_summary_tokens = (
            max_summary_tokens
            if max_summary_tokens is not None
            else ROLLING_SUMMARY_MAX_TOKENS
        )
        self._enabled = enabled if enabled is not None else ROLLING_SUMMARY_ENABLED

        # In-memory cache: chat_id → CachedSummary
        self._cache: dict[str, CachedSummary] = {}

    # ── Properties ────────────────────────────────────────────

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def recent_count(self) -> int:
        return self._recent_count

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Public API ────────────────────────────────────────────

    async def get_summary(
        self,
        chat_id: str,
        messages: list[HumanChatMessage],
    ) -> RollingSummaryResult | None:
        """Get a rolling summary for a conversation.

        Args:
            chat_id: The conversation ID (used for cache key).
            messages: All messages in the conversation.

        Returns:
            A ``RollingSummaryResult`` if the conversation exceeds the
            threshold, or ``None`` if no summarization is needed
            (short conversation or feature disabled).
        """
        if not self._enabled:
            return None

        if len(messages) <= self._threshold:
            return None

        # Split: older messages to summarize, recent to keep raw
        split_idx = len(messages) - self._recent_count
        if split_idx <= 0:
            return None

        older_messages = messages[:split_idx]
        recent_messages = messages[split_idx:]

        # Check cache
        content_hash = self._compute_hash(older_messages)
        cached = self._cache.get(chat_id)

        if cached is not None and cached.content_hash == content_hash:
            # Cache hit — reuse existing summary
            return RollingSummaryResult(
                summary_text=cached.summary_text,
                recent_messages=list(recent_messages),
                summarized_count=len(older_messages),
                token_estimate=self._estimate_tokens(cached.summary_text),
            )

        # Cache miss — generate new summary via LLM
        try:
            summary_text = await self._generate_summary(older_messages)
        except Exception:
            # LLM failure — graceful fallback to None (caller uses raw messages)
            return None

        # Update cache
        self._cache[chat_id] = CachedSummary(
            content_hash=content_hash,
            summary_text=summary_text,
            message_count=len(older_messages),
        )

        return RollingSummaryResult(
            summary_text=summary_text,
            recent_messages=list(recent_messages),
            summarized_count=len(older_messages),
            token_estimate=self._estimate_tokens(summary_text),
        )

    def invalidate_cache(self, chat_id: str) -> None:
        """Remove a cached summary for a conversation."""
        self._cache.pop(chat_id, None)

    def clear_cache(self) -> None:
        """Clear all cached summaries."""
        self._cache.clear()

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _compute_hash(messages: list[HumanChatMessage]) -> str:
        """Compute a content hash for a list of messages."""
        hasher = hashlib.sha256()
        for msg in messages:
            hasher.update(msg.speaker.encode("utf-8"))
            hasher.update(b"|")
            hasher.update(msg.content.encode("utf-8"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    async def _generate_summary(
        self,
        messages: list[HumanChatMessage],
    ) -> str:
        """Generate an LLM summary of conversation messages."""
        from core.api_client import ChatMessage, ChatResponse
        from core.registry import CouncilMember

        # Build the conversation text for the summarizer
        conversation_text = self._format_messages_for_summary(messages)

        # Resolve summarization provider/model from settings
        provider = os.environ.get(
            SUMMARIZATION_PROVIDER_ENV, DEFAULT_SUMMARIZATION_PROVIDER
        )
        model = os.environ.get(
            SUMMARIZATION_MODEL_ENV, DEFAULT_SUMMARIZATION_MODEL
        )

        # Build a lightweight "member" for the API call
        summarizer_member = CouncilMember(
            name="Summarizer",
            role="conversation_summarizer",
            description="Summarizes conversations",
            personality={},
            api_provider=provider,
            model=model,
            vote_weight=0.0,
            specialties=[],
            system_prompt=(
                "You are a precise conversation summarizer. "
                "Summarize the key points, decisions, and topics discussed. "
                "Be concise but preserve important context, names, and "
                "any commitments or action items. Write in third person. "
                "Do NOT include greetings or meta-commentary."
            ),
        )

        api_messages = [
            ChatMessage(
                role="user",
                content=(
                    f"Summarize this conversation in {self._max_summary_tokens} "
                    f"tokens or fewer:\n\n{conversation_text}"
                ),
            ),
        ]

        response: ChatResponse = await self._api_client.chat(
            summarizer_member,
            api_messages,
            max_tokens=self._max_summary_tokens * 4,  # char estimate
        )

        return (response.content or "").strip()

    @staticmethod
    def _format_messages_for_summary(
        messages: list[HumanChatMessage],
    ) -> str:
        """Format messages into a readable transcript for the LLM."""
        lines: list[str] = []
        for msg in messages:
            label = "Human" if msg.role == "human" else msg.speaker
            lines.append(f"{label}: {msg.content}")
        return "\n".join(lines)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate (chars / 4)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        cached = len(self._cache)
        return (
            f"ConversationSummarizer("
            f"threshold={self._threshold}, "
            f"recent={self._recent_count}, "
            f"cached={cached})"
        )
