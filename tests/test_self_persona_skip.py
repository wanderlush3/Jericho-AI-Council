"""
Tests for F-056: Skip Self-Persona Preview in Participant Context.

Verifies that:
1. _build_participant_context skips persona preview when current_speaker matches
2. Other participants' persona previews are preserved
3. Characters skip both backstory AND persona preview for self
4. Traits and description are always preserved (even for self)
5. Case-insensitive matching works correctly
6. _helpers.py re-export correctly forwards current_speaker
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Council Member Self-Persona Skip ─────────────────────────────────


class TestCouncilMemberSelfPersonaSkip:
    """Test current_speaker parameter skips council member persona."""

    def _build(self, participants, *, current_speaker=None):
        """Import and call the real function."""
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,  # skip world to simplify
            current_speaker=current_speaker,
        )

    def _mock_member(self, name="Sage", role="Ethics Advisor",
                     description="Wise counsel",
                     system_prompt="You are Sage, the ethics advisor."):
        """Create a mock CouncilMember."""
        member = MagicMock()
        member.name = name
        member.role = role
        member.description = description
        member.system_prompt = system_prompt
        member.specialties = ["ethics"]
        return member

    @patch("core.routes.explore.get_registry")
    def test_no_current_speaker_includes_persona(self, mock_registry):
        """Without current_speaker, persona preview is included."""
        member = self._mock_member()
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            current_speaker=None,
        )

        assert "**Persona:**" in result
        assert "You are Sage" in result

    @patch("core.routes.explore.get_registry")
    def test_current_speaker_skips_own_persona(self, mock_registry):
        """When current_speaker matches, persona preview is omitted."""
        member = self._mock_member()
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            current_speaker="Sage",
        )

        assert "**Persona:**" not in result
        assert "You are Sage" not in result
        # But name, role, and description are still present
        assert "Sage" in result
        assert "Ethics Advisor" in result
        assert "Wise counsel" in result

    @patch("core.routes.explore.get_registry")
    def test_current_speaker_case_insensitive(self, mock_registry):
        """current_speaker matching is case-insensitive."""
        member = self._mock_member()
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            current_speaker="SAGE",
        )

        assert "**Persona:**" not in result

    @patch("core.routes.explore.get_registry")
    def test_non_matching_speaker_keeps_persona(self, mock_registry):
        """When current_speaker doesn't match, persona is preserved."""
        member = self._mock_member()
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            current_speaker="OtherMember",
        )

        assert "**Persona:**" in result
        assert "You are Sage" in result

    @patch("core.routes.explore.get_registry")
    def test_multiple_members_only_self_skipped(self, mock_registry):
        """With multiple council members, only the speaker's persona is skipped."""
        sage = self._mock_member(
            name="Sage", system_prompt="You are Sage the wise.",
        )
        drift = self._mock_member(
            name="Drift", role="Explorer",
            description="A wanderer",
            system_prompt="You are Drift the explorer.",
        )
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [sage, drift]
        mock_registry.return_value = mock_reg

        result = self._build(
            [
                {"id": "sage", "type": "council"},
                {"id": "drift", "type": "council"},
            ],
            current_speaker="Sage",
        )

        # Sage's persona is skipped
        assert "You are Sage" not in result
        # Drift's persona is preserved
        assert "You are Drift" in result

    @patch("core.routes.explore.get_registry")
    def test_specialties_preserved_for_self(self, mock_registry):
        """Specialties are always included even when persona is skipped."""
        member = self._mock_member()
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        result = self._build(
            [{"id": "sage", "type": "council"}],
            current_speaker="Sage",
        )

        assert "ethics" in result


# ── Character Self-Persona Skip ──────────────────────────────────────


class TestCharacterSelfPersonaSkip:
    """Test current_speaker parameter skips character persona/backstory."""

    def _build(self, participants, *, current_speaker=None):
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,
            current_speaker=current_speaker,
        )

    def _mock_char(self, name="Aria", description="A mysterious elf",
                   backstory="Born under twin moons in the ancient forest.",
                   system_prompt="You are Aria, an elf mage."):
        """Create a mock CharacterTemplate."""
        char = MagicMock()
        char.name = name
        char.description = description
        char.backstory = backstory
        char.system_prompt = system_prompt

        # Mock traits
        trait = MagicMock()
        trait.name = "Wise"
        trait.trait_type = "personality"
        trait.intensity = 0.8
        char.traits = [trait]

        return char

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_no_current_speaker_includes_all(
        self, mock_registry, mock_char_mgr,
    ):
        """Without current_speaker, backstory + persona are included."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = self._mock_char()
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            current_speaker=None,
        )

        assert "**Backstory:**" in result
        assert "twin moons" in result
        assert "**Persona:**" in result
        assert "You are Aria" in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_current_speaker_skips_backstory_and_persona(
        self, mock_registry, mock_char_mgr,
    ):
        """When current_speaker matches character, backstory + persona omitted."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = self._mock_char()
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            current_speaker="Aria",
        )

        assert "**Backstory:**" not in result
        assert "twin moons" not in result
        assert "**Persona:**" not in result
        assert "You are Aria" not in result
        # Description and traits are preserved
        assert "mysterious elf" in result
        assert "Wise" in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_character_speaker_case_insensitive(
        self, mock_registry, mock_char_mgr,
    ):
        """Case-insensitive matching for character names."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = self._mock_char()
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            current_speaker="aria",
        )

        assert "**Backstory:**" not in result
        assert "**Persona:**" not in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_traits_always_preserved(
        self, mock_registry, mock_char_mgr,
    ):
        """Traits are always included even for the current speaker."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = self._mock_char()
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            current_speaker="Aria",
        )

        assert "Wise" in result
        assert "**Traits:**" in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_description_always_preserved(
        self, mock_registry, mock_char_mgr,
    ):
        """Description is always included even for the current speaker."""
        mock_reg = MagicMock()
        mock_reg.list_members.return_value = []
        mock_registry.return_value = mock_reg

        char = self._mock_char()
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [{"id": "CH-0001", "type": "character"}],
            current_speaker="Aria",
        )

        assert "mysterious elf" in result
        assert "**Description:**" in result


# ── Mixed Participants ───────────────────────────────────────────────


class TestMixedParticipantsSelfSkip:
    """Test current_speaker with mixed council + character participants."""

    def _build(self, participants, *, current_speaker=None):
        from core.routes.explore import _build_participant_context
        return _build_participant_context(
            participants,
            skip_world_context=True,
            current_speaker=current_speaker,
        )

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_council_speaker_character_preserved(
        self, mock_registry, mock_char_mgr,
    ):
        """Council member is speaker; character's full context is preserved."""
        sage = MagicMock()
        sage.name = "Sage"
        sage.role = "Ethics Advisor"
        sage.description = "Wise counsel"
        sage.system_prompt = "You are Sage the wise."
        sage.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [sage]
        mock_registry.return_value = mock_reg

        char = MagicMock()
        char.name = "Aria"
        char.description = "A mysterious elf"
        char.backstory = "Born under twin moons"
        char.system_prompt = "You are Aria the elf."
        char.traits = []
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [
                {"id": "sage", "type": "council"},
                {"id": "CH-0001", "type": "character"},
            ],
            current_speaker="Sage",
        )

        # Sage's persona skipped
        assert "You are Sage" not in result
        # Aria's backstory and persona preserved
        assert "twin moons" in result
        assert "You are Aria" in result

    @patch("core.routes.explore.get_character_manager")
    @patch("core.routes.explore.get_registry")
    def test_character_speaker_council_preserved(
        self, mock_registry, mock_char_mgr,
    ):
        """Character is speaker; council member's full context is preserved."""
        sage = MagicMock()
        sage.name = "Sage"
        sage.role = "Ethics Advisor"
        sage.description = "Wise counsel"
        sage.system_prompt = "You are Sage the wise."
        sage.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [sage]
        mock_registry.return_value = mock_reg

        char = MagicMock()
        char.name = "Aria"
        char.description = "A mysterious elf"
        char.backstory = "Born under twin moons"
        char.system_prompt = "You are Aria the elf."
        char.traits = []
        mock_char_mgr.return_value.get.return_value = char

        result = self._build(
            [
                {"id": "sage", "type": "council"},
                {"id": "CH-0001", "type": "character"},
            ],
            current_speaker="Aria",
        )

        # Sage's persona preserved
        assert "You are Sage" in result
        # Aria's backstory and persona skipped
        assert "twin moons" not in result
        assert "You are Aria" not in result


# ── Helpers Re-export ────────────────────────────────────────────────


class TestHelpersForwardsCurrentSpeaker:
    """Test that _helpers.py re-export correctly forwards current_speaker."""

    @patch("core.routes.explore.get_registry")
    def test_helpers_forwards_current_speaker(self, mock_registry):
        """The _helpers re-export accepts and forwards current_speaker."""
        member = MagicMock()
        member.name = "Sage"
        member.role = "Ethics Advisor"
        member.description = "Wise counsel"
        member.system_prompt = "You are Sage the wise."
        member.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        from core.routes._helpers import _build_participant_context
        result = _build_participant_context(
            [{"id": "sage", "type": "council"}],
            skip_world_context=True,
            current_speaker="Sage",
        )
        assert "**Persona:**" not in result
        assert "Sage" in result

    @patch("core.routes.explore.get_registry")
    def test_helpers_none_speaker_preserves_persona(self, mock_registry):
        """Helpers re-export with current_speaker=None preserves persona."""
        member = MagicMock()
        member.name = "Sage"
        member.role = "Ethics Advisor"
        member.description = "Wise counsel"
        member.system_prompt = "You are Sage the wise."
        member.specialties = []

        mock_reg = MagicMock()
        mock_reg.list_members.return_value = [member]
        mock_registry.return_value = mock_reg

        from core.routes._helpers import _build_participant_context
        result = _build_participant_context(
            [{"id": "sage", "type": "council"}],
            skip_world_context=True,
            current_speaker=None,
        )
        assert "**Persona:**" in result
