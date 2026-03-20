"""Unit tests for core.png_embed — PNG tEXt chunk character card emb."""

from __future__ import annotations

import json, base64, struct, zlib
from pathlib import Path

import pytest

from core.png_embed import (
    create_minimal_png,
    embed_character_in_png,
    extract_character_from_png,
    character_to_tavern_v2,
    _read_chunks,
)


# ── Helpers ─────────────────────────────────────────────────────

def _make_character(tmpdir):
    """Create a real CharacterTemplate via CharacterManager."""
    from core.characters import CharacterManager, Trait

    mgr = CharacterManager(characters_dir=Path(tmpdir))
    trait = Trait.create("personality", "Curious", "Loves learning", 0.9)
    char = mgr.create(
        "Atlas",
        "A wandering cartographer",
        author="Forge",
        backstory="Once explored every continent",
        traits=[trait],
        system_prompt="You are Atlas the explorer.",
        greeting="Hello traveler!",
        example_messages=["What lies beyond the horizon?"],
        tags=["explorer", "cartographer"],
    )
    return char


# ── Tests ───────────────────────────────────────────────────────

class TestCreateMinimalPng:
    def test_valid_png(self):
        data = create_minimal_png()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        chunks = _read_chunks(data)
        types = [c["type"] for c in chunks]
        assert "IHDR" in types
        assert "IDAT" in types
        assert "IEND" in types


class TestEmbedAndExtract:
    def test_round_trip(self, tmp_path):
        char = _make_character(tmp_path)
        png = create_minimal_png()

        embedded = embed_character_in_png(png, char)
        assert embedded[:8] == b"\x89PNG\r\n\x1a\n"

        result = extract_character_from_png(embedded)
        assert result is not None
        assert result["spec"] == "chara_card_v2"
        assert result["data"]["name"] == "Atlas"
        assert result["data"]["creator"] == "Forge"
        assert "explorer" in result["data"]["tags"]

    def test_replaces_existing_text_chunks(self, tmp_path):
        """Embedding twice should not accumulate tEXt chunks."""
        char = _make_character(tmp_path)
        png = create_minimal_png()

        once = embed_character_in_png(png, char)
        twice = embed_character_in_png(once, char)
        chunks = _read_chunks(twice)
        text_chunks = [c for c in chunks if c["type"] == "tEXt"]
        assert len(text_chunks) == 1

    def test_extract_from_clean_png_returns_none(self):
        png = create_minimal_png()
        assert extract_character_from_png(png) is None

    def test_invalid_data_raises(self):
        with pytest.raises(ValueError):
            _read_chunks(b"not a png")


class TestCharacterToTavernV2:
    def test_basic_conversion(self, tmp_path):
        char = _make_character(tmp_path)
        result = character_to_tavern_v2(char)

        assert result["spec"] == "chara_card_v2"
        assert result["spec_version"] == "2.0"
        d = result["data"]
        assert d["name"] == "Atlas"
        assert d["creator"] == "Forge"
        assert d["first_mes"] == "Hello traveler!"
        assert d["system_prompt"] == "You are Atlas the explorer."
        assert "explorer" in d["tags"]
        assert "Curious" in d["personality"]
        assert d["extensions"]["jericho"]["id"].startswith("CH-")
