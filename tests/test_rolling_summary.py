"""
Tests for F-058 — Rolling Conversation Summary

Tests the ConversationSummarizer class, modified _build_human_chat_prompt,
modified _build_api_messages, and integration with HumanChat response methods.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.api_client import ChatMessage, ChatResponse
from core.conversation_summary import (
    CachedSummary,
    ConversationSummarizer,
    RollingSummaryResult,
)
from core.human_chat import (
    HumanChat,
    HumanChatMessage,
    HumanChatRecord,
    _build_human_chat_prompt,
)
from core.registry import CouncilMember


# ─── Helpers ───────────────────────────────────────────────────


def _make_message(
    role: str = "human",
    speaker: str = "Human",
    content: str = "Hello",
    metadata: dict[str, Any] | None = None,
) -> HumanChatMessage:
    """Create a test HumanChatMessage."""
    return HumanChatMessage(
        role=role,
        speaker=speaker,
        content=content,
        timestamp="2026-01-01T00:00:00Z",
        metadata=metadata or {},
    )


def _make_messages(count: int) -> list[HumanChatMessage]:
    """Create a list of alternating human/agent messages."""
    msgs: list[HumanChatMessage] = []
    for i in range(count):
        if i % 2 == 0:
            msgs.append(_make_message(
                role="human",
                speaker="Human",
                content=f"Human message {i}",
            ))
        else:
            msgs.append(_make_message(
                role="agent",
                speaker="Sage",
                content=f"Agent message {i}",
            ))
    return msgs


def _make_member(name: str = "Sage") -> CouncilMember:
    """Create a test council member."""
    return CouncilMember(
        name=name,
        role="Advisor",
        description="A wise advisor",
        personality={},
        api_provider="openrouter",
        model="test-model",
        vote_weight=1.0,
        specialties=["wisdom"],
        system_prompt="You are Sage.",
    )


def _make_record(
    chat_id: str = "test-001",
    messages: list[HumanChatMessage] | None = None,
    council_members: list[str] | None = None,
    characters: list[str] | None = None,
) -> HumanChatRecord:
    """Create a test chat record."""
    return HumanChatRecord(
        chat_id=chat_id,
        title="Test Chat",
        member_name="Sage",
        topic="Test Topic",
        messages=messages or [],
        summary="",
        created_at="2026-01-01T00:00:00Z",
        closed_at="",
        metadata={},
        council_members=council_members or ["Sage"],
        characters=characters or [],
        paused=False,
    )


# ─── ConversationSummarizer Unit Tests ────────────────────────


class TestConversationSummarizer:
    """Tests for the ConversationSummarizer class."""

    @pytest.fixture
    def mock_api_client(self):
        """Create a mock API client that returns a summary."""
        client = AsyncMock()
        client.chat = AsyncMock(return_value=ChatResponse(
            content="Summary of the conversation about various topics.",
            model="test-model",
            provider="openrouter",
        ))
        return client

    @pytest.fixture
    def summarizer(self, mock_api_client):
        """Create a summarizer with default settings."""
        return ConversationSummarizer(api_client=mock_api_client)

    @pytest.mark.asyncio
    async def test_short_conversation_returns_none(self, summarizer):
        """Conversations at or below threshold should return None."""
        messages = _make_messages(10)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_exact_threshold_returns_none(self, summarizer):
        """Exactly threshold messages should not trigger summarization."""
        messages = _make_messages(10)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_above_threshold_returns_result(self, summarizer):
        """More than threshold messages should trigger summarization."""
        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        assert isinstance(result, RollingSummaryResult)
        assert result.summary_text != ""
        assert len(result.recent_messages) == 5  # default recent_count
        assert result.summarized_count == 10  # 15 - 5

    @pytest.mark.asyncio
    async def test_recent_messages_are_last_n(self, summarizer):
        """Recent messages should be the last recent_count messages."""
        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        assert result.recent_messages == messages[-5:]

    @pytest.mark.asyncio
    async def test_custom_threshold(self, mock_api_client):
        """Custom threshold should be respected."""
        summarizer = ConversationSummarizer(
            api_client=mock_api_client, threshold=5, recent_count=2,
        )
        messages = _make_messages(6)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        assert len(result.recent_messages) == 2
        assert result.summarized_count == 4

    @pytest.mark.asyncio
    async def test_custom_threshold_below_not_triggered(self, mock_api_client):
        """Below custom threshold should not trigger summarization."""
        summarizer = ConversationSummarizer(
            api_client=mock_api_client, threshold=5, recent_count=2,
        )
        messages = _make_messages(5)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, mock_api_client):
        """Disabled summarizer should always return None."""
        summarizer = ConversationSummarizer(
            api_client=mock_api_client, enabled=False,
        )
        messages = _make_messages(20)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, summarizer, mock_api_client):
        """Second call with same messages should use cache (no LLM call)."""
        messages = _make_messages(15)

        result1 = await summarizer.get_summary("chat-1", messages)
        assert result1 is not None
        assert mock_api_client.chat.call_count == 1

        result2 = await summarizer.get_summary("chat-1", messages)
        assert result2 is not None
        # Should NOT have called API again
        assert mock_api_client.chat.call_count == 1
        assert result2.summary_text == result1.summary_text

    @pytest.mark.asyncio
    async def test_cache_miss_on_new_messages(self, summarizer, mock_api_client):
        """Adding new messages should invalidate cache and re-summarize."""
        messages = _make_messages(15)

        result1 = await summarizer.get_summary("chat-1", messages)
        assert result1 is not None
        assert mock_api_client.chat.call_count == 1

        # Add more messages — the "older" part changes
        messages_extended = messages + [
            _make_message(role="human", content="New question"),
            _make_message(role="agent", speaker="Sage", content="New answer"),
        ]

        result2 = await summarizer.get_summary("chat-1", messages_extended)
        assert result2 is not None
        # Should have called API again — cache miss
        assert mock_api_client.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, mock_api_client):
        """LLM failure should gracefully return None."""
        mock_api_client.chat = AsyncMock(side_effect=Exception("API failed"))
        summarizer = ConversationSummarizer(api_client=mock_api_client)

        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_estimate_populated(self, summarizer):
        """Token estimate should be positive for non-empty summaries."""
        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        assert result.token_estimate > 0

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, summarizer, mock_api_client):
        """invalidate_cache should force re-summarization."""
        messages = _make_messages(15)

        await summarizer.get_summary("chat-1", messages)
        assert mock_api_client.chat.call_count == 1

        summarizer.invalidate_cache("chat-1")

        await summarizer.get_summary("chat-1", messages)
        assert mock_api_client.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_clear_cache(self, summarizer, mock_api_client):
        """clear_cache should empty all cached summaries."""
        messages = _make_messages(15)

        await summarizer.get_summary("chat-1", messages)
        await summarizer.get_summary("chat-2", messages)
        assert mock_api_client.chat.call_count == 2

        summarizer.clear_cache()

        await summarizer.get_summary("chat-1", messages)
        await summarizer.get_summary("chat-2", messages)
        assert mock_api_client.chat.call_count == 4

    @pytest.mark.asyncio
    async def test_different_chat_ids_separate_caches(
        self, summarizer, mock_api_client,
    ):
        """Each chat_id should have its own cache entry."""
        messages = _make_messages(15)

        await summarizer.get_summary("chat-1", messages)
        await summarizer.get_summary("chat-2", messages)
        # Two separate LLM calls (different chat IDs)
        assert mock_api_client.chat.call_count == 2

    def test_repr(self, summarizer):
        """repr should be informative."""
        r = repr(summarizer)
        assert "ConversationSummarizer" in r
        assert "threshold=10" in r

    @pytest.mark.asyncio
    async def test_empty_summary_from_llm(self, mock_api_client):
        """Empty LLM response should still return a valid result."""
        mock_api_client.chat = AsyncMock(return_value=ChatResponse(
            content="",
            model="test-model",
            provider="openrouter",
        ))
        summarizer = ConversationSummarizer(api_client=mock_api_client)
        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        assert result.summary_text == ""

    @pytest.mark.asyncio
    async def test_none_content_from_llm(self, mock_api_client):
        """None content from LLM should be handled gracefully."""
        mock_api_client.chat = AsyncMock(return_value=ChatResponse(
            content=None,
            model="test-model",
            provider="openrouter",
        ))
        summarizer = ConversationSummarizer(api_client=mock_api_client)
        messages = _make_messages(15)
        result = await summarizer.get_summary("chat-1", messages)
        assert result is not None
        # Should have converted None to ""
        assert result.summary_text == ""


class TestComputeHash:
    """Tests for the content hash computation."""

    def test_same_messages_produce_same_hash(self):
        """Identical messages should produce identical hashes."""
        msgs1 = _make_messages(5)
        msgs2 = _make_messages(5)
        h1 = ConversationSummarizer._compute_hash(msgs1)
        h2 = ConversationSummarizer._compute_hash(msgs2)
        assert h1 == h2

    def test_different_messages_produce_different_hash(self):
        """Different messages should produce different hashes."""
        msgs1 = _make_messages(5)
        msgs2 = _make_messages(5)
        msgs2 = list(msgs2) + [_make_message(content="Extra")]
        h1 = ConversationSummarizer._compute_hash(msgs1)
        h2 = ConversationSummarizer._compute_hash(msgs2)
        assert h1 != h2

    def test_empty_messages(self):
        """Empty messages list should return a valid hash."""
        h = ConversationSummarizer._compute_hash([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest


class TestFormatMessagesForSummary:
    """Tests for message formatting used in LLM prompt."""

    def test_human_messages_labeled_correctly(self):
        """Human messages should be prefixed with 'Human:'."""
        msgs = [_make_message(role="human", speaker="Human", content="Hi")]
        text = ConversationSummarizer._format_messages_for_summary(msgs)
        assert text == "Human: Hi"

    def test_agent_messages_use_speaker_name(self):
        """Agent messages should use the speaker's name."""
        msgs = [_make_message(role="agent", speaker="Sage", content="Hello")]
        text = ConversationSummarizer._format_messages_for_summary(msgs)
        assert text == "Sage: Hello"

    def test_mixed_messages(self):
        """Mixed messages should be formatted correctly."""
        msgs = [
            _make_message(role="human", content="Question?"),
            _make_message(role="agent", speaker="Oracle", content="Answer."),
        ]
        text = ConversationSummarizer._format_messages_for_summary(msgs)
        assert "Human: Question?" in text
        assert "Oracle: Answer." in text


# ─── _build_human_chat_prompt Tests ───────────────────────────


class TestBuildHumanChatPromptWithSummary:
    """Tests for _build_human_chat_prompt with summary_result parameter."""

    def test_no_summary_uses_raw_messages(self):
        """Without summary_result, last 10 messages should be used."""
        member = _make_member()
        messages = _make_messages(15)
        prompt = _build_human_chat_prompt(
            member, messages, "Test Topic",
        )
        # Should contain the last 10 messages' content
        assert "Human message 10" in prompt
        assert "Human message 14" in prompt
        # Should NOT contain early messages
        assert "Human message 0" not in prompt

    def test_summary_injected(self):
        """With summary_result, the summary should be injected."""
        member = _make_member()
        messages = _make_messages(15)
        summary_result = RollingSummaryResult(
            summary_text="They discussed world building.",
            recent_messages=messages[-5:],
            summarized_count=10,
            token_estimate=20,
        )
        prompt = _build_human_chat_prompt(
            member, messages, "Test Topic",
            summary_result=summary_result,
        )
        assert "[Summary of prior conversation: They discussed world building.]" in prompt

    def test_summary_recent_messages_included(self):
        """Recent messages from summary should appear in the prompt."""
        member = _make_member()
        messages = _make_messages(15)
        summary_result = RollingSummaryResult(
            summary_text="Prior context.",
            recent_messages=messages[-5:],
            summarized_count=10,
        )
        prompt = _build_human_chat_prompt(
            member, messages, "Test Topic",
            summary_result=summary_result,
        )
        # Last 5 messages should be in the prompt
        assert "Human message 10" in prompt
        assert "Human message 14" in prompt
        # Early messages should NOT be in the prompt (they are summarized)
        assert "Human message 0" not in prompt
        assert "Human message 4" not in prompt

    def test_empty_messages_with_summary(self):
        """If messages list is empty, no conversation section appears."""
        member = _make_member()
        summary_result = RollingSummaryResult(
            summary_text="Some summary.",
            recent_messages=[],
            summarized_count=0,
        )
        prompt = _build_human_chat_prompt(
            member, [], "Test Topic",
            summary_result=summary_result,
        )
        # No "Conversation So Far" section when messages is empty
        assert "Summary" not in prompt


# ─── _build_api_messages Tests ────────────────────────────────


class TestBuildApiMessagesWithSummary:
    """Tests for HumanChat._build_api_messages with summary_result."""

    def _make_chat(self, tmp_path: Path) -> HumanChat:
        """Create a minimal HumanChat for testing."""
        from core.registry import CouncilRegistry
        registry = MagicMock(spec=CouncilRegistry)
        client = AsyncMock()
        return HumanChat(
            registry=registry,
            api_client=client,
            conversations_dir=tmp_path,
        )

    def test_no_summary_uses_last_10(self, tmp_path):
        """Without summary, raw last 10 messages should be used."""
        chat = self._make_chat(tmp_path)
        member = _make_member()
        messages = _make_messages(15)
        record = _make_record(messages=messages)

        api_msgs = chat._build_api_messages(record, member, "prompt text")
        # 10 history messages + 1 prompt message = 11
        assert len(api_msgs) == 11
        assert api_msgs[-1].content == "prompt text"

    def test_summary_prepended(self, tmp_path):
        """With summary, a summary message should be prepended."""
        chat = self._make_chat(tmp_path)
        member = _make_member()
        messages = _make_messages(15)
        record = _make_record(messages=messages)

        summary_result = RollingSummaryResult(
            summary_text="Context from earlier.",
            recent_messages=messages[-5:],
            summarized_count=10,
        )

        api_msgs = chat._build_api_messages(
            record, member, "prompt text",
            summary_result=summary_result,
        )
        # 1 summary + 5 recent + 1 prompt = 7
        assert len(api_msgs) == 7
        assert "[Summary of prior conversation:" in api_msgs[0].content
        assert "Context from earlier." in api_msgs[0].content
        assert api_msgs[0].role == "user"
        assert api_msgs[-1].content == "prompt text"

    def test_summary_message_roles(self, tmp_path):
        """Check that message roles are correctly assigned with summary."""
        chat = self._make_chat(tmp_path)
        member = _make_member("Sage")
        recent = [
            _make_message(role="human", content="Question"),
            _make_message(role="agent", speaker="Sage", content="Answer"),
            _make_message(role="agent", speaker="Oracle", content="Also answer"),
        ]
        record = _make_record(messages=_make_messages(15))

        summary_result = RollingSummaryResult(
            summary_text="Prior context.",
            recent_messages=recent,
            summarized_count=5,
        )

        api_msgs = chat._build_api_messages(
            record, member, "go",
            summary_result=summary_result,
        )
        # Summary(user) + Question(user) + Answer(assistant) + Also(user) + prompt(user) = 5
        assert len(api_msgs) == 5
        assert api_msgs[0].role == "user"    # summary
        assert api_msgs[1].role == "user"    # human question
        assert api_msgs[2].role == "assistant"  # Sage's own answer
        assert api_msgs[3].role == "user"    # Oracle's answer (other member)
        assert api_msgs[4].role == "user"    # prompt


# ─── Integration Tests ────────────────────────────────────────


class TestRollingSummaryIntegration:
    """Integration tests: summarizer wired into HumanChat response methods."""

    @pytest.fixture
    def setup_chat(self, tmp_path):
        """Set up a HumanChat with a mocked summarizer and API client."""
        from core.registry import CouncilRegistry

        # Mock registry
        registry = MagicMock(spec=CouncilRegistry)
        member = _make_member("Sage")
        registry.get.return_value = member
        registry.list_names.return_value = ["Sage"]
        registry.__contains__ = lambda self, name: name == "Sage"

        # Mock API client
        api_client = AsyncMock()
        api_client.chat = AsyncMock(return_value=ChatResponse(
            content="Agent response text",
            model="test-model",
            provider="openrouter",
        ))

        # Mock summarizer
        summarizer = AsyncMock(spec=ConversationSummarizer)
        summarizer.enabled = True

        # Create chat with summarizer
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        chat = HumanChat(
            registry=registry,
            api_client=api_client,
            conversations_dir=conv_dir,
            summarizer=summarizer,
        )

        return chat, summarizer, api_client, member, conv_dir

    @pytest.mark.asyncio
    async def test_get_agent_response_uses_summarizer(self, setup_chat):
        """get_agent_response should call summarizer when available."""
        chat, summarizer, api_client, member, conv_dir = setup_chat

        # Create a chat with many messages
        messages = _make_messages(15)
        record = _make_record(messages=messages)

        # Save the record so chat.get() can find it
        filepath = conv_dir / f"H-{record.chat_id}.json"
        filepath.write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )

        # Configure summarizer to return a result
        summary_result = RollingSummaryResult(
            summary_text="Prior discussion context.",
            recent_messages=messages[-5:],
            summarized_count=10,
        )
        summarizer.get_summary = AsyncMock(return_value=summary_result)

        # Patch APIKeyManager to avoid file system access
        with patch("core.api_keys.APIKeyManager") as mock_akm:
            mock_akm.return_value.get_user_description.return_value = ""
            mock_akm.return_value.get_user_name.return_value = ""

            updated_record, response = await chat.get_agent_response(
                record.chat_id,
            )

        # Verify summarizer was called
        summarizer.get_summary.assert_called_once()
        call_args = summarizer.get_summary.call_args
        assert call_args[0][0] == record.chat_id  # chat_id

    @pytest.mark.asyncio
    async def test_summarizer_failure_falls_back(self, setup_chat):
        """Summarizer failure should not crash the response."""
        chat, summarizer, api_client, member, conv_dir = setup_chat

        messages = _make_messages(15)
        record = _make_record(messages=messages)

        filepath = conv_dir / f"H-{record.chat_id}.json"
        filepath.write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )

        # Summarizer raises an error
        summarizer.get_summary = AsyncMock(side_effect=Exception("LLM down"))

        with patch("core.api_keys.APIKeyManager") as mock_akm:
            mock_akm.return_value.get_user_description.return_value = ""
            mock_akm.return_value.get_user_name.return_value = ""

            # Should not raise
            updated_record, response = await chat.get_agent_response(
                record.chat_id,
            )

        # Response should still be generated (fallback to raw messages)
        assert response is not None

    @pytest.mark.asyncio
    async def test_no_summarizer_uses_legacy_behavior(self, tmp_path):
        """Without a summarizer, legacy raw-message behavior should apply."""
        from core.registry import CouncilRegistry

        registry = MagicMock(spec=CouncilRegistry)
        member = _make_member("Sage")
        registry.get.return_value = member
        registry.list_names.return_value = ["Sage"]
        registry.__contains__ = lambda self, name: name == "Sage"

        api_client = AsyncMock()
        api_client.chat = AsyncMock(return_value=ChatResponse(
            content="Reply",
            model="test-model",
            provider="openrouter",
        ))

        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()

        # No summarizer provided
        chat = HumanChat(
            registry=registry,
            api_client=api_client,
            conversations_dir=conv_dir,
        )

        messages = _make_messages(15)
        record = _make_record(messages=messages)
        filepath = conv_dir / f"H-{record.chat_id}.json"
        filepath.write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )

        with patch("core.api_keys.APIKeyManager") as mock_akm:
            mock_akm.return_value.get_user_description.return_value = ""
            mock_akm.return_value.get_user_name.return_value = ""

            updated_record, response = await chat.get_agent_response(
                record.chat_id,
            )

        assert response is not None
        assert response.content == "Reply"


class TestRollingSummaryResultDataclass:
    """Tests for RollingSummaryResult dataclass."""

    def test_default_values(self):
        """Default values should be set correctly."""
        result = RollingSummaryResult(
            summary_text="test",
            recent_messages=[],
        )
        assert result.summarized_count == 0
        assert result.token_estimate == 0

    def test_all_fields(self):
        """All fields should be accessible."""
        msgs = _make_messages(3)
        result = RollingSummaryResult(
            summary_text="summary",
            recent_messages=msgs,
            summarized_count=7,
            token_estimate=50,
        )
        assert result.summary_text == "summary"
        assert len(result.recent_messages) == 3
        assert result.summarized_count == 7
        assert result.token_estimate == 50


class TestCachedSummaryDataclass:
    """Tests for CachedSummary dataclass."""

    def test_fields(self):
        """CachedSummary should store all fields correctly."""
        cached = CachedSummary(
            content_hash="abc123",
            summary_text="summary text",
            message_count=10,
        )
        assert cached.content_hash == "abc123"
        assert cached.summary_text == "summary text"
        assert cached.message_count == 10

    def test_frozen(self):
        """CachedSummary should be immutable."""
        cached = CachedSummary(
            content_hash="abc", summary_text="test", message_count=5,
        )
        with pytest.raises(AttributeError):
            cached.content_hash = "xyz"
