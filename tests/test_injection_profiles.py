"""
Tests for F-061: Tiered Injection Profiles

Verifies:
- InjectionProfile enum values and membership
- ProfileConfig dataclass construction and immutability
- All 5 profile configurations have correct boolean flags
- get_profile() lookup and error handling
- should_include() convenience checks
- _build_participant_context() integration with profiles
- Backward compatibility (profile=None)
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import FrozenInstanceError


# ── InjectionProfile Enum ────────────────────────────────────


class TestInjectionProfile:
    """Verify the InjectionProfile enum."""

    def test_has_five_members(self):
        from core.injection_profiles import InjectionProfile
        assert len(InjectionProfile) == 5

    def test_chat_full_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile.CHAT_FULL.value == "chat_full"

    def test_chat_light_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile.CHAT_LIGHT.value == "chat_light"

    def test_image_gen_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile.IMAGE_GEN.value == "image_gen"

    def test_narration_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile.NARRATION.value == "narration"

    def test_discussion_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile.DISCUSSION.value == "discussion"

    def test_enum_from_value(self):
        from core.injection_profiles import InjectionProfile
        assert InjectionProfile("chat_full") is InjectionProfile.CHAT_FULL

    def test_invalid_value_raises(self):
        from core.injection_profiles import InjectionProfile
        with pytest.raises(ValueError):
            InjectionProfile("invalid_profile")


# ── ProfileConfig Dataclass ──────────────────────────────────


class TestProfileConfig:
    """Verify ProfileConfig construction and immutability."""

    def test_all_defaults_true(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(name="test")
        assert cfg.include_system_prompt is True
        assert cfg.include_history is True
        assert cfg.include_memories is True
        assert cfg.include_beliefs is True
        assert cfg.include_world_context is True
        assert cfg.include_laws is True
        assert cfg.include_injections is True
        assert cfg.include_participant_context is True

    def test_custom_flags(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(
            name="custom",
            include_memories=False,
            include_world_context=False,
        )
        assert cfg.include_memories is False
        assert cfg.include_world_context is False
        assert cfg.include_system_prompt is True  # default

    def test_frozen(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(name="frozen_test")
        with pytest.raises(FrozenInstanceError):
            cfg.include_memories = False

    def test_to_dict(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(name="dict_test", include_memories=False)
        d = cfg.to_dict()
        assert d["name"] == "dict_test"
        assert d["include_memories"] is False
        assert d["include_system_prompt"] is True
        assert len(d) == 9  # name + 8 flags

    def test_enabled_layers_all(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(name="all")
        layers = cfg.enabled_layers
        assert "system_prompt" in layers
        assert "history" in layers
        assert "memories" in layers
        assert "beliefs" in layers
        assert "world_context" in layers
        assert "laws" in layers
        assert "injections" in layers
        assert "participant_context" in layers
        assert len(layers) == 8

    def test_enabled_layers_partial(self):
        from core.injection_profiles import ProfileConfig
        cfg = ProfileConfig(
            name="partial",
            include_memories=False,
            include_beliefs=False,
            include_world_context=False,
        )
        layers = cfg.enabled_layers
        assert "memories" not in layers
        assert "beliefs" not in layers
        assert "world_context" not in layers
        assert "system_prompt" in layers
        assert len(layers) == 5


# ── Profile Registry ────────────────────────────────────────


class TestProfileConfigs:
    """Verify all 5 profiles are registered with correct flags."""

    def test_all_profiles_registered(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        for p in InjectionProfile:
            assert p in PROFILE_CONFIGS

    def test_chat_full_all_enabled(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        cfg = PROFILE_CONFIGS[InjectionProfile.CHAT_FULL]
        assert cfg.name == "chat_full"
        assert all([
            cfg.include_system_prompt,
            cfg.include_history,
            cfg.include_memories,
            cfg.include_beliefs,
            cfg.include_world_context,
            cfg.include_laws,
            cfg.include_injections,
            cfg.include_participant_context,
        ])

    def test_chat_light_minimal(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        cfg = PROFILE_CONFIGS[InjectionProfile.CHAT_LIGHT]
        assert cfg.name == "chat_light"
        assert cfg.include_system_prompt is True
        assert cfg.include_history is True
        assert cfg.include_participant_context is True
        # These should be disabled
        assert cfg.include_memories is False
        assert cfg.include_beliefs is False
        assert cfg.include_world_context is False
        assert cfg.include_laws is False
        assert cfg.include_injections is False

    def test_image_gen_stripped(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        cfg = PROFILE_CONFIGS[InjectionProfile.IMAGE_GEN]
        assert cfg.name == "image_gen"
        assert cfg.include_participant_context is True
        # Everything else disabled
        assert cfg.include_system_prompt is False
        assert cfg.include_history is False
        assert cfg.include_memories is False
        assert cfg.include_beliefs is False
        assert cfg.include_world_context is False
        assert cfg.include_laws is False
        assert cfg.include_injections is False

    def test_narration_selective(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        cfg = PROFILE_CONFIGS[InjectionProfile.NARRATION]
        assert cfg.name == "narration"
        assert cfg.include_system_prompt is True
        assert cfg.include_world_context is True
        assert cfg.include_laws is True
        assert cfg.include_injections is True
        assert cfg.include_participant_context is True
        # These should be disabled
        assert cfg.include_history is False
        assert cfg.include_memories is False
        assert cfg.include_beliefs is False

    def test_discussion_beliefs_only(self):
        from core.injection_profiles import PROFILE_CONFIGS, InjectionProfile
        cfg = PROFILE_CONFIGS[InjectionProfile.DISCUSSION]
        assert cfg.name == "discussion"
        assert cfg.include_system_prompt is True
        assert cfg.include_history is True
        assert cfg.include_beliefs is True
        # These should be disabled
        assert cfg.include_memories is False
        assert cfg.include_world_context is False
        assert cfg.include_laws is False
        assert cfg.include_injections is False
        assert cfg.include_participant_context is False


# ── get_profile() ────────────────────────────────────────────


class TestGetProfile:
    """Verify get_profile() lookup."""

    def test_valid_lookup(self):
        from core.injection_profiles import get_profile, InjectionProfile
        cfg = get_profile(InjectionProfile.CHAT_FULL)
        assert cfg.name == "chat_full"

    def test_all_profiles_lookup(self):
        from core.injection_profiles import get_profile, InjectionProfile
        for p in InjectionProfile:
            cfg = get_profile(p)
            assert cfg.name == p.value

    def test_returns_frozen(self):
        from core.injection_profiles import get_profile, InjectionProfile
        cfg = get_profile(InjectionProfile.IMAGE_GEN)
        with pytest.raises(FrozenInstanceError):
            cfg.include_world_context = True


# ── should_include() ────────────────────────────────────────


class TestShouldInclude:
    """Verify should_include() convenience function."""

    def test_chat_full_includes_all(self):
        from core.injection_profiles import should_include, InjectionProfile
        for layer in ("system_prompt", "history", "memories", "beliefs",
                      "world_context", "laws", "injections",
                      "participant_context"):
            assert should_include(InjectionProfile.CHAT_FULL, layer) is True

    def test_image_gen_excludes_most(self):
        from core.injection_profiles import should_include, InjectionProfile
        assert should_include(InjectionProfile.IMAGE_GEN, "participant_context") is True
        assert should_include(InjectionProfile.IMAGE_GEN, "system_prompt") is False
        assert should_include(InjectionProfile.IMAGE_GEN, "memories") is False
        assert should_include(InjectionProfile.IMAGE_GEN, "world_context") is False

    def test_invalid_layer_raises(self):
        from core.injection_profiles import should_include, InjectionProfile
        with pytest.raises(AttributeError):
            should_include(InjectionProfile.CHAT_FULL, "nonexistent_layer")

    def test_discussion_includes_beliefs(self):
        from core.injection_profiles import should_include, InjectionProfile
        assert should_include(InjectionProfile.DISCUSSION, "beliefs") is True
        assert should_include(InjectionProfile.DISCUSSION, "memories") is False

    def test_narration_includes_world(self):
        from core.injection_profiles import should_include, InjectionProfile
        assert should_include(InjectionProfile.NARRATION, "world_context") is True
        assert should_include(InjectionProfile.NARRATION, "laws") is True
        assert should_include(InjectionProfile.NARRATION, "memories") is False


# ── Settings Constant ────────────────────────────────────────


class TestSettingsConstant:
    """Verify the DEFAULT_INJECTION_PROFILE setting exists."""

    def test_exists(self):
        from config.settings import DEFAULT_INJECTION_PROFILE
        assert DEFAULT_INJECTION_PROFILE == "chat_full"

    def test_valid_profile_value(self):
        from config.settings import DEFAULT_INJECTION_PROFILE
        from core.injection_profiles import InjectionProfile
        # Should be a valid profile value
        profile = InjectionProfile(DEFAULT_INJECTION_PROFILE)
        assert profile is InjectionProfile.CHAT_FULL


# ── Participant Context Integration ──────────────────────────


class TestParticipantContextWithProfile:
    """Integration tests verifying profile behavior in _build_participant_context."""

    def _make_mock_member(self, name="Sage", role="Advisor",
                          description="A wise advisor",
                          system_prompt="You are wise.",
                          specialties=None):
        """Create a mock council member."""
        m = MagicMock()
        m.name = name
        m.role = role
        m.description = description
        m.system_prompt = system_prompt
        m.specialties = specialties or ["wisdom"]
        return m

    def _make_mock_registry(self, members):
        """Create a mock registry that returns given members."""
        reg = MagicMock()
        reg.list_members.return_value = members
        return reg

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_image_gen_skips_world_context(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """IMAGE_GEN profile should skip world context entirely."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = self._make_mock_member()
        mock_reg.return_value = self._make_mock_registry([member])

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.IMAGE_GEN,
        )

        # Should have participant info
        assert "Sage" in result
        assert "Advisor" in result
        # Laws, locations, items, stores should NOT be called
        mock_laws.return_value.list_laws.assert_not_called()
        mock_locs.return_value.list_locations.assert_not_called()
        mock_items.return_value.list_items.assert_not_called()
        mock_stores.return_value.list_stores.assert_not_called()

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_image_gen_skips_memories(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """IMAGE_GEN profile should not instantiate MemoryInfluence."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = self._make_mock_member()
        mock_reg.return_value = self._make_mock_registry([member])

        participants = [{"id": "Sage", "type": "council"}]

        # Patch at the source module level — the lazy import pulls from here
        with patch("core.memory_influence.MemoryInfluence") as mock_mi:
            result = _build_participant_context(
                participants, profile=InjectionProfile.IMAGE_GEN,
            )
            # MemoryInfluence should never be instantiated
            mock_mi.assert_not_called()

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_narration_includes_world_context(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """NARRATION profile should include world context but skip memories."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = self._make_mock_member()
        mock_reg.return_value = self._make_mock_registry([member])

        # Set up mock laws
        mock_law = MagicMock()
        mock_law.title = "Tax Law"
        mock_law.description = "All trades are taxed"
        mock_laws.return_value.list_laws.return_value = [mock_law]

        # Set up mock locations
        mock_loc = MagicMock()
        mock_loc.name = "Town Square"
        mock_loc.description = "A bustling town square"
        mock_loc.lore = None
        mock_loc.llm_injection = "Important place"
        mock_locs.return_value.list_locations.return_value = [mock_loc]

        # Empty items and stores
        mock_items.return_value.list_items.return_value = []
        mock_stores.return_value.list_stores.return_value = []

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.NARRATION,
        )

        # Should include world context
        assert "World Context" in result
        assert "Tax Law" in result
        assert "Town Square" in result
        # Should include LLM injections (narration profile has include_injections=True)
        assert "Important place" in result

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_chat_full_includes_everything(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """CHAT_FULL profile should behave identically to no profile."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = self._make_mock_member()
        mock_reg.return_value = self._make_mock_registry([member])

        mock_law = MagicMock()
        mock_law.title = "Tax Law"
        mock_law.description = "All trades are taxed"
        mock_laws.return_value.list_laws.return_value = [mock_law]
        mock_locs.return_value.list_locations.return_value = []
        mock_items.return_value.list_items.return_value = []
        mock_stores.return_value.list_stores.return_value = []

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.CHAT_FULL,
        )

        assert "World Context" in result
        assert "Tax Law" in result

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_discussion_skips_world_and_participants(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """DISCUSSION profile skips world context entirely."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = self._make_mock_member()
        mock_reg.return_value = self._make_mock_registry([member])

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.DISCUSSION,
        )

        # Should still have header but no world context section
        assert "Present Participants" in result
        mock_laws.return_value.list_laws.assert_not_called()
        mock_locs.return_value.list_locations.assert_not_called()


class TestBackwardCompatibility:
    """Verify that profile=None produces identical behavior."""

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_none_profile_same_as_omitted(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """Calling with profile=None should produce same output as no profile arg."""
        from core.routes.explore import _build_participant_context

        member = MagicMock()
        member.name = "Sage"
        member.role = "Advisor"
        member.description = "Wise"
        member.system_prompt = "You are wise."
        member.specialties = []
        reg = MagicMock()
        reg.list_members.return_value = [member]
        mock_reg.return_value = reg

        mock_laws.return_value.list_laws.return_value = []
        mock_locs.return_value.list_locations.return_value = []
        mock_items.return_value.list_items.return_value = []
        mock_stores.return_value.list_stores.return_value = []

        participants = [{"id": "Sage", "type": "council"}]

        result_none = _build_participant_context(
            participants, profile=None,
        )
        result_omitted = _build_participant_context(participants)

        assert result_none == result_omitted

    def test_empty_participants_unchanged(self):
        """Empty participants should return empty string regardless of profile."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        for profile in InjectionProfile:
            result = _build_participant_context([], profile=profile)
            assert result == ""

        result_none = _build_participant_context([], profile=None)
        assert result_none == ""


class TestHelpersForwarding:
    """Verify _helpers.py forwards the profile parameter."""

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_helpers_forwards_profile(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """The helpers wrapper should forward profile to the real function."""
        from core.injection_profiles import InjectionProfile
        from core.routes._helpers import _build_participant_context

        member = MagicMock()
        member.name = "Sage"
        member.role = "Advisor"
        member.description = "Wise"
        member.system_prompt = "You are wise."
        member.specialties = []
        reg = MagicMock()
        reg.list_members.return_value = [member]
        mock_reg.return_value = reg

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.IMAGE_GEN,
        )

        # IMAGE_GEN should skip world context
        assert "World Context" not in result
        mock_laws.return_value.list_laws.assert_not_called()


class TestNarrationInjectionBehavior:
    """Verify NARRATION profile handles LLM injections correctly."""

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_narration_includes_store_injections(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """NARRATION includes world context with LLM injections."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        reg = MagicMock()
        reg.list_members.return_value = []
        mock_reg.return_value = reg

        mock_laws.return_value.list_laws.return_value = []
        mock_locs.return_value.list_locations.return_value = []
        mock_items.return_value.list_items.return_value = []

        mock_store = MagicMock()
        mock_store.name = "Magic Shop"
        mock_store.description = "Sells enchanted items"
        mock_store.store_type = "enchanter"
        mock_store.llm_injection = "The shopkeeper whispers secrets"
        mock_stores.return_value.list_stores.return_value = [mock_store]

        participants = [{"id": "nobody", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.NARRATION,
        )

        assert "Magic Shop" in result
        assert "shopkeeper whispers" in result

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_image_gen_excludes_store_injections(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """IMAGE_GEN should not include world context at all."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        reg = MagicMock()
        reg.list_members.return_value = []
        mock_reg.return_value = reg

        mock_store = MagicMock()
        mock_store.name = "Magic Shop"
        mock_store.description = "Sells enchanted items"
        mock_store.store_type = "enchanter"
        mock_store.llm_injection = "Secret whisper"
        mock_stores.return_value.list_stores.return_value = [mock_store]

        participants = [{"id": "nobody", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.IMAGE_GEN,
        )

        assert "Magic Shop" not in result
        assert "Secret whisper" not in result


class TestChatLightProfile:
    """Verify CHAT_LIGHT profile behavior."""

    @patch("core.context_builder.get_registry")
    @patch("core.context_builder.get_law_manager")
    @patch("core.context_builder.get_location_manager")
    @patch("core.context_builder.get_item_manager")
    @patch("core.context_builder.get_store_manager")
    def test_chat_light_includes_identity(
        self, mock_stores, mock_items, mock_locs, mock_laws, mock_reg,
    ):
        """CHAT_LIGHT should include participant identity but skip world."""
        from core.injection_profiles import InjectionProfile
        from core.routes.explore import _build_participant_context

        member = MagicMock()
        member.name = "Sage"
        member.role = "Advisor"
        member.description = "A wise advisor"
        member.system_prompt = "You are wise."
        member.specialties = ["wisdom"]
        reg = MagicMock()
        reg.list_members.return_value = [member]
        mock_reg.return_value = reg

        participants = [{"id": "Sage", "type": "council"}]
        result = _build_participant_context(
            participants, profile=InjectionProfile.CHAT_LIGHT,
        )

        # Should have identity
        assert "Sage" in result
        assert "Advisor" in result
        # Should NOT have world context
        assert "World Context" not in result
        mock_laws.return_value.list_laws.assert_not_called()
