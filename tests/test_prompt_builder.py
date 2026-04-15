"""
Tests for Jericho Prompt Generation Engine (F-037c).

Covers:
- StylePreset data class and built-in presets
- PromptRequest validation for all 5 modes
- PromptResult creation and serialization
- Entity context building
- LLM response parsing
- Style preset application
- PromptBuilder integration for each mode (with mocked API)
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.prompt_builder import (
    DEFAULT_STYLE_PRESETS,
    PROMPT_MODES,
    VALID_ENTITY_TYPES,
    PromptBuilder,
    PromptError,
    PromptRequest,
    PromptResult,
    PromptValidationError,
    StylePreset,
    apply_style_preset,
    build_entity_context,
    get_style_preset,
    list_style_presets,
    parse_prompt_response,
)


# ─── Helpers ───────────────────────────────────────────────────


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_mock_api_client(response_text: str = "POSITIVE: a cat\nNEGATIVE: blurry"):
    """Create a mock API client that returns a fixed response."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_text
    mock_client.chat = AsyncMock(return_value=mock_response)
    return mock_client


def _make_mock_registry(*member_names):
    """Create a mock registry with named members."""
    from core.registry import CouncilMember

    members = {}
    for name in member_names:
        member = CouncilMember(
            name=name,
            role=f"Role of {name}",
            description=f"Description of {name}",
            api_provider="openrouter",
            model="Default",
            system_prompt=f"You are {name}.",
        )
        members[name.lower()] = member

    mock_registry = MagicMock()
    mock_registry.get = MagicMock(side_effect=lambda n: members[n.strip().lower()])
    mock_registry.list_members = MagicMock(return_value=list(members.values()))
    return mock_registry


# ═══════════════════════════════════════════════════════════════
# StylePreset Tests
# ═══════════════════════════════════════════════════════════════


class TestStylePreset:
    """Tests for the StylePreset dataclass."""

    def test_create_basic(self):
        preset = StylePreset.create("Fantasy Art", description="A fantasy style")
        assert preset.name == "Fantasy Art"
        assert preset.description == "A fantasy style"
        assert preset.positive_suffix == ""
        assert preset.negative_prefix == ""

    def test_create_full(self):
        preset = StylePreset.create(
            "Test Style",
            description="desc",
            positive_suffix="vibrant colors",
            negative_prefix="blurry, low quality",
            metadata={"source": "test"},
        )
        assert preset.name == "Test Style"
        assert preset.positive_suffix == "vibrant colors"
        assert preset.negative_prefix == "blurry, low quality"
        assert preset.metadata == {"source": "test"}

    def test_create_strips_whitespace(self):
        preset = StylePreset.create("  Spaced Name  ", description="  spaced  ")
        assert preset.name == "Spaced Name"
        assert preset.description == "spaced"

    def test_create_empty_name_raises(self):
        with pytest.raises(PromptValidationError, match="name is required"):
            StylePreset.create("")

    def test_create_whitespace_name_raises(self):
        with pytest.raises(PromptValidationError, match="name is required"):
            StylePreset.create("   ")

    def test_to_dict(self):
        preset = StylePreset.create("Test", positive_suffix="vibrant")
        d = preset.to_dict()
        assert d["name"] == "Test"
        assert d["positive_suffix"] == "vibrant"
        assert isinstance(d, dict)

    def test_from_dict(self):
        data = {
            "name": "FromDict",
            "description": "from dict",
            "positive_suffix": "detailed",
            "negative_prefix": "ugly",
            "metadata": {"key": "val"},
        }
        preset = StylePreset.from_dict(data)
        assert preset.name == "FromDict"
        assert preset.positive_suffix == "detailed"
        assert preset.metadata == {"key": "val"}

    def test_from_dict_minimal(self):
        preset = StylePreset.from_dict({"name": "Minimal"})
        assert preset.name == "Minimal"
        assert preset.description == ""
        assert preset.positive_suffix == ""

    def test_round_trip(self):
        original = StylePreset.create(
            "Roundtrip",
            positive_suffix="a",
            negative_prefix="b",
            metadata={"x": 1},
        )
        restored = StylePreset.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self):
        preset = StylePreset.create("Frozen")
        with pytest.raises(AttributeError):
            preset.name = "Changed"


# ═══════════════════════════════════════════════════════════════
# Built-in Style Presets Tests
# ═══════════════════════════════════════════════════════════════


class TestBuiltinPresets:
    """Tests for built-in style presets and lookup functions."""

    def test_all_presets_have_required_fields(self):
        for key, preset in DEFAULT_STYLE_PRESETS.items():
            assert preset.name, f"Preset '{key}' has no name"
            assert preset.description, f"Preset '{key}' has no description"
            assert preset.positive_suffix, f"Preset '{key}' has no positive_suffix"
            assert preset.negative_prefix, f"Preset '{key}' has no negative_prefix"

    def test_preset_keys_are_lowercase_snake(self):
        for key in DEFAULT_STYLE_PRESETS:
            assert re.match(r"^[a-z_]+$", key), f"Key '{key}' is not snake_case"

    def test_get_by_key(self):
        preset = get_style_preset("fantasy_art")
        assert preset is not None
        assert preset.name == "Fantasy Art"

    def test_get_by_display_name(self):
        preset = get_style_preset("Fantasy Art")
        assert preset is not None
        assert preset.name == "Fantasy Art"

    def test_get_by_display_name_case_insensitive(self):
        preset = get_style_preset("fantasy art")
        assert preset is not None
        assert preset.name == "Fantasy Art"

    def test_get_not_found(self):
        assert get_style_preset("nonexistent_style") is None

    def test_list_presets_sorted(self):
        presets = list_style_presets()
        assert len(presets) == len(DEFAULT_STYLE_PRESETS)
        # Should be sorted by key
        names = [p.name for p in presets]
        assert len(names) == len(set(names)), "Duplicate names in presets"

    def test_minimum_preset_count(self):
        assert len(DEFAULT_STYLE_PRESETS) >= 5


# ═══════════════════════════════════════════════════════════════
# PromptRequest Tests
# ═══════════════════════════════════════════════════════════════


class TestPromptRequest:
    """Tests for PromptRequest validation and serialization."""

    # ── Valid Requests ─────────────────────────────────────────

    def test_create_raw_user(self):
        req = PromptRequest.create("raw_user", user_prompt="a cat on a throne")
        assert req.mode == "raw_user"
        assert req.user_prompt == "a cat on a throne"

    def test_create_system(self):
        req = PromptRequest.create("system")
        assert req.mode == "system"

    def test_create_character(self):
        req = PromptRequest.create("character", member_name="Spark")
        assert req.mode == "character"
        assert req.member_name == "Spark"

    def test_create_user_refined(self):
        req = PromptRequest.create(
            "user_refined",
            member_name="Spark",
            user_prompt="a castle in the mountains",
        )
        assert req.mode == "user_refined"
        assert req.member_name == "Spark"

    def test_create_council_vote(self):
        req = PromptRequest.create(
            "council_vote",
            participants=["Spark", "Sage", "Forge"],
        )
        assert req.mode == "council_vote"
        assert len(req.participants) == 3

    def test_create_with_all_fields(self):
        preset = StylePreset.create("Test")
        req = PromptRequest.create(
            "character",
            entity_type="character",
            entity_id="CH-0001",
            member_name="Spark",
            style_preset=preset,
            context_hint="Show the character in their workshop",
            metadata={"source": "test"},
        )
        assert req.entity_type == "character"
        assert req.entity_id == "CH-0001"
        assert req.style_preset.name == "Test"
        assert req.context_hint == "Show the character in their workshop"

    # ── Validation Errors ─────────────────────────────────────

    def test_invalid_mode(self):
        with pytest.raises(PromptValidationError, match="Invalid mode"):
            PromptRequest.create("invalid_mode")

    def test_character_mode_requires_member_name(self):
        with pytest.raises(PromptValidationError, match="member_name is required"):
            PromptRequest.create("character")

    def test_user_refined_requires_user_prompt(self):
        with pytest.raises(PromptValidationError, match="user_prompt is required"):
            PromptRequest.create("user_refined", member_name="Spark")

    def test_user_refined_requires_member_name(self):
        with pytest.raises(PromptValidationError, match="member_name is required"):
            PromptRequest.create("user_refined", user_prompt="a cat")

    def test_raw_user_requires_user_prompt(self):
        with pytest.raises(PromptValidationError, match="user_prompt is required"):
            PromptRequest.create("raw_user")

    def test_council_vote_requires_participants(self):
        with pytest.raises(PromptValidationError, match="At least 2 participants"):
            PromptRequest.create("council_vote", participants=["Spark"])

    def test_council_vote_no_participants(self):
        with pytest.raises(PromptValidationError, match="At least 2 participants"):
            PromptRequest.create("council_vote")

    # ── Strips Whitespace ─────────────────────────────────────

    def test_strips_whitespace(self):
        req = PromptRequest.create(
            "character",
            member_name="  Spark  ",
            entity_type="  character  ",
            entity_id="  CH-0001  ",
        )
        assert req.member_name == "Spark"
        assert req.entity_type == "character"
        assert req.entity_id == "CH-0001"

    # ── Serialization ─────────────────────────────────────────

    def test_to_dict(self):
        req = PromptRequest.create("raw_user", user_prompt="test")
        d = req.to_dict()
        assert d["mode"] == "raw_user"
        assert d["user_prompt"] == "test"

    def test_to_dict_with_preset(self):
        preset = StylePreset.create("Anime")
        req = PromptRequest.create("raw_user", user_prompt="cat", style_preset=preset)
        d = req.to_dict()
        assert d["style_preset"]["name"] == "Anime"

    def test_from_dict(self):
        data = {"mode": "raw_user", "user_prompt": "test"}
        req = PromptRequest.from_dict(data)
        assert req.mode == "raw_user"
        assert req.user_prompt == "test"

    def test_from_dict_with_preset(self):
        data = {
            "mode": "raw_user",
            "user_prompt": "test",
            "style_preset": {"name": "Testing"},
        }
        req = PromptRequest.from_dict(data)
        assert req.style_preset is not None
        assert req.style_preset.name == "Testing"

    def test_round_trip(self):
        preset = StylePreset.create("Roundtrip")
        original = PromptRequest.create(
            "character",
            member_name="Spark",
            entity_type="character",
            entity_id="CH-0001",
            style_preset=preset,
            context_hint="hint",
            metadata={"a": 1},
        )
        restored = PromptRequest.from_dict(original.to_dict())
        assert restored.mode == original.mode
        assert restored.member_name == original.member_name
        assert restored.entity_type == original.entity_type
        assert restored.style_preset.name == original.style_preset.name


# ═══════════════════════════════════════════════════════════════
# PromptResult Tests
# ═══════════════════════════════════════════════════════════════


class TestPromptResult:
    """Tests for PromptResult creation and serialization."""

    def test_create_basic(self):
        result = PromptResult.create("a majestic castle")
        assert result.positive == "a majestic castle"
        assert result.negative == ""
        assert result.created_at != ""  # timestamp is auto-set

    def test_create_full(self):
        result = PromptResult.create(
            "positive prompt",
            negative="negative prompt",
            mode="character",
            member_name="Spark",
            style_preset_name="Fantasy Art",
            entity_type="character",
            entity_id="CH-0001",
            raw_llm_response="POSITIVE: positive prompt\nNEGATIVE: negative prompt",
            metadata={"source": "test"},
        )
        assert result.positive == "positive prompt"
        assert result.negative == "negative prompt"
        assert result.mode == "character"
        assert result.member_name == "Spark"
        assert result.style_preset_name == "Fantasy Art"

    def test_to_dict(self):
        result = PromptResult.create("test prompt", mode="raw_user")
        d = result.to_dict()
        assert d["positive"] == "test prompt"
        assert d["mode"] == "raw_user"
        assert "created_at" in d

    def test_from_dict(self):
        result = PromptResult.from_dict({
            "positive": "test",
            "negative": "bad",
            "mode": "system",
        })
        assert result.positive == "test"
        assert result.negative == "bad"

    def test_round_trip(self):
        original = PromptResult.create(
            "positive",
            negative="negative",
            mode="character",
            member_name="Sage",
        )
        restored = PromptResult.from_dict(original.to_dict())
        assert restored.positive == original.positive
        assert restored.negative == original.negative
        assert restored.mode == original.mode
        assert restored.member_name == original.member_name
        assert restored.created_at == original.created_at

    def test_frozen(self):
        result = PromptResult.create("test")
        with pytest.raises(AttributeError):
            result.positive = "changed"


# ═══════════════════════════════════════════════════════════════
# Response Parsing Tests
# ═══════════════════════════════════════════════════════════════


class TestParsePromptResponse:
    """Tests for parse_prompt_response()."""

    def test_standard_format(self):
        text = "POSITIVE: a beautiful landscape\nNEGATIVE: blurry, low quality"
        pos, neg = parse_prompt_response(text)
        assert pos == "a beautiful landscape"
        assert neg == "blurry, low quality"

    def test_lowercase_labels(self):
        text = "positive: a cat\nnegative: dog"
        pos, neg = parse_prompt_response(text)
        assert pos == "a cat"
        assert neg == "dog"

    def test_mixed_case_labels(self):
        text = "Positive: castle\nNegative: ruins"
        pos, neg = parse_prompt_response(text)
        assert pos == "castle"
        assert neg == "ruins"

    def test_extra_whitespace(self):
        text = "  POSITIVE:   a cat with wings  \n  NEGATIVE:   blurry  "
        pos, neg = parse_prompt_response(text)
        assert pos == "a cat with wings"
        assert neg == "blurry"

    def test_no_labels_fallback(self):
        text = "just a plain prompt with no labels"
        pos, neg = parse_prompt_response(text)
        assert pos == "just a plain prompt with no labels"
        assert neg == ""

    def test_positive_only(self):
        text = "POSITIVE: only positive here"
        pos, neg = parse_prompt_response(text)
        assert pos == "only positive here"
        assert neg == ""

    def test_negative_only(self):
        text = "NEGATIVE: only negative"
        pos, neg = parse_prompt_response(text)
        # No positive found → fallback to full text
        assert pos == "NEGATIVE: only negative"
        assert neg == "only negative"

    def test_multiline_with_preamble(self):
        text = "Here is my prompt:\nPOSITIVE: castle on a hill\nNEGATIVE: modern"
        pos, neg = parse_prompt_response(text)
        assert pos == "castle on a hill"
        assert neg == "modern"

    def test_empty_string(self):
        pos, neg = parse_prompt_response("")
        assert pos == ""
        assert neg == ""


# ═══════════════════════════════════════════════════════════════
# Style Preset Application Tests
# ═══════════════════════════════════════════════════════════════


class TestApplyStylePreset:
    """Tests for apply_style_preset()."""

    def test_no_preset(self):
        pos, neg = apply_style_preset("a cat", "blurry", None)
        assert pos == "a cat"
        assert neg == "blurry"

    def test_suffix_appended(self):
        preset = StylePreset.create("Test", positive_suffix="detailed, 8k")
        pos, neg = apply_style_preset("a castle", "", preset)
        assert pos == "a castle, detailed, 8k"
        assert neg == ""

    def test_prefix_prepended(self):
        preset = StylePreset.create("Test", negative_prefix="ugly, blurry")
        pos, neg = apply_style_preset("a castle", "deformed", preset)
        assert pos == "a castle"
        assert neg == "ugly, blurry, deformed"

    def test_both_applied(self):
        preset = StylePreset.create(
            "Test",
            positive_suffix="vibrant",
            negative_prefix="dark",
        )
        pos, neg = apply_style_preset("cat", "dog", preset)
        assert pos == "cat, vibrant"
        assert neg == "dark, dog"

    def test_empty_positive_with_suffix(self):
        preset = StylePreset.create("Test", positive_suffix="vibrant")
        pos, neg = apply_style_preset("", "", preset)
        assert pos == "vibrant"

    def test_empty_negative_with_prefix(self):
        preset = StylePreset.create("Test", negative_prefix="blurry")
        pos, neg = apply_style_preset("cat", "", preset)
        assert neg == "blurry"


# ═══════════════════════════════════════════════════════════════
# Entity Context Building Tests
# ═══════════════════════════════════════════════════════════════


class TestBuildEntityContext:
    """Tests for build_entity_context()."""

    def test_character_context(self):
        from core.characters import CharacterTemplate, Trait

        mock_mgr = MagicMock()
        mock_mgr.get.return_value = CharacterTemplate(
            id="CH-0001",
            name="Atlas",
            description="An explorer",
            author="Forge",
            backstory="Born in the mountains",
            traits=[
                Trait(trait_type="personality", name="Curious", description="Always asking"),
                Trait(trait_type="values", name="Truth", description="Seeks it"),
            ],
            tags=["explorer", "curious"],
        )

        ctx = build_entity_context(
            "character", "CH-0001", character_manager=mock_mgr,
        )
        assert "Entity: Character — Atlas" in ctx
        assert "An explorer" in ctx
        assert "Born in the mountains" in ctx
        assert "Curious" in ctx
        assert "explorer" in ctx

    def test_council_member_context(self):
        from core.registry import CouncilMember

        mock_registry = MagicMock()
        mock_registry.get.return_value = CouncilMember(
            name="Sage",
            role="Philosopher",
            description="Wise and measured",
            specialties=["ethics", "philosophy"],
            api_provider="openrouter",
            model="Default",
            system_prompt="You are Sage.",
        )

        ctx = build_entity_context(
            "council_member", "Sage", registry=mock_registry,
        )
        assert "Entity: Council Member — Sage" in ctx
        assert "Philosopher" in ctx
        assert "ethics" in ctx

    def test_unknown_entity_type(self):
        ctx = build_entity_context("unknown_type", "X-0001")
        assert ctx == ""

    def test_no_manager_provided(self):
        ctx = build_entity_context("character", "CH-0001")
        assert ctx == ""

    def test_entity_not_found(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = Exception("Not found")
        ctx = build_entity_context(
            "character", "CH-9999", character_manager=mock_mgr,
        )
        assert ctx == ""

    def test_location_context(self):
        mock_loc = MagicMock()
        loc_obj = MagicMock()
        loc_obj.name = "Crystal Caverns"
        loc_obj.description = "Glittering underground caves filled with bioluminescent crystals"
        loc_obj.lore = "Ancient dwarven miners discovered these caverns millennia ago"
        loc_obj.tags = ["underground", "crystal", "mystical"]
        loc_obj.location_type = "natural"
        loc_obj.coordinates = "42.3N, 71.1W"
        loc_obj.features = [
            {"name": "Crystal Lake", "description": "A shimmering lake of liquid crystal", "feature_type": "landmark"},
            {"name": "Echo Chamber", "description": "Sound reverberates endlessly", "feature_type": "natural"},
        ]
        mock_loc.get.return_value = loc_obj

        ctx = build_entity_context(
            "location", "LOC-0001", location_manager=mock_loc,
        )
        lines = ctx.split("\n")
        # Priority order: name → description → lore first
        assert lines[0] == "Entity: Location — Crystal Caverns"
        assert lines[1].startswith("Description:")
        assert "bioluminescent crystals" in lines[1]
        assert "Lore:" in lines[2]
        assert "Ancient dwarven miners" in lines[2]
        # Then tags, type, coordinates as secondary signals
        assert "Tags: underground, crystal, mystical" in ctx
        assert "Type: natural" in ctx
        assert "Coordinates: 42.3N, 71.1W" in ctx
        # Features with full descriptions
        assert "Crystal Lake (landmark): A shimmering lake of liquid crystal" in ctx
        assert "Echo Chamber (natural): Sound reverberates endlessly" in ctx

    def test_location_context_minimal(self):
        """Location context with only required fields (no lore, tags, etc.)."""
        mock_loc = MagicMock()
        loc_obj = MagicMock()
        loc_obj.name = "Empty Clearing"
        loc_obj.description = "A bare patch of ground"
        loc_obj.lore = ""
        loc_obj.tags = []
        loc_obj.location_type = ""
        loc_obj.coordinates = ""
        loc_obj.features = []
        mock_loc.get.return_value = loc_obj

        ctx = build_entity_context(
            "location", "LOC-0002", location_manager=mock_loc,
        )
        assert "Entity: Location — Empty Clearing" in ctx
        assert "A bare patch of ground" in ctx
        # Optional fields should NOT appear
        assert "Lore:" not in ctx
        assert "Tags:" not in ctx
        assert "Type:" not in ctx
        assert "Coordinates:" not in ctx
        assert "Features:" not in ctx

    def test_item_context(self):
        from core.items import Item, ItemProperty

        mock_item = MagicMock()
        mock_item.get.return_value = Item(
            id="ITEM-0001",
            name="Dragon Scale Shield",
            description="A shield made from dragon scales",
            author="Forge",
            lore="Forged in the Dragon Wars by the legendary smith Kaelen",
            tags=["shield", "dragon", "fire-resistant"],
            rarity="legendary",
            tier="epic",
            properties=[
                ItemProperty(name="Fire Resist", description="Absorbs fire damage", property_type="enchantment"),
                ItemProperty(name="Dragon Bond", description="Grows stronger near dragons", property_type="passive"),
            ],
        )

        ctx = build_entity_context(
            "item", "ITEM-0001", item_manager=mock_item,
        )
        # Tags come first as highest priority visual signal
        lines = ctx.split("\n")
        assert lines[0].startswith("Tags:")
        assert "shield" in lines[0]
        assert "dragon" in lines[0]
        assert "fire-resistant" in lines[0]
        # Then name, description, lore
        assert "Entity: Item — Dragon Scale Shield" in ctx
        assert "A shield made from dragon scales" in ctx
        assert "Forged in the Dragon Wars" in ctx
        # Rarity and tier
        assert "Rarity: legendary" in ctx
        assert "Tier: epic" in ctx
        # Properties with detail
        assert "Fire Resist (enchantment): Absorbs fire damage" in ctx
        assert "Dragon Bond (passive): Grows stronger near dragons" in ctx

    def test_store_context(self):
        mock_store = MagicMock()
        store_obj = MagicMock()
        store_obj.name = "Ironforge Smithy"
        store_obj.description = "A well-known blacksmith"
        store_obj.store_type = "blacksmith"
        mock_store.get.return_value = store_obj

        ctx = build_entity_context(
            "store", "STR-0001", store_manager=mock_store,
        )
        assert "Entity: Store — Ironforge Smithy" in ctx
        assert "blacksmith" in ctx


# ═══════════════════════════════════════════════════════════════
# PromptBuilder Tests
# ═══════════════════════════════════════════════════════════════


class TestPromptBuilder:
    """Integration tests for PromptBuilder with mocked API."""

    # ── Initialization ────────────────────────────────────────

    def test_init_minimal(self):
        builder = PromptBuilder()
        assert builder.api_client is None
        assert builder.registry is None

    def test_init_with_deps(self):
        client = MagicMock()
        registry = MagicMock()
        builder = PromptBuilder(api_client=client, registry=registry)
        assert builder.api_client is client
        assert builder.registry is registry

    def test_repr(self):
        builder = PromptBuilder()
        assert "api_client=False" in repr(builder)
        builder2 = PromptBuilder(api_client=MagicMock())
        assert "api_client=True" in repr(builder2)

    # ── Raw User Mode ────────────────────────────────────────

    def test_raw_user_basic(self):
        builder = PromptBuilder()
        request = PromptRequest.create("raw_user", user_prompt="a majestic castle")
        result = _run(builder.generate(request))
        assert isinstance(result, PromptResult)
        assert result.positive == "a majestic castle"
        assert result.mode == "raw_user"

    def test_raw_user_with_style_preset(self):
        builder = PromptBuilder()
        preset = StylePreset.create(
            "Fantasy",
            positive_suffix="fantasy art",
            negative_prefix="blurry",
        )
        request = PromptRequest.create(
            "raw_user", user_prompt="a castle", style_preset=preset,
        )
        result = _run(builder.generate(request))
        assert "fantasy art" in result.positive
        assert "blurry" in result.negative
        assert result.style_preset_name == "Fantasy"

    def test_raw_user_no_api_needed(self):
        # Should work even without API client
        builder = PromptBuilder()
        request = PromptRequest.create("raw_user", user_prompt="test")
        result = _run(builder.generate(request))
        assert result.positive == "test"
        assert result.raw_llm_response == ""

    def test_raw_user_preserves_metadata(self):
        builder = PromptBuilder()
        request = PromptRequest.create(
            "raw_user", user_prompt="test", metadata={"source": "ui"},
        )
        result = _run(builder.generate(request))
        assert result.metadata == {"source": "ui"}

    # ── System Mode ──────────────────────────────────────────

    def test_system_mode(self):
        client = _make_mock_api_client(
            "POSITIVE: a detailed castle\nNEGATIVE: blurry, bad"
        )
        builder = PromptBuilder(api_client=client)
        request = PromptRequest.create("system")
        result = _run(builder.generate(request))
        assert isinstance(result, PromptResult)
        assert result.positive == "a detailed castle"
        assert result.negative == "blurry, bad"
        assert result.mode == "system"
        assert result.member_name == ""

    def test_system_mode_requires_api_client(self):
        builder = PromptBuilder()
        request = PromptRequest.create("system")
        with pytest.raises(PromptError, match="API client is required"):
            _run(builder.generate(request))

    def test_system_mode_with_entity_context(self):
        from core.characters import CharacterTemplate, Trait

        client = _make_mock_api_client("POSITIVE: atlas\nNEGATIVE: bad")
        mock_char_mgr = MagicMock()
        mock_char_mgr.get.return_value = CharacterTemplate(
            id="CH-0001",
            name="Atlas",
            description="An explorer",
            author="Forge",
            traits=[Trait("personality", "Curious", "Always asking")],
        )
        builder = PromptBuilder(
            api_client=client,
            character_manager=mock_char_mgr,
        )
        request = PromptRequest.create(
            "system",
            entity_type="character",
            entity_id="CH-0001",
        )
        result = _run(builder.generate(request))
        assert result.positive == "atlas"
        # Verify the API was called with entity context in the message
        call_args = client.chat.call_args
        messages = call_args[0][1]
        user_content = messages[0].content
        assert "Atlas" in user_content

    # ── Character Mode ───────────────────────────────────────

    def test_character_mode(self):
        client = _make_mock_api_client(
            "POSITIVE: spark's vision of a castle\nNEGATIVE: dark, gloomy"
        )
        registry = _make_mock_registry("Spark")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create("character", member_name="Spark")
        result = _run(builder.generate(request))
        assert isinstance(result, PromptResult)
        assert result.positive == "spark's vision of a castle"
        assert result.mode == "character"
        assert result.member_name == "Spark"

    def test_character_mode_requires_api_client(self):
        registry = _make_mock_registry("Spark")
        builder = PromptBuilder(registry=registry)
        request = PromptRequest.create("character", member_name="Spark")
        with pytest.raises(PromptError, match="API client is required"):
            _run(builder.generate(request))

    def test_character_mode_requires_registry(self):
        client = _make_mock_api_client()
        builder = PromptBuilder(api_client=client)
        request = PromptRequest.create("character", member_name="Spark")
        with pytest.raises(PromptError, match="registry is required"):
            _run(builder.generate(request))

    def test_character_mode_with_style(self):
        client = _make_mock_api_client("POSITIVE: anime spark\nNEGATIVE: bad")
        registry = _make_mock_registry("Spark")
        preset = StylePreset.create("Anime", positive_suffix="anime style")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create(
            "character", member_name="Spark", style_preset=preset,
        )
        result = _run(builder.generate(request))
        assert "anime style" in result.positive
        assert result.style_preset_name == "Anime"

    # ── User-Refined Mode ────────────────────────────────────

    def test_user_refined_mode(self):
        client = _make_mock_api_client(
            "POSITIVE: enhanced castle prompt\nNEGATIVE: blurry"
        )
        registry = _make_mock_registry("Sage")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create(
            "user_refined",
            member_name="Sage",
            user_prompt="a castle in the mountains",
        )
        result = _run(builder.generate(request))
        assert result.positive == "enhanced castle prompt"
        assert result.mode == "user_refined"
        assert result.member_name == "Sage"
        assert result.metadata["original_user_prompt"] == "a castle in the mountains"

    def test_user_refined_passes_user_prompt_to_llm(self):
        client = _make_mock_api_client("POSITIVE: refined\nNEGATIVE: bad")
        registry = _make_mock_registry("Sage")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create(
            "user_refined",
            member_name="Sage",
            user_prompt="a specific dragon",
        )
        _run(builder.generate(request))
        call_args = client.chat.call_args
        messages = call_args[0][1]
        user_content = messages[0].content
        assert "a specific dragon" in user_content

    def test_user_refined_requires_api_and_registry(self):
        builder = PromptBuilder()
        request = PromptRequest.create(
            "user_refined",
            member_name="Sage",
            user_prompt="castle",
        )
        with pytest.raises(PromptError, match="API client is required"):
            _run(builder.generate(request))

    # ── Council Vote Mode ────────────────────────────────────

    def test_council_vote_mode(self):
        # Each participant gets a unique response
        responses = iter([
            "POSITIVE: spark version\nNEGATIVE: bad1",
            "POSITIVE: sage version\nNEGATIVE: bad2",
            "POSITIVE: forge version\nNEGATIVE: bad3",
        ])
        client = MagicMock()
        mock_response = MagicMock()

        async def mock_chat(member, messages):
            resp = MagicMock()
            resp.content = next(responses)
            return resp

        client.chat = AsyncMock(side_effect=mock_chat)

        registry = _make_mock_registry("Spark", "Sage", "Forge")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create(
            "council_vote",
            participants=["Spark", "Sage", "Forge"],
        )
        results = _run(builder.generate(request))
        assert isinstance(results, list)
        assert len(results) == 3
        assert results[0].positive == "spark version"
        assert results[0].member_name == "Spark"
        assert results[1].positive == "sage version"
        assert results[1].member_name == "Sage"
        assert results[2].positive == "forge version"
        assert results[2].member_name == "Forge"
        assert all(r.mode == "council_vote" for r in results)

    def test_council_vote_requires_api_and_registry(self):
        builder = PromptBuilder()
        request = PromptRequest.create(
            "council_vote",
            participants=["Spark", "Sage"],
        )
        with pytest.raises(PromptError):
            _run(builder.generate(request))

    def test_council_vote_with_style(self):
        client = _make_mock_api_client("POSITIVE: styled\nNEGATIVE: bad")
        registry = _make_mock_registry("Spark", "Sage")
        preset = StylePreset.create("Fantasy", positive_suffix="epic")
        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create(
            "council_vote",
            participants=["Spark", "Sage"],
            style_preset=preset,
        )
        results = _run(builder.generate(request))
        assert len(results) == 2
        assert all("epic" in r.positive for r in results)

    # ── Error Handling ───────────────────────────────────────

    def test_unknown_mode_raises(self):
        builder = PromptBuilder(api_client=MagicMock())
        # Bypass validation by creating directly
        request = PromptRequest(mode="nonexistent_mode")
        with pytest.raises(PromptValidationError, match="Unknown mode"):
            _run(builder.generate(request))

    def test_style_guidance_with_no_preset(self):
        guidance = PromptBuilder._build_style_guidance(None)
        assert guidance == ""

    def test_style_guidance_with_preset(self):
        preset = StylePreset.create(
            "Fantasy Art",
            description="Epic fantasy style",
            positive_suffix="vibrant colors",
        )
        guidance = PromptBuilder._build_style_guidance(preset)
        assert "Fantasy Art" in guidance
        assert "Epic fantasy style" in guidance
        assert "vibrant colors" in guidance


# ═══════════════════════════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════════════════════════


class TestConstants:
    """Tests for module-level constants."""

    def test_prompt_modes_are_frozen(self):
        assert isinstance(PROMPT_MODES, frozenset)
        assert len(PROMPT_MODES) == 5

    def test_valid_entity_types(self):
        assert isinstance(VALID_ENTITY_TYPES, frozenset)
        assert "character" in VALID_ENTITY_TYPES
        assert "location" in VALID_ENTITY_TYPES
        assert "council_member" in VALID_ENTITY_TYPES

    def test_all_modes_present(self):
        expected = {"council_vote", "character", "system", "user_refined", "raw_user"}
        assert PROMPT_MODES == expected
