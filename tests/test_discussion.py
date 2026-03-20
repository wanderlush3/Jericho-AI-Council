"""
Tests for Jericho — Discussion Rounds (F-010)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_member, mock_registry, mock_api_client
from core.discussion import (
    DiscussionContribution,
    DiscussionError,
    DiscussionManager,
    DiscussionNotFoundError,
    DiscussionRecord,
    DiscussionStateError,
    DiscussionValidationError,
    _build_discussion_prompt,
)
from core.api_client import ChatMessage, ChatResponse
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.proposals import Proposal, ProposalManager
from core.registry import CouncilMember, CouncilRegistry


# ─── Fixtures ──────────────────────────────────────────────────


def _mock_proposal(
    proposal_id: str = "P-0001",
    title: str = "Test Proposal",
    description: str = "A test proposal",
    author: str = "Sage",
    category: str = "ethics",
    body: str = "Full proposal body here.",
) -> Proposal:
    return Proposal(
        id=proposal_id,
        title=title,
        description=description,
        author=author,
        category=category,
        body=body,
        status="open",
    )


def _mock_proposal_manager(proposal: Proposal | None = None) -> MagicMock:
    """Build a mock ProposalManager."""
    mgr = MagicMock(spec=ProposalManager)
    p = proposal or _mock_proposal()
    mgr.get.return_value = p
    return mgr


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    """Provide temp dirs for discussions and memories."""
    return {
        "discussions": tmp_path / "discussions",
        "memories": tmp_path / "memories",
        "shared": tmp_path / "memories" / "shared",
        "proposals": tmp_path / "proposals",
    }


@pytest.fixture
def members():
    sage = make_member("Sage", "Ethics")
    logic = make_member("Logic", "Systems")
    drift = make_member("Drift", "Devil's Advocate", api_provider="mancer")
    return sage, logic, drift


@pytest.fixture
def registry(members):
    return mock_registry(*members)


@pytest.fixture
def api_client():
    return mock_api_client()


@pytest.fixture
def proposal():
    return _mock_proposal()


@pytest.fixture
def proposal_manager(proposal):
    return _mock_proposal_manager(proposal)


@pytest.fixture
def discussion_mgr(registry, api_client, proposal_manager, tmp_dirs):
    shared = SharedMemory(shared_dir=tmp_dirs["shared"])
    return DiscussionManager(
        registry=registry,
        api_client=api_client,
        proposal_manager=proposal_manager,
        discussions_dir=tmp_dirs["discussions"],
        shared_memory=shared,
    )


# ─── DiscussionContribution Tests ────────────────────────────


class TestDiscussionContribution:
    def test_fields(self):
        c = DiscussionContribution(speaker="Sage", content="I agree.")
        assert c.speaker == "Sage"
        assert c.content == "I agree."
        assert c.round_number == 0
        assert c.timestamp == ""
        assert c.metadata == {}

    def test_frozen(self):
        c = DiscussionContribution(speaker="Sage", content="Hello")
        with pytest.raises(AttributeError):
            c.speaker = "Logic"  # type: ignore

    def test_to_dict_roundtrip(self):
        c = DiscussionContribution.create(
            "Sage", "Hello", round_number=1, metadata={"key": "val"}
        )
        d = c.to_dict()
        restored = DiscussionContribution.from_dict(d)
        assert restored.speaker == c.speaker
        assert restored.content == c.content
        assert restored.round_number == 1
        assert restored.timestamp == c.timestamp
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        c = DiscussionContribution.create("Sage", "Thoughts", round_number=2)
        assert c.speaker == "Sage"
        assert c.content == "Thoughts"
        assert c.round_number == 2
        assert c.timestamp != ""

    def test_metadata_preserved(self):
        c = DiscussionContribution.create(
            "Sage", "test", metadata={"model": "test-model"}
        )
        assert c.metadata["model"] == "test-model"


# ─── DiscussionRecord Tests ─────────────────────────────────


class TestDiscussionRecord:
    def test_fields(self):
        rec = DiscussionRecord(
            discussion_id="D-001",
            proposal_id="P-0001",
            title="Test",
        )
        assert rec.discussion_id == "D-001"
        assert rec.proposal_id == "P-0001"
        assert rec.title == "Test"
        assert rec.participants == []
        assert rec.contributions == []
        assert rec.status == "open"
        assert rec.current_round == 0

    def test_frozen(self):
        rec = DiscussionRecord(
            discussion_id="D-001", proposal_id="P-0001", title="Test"
        )
        with pytest.raises(AttributeError):
            rec.title = "New"  # type: ignore

    def test_to_dict_roundtrip(self):
        c = DiscussionContribution.create("Sage", "Hello", round_number=1)
        rec = DiscussionRecord(
            discussion_id="D-001",
            proposal_id="P-0001",
            title="Roundtrip",
            participants=["Sage", "Logic"],
            contributions=[c],
            round_count=2,
            current_round=1,
            metadata={"key": "val"},
        )
        d = rec.to_dict()
        restored = DiscussionRecord.from_dict(d)
        assert restored.discussion_id == rec.discussion_id
        assert restored.proposal_id == rec.proposal_id
        assert restored.title == rec.title
        assert len(restored.contributions) == 1
        assert restored.contributions[0].speaker == "Sage"
        assert restored.round_count == 2
        assert restored.current_round == 1
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        rec = DiscussionRecord.create(
            "D-001", "P-0001", "Ethics Discussion",
            participants=["Sage", "Logic"],
            round_count=3,
        )
        assert rec.discussion_id == "D-001"
        assert rec.proposal_id == "P-0001"
        assert rec.created_at != ""
        assert rec.round_count == 3
        assert rec.status == "open"

    def test_create_empty_id_raises(self):
        with pytest.raises(DiscussionValidationError) as exc_info:
            DiscussionRecord.create("", "P-0001", "Title")
        assert "Discussion ID" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(DiscussionValidationError) as exc_info:
            DiscussionRecord.create("D-001", "P-0001", "")
        assert "Title" in str(exc_info.value)

    def test_create_whitespace_strip(self):
        rec = DiscussionRecord.create("  D-001  ", "  P-0001  ", "  Test  ")
        assert rec.discussion_id == "D-001"
        assert rec.proposal_id == "P-0001"
        assert rec.title == "Test"


# ─── DiscussionManager Init Tests ────────────────────────────


class TestDiscussionManagerInit:
    def test_creates_dir(self, discussion_mgr, tmp_dirs):
        assert tmp_dirs["discussions"].exists()

    def test_properties(self, discussion_mgr, tmp_dirs, registry, proposal_manager):
        assert discussion_mgr.directory == tmp_dirs["discussions"]
        assert discussion_mgr.registry is registry
        assert discussion_mgr.proposal_manager is proposal_manager

    def test_repr(self, discussion_mgr):
        r = repr(discussion_mgr)
        assert "DiscussionManager" in r
        assert "discussions=0" in r


# ─── Create Discussion Tests ─────────────────────────────────


class TestCreateDiscussion:
    def test_basic_creation(self, discussion_mgr):
        rec = discussion_mgr.create_discussion(
            "D-001", "P-0001", "Ethics Discussion",
            participants=["Sage", "Logic"],
        )
        assert rec.discussion_id == "D-001"
        assert rec.proposal_id == "P-0001"
        assert rec.title == "Ethics Discussion"
        assert rec.participants == ["Sage", "Logic"]

    def test_with_options(self, discussion_mgr):
        rec = discussion_mgr.create_discussion(
            "D-001", "P-0001", "Debate",
            participants=["Sage", "Logic"],
            round_count=3,
            metadata={"priority": "high"},
        )
        assert rec.round_count == 3
        assert rec.metadata["priority"] == "high"

    def test_persistence(self, discussion_mgr, tmp_dirs):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Persist Test",
            participants=["Sage", "Logic"],
        )
        filepath = tmp_dirs["discussions"] / "D-D-001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["discussion_id"] == "D-001"
        assert data["proposal_id"] == "P-0001"

    def test_duplicate_raises(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "First",
            participants=["Sage", "Logic"],
        )
        with pytest.raises(DiscussionError) as exc_info:
            discussion_mgr.create_discussion(
                "D-001", "P-0001", "Second",
                participants=["Sage", "Logic"],
            )
        assert "already exists" in str(exc_info.value)

    def test_unknown_participant_raises(self, discussion_mgr):
        with pytest.raises(DiscussionValidationError) as exc_info:
            discussion_mgr.create_discussion(
                "D-001", "P-0001", "Test",
                participants=["Sage", "UnknownMember"],
            )
        assert "Unknown council member" in str(exc_info.value)

    def test_missing_proposal_raises(self, discussion_mgr, proposal_manager):
        from core.proposals import ProposalNotFoundError
        proposal_manager.get.side_effect = ProposalNotFoundError("P-9999")
        with pytest.raises(ProposalNotFoundError):
            discussion_mgr.create_discussion(
                "D-001", "P-9999", "Bad Proposal",
                participants=["Sage", "Logic"],
            )

    def test_single_participant_raises(self, discussion_mgr):
        with pytest.raises(DiscussionValidationError) as exc_info:
            discussion_mgr.create_discussion(
                "D-001", "P-0001", "Solo",
                participants=["Sage"],
            )
        assert "At least 2" in str(exc_info.value)

    def test_exceeds_max_rounds_raises(self, discussion_mgr):
        with pytest.raises(DiscussionValidationError) as exc_info:
            discussion_mgr.create_discussion(
                "D-001", "P-0001", "Too Many Rounds",
                participants=["Sage", "Logic"],
                round_count=99,
            )
        assert "exceeds maximum" in str(exc_info.value)


# ─── Run Round Tests ─────────────────────────────────────────


class TestRunRound:
    def _create_discussion(self, discussion_mgr, round_count=2):
        return discussion_mgr.create_discussion(
            "D-001", "P-0001", "Round Test",
            participants=["Sage", "Logic"],
            round_count=round_count,
        )

    def test_basic_round(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert len(rec.contributions) == 2
        assert rec.current_round == 1

    def test_records_contributions(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert rec.contributions[0].speaker == "Sage"
        assert rec.contributions[1].speaker == "Logic"
        assert rec.contributions[0].round_number == 1
        assert rec.contributions[1].round_number == 1

    def test_api_called(self, discussion_mgr, api_client):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(discussion_mgr.run_round("D-001"))
        assert api_client.chat.call_count == 2

    def test_memory_recorded(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()

        with patch("core.discussion.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
            assert mock_mem_instance.append_session_event.call_count == 2
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.event_type == "discussion"
            assert entry.source == "discussion"

    def test_round_tracking(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert rec.current_round == 1

        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert rec.current_round == 2
        assert len(rec.contributions) == 4

    def test_closed_discussion_raises(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        discussion_mgr.close_discussion("D-001")
        loop = asyncio.get_event_loop()
        with pytest.raises(DiscussionStateError) as exc_info:
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
        assert "closed" in str(exc_info.value).lower()

    def test_not_found_raises(self, discussion_mgr):
        loop = asyncio.get_event_loop()
        with pytest.raises(DiscussionNotFoundError):
            loop.run_until_complete(
                discussion_mgr.run_round("MISSING")
            )

    def test_all_rounds_complete_raises(self, discussion_mgr):
        self._create_discussion(discussion_mgr, round_count=1)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(discussion_mgr.run_round("D-001"))
        with pytest.raises(DiscussionStateError) as exc_info:
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
        assert "complete" in str(exc_info.value).lower()


# ─── Run All Rounds Tests ────────────────────────────────────


class TestRunAllRounds:
    def _create_discussion(self, discussion_mgr, round_count=2):
        return discussion_mgr.create_discussion(
            "D-001", "P-0001", "All Rounds Test",
            participants=["Sage", "Logic"],
            round_count=round_count,
        )

    def test_default_rounds(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_all_rounds("D-001")
        )
        assert rec.current_round == 2
        assert len(rec.contributions) == 4

    def test_custom_rounds(self, discussion_mgr):
        self._create_discussion(discussion_mgr, round_count=3)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_all_rounds("D-001", rounds=1)
        )
        assert rec.current_round == 1
        assert len(rec.contributions) == 2

    def test_records_all(self, discussion_mgr, tmp_dirs):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            discussion_mgr.run_all_rounds("D-001")
        )
        filepath = tmp_dirs["discussions"] / "D-D-001.json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert len(data["contributions"]) == 4

    def test_closed_raises(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        discussion_mgr.close_discussion("D-001")
        loop = asyncio.get_event_loop()
        with pytest.raises(DiscussionStateError) as exc_info:
            loop.run_until_complete(
                discussion_mgr.run_all_rounds("D-001")
            )
        assert "closed" in str(exc_info.value).lower()

    def test_respects_remaining_rounds(self, discussion_mgr):
        self._create_discussion(discussion_mgr, round_count=3)
        loop = asyncio.get_event_loop()
        # Run 1 round manually
        loop.run_until_complete(discussion_mgr.run_round("D-001"))
        # run_all_rounds should only run 2 more
        rec = loop.run_until_complete(
            discussion_mgr.run_all_rounds("D-001")
        )
        assert rec.current_round == 3
        assert len(rec.contributions) == 6  # 2 per round × 3 rounds


# ─── Close Discussion Tests ─────────────────────────────────


class TestCloseDiscussion:
    def _create_discussion(self, discussion_mgr):
        return discussion_mgr.create_discussion(
            "D-001", "P-0001", "Close Test",
            participants=["Sage", "Logic"],
        )

    def test_basic_close(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        rec = discussion_mgr.close_discussion("D-001")
        assert rec.closed_at != ""
        assert rec.status == "closed"

    def test_close_with_summary(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        rec = discussion_mgr.close_discussion(
            "D-001", summary="Thorough discussion completed."
        )
        assert rec.summary == "Thorough discussion completed."
        assert rec.closed_at != ""

    def test_close_auto_summary(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        rec = discussion_mgr.close_discussion("D-001")
        assert rec.summary != ""
        assert "Close Test" in rec.summary

    def test_close_records_shared_memory(self, discussion_mgr, tmp_dirs):
        self._create_discussion(discussion_mgr)
        discussion_mgr.close_discussion("D-001", summary="Done.")
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["type"] == "discussion_closed"
        assert decisions[0]["discussion_id"] == "D-001"
        assert decisions[0]["proposal_id"] == "P-0001"

    def test_already_closed_raises(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        discussion_mgr.close_discussion("D-001")
        with pytest.raises(DiscussionStateError) as exc_info:
            discussion_mgr.close_discussion("D-001")
        assert "already closed" in str(exc_info.value).lower()


# ─── Query Tests ─────────────────────────────────────────────


class TestQueryMethods:
    def test_get_existing(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Test",
            participants=["Sage", "Logic"],
        )
        rec = discussion_mgr.get("D-001")
        assert rec.discussion_id == "D-001"

    def test_get_not_found(self, discussion_mgr):
        with pytest.raises(DiscussionNotFoundError):
            discussion_mgr.get("MISSING")

    def test_list_all(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "First",
            participants=["Sage", "Logic"],
        )
        discussion_mgr.create_discussion(
            "D-002", "P-0001", "Second",
            participants=["Sage", "Logic"],
        )
        discussions = discussion_mgr.list_discussions()
        assert len(discussions) == 2

    def test_list_filter_proposal(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "First",
            participants=["Sage", "Logic"],
        )
        discussion_mgr.create_discussion(
            "D-002", "P-0002", "Second",
            participants=["Sage", "Logic"],
        )
        p1 = discussion_mgr.list_discussions(proposal_id="P-0001")
        assert len(p1) == 1
        assert p1[0].discussion_id == "D-001"

    def test_list_filter_status(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Open",
            participants=["Sage", "Logic"],
        )
        discussion_mgr.create_discussion(
            "D-002", "P-0001", "Closed",
            participants=["Sage", "Logic"],
        )
        discussion_mgr.close_discussion("D-002")
        open_d = discussion_mgr.list_discussions(status="open")
        closed_d = discussion_mgr.list_discussions(status="closed")
        assert len(open_d) == 1
        assert len(closed_d) == 1

    def test_has_discussion(self, discussion_mgr):
        assert not discussion_mgr.has_discussion("D-001")
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Test",
            participants=["Sage", "Logic"],
        )
        assert discussion_mgr.has_discussion("D-001")

    def test_get_contributions(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Test",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(discussion_mgr.run_round("D-001"))

        all_c = discussion_mgr.get_contributions("D-001")
        sage_c = discussion_mgr.get_contributions("D-001", speaker="Sage")
        r1_c = discussion_mgr.get_contributions("D-001", round_number=1)
        assert len(all_c) == 2
        assert len(sage_c) == 1
        assert sage_c[0].speaker == "Sage"
        assert len(r1_c) == 2

    def test_corrupt_file_skipped(self, discussion_mgr, tmp_dirs):
        corrupt = tmp_dirs["discussions"] / "D-CORRUPT.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("not json!", encoding="utf-8")
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Good",
            participants=["Sage", "Logic"],
        )
        discussions = discussion_mgr.list_discussions()
        assert len(discussions) == 1

    def test_list_filter_participant(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "With Drift",
            participants=["Sage", "Drift"],
        )
        discussion_mgr.create_discussion(
            "D-002", "P-0001", "Without Drift",
            participants=["Sage", "Logic"],
        )
        drift_d = discussion_mgr.list_discussions(participant="Drift")
        assert len(drift_d) == 1
        assert drift_d[0].discussion_id == "D-001"


# ─── Prompt Builder Tests ────────────────────────────────────


class TestPromptBuilder:
    def test_includes_proposal_title(self):
        member = make_member("Sage")
        proposal = _mock_proposal(title="Ethics Framework")
        prompt = _build_discussion_prompt(member, proposal, [], 1)
        assert "Ethics Framework" in prompt

    def test_includes_proposal_body(self):
        member = make_member("Sage")
        proposal = _mock_proposal(body="Detailed body content")
        prompt = _build_discussion_prompt(member, proposal, [], 1)
        assert "Detailed body content" in prompt

    def test_includes_prior_contributions(self):
        member = make_member("Logic")
        proposal = _mock_proposal()
        contributions = [
            DiscussionContribution.create("Sage", "I support this.", round_number=1),
        ]
        prompt = _build_discussion_prompt(member, proposal, contributions, 1)
        assert "Sage" in prompt
        assert "I support this" in prompt

    def test_context_limit(self):
        member = make_member("Sage")
        proposal = _mock_proposal()
        # Generate more than 10 contributions
        contributions = [
            DiscussionContribution.create(f"Speaker{i}", f"Message {i}", round_number=1)
            for i in range(15)
        ]
        prompt = _build_discussion_prompt(member, proposal, contributions, 2)
        assert "Message 14" in prompt
        assert "Message 5" in prompt
        assert "Message 4" not in prompt

    def test_member_identity(self):
        member = make_member("Logic", "Systems")
        proposal = _mock_proposal()
        prompt = _build_discussion_prompt(member, proposal, [], 1)
        assert "Logic" in prompt
        assert "Systems" in prompt
        assert "round 1" in prompt


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(DiscussionNotFoundError, DiscussionError)
        assert issubclass(DiscussionValidationError, DiscussionError)
        assert issubclass(DiscussionStateError, DiscussionError)

    def test_not_found_fields(self):
        err = DiscussionNotFoundError("D-999")
        assert err.discussion_id == "D-999"
        assert "D-999" in str(err)

    def test_validation_fields(self):
        err = DiscussionValidationError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)

    def test_state_error_fields(self):
        err = DiscussionStateError("D-001", "something wrong")
        assert err.discussion_id == "D-001"
        assert "something wrong" in str(err)


# ─── Edge Case Tests ─────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Ünïcödé Discussion",
            participants=["Sage", "Logic"],
        )
        rec = discussion_mgr.get("D-001")
        assert rec.title == "Ünïcödé Discussion"

    def test_long_content(self, discussion_mgr, api_client):
        long_content = "A" * 10000
        api_client.chat = AsyncMock(return_value=ChatResponse(
            content=long_content,
            model="test-model",
            provider="openrouter",
        ))
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Long Test",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert len(rec.contributions[0].content) == 10000

    def test_many_participants(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Many Participants",
            participants=["Sage", "Logic", "Drift"],
        )
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_round("D-001")
        )
        assert len(rec.contributions) == 3
        assert rec.contributions[0].speaker == "Sage"
        assert rec.contributions[1].speaker == "Logic"
        assert rec.contributions[2].speaker == "Drift"

    def test_persistence_roundtrip(self, discussion_mgr):
        discussion_mgr.create_discussion(
            "D-001", "P-0001", "Roundtrip",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(discussion_mgr.run_round("D-001"))
        # Reload from disk
        rec = discussion_mgr.get("D-001")
        assert len(rec.contributions) == 2
        assert rec.contributions[0].speaker == "Sage"
        assert rec.contributions[1].speaker == "Logic"

    def test_full_lifecycle(self, discussion_mgr, tmp_dirs):
        # Create
        rec = discussion_mgr.create_discussion(
            "D-001", "P-0001", "Full Lifecycle",
            participants=["Sage", "Logic"],
            round_count=2,
        )
        assert rec.status == "open"
        assert rec.closed_at == ""

        # Run all rounds
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            discussion_mgr.run_all_rounds("D-001")
        )
        assert rec.current_round == 2
        assert len(rec.contributions) == 4

        # Close
        rec = discussion_mgr.close_discussion(
            "D-001", summary="Ethics debated."
        )
        assert rec.status == "closed"
        assert rec.closed_at != ""
        assert rec.summary == "Ethics debated."

        # Verify shared memory
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        history = shared.read_history()
        assert "Full Lifecycle" in history


# ─── Memory Integration Tests ────────────────────────────────


class TestMemoryIntegration:
    def _create_discussion(self, discussion_mgr):
        return discussion_mgr.create_discussion(
            "D-001", "P-0001", "Memory Test",
            participants=["Sage", "Logic"],
        )

    def test_each_speaker_recorded(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()

        with patch("core.discussion.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
            assert mock_mem_instance.append_session_event.call_count == 2

    def test_memory_content(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()

        with patch("core.discussion.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert "Test Proposal" in entry.content
            assert "P-0001" in entry.content

    def test_session_id_matches(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()

        with patch("core.discussion.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.session_id == "D-001"

    def test_source_type(self, discussion_mgr):
        self._create_discussion(discussion_mgr)
        loop = asyncio.get_event_loop()

        member_names_used = []
        with patch("core.discussion.AgentMemory") as MockMem:
            def capture_name(name):
                member_names_used.append(name)
                return MagicMock()
            MockMem.side_effect = capture_name
            loop.run_until_complete(
                discussion_mgr.run_round("D-001")
            )
        assert "Sage" in member_names_used
        assert "Logic" in member_names_used
