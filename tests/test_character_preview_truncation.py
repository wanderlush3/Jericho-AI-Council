"""
Tests for F-062: Aggressive Character Preview Truncation.

Verifies that:
1. Character backstory previews are truncated to 200 chars (not 500)
2. Character persona (system_prompt) previews are truncated to 200 chars
3. Council member persona previews remain at 500 chars
4. Truncated text gets "…" appended, non-truncated text does not
5. Settings constants are used (configurable, not hardcoded)
6. Token savings are realized with multiple characters
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Character Backstory Truncation ───────────────────────────────────


class TestCharacterBackstoryTruncation:
    """Test that character backstory is truncated to 200 chars."""

    def _build(self, participants, *, current_speaker=None):
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,
            current_speaker=current_speaker,
        )

    def _mock_char(self, name="Aria", backstory="", system_prompt="",
                   description="An elf mage"):
        char = MagicMock()
        char.name = name
        char.description = description
        char.backstory = backstory
        char.system_prompt = system_prompt
        char.traits = []
        return char

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_short_backstory_not_truncated(self, mock_registry, mock_cmgr):
        """Backstory under 200 chars is included in full without ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        short_bs = "Born in the crystal caves of Aetheron."  # ~38 chars
        char = self._mock_char(backstory=short_bs)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        assert short_bs in result
        assert "…" not in result.split("**Backstory:**")[1].split("\n")[0]

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_long_backstory_truncated_at_200(self, mock_registry, mock_cmgr):
        """Backstory over 200 chars is truncated with ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        long_bs = "A" * 500  # Well over 200
        char = self._mock_char(backstory=long_bs)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        # Should contain exactly 200 A's, not 500
        backstory_line = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ][0]
        # Extract the preview text after "**Backstory:** "
        preview = backstory_line.split("**Backstory:** ")[1]
        assert preview == "A" * 200 + "…"

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_exactly_200_char_backstory_no_ellipsis(
        self, mock_registry, mock_cmgr,
    ):
        """Backstory of exactly 200 chars gets no ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        exact_bs = "B" * 200
        char = self._mock_char(backstory=exact_bs)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        backstory_line = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ][0]
        preview = backstory_line.split("**Backstory:** ")[1]
        assert preview == "B" * 200  # No ellipsis

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_201_char_backstory_has_ellipsis(
        self, mock_registry, mock_cmgr,
    ):
        """Backstory of 201 chars gets ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        bs = "C" * 201
        char = self._mock_char(backstory=bs)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        backstory_line = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ][0]
        preview = backstory_line.split("**Backstory:** ")[1]
        assert preview == "C" * 200 + "…"


# ── Character Persona Truncation ─────────────────────────────────────


class TestCharacterPersonaTruncation:
    """Test that character system_prompt preview is truncated to 200 chars."""

    def _build(self, participants, *, current_speaker=None):
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,
            current_speaker=current_speaker,
        )

    def _mock_char(self, name="Aria", backstory="", system_prompt="",
                   description="An elf mage"):
        char = MagicMock()
        char.name = name
        char.description = description
        char.backstory = backstory
        char.system_prompt = system_prompt
        char.traits = []
        return char

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_short_persona_not_truncated(self, mock_registry, mock_cmgr):
        """System prompt under 200 chars is included in full."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        short_prompt = "You are Aria, a wise elf mage."
        char = self._mock_char(system_prompt=short_prompt)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        assert short_prompt in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_long_persona_truncated_at_200(self, mock_registry, mock_cmgr):
        """System prompt over 200 chars is truncated with ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        long_prompt = "X" * 500
        char = self._mock_char(system_prompt=long_prompt)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        persona_line = [
            l for l in result.split("\n") if "**Persona:**" in l
        ][0]
        preview = persona_line.split("**Persona:** ")[1]
        assert preview == "X" * 200 + "…"

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_exactly_200_char_persona_no_ellipsis(
        self, mock_registry, mock_cmgr,
    ):
        """System prompt of exactly 200 chars gets no ellipsis."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        exact_prompt = "Y" * 200
        char = self._mock_char(system_prompt=exact_prompt)
        mock_cmgr.return_value.get.return_value = char

        result = self._build([{"id": "CH-0001", "type": "character"}])

        persona_line = [
            l for l in result.split("\n") if "**Persona:**" in l
        ][0]
        preview = persona_line.split("**Persona:** ")[1]
        assert preview == "Y" * 200


# ── Council Member Persona Stays at 500 ──────────────────────────────


class TestCouncilMemberPreserved:
    """Council member persona preview remains at 500 chars."""

    def _build(self, participants, *, current_speaker=None):
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,
            current_speaker=current_speaker,
        )

    @patch("core.routes.explore.get_registry")
    def test_council_member_uses_500_char_preview(self, mock_registry):
        """Council member system_prompt is truncated at 500, not 200."""
        member = MagicMock()
        member.name = "Sage"
        member.role = "Ethics Advisor"
        member.description = "Wise"
        member.system_prompt = "Z" * 600
        member.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build([{"id": "sage", "type": "council"}])

        persona_line = [
            l for l in result.split("\n") if "**Persona:**" in l
        ][0]
        preview = persona_line.split("**Persona:** ")[1]
        # Should have 500 Z's + ellipsis, NOT 200
        assert preview == "Z" * 500 + "…"

    @patch("core.routes.explore.get_registry")
    def test_council_300_char_prompt_no_ellipsis(self, mock_registry):
        """Council member with 300-char prompt: no truncation, no ellipsis."""
        member = MagicMock()
        member.name = "Sage"
        member.role = "Ethics"
        member.description = ""
        member.system_prompt = "W" * 300
        member.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build([{"id": "sage", "type": "council"}])

        persona_line = [
            l for l in result.split("\n") if "**Persona:**" in l
        ][0]
        preview = persona_line.split("**Persona:** ")[1]
        assert preview == "W" * 300  # 300 is within 500 limit


# ── Settings Constants Used ──────────────────────────────────────────


class TestSettingsConstants:
    """Verify the settings constants exist and have expected values."""

    def test_character_backstory_preview_length(self):
        from config.settings import CHARACTER_BACKSTORY_PREVIEW_LENGTH
        assert CHARACTER_BACKSTORY_PREVIEW_LENGTH == 200

    def test_character_persona_preview_length(self):
        from config.settings import CHARACTER_PERSONA_PREVIEW_LENGTH
        assert CHARACTER_PERSONA_PREVIEW_LENGTH == 200

    def test_council_persona_preview_length(self):
        from config.settings import COUNCIL_PERSONA_PREVIEW_LENGTH
        assert COUNCIL_PERSONA_PREVIEW_LENGTH == 500


# ── Configurable Preview Length ──────────────────────────────────────


class TestConfigurablePreviewLength:
    """Test that changing the config constant changes the behavior."""

    @patch("core.routes.explore.CHARACTER_BACKSTORY_PREVIEW_LENGTH", 100)
    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_custom_backstory_length(self, mock_registry, mock_cmgr):
        """Overriding CHARACTER_BACKSTORY_PREVIEW_LENGTH to 100 works."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = MagicMock()
        char.name = "Aria"
        char.description = "Elf"
        char.backstory = "D" * 300
        char.system_prompt = ""
        char.traits = []
        mock_cmgr.return_value.get.return_value = char

        from core.routes.explore import _build_participant_context
        result = _build_participant_context(
            [{"id": "CH-0001", "type": "character"}],
            skip_world_context=True,
        )

        backstory_line = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ][0]
        preview = backstory_line.split("**Backstory:** ")[1]
        assert preview == "D" * 100 + "…"

    @patch("core.routes.explore.CHARACTER_PERSONA_PREVIEW_LENGTH", 50)
    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_custom_persona_length(self, mock_registry, mock_cmgr):
        """Overriding CHARACTER_PERSONA_PREVIEW_LENGTH to 50 works."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = MagicMock()
        char.name = "Aria"
        char.description = "Elf"
        char.backstory = ""
        char.system_prompt = "E" * 300
        char.traits = []
        mock_cmgr.return_value.get.return_value = char

        from core.routes.explore import _build_participant_context
        result = _build_participant_context(
            [{"id": "CH-0001", "type": "character"}],
            skip_world_context=True,
        )

        persona_line = [
            l for l in result.split("\n") if "**Persona:**" in l
        ][0]
        preview = persona_line.split("**Persona:** ")[1]
        assert preview == "E" * 50 + "…"


# ── Multi-Character Token Savings ────────────────────────────────────


class TestMultiCharacterSavings:
    """Verify token savings when multiple characters are present."""

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_multiple_characters_use_short_previews(
        self, mock_registry, mock_cmgr,
    ):
        """Multiple characters each get 200-char previews, not 500."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char1 = MagicMock()
        char1.name = "Aria"
        char1.description = "Elf"
        char1.backstory = "F" * 500
        char1.system_prompt = "G" * 500
        char1.traits = []

        char2 = MagicMock()
        char2.name = "Bor"
        char2.description = "Dwarf"
        char2.backstory = "H" * 500
        char2.system_prompt = "I" * 500
        char2.traits = []

        mock_cmgr.return_value.get.side_effect = [char1, char2]

        from core.routes.explore import _build_participant_context
        result = _build_participant_context(
            [
                {"id": "CH-0001", "type": "character"},
                {"id": "CH-0002", "type": "character"},
            ],
            skip_world_context=True,
        )

        # Each backstory should have exactly 200 + ellipsis
        backstory_lines = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ]
        assert len(backstory_lines) == 2
        for line in backstory_lines:
            preview_text = line.split("**Backstory:** ")[1]
            # Should be 200 chars + "…" = 201 visible chars
            assert len(preview_text) == 201
            assert preview_text.endswith("…")

        # Each persona should have exactly 200 + ellipsis
        persona_lines = [
            l for l in result.split("\n") if "**Persona:**" in l
        ]
        assert len(persona_lines) == 2
        for line in persona_lines:
            preview_text = line.split("**Persona:** ")[1]
            assert len(preview_text) == 201
            assert preview_text.endswith("…")

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_three_characters_total_backstory_under_700(
        self, mock_registry, mock_cmgr,
    ):
        """3 chars × 200-char backstory < 700 chars total (was 1500 at 500)."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        chars = []
        for i, name in enumerate(["Aria", "Bor", "Cel"]):
            c = MagicMock()
            c.name = name
            c.description = f"Char {name}"
            c.backstory = f"{'X' * 500}"
            c.system_prompt = ""
            c.traits = []
            chars.append(c)

        mock_cmgr.return_value.get.side_effect = chars

        from core.routes.explore import _build_participant_context
        result = _build_participant_context(
            [
                {"id": f"CH-000{i}", "type": "character"}
                for i in range(1, 4)
            ],
            skip_world_context=True,
        )

        # Count total backstory chars (3 × 200 = 600 chars of content)
        backstory_lines = [
            l for l in result.split("\n") if "**Backstory:**" in l
        ]
        assert len(backstory_lines) == 3
        total_backstory_chars = sum(
            len(line.split("**Backstory:** ")[1].rstrip("…"))
            for line in backstory_lines
        )
        assert total_backstory_chars == 600  # 3 × 200, not 3 × 500
