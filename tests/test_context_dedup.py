"""
Tests for F-055: Eliminate Explore/Story Chat Context Duplication.

Verifies that:
1. _build_participant_context skips world context when skip_world_context=True
2. _build_participant_context includes world context by default
3. MemoryInfluence.build_context skips world entities when skip_world_entities=True
4. HumanChat._should_skip_world_entities detects explore/story chats
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── _build_participant_context tests ──────────────────────────────────

class TestBuildParticipantContextSkipWorld:
    """Test skip_world_context parameter on _build_participant_context."""

    def _build(self, participants, *, skip_world_context=False):
        """Import and call the real function."""
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants, skip_world_context=skip_world_context,
        )

    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    @patch("core.context_builder.get_registry")
    def test_default_includes_world_context(
        self,
        mock_registry, mock_store_mgr, mock_item_mgr,
        mock_loc_mgr, mock_law_mgr,
    ):
        """Default call includes 'World Context' section."""
        # Mock registry returns no members (simplifies test)
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        # Mock managers return empty lists
        mock_law_mgr.return_value.list_laws.return_value = []
        mock_loc_mgr.return_value.list_locations.return_value = []
        mock_item_mgr.return_value.list_items.return_value = []
        mock_store_mgr.return_value.list_stores.return_value = []

        result = self._build(
            [{"id": "sage", "type": "council"}],
            skip_world_context=False,
        )

        assert "World Context" in result

    @patch("core.context_builder.get_registry")
    def test_skip_world_context_omits_section(self, mock_registry):
        """When skip_world_context=True, 'World Context' is NOT in output."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            skip_world_context=True,
        )

        assert "World Context" not in result
        assert "Known Locations" not in result
        assert "Known Items" not in result
        assert "Known Stores" not in result
        assert "Active Laws" not in result

    @patch("core.context_builder.get_registry")
    def test_skip_world_context_still_includes_participants(
        self, mock_registry,
    ):
        """Participant data is preserved when world context is skipped."""
        mock_reg = MagicMock()
        member = MagicMock()
        member.name = "Sage"
        member.role = "Ethics Advisor"
        member.description = "Wise counsel"
        member.system_prompt = "You are Sage"
        member.specialties = ["ethics"]
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            skip_world_context=True,
        )

        assert "Present Participants" in result
        assert "Sage" in result
        assert "Ethics Advisor" in result

    @patch("core.context_builder.get_character_manager")
    @patch("core.context_builder.get_registry")
    def test_skip_world_preserves_character_context(
        self, mock_registry, mock_char_mgr,
    ):
        """Character data is preserved when world context is skipped."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        mock_char = MagicMock()
        mock_char.name = "Aria"
        mock_char.description = "A mysterious elf"
        mock_char.backstory = "Born under the twin moons"
        mock_char.traits = []
        mock_char.system_prompt = ""
        mock_char_mgr.return_value.get.return_value = mock_char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            skip_world_context=True,
        )

        assert "Aria" in result
        assert "mysterious elf" in result
        assert "World Context" not in result

    def test_empty_participants_returns_empty(self):
        """Empty participant list returns empty string regardless."""
        result_default = self._build([], skip_world_context=False)
        result_skip = self._build([], skip_world_context=True)
        assert result_default == ""
        assert result_skip == ""


# ── _helpers.py re-export tests ───────────────────────────────────────

class TestHelpersReExport:
    """Test that _helpers.py correctly forwards skip_world_context."""

    @patch("core.context_builder.get_registry")
    def test_helpers_forwards_skip_world(self, mock_registry):
        """The _helpers re-export accepts and forwards skip_world_context."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        from core.routes._helpers import _build_participant_context
        result = _build_participant_context(
            [{"id": "sage", "type": "council"}],
            skip_world_context=True,
        )
        assert "World Context" not in result


# ── MemoryInfluence.build_context tests ───────────────────────────────

class TestMemoryInfluenceSkipWorld:
    """Test skip_world_entities parameter on build_context."""

    def _make_mi(self, tmp_path):
        """Create a MemoryInfluence with file-based test fixtures."""
        from core.memory_influence import MemoryInfluence

        # Create a minimal agent memory directory
        sage_dir = tmp_path / "sage"
        sage_dir.mkdir()
        (sage_dir / "core_beliefs.json").write_text("[]", encoding="utf-8")
        (sage_dir / "session_log.jsonl").write_text("", encoding="utf-8")

        return MemoryInfluence(
            embedding_provider=None,
            memories_dir=tmp_path,
            contested_enabled=False,
        )

    def test_skip_world_entities_no_locations_or_items(self, tmp_path):
        """When skip_world_entities=True, formatted_text has no world data."""
        mi = self._make_mi(tmp_path)

        # Create a location file so we can verify it's skipped
        loc_dir = tmp_path / "locations"
        loc_dir.mkdir()
        loc_data = {
            "id": "LOC-0001",
            "name": "Test Village",
            "description": "A quiet village",
            "lore": "",
            "tags": [],
            "status": "active",
            "coordinates": {},
            "parent_location_id": "",
            "features": [],
            "images": [],
            "llm_injection": "",
        }
        (loc_dir / "LOC-0001.json").write_text(
            json.dumps(loc_data), encoding="utf-8",
        )

        ctx = mi.build_context(
            "sage", ["test"],
            memories_dir=tmp_path,
            locations_dir=loc_dir,
            skip_world_entities=True,
        )

        assert "Test Village" not in ctx.formatted_text
        assert "World Locations" not in ctx.formatted_text
        assert "World Items" not in ctx.formatted_text

    @patch("core.memory_influence.MemoryInfluence._load_active_items")
    @patch("core.memory_influence.MemoryInfluence._load_active_locations")
    def test_default_includes_world_entities(
        self, mock_locs, mock_items, tmp_path,
    ):
        """Default call includes world locations/items."""
        mi = self._make_mi(tmp_path)

        # Mock a location object
        mock_loc = MagicMock()
        mock_loc.name = "Test Village"
        mock_loc.description = "A quiet village"
        mock_loc.lore = ""
        mock_loc.features = []
        mock_locs.return_value = [mock_loc]
        mock_items.return_value = []

        ctx = mi.build_context(
            "sage", ["test"],
            memories_dir=tmp_path,
            skip_world_entities=False,
        )

        assert "Test Village" in ctx.formatted_text


# ── HumanChat._should_skip_world_entities tests ──────────────────────

class TestShouldSkipWorldEntities:
    """Test the _should_skip_world_entities classifier."""

    def _make_record(self, metadata=None):
        """Create a minimal HumanChatRecord."""
        from core.human_chat import HumanChatRecord
        return HumanChatRecord(
            chat_id="H-TEST",
            title="Test Chat",
            member_name="sage",
            topic="test",
            messages=[],
            summary="",
            created_at="2025-01-01T00:00:00+00:00",
            closed_at="",
            metadata=metadata or {},
            council_members=["sage"],
            characters=[],
            paused=False,
        )

    def test_regular_chat_does_not_skip(self):
        """Regular human chats should NOT skip world entities."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata={})
        assert HumanChat._should_skip_world_entities(record) is False

    def test_explore_chat_skips(self):
        """Explore chats (with explore_location_id) SHOULD skip."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata={
            "explore_location_id": "LOC-0001",
            "location_name": "Test Village",
        })
        assert HumanChat._should_skip_world_entities(record) is True

    def test_story_chat_skips(self):
        """Story chats (with story_chat=True) SHOULD skip."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata={
            "story_chat": True,
            "story_id": "STR-0001",
        })
        assert HumanChat._should_skip_world_entities(record) is True

    def test_empty_metadata_does_not_skip(self):
        """Chat with None metadata should NOT skip."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata=None)
        assert HumanChat._should_skip_world_entities(record) is False

    def test_story_chat_false_does_not_skip(self):
        """Chat with story_chat=False should NOT skip."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata={"story_chat": False})
        assert HumanChat._should_skip_world_entities(record) is False

    def test_empty_explore_location_does_not_skip(self):
        """Chat with blank explore_location_id should NOT skip."""
        from core.human_chat import HumanChat
        record = self._make_record(metadata={"explore_location_id": ""})
        assert HumanChat._should_skip_world_entities(record) is False
