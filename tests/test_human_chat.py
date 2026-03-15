"""
Tests for Jericho — Human-to-Agent Chat (F-009)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.human_chat import (
    HumanChat,
    HumanChatError,
    HumanChatMessage,
    HumanChatNotFoundError,
    HumanChatRecord,
    HumanChatValidationError,
    _build_human_chat_prompt,
)
from core.api_client import ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.registry import CouncilMember, CouncilRegistry


# ─── Fixtures ──────────────────────────────────────────────────


def _make_member(
    name: str = "Sage",
    role: str = "Ethics",
    api_provider: str = "openrouter",
    model: str = "test-model",
) -> CouncilMember:
    return CouncilMember(
        name=name,
        role=role,
        description=f"{name} description",
        api_provider=api_provider,
        model=model,
        system_prompt=f"You are {name}.",
    )


def _mock_registry(*members: CouncilMember) -> CouncilRegistry:
    """Build a mock registry pre-loaded with given members."""
    reg = MagicMock(spec=CouncilRegistry)
    member_dict = {m.name.lower(): m for m in members}
    reg.get.side_effect = lambda name: member_dict[name.strip().lower()]
    reg.list_names.return_value = [m.name for m in members]
    reg.list_members.return_value = list(members)
    reg.__len__ = lambda self: len(members)
    reg.__contains__ = lambda self, n: n.strip().lower() in member_dict
    return reg


def _mock_api_client(content: str = "Test response.") -> AsyncMock:
    """Build a mock async API client."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=ChatResponse(
        content=content,
        model="test-model",
        provider="openrouter",
    ))
    return client


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    """Provide temp dirs for conversations and memories."""
    return {
        "conversations": tmp_path / "conversations",
        "memories": tmp_path / "memories",
        "shared": tmp_path / "memories" / "shared",
    }


@pytest.fixture
def members():
    sage = _make_member("Sage", "Ethics")
    logic = _make_member("Logic", "Systems")
    spark = _make_member("Spark", "Creative", api_provider="mancer")
    return sage, logic, spark


@pytest.fixture
def registry(members):
    return _mock_registry(*members)


@pytest.fixture
def api_client():
    return _mock_api_client()


@pytest.fixture
def human_chat(registry, api_client, tmp_dirs):
    shared = SharedMemory(shared_dir=tmp_dirs["shared"])
    return HumanChat(
        registry=registry,
        api_client=api_client,
        conversations_dir=tmp_dirs["conversations"],
        shared_memory=shared,
    )


# ─── HumanChatMessage Tests ─────────────────────────────────


class TestHumanChatMessage:
    def test_fields(self):
        msg = HumanChatMessage(role="human", speaker="Human", content="Hi")
        assert msg.role == "human"
        assert msg.speaker == "Human"
        assert msg.content == "Hi"
        assert msg.timestamp == ""
        assert msg.metadata == {}

    def test_frozen(self):
        msg = HumanChatMessage(role="human", speaker="Human", content="Hi")
        with pytest.raises(AttributeError):
            msg.content = "Changed"  # type: ignore

    def test_to_dict_roundtrip(self):
        msg = HumanChatMessage.create(
            "human", "Human", "Hello", metadata={"key": "val"}
        )
        d = msg.to_dict()
        restored = HumanChatMessage.from_dict(d)
        assert restored.role == msg.role
        assert restored.speaker == msg.speaker
        assert restored.content == msg.content
        assert restored.timestamp == msg.timestamp
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        msg = HumanChatMessage.create("human", "Human", "Hello")
        assert msg.role == "human"
        assert msg.speaker == "Human"
        assert msg.timestamp != ""

    def test_metadata_preserved(self):
        msg = HumanChatMessage.create(
            "agent", "Sage", "Response", metadata={"model": "test-model"}
        )
        assert msg.metadata["model"] == "test-model"

    def test_invalid_role_raises(self):
        with pytest.raises(HumanChatValidationError) as exc_info:
            HumanChatMessage.create("invalid", "Someone", "text")
        assert "Invalid role" in str(exc_info.value)


# ─── HumanChatRecord Tests ──────────────────────────────────


class TestHumanChatRecord:
    def test_fields(self):
        rec = HumanChatRecord(chat_id="H-001", title="Test")
        assert rec.chat_id == "H-001"
        assert rec.title == "Test"
        assert rec.member_name == ""
        assert rec.messages == []
        assert rec.topic == ""

    def test_frozen(self):
        rec = HumanChatRecord(chat_id="H-001", title="Test")
        with pytest.raises(AttributeError):
            rec.title = "New"  # type: ignore

    def test_to_dict_roundtrip(self):
        msg = HumanChatMessage.create("human", "Human", "Hello")
        rec = HumanChatRecord(
            chat_id="H-001",
            title="Roundtrip Test",
            member_name="Sage",
            topic="Ethics",
            messages=[msg],
            metadata={"key": "value"},
        )
        d = rec.to_dict()
        restored = HumanChatRecord.from_dict(d)
        assert restored.chat_id == rec.chat_id
        assert restored.title == rec.title
        assert len(restored.messages) == 1
        assert restored.messages[0].role == "human"
        assert restored.member_name == "Sage"
        assert restored.topic == "Ethics"
        assert restored.metadata == {"key": "value"}

    def test_create_factory(self):
        rec = HumanChatRecord.create(
            "H-001", "Ethics Q&A",
            member_name="Sage",
            topic="AI autonomy",
        )
        assert rec.chat_id == "H-001"
        assert rec.created_at != ""
        assert rec.member_name == "Sage"
        assert rec.topic == "AI autonomy"

    def test_create_empty_id_raises(self):
        with pytest.raises(HumanChatValidationError) as exc_info:
            HumanChatRecord.create("", "Title")
        assert "Chat ID" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(HumanChatValidationError) as exc_info:
            HumanChatRecord.create("H-001", "")
        assert "Title" in str(exc_info.value)

    def test_create_whitespace_strip(self):
        rec = HumanChatRecord.create("  H-001  ", "  Test  ")
        assert rec.chat_id == "H-001"
        assert rec.title == "Test"


# ─── HumanChat Init Tests ───────────────────────────────────


class TestHumanChatInit:
    def test_creates_dir(self, human_chat, tmp_dirs):
        assert tmp_dirs["conversations"].exists()

    def test_properties(self, human_chat, tmp_dirs, registry):
        assert human_chat.directory == tmp_dirs["conversations"]
        assert human_chat.registry is registry

    def test_repr(self, human_chat):
        r = repr(human_chat)
        assert "HumanChat" in r
        assert "chats=0" in r


# ─── Create Chat Tests ──────────────────────────────────────


class TestCreateChat:
    def test_basic_creation(self, human_chat):
        rec = human_chat.create_chat(
            "H-001", "Ethics Q&A", member_name="Sage"
        )
        assert rec.chat_id == "H-001"
        assert rec.title == "Ethics Q&A"
        assert rec.member_name == "Sage"

    def test_with_options(self, human_chat):
        rec = human_chat.create_chat(
            "H-001", "Debate",
            member_name="Sage",
            topic="AI Ethics",
            metadata={"priority": "high"},
        )
        assert rec.topic == "AI Ethics"
        assert rec.metadata["priority"] == "high"

    def test_persistence(self, human_chat, tmp_dirs):
        human_chat.create_chat(
            "H-001", "Persist Test", member_name="Sage"
        )
        filepath = tmp_dirs["conversations"] / "H-H-001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["chat_id"] == "H-001"

    def test_duplicate_raises(self, human_chat):
        human_chat.create_chat("H-001", "First", member_name="Sage")
        with pytest.raises(HumanChatError) as exc_info:
            human_chat.create_chat("H-001", "Second", member_name="Logic")
        assert "already exists" in str(exc_info.value)

    def test_unknown_member_raises(self, human_chat):
        with pytest.raises(HumanChatValidationError) as exc_info:
            human_chat.create_chat(
                "H-001", "Test", member_name="UnknownMember"
            )
        assert "Unknown council member" in str(exc_info.value)

    def test_sequential_ids(self, human_chat):
        human_chat.create_chat("H-001", "First", member_name="Sage")
        human_chat.create_chat("H-002", "Second", member_name="Logic")
        assert human_chat.has_chat("H-001")
        assert human_chat.has_chat("H-002")


# ─── Send Human Message Tests ───────────────────────────────


class TestSendHumanMessage:
    def test_basic_send(self, human_chat):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        rec = human_chat.send_human_message("H-001", "Hello, Sage!")
        assert len(rec.messages) == 1
        assert rec.messages[0].role == "human"
        assert rec.messages[0].speaker == "Human"
        assert rec.messages[0].content == "Hello, Sage!"

    def test_multiple_messages(self, human_chat):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        human_chat.send_human_message("H-001", "First")
        rec = human_chat.send_human_message("H-001", "Second")
        assert len(rec.messages) == 2
        assert rec.messages[0].content == "First"
        assert rec.messages[1].content == "Second"

    def test_persistence(self, human_chat, tmp_dirs):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        human_chat.send_human_message("H-001", "Hello!")
        filepath = tmp_dirs["conversations"] / "H-H-001.json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Hello!"

    def test_closed_raises(self, human_chat):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        human_chat.close_chat("H-001")
        with pytest.raises(HumanChatError) as exc_info:
            human_chat.send_human_message("H-001", "Hello")
        assert "closed" in str(exc_info.value)

    def test_not_found_raises(self, human_chat):
        with pytest.raises(HumanChatNotFoundError):
            human_chat.send_human_message("MISSING", "Hello")

    def test_with_metadata(self, human_chat):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        rec = human_chat.send_human_message(
            "H-001", "Hello", metadata={"source": "cli"}
        )
        assert rec.messages[0].metadata["source"] == "cli"


# ─── Get Agent Response Tests ────────────────────────────────


class TestGetAgentResponse:
    def _create_chat_with_msg(self, human_chat):
        human_chat.create_chat(
            "H-001", "Agent Test",
            member_name="Sage",
            topic="AI Ethics",
        )
        human_chat.send_human_message("H-001", "What do you think?")

    def test_basic_response(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()
        rec, response = loop.run_until_complete(
            human_chat.get_agent_response("H-001")
        )
        assert len(rec.messages) == 2
        assert rec.messages[0].role == "human"
        assert rec.messages[1].role == "agent"
        assert rec.messages[1].speaker == "Sage"
        assert response.content == "Test response."

    def test_api_called(self, human_chat, api_client):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(human_chat.get_agent_response("H-001"))
        api_client.chat.assert_called_once()

    def test_memory_recorded(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()

        with patch("core.human_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
            mock_mem_instance.append_session_event.assert_called_once()
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.event_type == "human_chat"
            assert entry.source == "human_chat"

    def test_closed_raises(self, human_chat):
        self._create_chat_with_msg(human_chat)
        human_chat.close_chat("H-001")
        loop = asyncio.get_event_loop()
        with pytest.raises(HumanChatError) as exc_info:
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
        assert "closed" in str(exc_info.value)

    def test_not_found_raises(self, human_chat):
        loop = asyncio.get_event_loop()
        with pytest.raises(HumanChatNotFoundError):
            loop.run_until_complete(
                human_chat.get_agent_response("MISSING")
            )

    def test_history_built_correctly(self, human_chat, api_client):
        human_chat.create_chat(
            "H-001", "History Test", member_name="Sage"
        )
        human_chat.send_human_message("H-001", "First question")

        loop = asyncio.get_event_loop()
        loop.run_until_complete(human_chat.get_agent_response("H-001"))

        # Check the API was called with messages including human's input
        call_args = api_client.chat.call_args
        messages = call_args[0][1]  # second positional arg
        # Should contain at least the human message + the prompt
        assert len(messages) >= 2
        # First message should be the human message (user role)
        assert messages[0].role == "user"

    def test_multi_turn(self, human_chat, api_client):
        """Human and agent alternate messages correctly."""
        human_chat.create_chat(
            "H-001", "Multi-turn", member_name="Sage"
        )
        loop = asyncio.get_event_loop()

        # Turn 1: human asks, agent responds
        human_chat.send_human_message("H-001", "Question 1")
        loop.run_until_complete(human_chat.get_agent_response("H-001"))

        # Turn 2: human asks again, agent responds
        human_chat.send_human_message("H-001", "Question 2")
        rec, _ = loop.run_until_complete(
            human_chat.get_agent_response("H-001")
        )

        assert len(rec.messages) == 4
        assert rec.messages[0].role == "human"
        assert rec.messages[1].role == "agent"
        assert rec.messages[2].role == "human"
        assert rec.messages[3].role == "agent"


# ─── Close Chat Tests ───────────────────────────────────────


class TestCloseChat:
    def _create_chat(self, human_chat):
        return human_chat.create_chat(
            "H-001", "Close Test",
            member_name="Sage",
            topic="AI Ethics",
        )

    def test_basic_close(self, human_chat):
        self._create_chat(human_chat)
        rec = human_chat.close_chat("H-001")
        assert rec.closed_at != ""

    def test_close_with_summary(self, human_chat):
        self._create_chat(human_chat)
        rec = human_chat.close_chat("H-001", summary="Great discussion.")
        assert rec.summary == "Great discussion."
        assert rec.closed_at != ""

    def test_close_auto_summary(self, human_chat):
        self._create_chat(human_chat)
        rec = human_chat.close_chat("H-001")
        assert rec.summary != ""
        assert "Close Test" in rec.summary
        assert "Sage" in rec.summary

    def test_close_records_shared_memory(self, human_chat, tmp_dirs):
        self._create_chat(human_chat)
        human_chat.close_chat("H-001", summary="Done.")
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["type"] == "human_chat_closed"
        assert decisions[0]["chat_id"] == "H-001"
        assert decisions[0]["member"] == "Sage"

    def test_already_closed_raises(self, human_chat):
        self._create_chat(human_chat)
        human_chat.close_chat("H-001")
        with pytest.raises(HumanChatError) as exc_info:
            human_chat.close_chat("H-001")
        assert "already closed" in str(exc_info.value)


# ─── Query Tests ─────────────────────────────────────────────


class TestQueryMethods:
    def test_get_existing(self, human_chat):
        human_chat.create_chat(
            "H-001", "Test", member_name="Sage"
        )
        rec = human_chat.get("H-001")
        assert rec.chat_id == "H-001"

    def test_get_not_found(self, human_chat):
        with pytest.raises(HumanChatNotFoundError):
            human_chat.get("MISSING")

    def test_list_all(self, human_chat):
        human_chat.create_chat("H-001", "First", member_name="Sage")
        human_chat.create_chat("H-002", "Second", member_name="Logic")
        chats = human_chat.list_chats()
        assert len(chats) == 2

    def test_list_filter_member(self, human_chat):
        human_chat.create_chat("H-001", "First", member_name="Sage")
        human_chat.create_chat("H-002", "Second", member_name="Logic")
        sage_chats = human_chat.list_chats(member="Sage")
        assert len(sage_chats) == 1
        assert sage_chats[0].member_name == "Sage"

    def test_list_filter_closed(self, human_chat):
        human_chat.create_chat("H-001", "Open", member_name="Sage")
        human_chat.create_chat("H-002", "Closed", member_name="Logic")
        human_chat.close_chat("H-002")
        open_chats = human_chat.list_chats(closed=False)
        closed_chats = human_chat.list_chats(closed=True)
        assert len(open_chats) == 1
        assert len(closed_chats) == 1

    def test_has_chat(self, human_chat):
        assert not human_chat.has_chat("H-001")
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        assert human_chat.has_chat("H-001")

    def test_get_messages(self, human_chat):
        human_chat.create_chat("H-001", "Test", member_name="Sage")
        human_chat.send_human_message("H-001", "Hello")
        human_chat.send_human_message("H-001", "Another")
        all_msgs = human_chat.get_messages("H-001")
        human_msgs = human_chat.get_messages("H-001", role="human")
        assert len(all_msgs) == 2
        assert len(human_msgs) == 2

    def test_corrupt_file_skipped(self, human_chat, tmp_dirs):
        corrupt = tmp_dirs["conversations"] / "H-CORRUPT.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("not json!", encoding="utf-8")
        human_chat.create_chat("H-001", "Good", member_name="Sage")
        chats = human_chat.list_chats()
        assert len(chats) == 1


# ─── Prompt Builder Tests ────────────────────────────────────


class TestPromptBuilder:
    def test_prompt_with_history(self):
        member = _make_member("Sage")
        messages = [
            HumanChatMessage.create("human", "Human", "What is ethics?"),
            HumanChatMessage.create("agent", "Sage", "Ethics is..."),
        ]
        prompt = _build_human_chat_prompt(member, messages, "Ethics")
        assert "Sage" in prompt
        assert "Ethics" in prompt
        assert "What is ethics?" in prompt
        assert "Ethics is..." in prompt

    def test_prompt_without_topic(self):
        member = _make_member("Sage")
        prompt = _build_human_chat_prompt(member, [], "")
        assert "Sage" in prompt
        assert "human operator" in prompt

    def test_human_messages_labeled(self):
        member = _make_member("Sage")
        messages = [
            HumanChatMessage.create("human", "Human", "My question"),
        ]
        prompt = _build_human_chat_prompt(member, messages, "")
        assert "**Human:**" in prompt

    def test_context_limit(self):
        member = _make_member("Sage")
        # Generate more than 10 messages
        messages = [
            HumanChatMessage.create("human", "Human", f"Message {i}")
            for i in range(15)
        ]
        prompt = _build_human_chat_prompt(member, messages, "Topic")
        # Should only show last 10
        assert "Message 14" in prompt
        assert "Message 5" in prompt
        assert "Message 4" not in prompt


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(HumanChatNotFoundError, HumanChatError)
        assert issubclass(HumanChatValidationError, HumanChatError)

    def test_not_found_fields(self):
        err = HumanChatNotFoundError("H-999")
        assert err.chat_id == "H-999"
        assert "H-999" in str(err)

    def test_validation_fields(self):
        err = HumanChatValidationError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)

    def test_base_error(self):
        err = HumanChatError("something failed")
        assert "something failed" in str(err)


# ─── Edge Case Tests ─────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, human_chat):
        human_chat.create_chat(
            "H-001", "Ünïcödé Chät",
            member_name="Sage",
            topic="日本語トピック",
        )
        rec = human_chat.get("H-001")
        assert rec.title == "Ünïcödé Chät"
        assert rec.topic == "日本語トピック"

    def test_long_content(self, human_chat):
        human_chat.create_chat("H-001", "Long Test", member_name="Sage")
        long_msg = "A" * 10000
        rec = human_chat.send_human_message("H-001", long_msg)
        assert len(rec.messages[0].content) == 10000

    def test_persistence_roundtrip(self, human_chat):
        human_chat.create_chat(
            "H-001", "Roundtrip",
            member_name="Sage",
            topic="Test",
        )
        human_chat.send_human_message("H-001", "Hello Sage")
        human_chat.send_human_message("H-001", "Follow up")
        # Reload from disk
        rec = human_chat.get("H-001")
        assert len(rec.messages) == 2
        assert rec.messages[0].content == "Hello Sage"
        assert rec.messages[1].content == "Follow up"

    def test_full_lifecycle(self, human_chat, tmp_dirs):
        # Create
        rec = human_chat.create_chat(
            "H-001", "Full Lifecycle",
            member_name="Sage",
            topic="Ethics",
        )
        assert rec.closed_at == ""

        # Human sends
        rec = human_chat.send_human_message("H-001", "What is ethics?")
        assert len(rec.messages) == 1

        # Agent responds
        loop = asyncio.get_event_loop()
        rec, resp = loop.run_until_complete(
            human_chat.get_agent_response("H-001")
        )
        assert len(rec.messages) == 2
        assert rec.messages[1].role == "agent"

        # Another round
        rec = human_chat.send_human_message("H-001", "Tell me more")
        rec, _ = loop.run_until_complete(
            human_chat.get_agent_response("H-001")
        )
        assert len(rec.messages) == 4

        # Close
        rec = human_chat.close_chat("H-001", summary="Done.")
        assert rec.closed_at != ""
        assert rec.summary == "Done."

        # Verify shared memory
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        history = shared.read_history()
        assert "Full Lifecycle" in history

    def test_multiple_chats_same_member(self, human_chat):
        human_chat.create_chat("H-001", "First Chat", member_name="Sage")
        human_chat.create_chat("H-002", "Second Chat", member_name="Sage")
        sage_chats = human_chat.list_chats(member="Sage")
        assert len(sage_chats) == 2


# ─── Memory Integration Tests ────────────────────────────────


class TestMemoryIntegration:
    def _create_chat_with_msg(self, human_chat):
        human_chat.create_chat(
            "H-001", "Memory Test",
            member_name="Sage",
            topic="Ethics",
        )
        human_chat.send_human_message("H-001", "Tell me about ethics")

    def test_agent_response_recorded(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()

        with patch("core.human_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
            assert mock_mem_instance.append_session_event.call_count == 1

    def test_memory_content(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()

        with patch("core.human_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert "human operator" in entry.content
            assert entry.event_type == "human_chat"

    def test_session_id_is_chat_id(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()

        with patch("core.human_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.session_id == "H-001"

    def test_source_is_human_chat(self, human_chat):
        self._create_chat_with_msg(human_chat)
        loop = asyncio.get_event_loop()

        with patch("core.human_chat.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                human_chat.get_agent_response("H-001")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.source == "human_chat"
