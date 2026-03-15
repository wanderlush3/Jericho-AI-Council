"""
Tests for Jericho — Collaborative Character Design (F-012)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.character_design import (
    CharacterDesigner,
    DesignContribution,
    DesignError,
    DesignNotFoundError,
    DesignRecord,
    DesignStateError,
    DesignValidationError,
    _build_backstory_prompt,
    _build_concept_prompt,
    _build_review_prompt,
    _build_traits_prompt,
    _build_prompt_prompt,
)
from core.api_client import ChatMessage, ChatResponse
from core.characters import CharacterManager, CharacterTemplate, Trait
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.registry import CouncilMember, CouncilRegistry


# ─── Fixtures ──────────────────────────────────────────────────


def _make_member(
    name: str = "Forge",
    role: str = "Character Builder",
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
    """Provide temp dirs for designs, characters, and memories."""
    return {
        "designs": tmp_path / "character_designs",
        "characters": tmp_path / "characters",
        "memories": tmp_path / "memories",
        "shared": tmp_path / "memories" / "shared",
    }


@pytest.fixture
def members():
    forge = _make_member("Forge", "Character Builder")
    spark = _make_member("Spark", "Creative")
    sage = _make_member("Sage", "Ethics")
    return forge, spark, sage


@pytest.fixture
def registry(members):
    return _mock_registry(*members)


@pytest.fixture
def api_client():
    return _mock_api_client()


@pytest.fixture
def char_manager(tmp_dirs):
    return CharacterManager(characters_dir=tmp_dirs["characters"])


@pytest.fixture
def designer(registry, api_client, char_manager, tmp_dirs):
    shared = SharedMemory(shared_dir=tmp_dirs["shared"])
    return CharacterDesigner(
        registry=registry,
        api_client=api_client,
        character_manager=char_manager,
        designs_dir=tmp_dirs["designs"],
        shared_memory=shared,
    )


# ─── DesignContribution Tests ────────────────────────────────


class TestDesignContribution:
    def test_fields(self):
        c = DesignContribution(speaker="Forge", content="A brave explorer.")
        assert c.speaker == "Forge"
        assert c.content == "A brave explorer."
        assert c.phase == ""
        assert c.parsed_data == {}
        assert c.timestamp == ""
        assert c.metadata == {}

    def test_frozen(self):
        c = DesignContribution(speaker="Forge", content="Hello")
        with pytest.raises(AttributeError):
            c.speaker = "Spark"  # type: ignore

    def test_to_dict_roundtrip(self):
        c = DesignContribution.create(
            "Forge", "Concept idea", phase="concept",
            parsed_data={"name": "Atlas"}, metadata={"key": "val"},
        )
        d = c.to_dict()
        restored = DesignContribution.from_dict(d)
        assert restored.speaker == c.speaker
        assert restored.content == c.content
        assert restored.phase == "concept"
        assert restored.parsed_data == {"name": "Atlas"}
        assert restored.timestamp == c.timestamp
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        c = DesignContribution.create("Forge", "Thoughts", phase="traits")
        assert c.speaker == "Forge"
        assert c.content == "Thoughts"
        assert c.phase == "traits"
        assert c.timestamp != ""

    def test_metadata_preserved(self):
        c = DesignContribution.create(
            "Forge", "test", metadata={"model": "test-model"}
        )
        assert c.metadata["model"] == "test-model"


# ─── DesignRecord Tests ─────────────────────────────────────


class TestDesignRecord:
    def test_fields(self):
        rec = DesignRecord(design_id="CD-001", title="Test")
        assert rec.design_id == "CD-001"
        assert rec.title == "Test"
        assert rec.contributors == []
        assert rec.contributions == []
        assert rec.current_phase == ""
        assert rec.phases_completed == []
        assert rec.target_character_id == ""
        assert rec.status == "open"

    def test_frozen(self):
        rec = DesignRecord(design_id="CD-001", title="Test")
        with pytest.raises(AttributeError):
            rec.title = "New"  # type: ignore

    def test_to_dict_roundtrip(self):
        c = DesignContribution.create("Forge", "Hello", phase="concept")
        rec = DesignRecord(
            design_id="CD-001",
            title="Roundtrip",
            contributors=["Forge", "Spark"],
            contributions=[c],
            current_phase="concept",
            phases_completed=["concept"],
            metadata={"key": "val"},
        )
        d = rec.to_dict()
        restored = DesignRecord.from_dict(d)
        assert restored.design_id == rec.design_id
        assert restored.title == rec.title
        assert len(restored.contributions) == 1
        assert restored.contributions[0].speaker == "Forge"
        assert restored.current_phase == "concept"
        assert restored.phases_completed == ["concept"]
        assert restored.metadata == {"key": "val"}

    def test_create_factory(self):
        rec = DesignRecord.create(
            "CD-001", "Explorer Design",
            contributors=["Forge", "Spark"],
        )
        assert rec.design_id == "CD-001"
        assert rec.created_at != ""
        assert rec.status == "open"

    def test_create_empty_id_raises(self):
        with pytest.raises(DesignValidationError) as exc_info:
            DesignRecord.create("", "Title")
        assert "Design ID" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(DesignValidationError) as exc_info:
            DesignRecord.create("CD-001", "")
        assert "Title" in str(exc_info.value)

    def test_create_whitespace_strip(self):
        rec = DesignRecord.create("  CD-001  ", "  Test  ")
        assert rec.design_id == "CD-001"
        assert rec.title == "Test"


# ─── CharacterDesigner Init Tests ────────────────────────────


class TestCharacterDesignerInit:
    def test_creates_dir(self, designer, tmp_dirs):
        assert tmp_dirs["designs"].exists()

    def test_properties(self, designer, tmp_dirs, registry, char_manager):
        assert designer.directory == tmp_dirs["designs"]
        assert designer.registry is registry
        assert designer.character_manager is char_manager

    def test_repr(self, designer):
        r = repr(designer)
        assert "CharacterDesigner" in r
        assert "designs=0" in r


# ─── Create Design Tests ────────────────────────────────────


class TestCreateDesign:
    def test_basic_creation(self, designer):
        rec = designer.create_design(
            "CD-001", "Explorer Character",
            contributors=["Forge", "Spark"],
        )
        assert rec.design_id == "CD-001"
        assert rec.title == "Explorer Character"
        assert rec.contributors == ["Forge", "Spark"]

    def test_with_options(self, designer):
        rec = designer.create_design(
            "CD-001", "Test",
            contributors=["Forge"],
            metadata={"priority": "high"},
        )
        assert rec.metadata["priority"] == "high"

    def test_persistence(self, designer, tmp_dirs):
        designer.create_design(
            "CD-001", "Persist Test",
            contributors=["Forge"],
        )
        filepath = tmp_dirs["designs"] / "CD-CD-001.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["design_id"] == "CD-001"

    def test_duplicate_raises(self, designer):
        designer.create_design(
            "CD-001", "First", contributors=["Forge"],
        )
        with pytest.raises(DesignError) as exc_info:
            designer.create_design(
                "CD-001", "Second", contributors=["Forge"],
            )
        assert "already exists" in str(exc_info.value)

    def test_unknown_contributor_raises(self, designer):
        with pytest.raises(DesignValidationError) as exc_info:
            designer.create_design(
                "CD-001", "Test",
                contributors=["Forge", "UnknownMember"],
            )
        assert "Unknown council member" in str(exc_info.value)

    def test_no_contributors_raises(self, designer):
        with pytest.raises(DesignValidationError) as exc_info:
            designer.create_design(
                "CD-001", "Empty", contributors=[],
            )
        assert "At least 1" in str(exc_info.value)

    def test_sequential_ids(self, designer):
        r1 = designer.create_design(
            "CD-001", "First", contributors=["Forge"],
        )
        r2 = designer.create_design(
            "CD-002", "Second", contributors=["Spark"],
        )
        assert r1.design_id == "CD-001"
        assert r2.design_id == "CD-002"


# ─── Run Phase Tests ─────────────────────────────────────────


class TestRunPhase:
    def _create_design(self, designer):
        return designer.create_design(
            "CD-001", "Phase Test",
            contributors=["Forge", "Spark"],
        )

    def test_basic_phase(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        assert len(rec.contributions) == 2
        assert rec.current_phase == "concept"

    def test_records_contributions(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        assert rec.contributions[0].speaker == "Forge"
        assert rec.contributions[1].speaker == "Spark"
        assert rec.contributions[0].phase == "concept"
        assert rec.contributions[1].phase == "concept"

    def test_api_called(self, designer, api_client):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(designer.run_phase("CD-001", "concept"))
        assert api_client.chat.call_count == 2

    def test_memory_recorded(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()

        with patch("core.character_design.AgentMemory") as MockMem:
            mock_mem_instance = MagicMock()
            MockMem.return_value = mock_mem_instance
            loop.run_until_complete(
                designer.run_phase("CD-001", "concept")
            )
            assert mock_mem_instance.append_session_event.call_count == 2
            call_args = mock_mem_instance.append_session_event.call_args
            entry = call_args[0][0]
            assert entry.event_type == "character_design"
            assert entry.source == "character_design"

    def test_phase_tracking(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        assert "concept" in rec.phases_completed
        assert rec.current_phase == "concept"

        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "traits")
        )
        assert "traits" in rec.phases_completed
        assert rec.current_phase == "traits"
        assert len(rec.contributions) == 4

    def test_closed_design_raises(self, designer):
        self._create_design(designer)
        designer.close_design("CD-001")
        loop = asyncio.get_event_loop()
        with pytest.raises(DesignStateError) as exc_info:
            loop.run_until_complete(
                designer.run_phase("CD-001", "concept")
            )
        assert "closed" in str(exc_info.value).lower()

    def test_not_found_raises(self, designer):
        loop = asyncio.get_event_loop()
        with pytest.raises(DesignNotFoundError):
            loop.run_until_complete(
                designer.run_phase("MISSING", "concept")
            )

    def test_invalid_phase_raises(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        with pytest.raises(DesignValidationError) as exc_info:
            loop.run_until_complete(
                designer.run_phase("CD-001", "nonexistent_phase")
            )
        assert "Unknown phase" in str(exc_info.value)


# ─── Run All Phases Tests ────────────────────────────────────


class TestRunAllPhases:
    def _create_design(self, designer):
        return designer.create_design(
            "CD-001", "All Phases Test",
            contributors=["Forge", "Spark"],
        )

    def test_default_phases(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_all_phases("CD-001")
        )
        assert len(rec.phases_completed) == 5
        assert "concept" in rec.phases_completed
        assert "review" in rec.phases_completed
        # 5 phases × 2 contributors = 10 contributions
        assert len(rec.contributions) == 10

    def test_records_all(self, designer, tmp_dirs):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            designer.run_all_phases("CD-001")
        )
        filepath = tmp_dirs["designs"] / "CD-CD-001.json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert len(data["contributions"]) == 10

    def test_closed_raises(self, designer):
        self._create_design(designer)
        designer.close_design("CD-001")
        loop = asyncio.get_event_loop()
        with pytest.raises(DesignStateError) as exc_info:
            loop.run_until_complete(
                designer.run_all_phases("CD-001")
            )
        assert "closed" in str(exc_info.value).lower()

    def test_sequential_phases(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_all_phases("CD-001")
        )
        # Phases should be in order
        assert rec.phases_completed == [
            "concept", "traits", "backstory", "prompt", "review"
        ]

    def test_respects_completed_phases(self, designer):
        self._create_design(designer)
        loop = asyncio.get_event_loop()
        # Run concept first
        loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        # run_all_phases should skip concept and run remaining 4
        rec = loop.run_until_complete(
            designer.run_all_phases("CD-001")
        )
        assert len(rec.phases_completed) == 5
        # 1 phase done manually (2 contribs) + 4 more (8 contribs)
        assert len(rec.contributions) == 10


# ─── Assemble Character Tests ────────────────────────────────


class TestAssembleCharacter:
    def _create_design_with_contributions(self, designer, api_client):
        designer.create_design(
            "CD-001", "Assembly Test",
            contributors=["Forge", "Spark"],
        )
        # Set up API to return concept-like content on first two calls
        concept_resp = ChatResponse(
            content="Name: Atlas\nA brave explorer who ventures into unknown territories.",
            model="test-model",
            provider="openrouter",
        )
        traits_resp = ChatResponse(
            content="- **Curious**: Always seeking new knowledge\n- **Brave**: Faces danger head-on",
            model="test-model",
            provider="openrouter",
        )
        backstory_resp = ChatResponse(
            content="Atlas was born in a small village on the edge of civilization.",
            model="test-model",
            provider="openrouter",
        )
        prompt_resp = ChatResponse(
            content="You are Atlas, a brave explorer. Stay in character at all times.",
            model="test-model",
            provider="openrouter",
        )
        review_resp = ChatResponse(
            content="This character is well-rounded and engaging.",
            model="test-model",
            provider="openrouter",
        )

        # Alternate responses for two contributors across 5 phases
        responses = [
            concept_resp, concept_resp,
            traits_resp, traits_resp,
            backstory_resp, backstory_resp,
            prompt_resp, prompt_resp,
            review_resp, review_resp,
        ]
        api_client.chat = AsyncMock(side_effect=responses)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(designer.run_all_phases("CD-001"))
        return designer

    def test_creates_template(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert isinstance(template, CharacterTemplate)
        assert template.status == "draft"

    def test_uses_concept_name(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert template.name == "Atlas"

    def test_includes_traits(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert len(template.traits) >= 1

    def test_includes_backstory(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert "Atlas" in template.backstory or "village" in template.backstory

    def test_includes_prompt(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert len(template.system_prompt) > 0

    def test_links_design_id(self, designer, api_client, char_manager):
        self._create_design_with_contributions(designer, api_client)
        template = designer.assemble_character("CD-001")
        assert template.metadata["design_id"] == "CD-001"
        assert "Forge" in template.metadata["contributors"]

        # Verify design record is updated too
        rec = designer.get("CD-001")
        assert rec.target_character_id == template.id

    def test_not_found_raises(self, designer):
        with pytest.raises(DesignNotFoundError):
            designer.assemble_character("MISSING")


# ─── Close Design Tests ─────────────────────────────────────


class TestCloseDesign:
    def _create_design(self, designer):
        return designer.create_design(
            "CD-001", "Close Test",
            contributors=["Forge"],
        )

    def test_basic_close(self, designer):
        self._create_design(designer)
        rec = designer.close_design("CD-001")
        assert rec.closed_at != ""
        assert rec.status == "closed"

    def test_close_with_summary(self, designer):
        self._create_design(designer)
        rec = designer.close_design(
            "CD-001", summary="Character design completed."
        )
        assert rec.summary == "Character design completed."
        assert rec.closed_at != ""

    def test_close_auto_summary(self, designer):
        self._create_design(designer)
        rec = designer.close_design("CD-001")
        assert rec.summary != ""
        assert "Close Test" in rec.summary

    def test_close_records_shared_memory(self, designer, tmp_dirs):
        self._create_design(designer)
        designer.close_design("CD-001", summary="Done.")
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        decisions = shared.read_decisions()
        assert len(decisions) == 1
        assert decisions[0]["type"] == "design_closed"
        assert decisions[0]["design_id"] == "CD-001"

    def test_already_closed_raises(self, designer):
        self._create_design(designer)
        designer.close_design("CD-001")
        with pytest.raises(DesignStateError) as exc_info:
            designer.close_design("CD-001")
        assert "already closed" in str(exc_info.value).lower()


# ─── Query Tests ─────────────────────────────────────────────


class TestQueryMethods:
    def test_get_existing(self, designer):
        designer.create_design(
            "CD-001", "Test", contributors=["Forge"],
        )
        rec = designer.get("CD-001")
        assert rec.design_id == "CD-001"

    def test_get_not_found(self, designer):
        with pytest.raises(DesignNotFoundError):
            designer.get("MISSING")

    def test_list_all(self, designer):
        designer.create_design(
            "CD-001", "First", contributors=["Forge"],
        )
        designer.create_design(
            "CD-002", "Second", contributors=["Spark"],
        )
        designs = designer.list_designs()
        assert len(designs) == 2

    def test_list_filter_status(self, designer):
        designer.create_design(
            "CD-001", "Open", contributors=["Forge"],
        )
        designer.create_design(
            "CD-002", "Closed", contributors=["Forge"],
        )
        designer.close_design("CD-002")
        open_d = designer.list_designs(status="open")
        closed_d = designer.list_designs(status="closed")
        assert len(open_d) == 1
        assert len(closed_d) == 1

    def test_list_filter_contributor(self, designer):
        designer.create_design(
            "CD-001", "Forge Only", contributors=["Forge"],
        )
        designer.create_design(
            "CD-002", "Spark Only", contributors=["Spark"],
        )
        forge_d = designer.list_designs(contributor="Forge")
        assert len(forge_d) == 1
        assert forge_d[0].design_id == "CD-001"

    def test_has_design(self, designer):
        assert not designer.has_design("CD-001")
        designer.create_design(
            "CD-001", "Test", contributors=["Forge"],
        )
        assert designer.has_design("CD-001")

    def test_get_contributions(self, designer):
        designer.create_design(
            "CD-001", "Test", contributors=["Forge", "Spark"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(designer.run_phase("CD-001", "concept"))

        all_c = designer.get_contributions("CD-001")
        forge_c = designer.get_contributions("CD-001", speaker="Forge")
        concept_c = designer.get_contributions("CD-001", phase="concept")
        assert len(all_c) == 2
        assert len(forge_c) == 1
        assert forge_c[0].speaker == "Forge"
        assert len(concept_c) == 2

    def test_corrupt_file_skipped(self, designer, tmp_dirs):
        corrupt = tmp_dirs["designs"] / "CD-CORRUPT.json"
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_text("not json!", encoding="utf-8")
        designer.create_design(
            "CD-001", "Good", contributors=["Forge"],
        )
        designs = designer.list_designs()
        assert len(designs) == 1


# ─── Prompt Builder Tests ────────────────────────────────────


class TestPromptBuilders:
    def test_concept_content(self):
        member = _make_member("Forge")
        record = DesignRecord(design_id="CD-001", title="Explorer")
        prompt = _build_concept_prompt(record, member)
        assert "Explorer" in prompt
        assert "Forge" in prompt
        assert "Name" in prompt

    def test_traits_with_prior(self):
        member = _make_member("Spark")
        record = DesignRecord(design_id="CD-001", title="Explorer")
        prior = [
            DesignContribution.create(
                "Forge", "Name: Atlas, an explorer.", phase="concept"
            ),
        ]
        prompt = _build_traits_prompt(record, member, prior)
        assert "Spark" in prompt
        assert "Forge" in prompt
        assert "Atlas" in prompt
        assert "personality" in prompt.lower() or "trait" in prompt.lower()

    def test_backstory_content(self):
        member = _make_member("Sage")
        record = DesignRecord(design_id="CD-001", title="Explorer")
        prior = [
            DesignContribution.create("Forge", "Concept content.", phase="concept"),
        ]
        prompt = _build_backstory_prompt(record, member, prior)
        assert "Sage" in prompt
        assert "backstory" in prompt.lower() or "Backstory" in prompt

    def test_prompt_phase_content(self):
        member = _make_member("Forge")
        record = DesignRecord(design_id="CD-001", title="Explorer")
        prior = [
            DesignContribution.create("Sage", "Backstory content.", phase="backstory"),
        ]
        prompt = _build_prompt_prompt(record, member, prior)
        assert "Forge" in prompt
        assert "system prompt" in prompt.lower()

    def test_review_content(self):
        member = _make_member("Spark")
        record = DesignRecord(design_id="CD-001", title="Explorer")
        prior = [
            DesignContribution.create("Forge", "Prompt content.", phase="prompt"),
        ]
        prompt = _build_review_prompt(record, member, prior)
        assert "Spark" in prompt
        assert "review" in prompt.lower() or "Review" in prompt


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(DesignNotFoundError, DesignError)
        assert issubclass(DesignValidationError, DesignError)
        assert issubclass(DesignStateError, DesignError)

    def test_not_found_fields(self):
        err = DesignNotFoundError("CD-999")
        assert err.design_id == "CD-999"
        assert "CD-999" in str(err)

    def test_validation_fields(self):
        err = DesignValidationError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)

    def test_state_error_fields(self):
        err = DesignStateError("CD-001", "something wrong")
        assert err.design_id == "CD-001"
        assert "something wrong" in str(err)


# ─── Edge Case Tests ─────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_content(self, designer):
        designer.create_design(
            "CD-001", "Ünïcödé Design",
            contributors=["Forge"],
        )
        rec = designer.get("CD-001")
        assert rec.title == "Ünïcödé Design"

    def test_long_content(self, designer, api_client):
        long_content = "A" * 10000
        api_client.chat = AsyncMock(return_value=ChatResponse(
            content=long_content,
            model="test-model",
            provider="openrouter",
        ))
        designer.create_design(
            "CD-001", "Long Test", contributors=["Forge"],
        )
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        assert len(rec.contributions[0].content) == 10000

    def test_many_contributors(self, designer):
        designer.create_design(
            "CD-001", "Many Contributors",
            contributors=["Forge", "Spark", "Sage"],
        )
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        assert len(rec.contributions) == 3
        assert rec.contributions[0].speaker == "Forge"
        assert rec.contributions[1].speaker == "Spark"
        assert rec.contributions[2].speaker == "Sage"

    def test_persistence_roundtrip(self, designer):
        designer.create_design(
            "CD-001", "Roundtrip",
            contributors=["Forge", "Spark"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            designer.run_phase("CD-001", "concept")
        )
        rec = designer.get("CD-001")
        assert len(rec.contributions) == 2
        assert rec.contributions[0].phase == "concept"

    def test_full_lifecycle(self, designer, api_client):
        # Create
        rec = designer.create_design(
            "CD-001", "Full Lifecycle",
            contributors=["Forge", "Spark"],
        )
        assert rec.status == "open"

        # Run all phases
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(
            designer.run_all_phases("CD-001")
        )
        assert len(rec.phases_completed) == 5
        assert len(rec.contributions) == 10

        # Assemble
        template = designer.assemble_character("CD-001")
        assert template.id.startswith("CH-")

        # Close
        rec = designer.close_design(
            "CD-001", summary="Lifecycle complete."
        )
        assert rec.status == "closed"
        assert rec.target_character_id == template.id
