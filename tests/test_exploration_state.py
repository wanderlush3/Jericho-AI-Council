"""
Tests for Exploration State Engine (F-079).

Tests the ExplorationState, ExplorationStateManager, and the
focused prompt builder.
"""

import json
import pytest
from pathlib import Path

from core.exploration_state import (
    ExplorationState,
    ExplorationStateManager,
    ExplorationStateError,
    InvalidMoveError,
    FOCUS_INITIAL,
    FOCUS_EXTERIOR,
    FOCUS_IMAGINATIVE,
    EXPLORATION_MODES,
    infer_location_dynamism,
)
from core.exploration import ExplorationManager


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def states_dir(tmp_path):
    """Create a temporary states directory."""
    d = tmp_path / "exploration" / "states"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def state_mgr(states_dir):
    """Create an ExplorationStateManager with temp dirs."""
    return ExplorationStateManager(states_dir=states_dir)


@pytest.fixture
def make_location():
    """Factory for creating minimal Location-like objects."""
    from core.locations import Location, LocationFeature

    def _make(
        name="Ironhaven",
        description="A fortified port city",
        features=None,
        tags=None,
        lore="",
    ):
        feats = features or [
            LocationFeature(
                name="Great Harbor",
                description="A massive natural harbor",
                feature_type="natural",
            ),
            LocationFeature(
                name="Iron Wall",
                description="Impenetrable fortifications",
                feature_type="infrastructure",
            ),
            LocationFeature(
                name="Market Square",
                description="A bustling marketplace",
                feature_type="landmark",
            ),
        ]
        return Location(
            id="LOC-0001",
            name=name,
            description=description,
            author="Council",
            features=feats,
            tags=tags or [],
            lore=lore,
        )

    return _make


# ─── ExplorationState Tests ──────────────────────────────────


class TestExplorationState:
    """Tests for the ExplorationState dataclass."""

    def test_default_state(self):
        state = ExplorationState(location_id="LOC-0001")
        assert state.location_id == "LOC-0001"
        assert state.current_focus == FOCUS_INITIAL
        assert state.explored_areas == []
        assert state.exploration_depth == 0
        assert state.mode == "guided"
        assert state.scene_setting == "outdoor"

    def test_to_dict(self):
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Great Hall",
            explored_areas=["exterior", "Great Hall"],
            exploration_depth=2,
        )
        d = state.to_dict()
        assert d["location_id"] == "LOC-0001"
        assert d["current_focus"] == "Great Hall"
        assert len(d["explored_areas"]) == 2
        assert d["exploration_depth"] == 2

    def test_from_dict(self):
        d = {
            "location_id": "LOC-0001",
            "current_focus": "exterior",
            "explored_areas": ["exterior"],
            "exploration_depth": 1,
            "mode": "guided",
            "scene_setting": "outdoor",
        }
        state = ExplorationState.from_dict(d)
        assert state.location_id == "LOC-0001"
        assert state.current_focus == "exterior"
        assert state.exploration_depth == 1

    def test_from_dict_defaults(self):
        state = ExplorationState.from_dict({"location_id": "LOC-0001"})
        assert state.current_focus == FOCUS_INITIAL
        assert state.mode == "guided"
        assert state.explored_areas == []

    def test_roundtrip(self):
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Market Square",
            explored_areas=["exterior", "Great Harbor", "Market Square"],
            exploration_depth=3,
            mode="guided",
            scene_setting="outdoor",
        )
        d = state.to_dict()
        restored = ExplorationState.from_dict(d)
        assert restored.location_id == state.location_id
        assert restored.current_focus == state.current_focus
        assert restored.explored_areas == state.explored_areas

    def test_reset(self):
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Great Hall",
            explored_areas=["exterior", "Great Hall"],
            exploration_depth=5,
            mode="imaginative",
            imaginative_history=["A hidden cave"],
        )
        state.reset()
        assert state.current_focus == FOCUS_INITIAL
        assert state.explored_areas == []
        assert state.exploration_depth == 0
        assert state.mode == "guided"
        assert state.imaginative_history == []


# ─── Movement Tests ──────────────────────────────────────────


class TestMovement:
    """Tests for ExplorationState.move_to()."""

    def test_move_to_exterior(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to(FOCUS_EXTERIOR)
        assert state.current_focus == FOCUS_EXTERIOR
        assert FOCUS_EXTERIOR in state.explored_areas
        assert state.exploration_depth == 1

    def test_move_to_feature(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to("Great Harbor")
        assert state.current_focus == "Great Harbor"
        assert "Great Harbor" in state.explored_areas
        assert state.exploration_depth == 1

    def test_move_depth_increments(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to(FOCUS_EXTERIOR)
        state.move_to("Great Harbor")
        state.move_to("Iron Wall")
        assert state.exploration_depth == 3

    def test_revisit_doesnt_duplicate(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to("Great Harbor")
        state.move_to("Great Harbor")  # Revisit
        assert state.explored_areas.count("Great Harbor") == 1
        assert state.exploration_depth == 2  # Still increments depth

    def test_move_to_explore_further(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to("explore_further")
        assert state.mode == "imaginative"
        assert state.current_focus == FOCUS_IMAGINATIVE

    def test_explore_further_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "core.exploration_state.IMAGINATIVE_MODE_ENABLED", False,
        )
        state = ExplorationState(location_id="LOC-0001")
        with pytest.raises(InvalidMoveError) as exc:
            state.move_to("explore_further")
        assert "disabled" in str(exc.value).lower()

    def test_exterior_revisit(self):
        state = ExplorationState(location_id="LOC-0001")
        state.move_to(FOCUS_EXTERIOR)
        state.move_to("Great Harbor")
        state.move_to(FOCUS_EXTERIOR)  # Go back outside
        assert state.current_focus == FOCUS_EXTERIOR
        assert state.explored_areas.count(FOCUS_EXTERIOR) == 1


# ─── Progress Tests ──────────────────────────────────────────


class TestProgress:
    """Tests for ExplorationState.get_exploration_progress()."""

    def test_zero_progress(self):
        state = ExplorationState(location_id="LOC-0001")
        progress = state.get_exploration_progress(3)
        assert progress["explored"] == 0
        assert progress["total"] == 3
        assert progress["percentage"] == 0
        assert progress["all_explored"] is False

    def test_partial_progress(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=["exterior", "Great Harbor"],
        )
        progress = state.get_exploration_progress(3)
        assert progress["explored"] == 1  # exterior doesn't count
        assert progress["total"] == 3
        assert progress["percentage"] == 33
        assert progress["all_explored"] is False

    def test_full_progress(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=["exterior", "A", "B", "C"],
        )
        progress = state.get_exploration_progress(3)
        assert progress["explored"] == 3
        assert progress["total"] == 3
        assert progress["percentage"] == 100
        assert progress["all_explored"] is True

    def test_zero_features(self):
        state = ExplorationState(location_id="LOC-0001")
        progress = state.get_exploration_progress(0)
        assert progress["total"] == 0
        assert progress["all_explored"] is False

    def test_exterior_not_counted_as_feature(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=[FOCUS_EXTERIOR, FOCUS_INITIAL],
        )
        progress = state.get_exploration_progress(3)
        assert progress["explored"] == 0


# ─── Available Moves Tests ───────────────────────────────────


class TestAvailableMoves:
    """Tests for ExplorationState.get_available_moves()."""

    def test_basic_moves(self):
        state = ExplorationState(location_id="LOC-0001")
        features = ["Great Harbor", "Iron Wall", "Market Square"]
        moves = state.get_available_moves(features)

        # exterior + 3 features = 4 moves
        assert len(moves) == 4
        targets = {m["target"] for m in moves}
        assert FOCUS_EXTERIOR in targets
        assert "Great Harbor" in targets

    def test_explored_flag(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=["Great Harbor"],
        )
        features = ["Great Harbor", "Iron Wall"]
        moves = state.get_available_moves(features)

        harbor = next(m for m in moves if m["target"] == "Great Harbor")
        wall = next(m for m in moves if m["target"] == "Iron Wall")
        assert harbor["explored"] is True
        assert wall["explored"] is False

    def test_imaginative_appears_when_all_explored(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=["A", "B"],
        )
        features = ["A", "B"]
        moves = state.get_available_moves(features)

        imaginative = [m for m in moves if m["type"] == "imaginative"]
        assert len(imaginative) == 1
        assert imaginative[0]["target"] == "explore_further"

    def test_no_imaginative_when_not_all_explored(self):
        state = ExplorationState(
            location_id="LOC-0001",
            explored_areas=["A"],
        )
        features = ["A", "B"]
        moves = state.get_available_moves(features)

        imaginative = [m for m in moves if m["type"] == "imaginative"]
        assert len(imaginative) == 0


# ─── Imaginative History Tests ───────────────────────────────


class TestImaginativeHistory:
    """Tests for ExplorationState.add_imaginative_discovery()."""

    def test_add_discovery(self):
        state = ExplorationState(location_id="LOC-0001")
        state.add_imaginative_discovery("A hidden cave behind the waterfall")
        assert len(state.imaginative_history) == 1

    def test_no_duplicates(self):
        state = ExplorationState(location_id="LOC-0001")
        state.add_imaginative_discovery("A hidden cave")
        state.add_imaginative_discovery("A hidden cave")
        assert len(state.imaginative_history) == 1

    def test_empty_string_ignored(self):
        state = ExplorationState(location_id="LOC-0001")
        state.add_imaginative_discovery("")
        assert len(state.imaginative_history) == 0


# ─── State Manager Tests ─────────────────────────────────────


class TestExplorationStateManager:
    """Tests for ExplorationStateManager persistence."""

    def test_get_nonexistent(self, state_mgr):
        state = state_mgr.get("LOC-9999")
        assert state is None

    def test_get_or_create(self, state_mgr):
        state = state_mgr.get_or_create("LOC-0001")
        assert state.location_id == "LOC-0001"
        assert state.current_focus == FOCUS_INITIAL

    def test_save_and_load(self, state_mgr):
        state = state_mgr.get_or_create("LOC-0001")
        state.move_to(FOCUS_EXTERIOR)
        state_mgr.save(state)

        loaded = state_mgr.get("LOC-0001")
        assert loaded is not None
        assert loaded.current_focus == FOCUS_EXTERIOR
        assert loaded.exploration_depth == 1

    def test_reset(self, state_mgr):
        state = state_mgr.get_or_create("LOC-0001")
        state.move_to(FOCUS_EXTERIOR)
        state.move_to("Great Harbor")
        state_mgr.save(state)

        reset_state = state_mgr.reset("LOC-0001")
        assert reset_state.current_focus == FOCUS_INITIAL
        assert reset_state.explored_areas == []

        # Verify it persisted
        loaded = state_mgr.get("LOC-0001")
        assert loaded.current_focus == FOCUS_INITIAL

    def test_delete(self, state_mgr):
        state_mgr.get_or_create("LOC-0001")
        assert state_mgr.delete("LOC-0001") is True
        assert state_mgr.get("LOC-0001") is None

    def test_delete_nonexistent(self, state_mgr):
        assert state_mgr.delete("LOC-9999") is False

    def test_corrupt_file_handled(self, states_dir, state_mgr):
        path = states_dir / "LOC-0001.json"
        path.write_text("not json", encoding="utf-8")
        assert state_mgr.get("LOC-0001") is None

    def test_repr(self, state_mgr):
        assert "ExplorationStateManager" in repr(state_mgr)


# ─── Location Dynamism Tests ────────────────────────────────


class TestLocationDynamism:
    """Tests for infer_location_dynamism()."""

    def test_static_by_tags(self, make_location):
        loc = make_location(name="The Tavern", tags=["tavern", "cozy"])
        assert infer_location_dynamism(loc) == "static"

    def test_dynamic_by_tags(self, make_location):
        loc = make_location(name="Dark Forest", tags=["forest", "wild"])
        assert infer_location_dynamism(loc) == "dynamic"

    def test_static_by_name(self, make_location):
        loc = make_location(name="Stifle's Home", tags=[])
        assert infer_location_dynamism(loc) == "static"

    def test_dynamic_by_name(self, make_location):
        loc = make_location(name="Enchanted Forest", tags=[])
        assert infer_location_dynamism(loc) == "dynamic"

    def test_mixed_tags_uses_feature_count(self, make_location):
        from core.locations import LocationFeature

        # Few features → static tendency
        loc = make_location(
            tags=["tavern", "forest"],
            features=[
                LocationFeature(name="A", description="x"),
            ],
        )
        assert infer_location_dynamism(loc) == "static"

    def test_many_features_is_dynamic(self, make_location):
        from core.locations import LocationFeature

        feats = [
            LocationFeature(name=f"F-{i}", description="x")
            for i in range(8)
        ]
        loc = make_location(tags=[], features=feats)
        assert infer_location_dynamism(loc) == "dynamic"

    def test_moderate_features(self, make_location):
        from core.locations import LocationFeature

        feats = [
            LocationFeature(name=f"F-{i}", description="x")
            for i in range(4)
        ]
        loc = make_location(tags=[], features=feats)
        assert infer_location_dynamism(loc) == "moderate"


# ─── Focused Prompt Builder Tests ────────────────────────────


class TestFocusedPromptBuilder:
    """Tests for ExplorationManager.build_focused_prompt()."""

    def test_initial_exterior(self, make_location):
        loc = make_location(lore="Founded by ancient mariners")
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_INITIAL,
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Ironhaven" in prompt
        assert "establishing exterior" in prompt.lower()
        assert "ancient mariners" in prompt

    def test_exterior_focus(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_EXTERIOR,
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "exterior" in prompt.lower()
        assert "Great Harbor" in prompt

    def test_guided_feature_focus(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Great Harbor",
            explored_areas=["exterior", "Great Harbor"],
            mode="guided",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Great Harbor" in prompt
        assert "Focus Area" in prompt
        assert "massive natural harbor" in prompt

    def test_guided_shows_previously_explored(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Iron Wall",
            explored_areas=["exterior", "Great Harbor", "Iron Wall"],
            mode="guided",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Previously explored" in prompt
        assert "Great Harbor" in prompt  # mentioned as previously explored

    def test_guided_feature_type_is_included(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Iron Wall",
            mode="guided",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "infrastructure" in prompt

    def test_guided_building_sets_indoor(self, make_location):
        from core.locations import LocationFeature

        loc = make_location(
            features=[
                LocationFeature(
                    name="Town Hall",
                    description="A grand stone building",
                    feature_type="building",
                ),
            ],
        )
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Town Hall",
            mode="guided",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Setting: indoor" in prompt

    def test_imaginative_static(self, make_location):
        loc = make_location(name="The Tavern", tags=["tavern"])
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_IMAGINATIVE,
            explored_areas=["exterior", "Great Harbor", "Iron Wall", "Market Square"],
            mode="imaginative",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "hidden details" in prompt.lower() or "overlooked" in prompt.lower()
        # Should NOT say "what lies further"
        assert "what lies further" not in prompt.lower()

    def test_imaginative_dynamic(self, make_location):
        loc = make_location(name="Dark Forest", tags=["forest"])
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_IMAGINATIVE,
            mode="imaginative",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "lies further" in prompt.lower() or "hidden path" in prompt.lower()

    def test_imaginative_includes_history(self, make_location):
        loc = make_location(tags=["forest"])
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_IMAGINATIVE,
            mode="imaginative",
            imaginative_history=["A glowing mushroom grove"],
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "glowing mushroom grove" in prompt

    def test_setting_keyword_in_exterior(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus=FOCUS_EXTERIOR,
            scene_setting="outdoor",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Setting: outdoor" in prompt

    def test_unknown_feature_handled(self, make_location):
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="Unknown Area",
            mode="guided",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Unknown Area" in prompt

    def test_fallback_generic(self, make_location):
        """If mode is neither guided nor imaginative, falls back to generic."""
        loc = make_location()
        state = ExplorationState(
            location_id="LOC-0001",
            current_focus="some_area",
            mode="unknown_mode",
        )
        prompt = ExplorationManager.build_focused_prompt(loc, state)
        assert "Ironhaven" in prompt


# ─── ExplorationScene focus_area Tests ───────────────────────


class TestSceneFocusArea:
    """Tests that the focus_area field works on ExplorationScene."""

    def test_create_with_focus_area(self):
        from core.exploration import ExplorationScene

        scene = ExplorationScene.create(
            location_id="LOC-0001",
            image_id="IMG-0001",
            focus_area="Great Harbor",
        )
        assert scene.focus_area == "Great Harbor"

    def test_focus_area_in_dict(self):
        from core.exploration import ExplorationScene

        scene = ExplorationScene.create(
            location_id="LOC-0001",
            image_id="IMG-0001",
            focus_area="Market Square",
        )
        d = scene.to_dict()
        assert d["focus_area"] == "Market Square"

    def test_focus_area_from_dict_default(self):
        from core.exploration import ExplorationScene

        d = {
            "scene_id": "SCN-legacy",
            "location_id": "LOC-0001",
            "image_id": "IMG-0001",
        }
        scene = ExplorationScene.from_dict(d)
        assert scene.focus_area == ""  # backward-compatible default

    def test_add_scene_with_focus_area(self, tmp_path):
        from core.exploration import ExplorationManager

        d = tmp_path / "exploration"
        d.mkdir()
        f = d / "scenes.json"
        mgr = ExplorationManager(scenes_file=f, exploration_dir=d)

        scene = mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            focus_area="Iron Wall",
        )
        assert scene.focus_area == "Iron Wall"


# ─── Exception Tests ─────────────────────────────────────────


class TestExplorationStateExceptions:
    """Tests for exception hierarchy."""

    def test_base_hierarchy(self):
        assert issubclass(InvalidMoveError, ExplorationStateError)

    def test_invalid_move_fields(self):
        err = InvalidMoveError("test_target", "test reason")
        assert err.target == "test_target"
        assert "test_target" in str(err)
        assert "test reason" in str(err)

    def test_invalid_move_no_reason(self):
        err = InvalidMoveError("test_target")
        assert "test_target" in str(err)
