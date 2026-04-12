"""
Tests for Jericho — Agent-to-Agent Chat (F-008)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_member
from core.agent_chat import (
    AgentChat,
    ChatError,
    ChatExchange,
    ChatNotFoundError,
    ChatValidationError,
    ConversationRecord,
    _build_chat_prompt,
    _build_opening_prompt,
)
from core.api_client import ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.registry import CouncilMember, CouncilRegistry


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def agent_chat(registry, api_client, tmp_dirs):
    shared = SharedMemory(shared_dir=tmp_dirs["shared"])
    return AgentChat(
        registry=registry,
        api_client=api_client,
        conversations_dir=tmp_dirs["conversations"],
        shared_memory=shared,
    )


# ─── ChatExchange Tests ──────────────────────────────────────


class TestChatExchange:
    def test_fields(self):
        ex = ChatExchange(speaker="Sage", content="Hello")
        assert ex.speaker == "Sage"
        assert ex.content == "Hello"
        assert ex.timestamp == ""
        assert ex.metadata == {}

    def test_frozen(self):
        ex = ChatExchange(speaker="Sage", content="Hello")
        with pytest.raises(AttributeError):
            ex.speaker = "Logic"  # type: ignore

    def test_to_dict_roundtrip(self):
        ex = ChatExchange.create("Sage", "Hello", metadata={"key": "val"})
        d = ex.to_dict()
        restored = ChatExchange.from_dict(d)
        assert restored.speaker == ex.speaker
        assert restored.content == ex.content
        assert restored.timestamp == ex.timestamp
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        ex = ChatExchange.create("Sage", "Hello")
        assert ex.speaker == "Sage"
        assert ex.content == "Hello"
        assert ex.timestamp != ""

    def test_metadata_preserved(self):
        ex = ChatExchange.create(
            "Sage", "test", metadata={"model": "test-model"}
        )
        assert ex.metadata["model"] == "test-model"


# ─── ConversationRecord Tests ────────────────────────────────


class TestConversationRecord:
    def test_fields(self):
        rec = ConversationRecord(
            conversation_id="C-001", title="Test"
        )
        assert rec.conversation_id == "C-001"
        assert rec.title == "Test"
        assert rec.participants == []
        assert rec.exchanges == []
        assert rec.topic == ""

    def test_frozen(self):
        rec = ConversationRecord(
            conversation_id="C-001", title="Test"
        )
        with pytest.raises(AttributeError):
            rec.title = "New"  # type: ignore

    def test_to_dict_roundtrip(self):
        ex = ChatExchange.create("Sage", "Hello")
        rec = ConversationRecord(
            conversation_id="C-001",
            title="Roundtrip Test",
            participants=["Sage", "Logic"],
            topic="Ethics",
            exchanges=[ex],
            metadata={"key": "value"},
        )
        d = rec.to_dict()
        restored = ConversationRecord.from_dict(d)
        assert restored.conversation_id == rec.conversation_id
        assert restored.title == rec.title
        assert len(restored.exchanges) == 1
        assert restored.exchanges[0].speaker == "Sage"
        assert restored.participants == ["Sage", "Logic"]
        assert restored.topic == "Ethics"
        assert restored.metadata == {"key": "value"}

    def test_create_factory(self):
        rec = ConversationRecord.create(
            "C-001", "Ethics Chat",
            participants=["Sage", "Logic"],
            topic="AI autonomy",
        )
        assert rec.conversation_id == "C-001"
        assert rec.created_at != ""
        assert rec.topic == "AI autonomy"

    def test_create_empty_id_raises(self):
        with pytest.raises(ChatValidationError) as exc_info:
            ConversationRecord.create("", "Title")
        assert "Conversation ID" in str(exc_info.value)

    def test_create_whitespace_strip(self):
        rec = ConversationRecord.create("  C-001  ", "  Test  ")
        assert rec.conversation_id == "C-001"
        assert rec.title == "Test"


# ─── AgentChat Init Tests ────────────────────────────────────


class TestAgentChatInit:
    def test_creates_dir(self, agent_chat, tmp_dirs):
        assert tmp_dirs["conversations"].exists()

    def test_properties(self, agent_chat, tmp_dirs, registry):
        assert agent_chat.directory == tmp_dirs["conversations"]
        assert agent_chat.registry is registry

    def test_repr(self, agent_chat):
        r = repr(agent_chat)
        assert "AgentChat" in r
        assert "conversations=0" in r


# ─── Create Conversation Tests ───────────────────────────────


class TestCreateConversation:
    def test_basic_creation(self, agent_chat):
        rec = agent_chat.create_conversation(
            "C-001", "Ethics Chat",
            participants=["Sage", "Logic"],
        )
        assert rec.conversation_id == "C-001"
        assert rec.title == "Ethics Chat"
        assert rec.participants == ["Sage", "Logic"]

    def test_with_options(self, agent_chat):
        rec = agent_chat.create_conversation(
            "C-001", "Debate",
            participants=["Sage", "Logic"],
            topic="AI Ethics",
            metadata={"priority": "high"},
        )
        assert rec.topic == "AI Ethics"
        assert rec.metadata["priority"] == "high"

    def test_persistence(self, agent_chat, tmp_dirs):
        agent_chat.create_conversation(
            "C-001", "Persist Test",
            participants=["Sage", "Logic"],
        )
        filepath = tmp_dirs["conversations"] / "C-C-001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["conversation_id"] == "C-001"

    def test_duplicate_raises(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "First",
            participants=["Sage", "Logic"],
        )
        with pytest.raises(ChatError) as exc_info:
            agent_chat.create_conversation(
                "C-001", "Second",
                participants=["Sage", "Logic"],
            )
        assert "already exists" in str(exc_info.value)

    def test_unknown_participant_raises(self, agent_chat):
        with pytest.raises(ChatValidationError) as exc_info:
            agent_chat.create_conversation(
                "C-001", "Test",
                participants=["Sage", "UnknownMember"],
            )
        assert "Unknown council member" in str(exc_info.value)

    def test_single_participant_rejected(self, agent_chat):
        with pytest.raises(ChatValidationError) as exc_info:
            agent_chat.create_conversation(
                "C-001", "Solo",
                participants=["Sage"],
            )
        assert "At least 2" in str(exc_info.value)

    def test_sequential_ids(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "First", participants=["Sage", "Logic"]
        )
        agent_chat.create_conversation(
            "C-002", "Second", participants=["Sage", "Logic"]
        )
        assert agent_chat.has_conversation("C-001")
        assert agent_chat.has_conversation("C-002")


# ─── Exchange Tests ──────────────────────────────────────────


class TestExchange:
    def _create_active_convo(self, agent_chat):
        return agent_chat.create_conversation(
            "C-001", "Exchange Test",
            participants=["Sage", "Logic"],
            topic="AI Ethics",
        )

    def test_basic_exchange(self, agent_chat):
        self._create_active_convo(agent_chat)
        loop = asyncio.new_event_loop()
        rec, response = loop.run_until_complete(
            agent_chat.exchange("C-001", "Sage")
        )
        assert len(rec.exchanges) == 1
        assert rec.exchanges[0].speaker == "Sage"
        assert response.content == "Acknowledged."

    def test_records_messages(self, agent_chat):
        self._create_active_convo(agent_chat)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(agent_chat.exchange("C-001", "Sage"))
        rec, _ = loop.run_until_complete(
            agent_chat.exchange("C-001", "Logic")
        )
        assert len(rec.exchanges) == 2
        assert rec.exchanges[0].speaker == "Sage"
        assert rec.exchanges[1].speaker == "Logic"

    def test_api_called(self, agent_chat, api_client):
        self._create_active_convo(agent_chat)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(agent_chat.exchange("C-001", "Sage"))
        api_client.chat.assert_called_once()

    def test_memory_recorded(self, agent_chat, tmp_dirs):
        self._create_active_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Sage")
            )
            mock_mem_instance.append_session_event.assert_called_once()
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.event_type == "agent_chat"
            assert entry.source == "agent_chat"

    def test_wrong_participant_raises(self, agent_chat):
        self._create_active_convo(agent_chat)
        loop = asyncio.new_event_loop()
        with pytest.raises(ChatValidationError) as exc_info:
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Spark")
            )
        assert "not a participant" in str(exc_info.value)

    def test_closed_conversation_raises(self, agent_chat):
        self._create_active_convo(agent_chat)
        agent_chat.close_conversation("C-001")
        loop = asyncio.new_event_loop()
        with pytest.raises(ChatError) as exc_info:
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Sage")
            )
        assert "closed" in str(exc_info.value)

    def test_not_found_raises(self, agent_chat):
        loop = asyncio.new_event_loop()
        with pytest.raises(ChatNotFoundError):
            loop.run_until_complete(
                agent_chat.exchange("MISSING", "Sage")
            )


# ─── Converse Tests ──────────────────────────────────────────


class TestConverse:
    def _create_convo(self, agent_chat):
        return agent_chat.create_conversation(
            "C-001", "Converse Test",
            participants=["Sage", "Logic"],
            topic="AI Ethics",
        )

    def test_two_members_one_round(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()
        rec = loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
        )
        assert len(rec.exchanges) == 2
        assert rec.exchanges[0].speaker == "Sage"
        assert rec.exchanges[1].speaker == "Logic"

    def test_multiple_rounds(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()
        rec = loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics", rounds=2)
        )
        assert len(rec.exchanges) == 4
        assert rec.exchanges[0].speaker == "Sage"
        assert rec.exchanges[1].speaker == "Logic"
        assert rec.exchanges[2].speaker == "Sage"
        assert rec.exchanges[3].speaker == "Logic"

    def test_records_all_exchanges(self, agent_chat, tmp_dirs):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
        )
        filepath = tmp_dirs["conversations"] / "C-C-001.json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert len(data["exchanges"]) == 2

    def test_api_calls_match_members(self, agent_chat, api_client):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics", rounds=2)
        )
        assert api_client.chat.call_count == 4

    def test_memory_per_member(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
            )
            # Two exchange() calls → two memory events
            assert mock_mem_instance.append_session_event.call_count == 2

    def test_closed_conversation_raises(self, agent_chat):
        self._create_convo(agent_chat)
        agent_chat.close_conversation("C-001")
        loop = asyncio.new_event_loop()
        with pytest.raises(ChatError) as exc_info:
            loop.run_until_complete(
                agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
            )
        assert "closed" in str(exc_info.value)

    def test_empty_members_raises(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()
        with pytest.raises(ChatValidationError) as exc_info:
            loop.run_until_complete(
                agent_chat.converse("C-001", [], "Ethics")
            )
        assert "At least one" in str(exc_info.value)


# ─── Close Conversation Tests ────────────────────────────────


class TestCloseConversation:
    def _create_convo(self, agent_chat):
        return agent_chat.create_conversation(
            "C-001", "Close Test",
            participants=["Sage", "Logic"],
            topic="AI Ethics",
        )

    def test_basic_close(self, agent_chat):
        self._create_convo(agent_chat)
        rec = agent_chat.close_conversation("C-001")
        assert rec.closed_at != ""

    def test_close_with_summary(self, agent_chat):
        self._create_convo(agent_chat)
        rec = agent_chat.close_conversation(
            "C-001", summary="Great discussion."
        )
        assert rec.summary == "Great discussion."
        assert rec.closed_at != ""

    def test_close_auto_summary(self, agent_chat):
        self._create_convo(agent_chat)
        rec = agent_chat.close_conversation("C-001")
        assert rec.summary != ""
        assert "Close Test" in rec.summary

    def test_close_records_shared_memory(self, agent_chat, tmp_dirs):
        self._create_convo(agent_chat)
        agent_chat.close_conversation("C-001", summary="Done.")
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["type"] == "conversation_closed"
        assert decisions[0]["conversation_id"] == "C-001"

    def test_already_closed_raises(self, agent_chat):
        self._create_convo(agent_chat)
        agent_chat.close_conversation("C-001")
        with pytest.raises(ChatError) as exc_info:
            agent_chat.close_conversation("C-001")
        assert "already closed" in str(exc_info.value)


# ─── Query Tests ─────────────────────────────────────────────


class TestQueryMethods:
    def test_get_existing(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Test", participants=["Sage", "Logic"]
        )
        rec = agent_chat.get("C-001")
        assert rec.conversation_id == "C-001"

    def test_get_not_found(self, agent_chat):
        with pytest.raises(ChatNotFoundError):
            agent_chat.get("MISSING")

    def test_list_all(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "First", participants=["Sage", "Logic"]
        )
        agent_chat.create_conversation(
            "C-002", "Second", participants=["Sage", "Logic"]
        )
        convos = agent_chat.list_conversations()
        assert len(convos) == 2

    def test_list_filter_participant(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "First", participants=["Sage", "Logic"]
        )
        agent_chat.create_conversation(
            "C-002", "Second", participants=["Sage", "Spark"]
        )
        logic_convos = agent_chat.list_conversations(participant="Logic")
        assert len(logic_convos) == 1
        assert logic_convos[0].conversation_id == "C-001"

    def test_list_filter_closed(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Open", participants=["Sage", "Logic"]
        )
        agent_chat.create_conversation(
            "C-002", "Closed", participants=["Sage", "Logic"]
        )
        agent_chat.close_conversation("C-002")
        open_convos = agent_chat.list_conversations(closed=False)
        closed_convos = agent_chat.list_conversations(closed=True)
        assert len(open_convos) == 1
        assert len(closed_convos) == 1

    def test_has_conversation(self, agent_chat):
        assert not agent_chat.has_conversation("C-001")
        agent_chat.create_conversation(
            "C-001", "Test", participants=["Sage", "Logic"]
        )
        assert agent_chat.has_conversation("C-001")

    def test_get_exchanges(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Test", participants=["Sage", "Logic"]
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
        )
        all_ex = agent_chat.get_exchanges("C-001")
        sage_ex = agent_chat.get_exchanges("C-001", speaker="Sage")
        assert len(all_ex) == 2
        assert len(sage_ex) == 1
        assert sage_ex[0].speaker == "Sage"

    def test_corrupt_file_skipped(self, agent_chat, tmp_dirs):
        corrupt = tmp_dirs["conversations"] / "C-CORRUPT.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("not json!", encoding="utf-8")
        agent_chat.create_conversation(
            "C-001", "Good", participants=["Sage", "Logic"]
        )
        convos = agent_chat.list_conversations()
        assert len(convos) == 1


# ─── Prompt Builder Tests ────────────────────────────────────


class TestPromptBuilders:
    def test_opening_prompt_content(self):
        member = make_member("Sage")
        prompt = _build_opening_prompt(member, "Logic", "AI Ethics")
        assert "Sage" in prompt
        assert "Logic" in prompt
        assert "AI Ethics" in prompt

    def test_opening_prompt_without_topic(self):
        member = make_member("Sage")
        prompt = _build_opening_prompt(member, "Logic", "")
        assert "Sage" in prompt
        assert "Logic" in prompt

    def test_chat_prompt_with_history(self):
        member = make_member("Logic")
        exchanges = [
            ChatExchange.create("Sage", "I think ethics matter."),
        ]
        prompt = _build_chat_prompt(member, "Sage", exchanges, "Ethics")
        assert "Sage" in prompt
        assert "ethics matter" in prompt
        assert "Logic" in prompt

    def test_chat_prompt_with_topic(self):
        member = make_member("Logic")
        prompt = _build_chat_prompt(member, "Sage", [], "AI Freedom")
        assert "AI Freedom" in prompt

    def test_context_limit(self):
        member = make_member("Sage")
        # Generate more than 10 exchanges
        exchanges = [
            ChatExchange.create(f"Speaker{i}", f"Message {i}")
            for i in range(15)
        ]
        prompt = _build_chat_prompt(member, "Logic", exchanges, "Topic")
        # Should only show last 10
        assert "Message 14" in prompt
        assert "Message 5" in prompt
        assert "Message 4" not in prompt


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(ChatNotFoundError, ChatError)
        assert issubclass(ChatValidationError, ChatError)

    def test_not_found_fields(self):
        err = ChatNotFoundError("C-999")
        assert err.conversation_id == "C-999"
        assert "C-999" in str(err)

    def test_validation_fields(self):
        err = ChatValidationError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)

    def test_chat_error_base(self):
        err = ChatError("something failed")
        assert "something failed" in str(err)


# ─── Edge Case Tests ─────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Ünïcödé Chät",
            participants=["Sage", "Logic"],
            topic="日本語トピック",
        )
        rec = agent_chat.get("C-001")
        assert rec.title == "Ünïcödé Chät"
        assert rec.topic == "日本語トピック"

    def test_long_content(self, agent_chat, api_client):
        long_content = "A" * 10000
        api_client.chat = AsyncMock(return_value=ChatResponse(
            content=long_content,
            model="test-model",
            provider="openrouter",
        ))
        agent_chat.create_conversation(
            "C-001", "Long Test",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.new_event_loop()
        rec, resp = loop.run_until_complete(
            agent_chat.exchange("C-001", "Sage")
        )
        assert len(rec.exchanges[0].content) == 10000

    def test_three_way_conversation(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Three Way",
            participants=["Sage", "Logic", "Spark"],
            topic="Ethics",
        )
        loop = asyncio.new_event_loop()
        rec = loop.run_until_complete(
            agent_chat.converse(
                "C-001", ["Sage", "Logic", "Spark"], "Ethics"
            )
        )
        assert len(rec.exchanges) == 3
        assert rec.exchanges[0].speaker == "Sage"
        assert rec.exchanges[1].speaker == "Logic"
        assert rec.exchanges[2].speaker == "Spark"

    def test_persistence_roundtrip(self, agent_chat):
        agent_chat.create_conversation(
            "C-001", "Roundtrip",
            participants=["Sage", "Logic"],
            topic="Test",
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Test")
        )
        # Reload from disk
        rec = agent_chat.get("C-001")
        assert len(rec.exchanges) == 2
        assert rec.exchanges[0].speaker == "Sage"
        assert rec.exchanges[1].speaker == "Logic"

    def test_full_lifecycle(self, agent_chat, tmp_dirs):
        # Create
        rec = agent_chat.create_conversation(
            "C-001", "Full Lifecycle",
            participants=["Sage", "Logic"],
            topic="Ethics",
        )
        assert rec.closed_at == ""

        # Converse
        loop = asyncio.new_event_loop()
        rec = loop.run_until_complete(
            agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics", rounds=2)
        )
        assert len(rec.exchanges) == 4

        # Close
        rec = agent_chat.close_conversation("C-001", summary="Done.")
        assert rec.closed_at != ""
        assert rec.summary == "Done."

        # Verify shared memory
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        history = shared.read_history()
        assert "Full Lifecycle" in history


# ─── Memory Integration Tests ────────────────────────────────


class TestMemoryIntegration:
    def _create_convo(self, agent_chat):
        return agent_chat.create_conversation(
            "C-001", "Memory Test",
            participants=["Sage", "Logic"],
            topic="Ethics",
        )

    def test_each_speaker_recorded(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
            )
            assert mock_mem_instance.append_session_event.call_count == 2

    def test_both_sides_recorded(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        member_names_used = []
        with patch("core.agent_chat.AgentMemory") as MockMem:
            def capture_name(name):
                member_names_used.append(name)
                return MagicMock()
            MockMem.side_effect = capture_name
            loop.run_until_complete(
                agent_chat.converse("C-001", ["Sage", "Logic"], "Ethics")
            )
        assert "Sage" in member_names_used
        assert "Logic" in member_names_used

    def test_memory_content(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Sage")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert "Logic" in entry.content  # partner name
            assert "Ethics" in entry.content  # topic

    def test_session_id_in_memory(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Sage")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.session_id == "C-001"

    def test_memory_source(self, agent_chat):
        self._create_convo(agent_chat)
        loop = asyncio.new_event_loop()

        with patch("core.agent_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                agent_chat.exchange("C-001", "Sage")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.source == "agent_chat"
