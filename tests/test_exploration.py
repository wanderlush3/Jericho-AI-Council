"""
Tests for Exploration Image Galleries (F-040).

Tests the ExplorationScene dataclass and ExplorationManager.
"""

import json
import pytest
from pathlib import Path

from core.exploration import (
    ExplorationScene,
    ExplorationManager,
    ExplorationError,
    SceneNotFoundError,
    ExplorationValidationError,
    SCENE_TYPES,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def exploration_dir(tmp_path):
    """Create a temporary exploration directory."""
    d = tmp_path / "exploration"
    d.mkdir()
    return d


@pytest.fixture
def scenes_file(exploration_dir):
    """Path for the scenes JSON file."""
    return exploration_dir / "scenes.json"


@pytest.fixture
def mgr(exploration_dir, scenes_file):
    """Create an ExplorationManager with temp dirs."""
    return ExplorationManager(
        scenes_file=scenes_file,
        exploration_dir=exploration_dir,
    )


# ─── ExplorationScene Tests ───────────────────────────────────


class TestExplorationScene:
    """Tests for the ExplorationScene frozen dataclass."""

    def test_fields(self):
        scene = ExplorationScene(
            scene_id="SCN-abc12345",
            location_id="LOC-0001",
            image_id="IMG-0042",
            scene_type="overview",
            description="A bustling marketplace",
            generated_at="2026-04-09T00:00:00+00:00",
        )
        assert scene.scene_id == "SCN-abc12345"
        assert scene.location_id == "LOC-0001"
        assert scene.image_id == "IMG-0042"
        assert scene.scene_type == "overview"
        assert scene.description == "A bustling marketplace"

    def test_frozen(self):
        scene = ExplorationScene(
            scene_id="SCN-test",
            location_id="LOC-0001",
            image_id="IMG-0001",
        )
        with pytest.raises(AttributeError):
            scene.scene_id = "SCN-other"

    def test_to_dict(self):
        scene = ExplorationScene(
            scene_id="SCN-test",
            location_id="LOC-0001",
            image_id="IMG-0001",
            scene_type="feature",
            description="The fountain",
            metadata={"key": "val"},
        )
        d = scene.to_dict()
        assert d["scene_id"] == "SCN-test"
        assert d["scene_type"] == "feature"
        assert d["metadata"] == {"key": "val"}

    def test_from_dict(self):
        d = {
            "scene_id": "SCN-test",
            "location_id": "LOC-0001",
            "image_id": "IMG-0001",
            "scene_type": "transition",
            "description": "Entering the gate",
        }
        scene = ExplorationScene.from_dict(d)
        assert scene.scene_type == "transition"
        assert scene.description == "Entering the gate"

    def test_roundtrip(self):
        scene = ExplorationScene.create(
            location_id="LOC-0001",
            image_id="IMG-0001",
            scene_type="overview",
            description="A scenic view",
            metadata={"seed": 12345},
        )
        d = scene.to_dict()
        restored = ExplorationScene.from_dict(d)
        assert restored.scene_id == scene.scene_id
        assert restored.location_id == scene.location_id
        assert restored.metadata == {"seed": 12345}

    def test_defaults(self):
        d = {
            "scene_id": "SCN-test",
            "location_id": "LOC-0001",
            "image_id": "IMG-0001",
        }
        scene = ExplorationScene.from_dict(d)
        assert scene.scene_type == "overview"
        assert scene.description == ""
        assert scene.metadata == {}

    def test_create_factory_auto_id(self):
        scene = ExplorationScene.create(
            location_id="LOC-0001",
            image_id="IMG-0001",
        )
        assert scene.scene_id.startswith("SCN-")
        assert len(scene.scene_id) == 12  # SCN- + 8 hex chars
        assert scene.generated_at != ""

    def test_create_factory_unique_ids(self):
        s1 = ExplorationScene.create(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        s2 = ExplorationScene.create(
            location_id="LOC-0001", image_id="IMG-0002"
        )
        assert s1.scene_id != s2.scene_id

    def test_create_validation_empty_location(self):
        with pytest.raises(ExplorationValidationError) as exc:
            ExplorationScene.create(
                location_id="", image_id="IMG-0001"
            )
        assert "location_id" in str(exc.value)

    def test_create_validation_empty_image(self):
        with pytest.raises(ExplorationValidationError) as exc:
            ExplorationScene.create(
                location_id="LOC-0001", image_id=""
            )
        assert "image_id" in str(exc.value)

    def test_create_validation_invalid_scene_type(self):
        with pytest.raises(ExplorationValidationError) as exc:
            ExplorationScene.create(
                location_id="LOC-0001",
                image_id="IMG-0001",
                scene_type="invalid",
            )
        assert "scene_type" in str(exc.value)


# ─── ExplorationManager Init Tests ───────────────────────────


class TestExplorationManagerInit:
    """Tests for ExplorationManager initialization."""

    def test_creates_directory(self, tmp_path):
        d = tmp_path / "new_dir"
        f = d / "scenes.json"
        mgr = ExplorationManager(scenes_file=f, exploration_dir=d)
        assert d.exists()

    def test_loads_empty(self, mgr):
        assert len(mgr) == 0

    def test_repr(self, mgr):
        r = repr(mgr)
        assert "ExplorationManager" in r
        assert "scenes=0" in r

    def test_loads_existing_scenes(self, exploration_dir, scenes_file):
        # Pre-populate scenes file
        scenes_data = [
            {
                "scene_id": "SCN-existing1",
                "location_id": "LOC-0001",
                "image_id": "IMG-0001",
                "scene_type": "overview",
                "description": "Test scene",
                "generated_at": "2026-04-09T00:00:00+00:00",
                "metadata": {},
            }
        ]
        scenes_file.write_text(
            json.dumps(scenes_data), encoding="utf-8"
        )
        mgr = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        assert len(mgr) == 1

    def test_handles_corrupt_file(self, exploration_dir, scenes_file):
        scenes_file.write_text("not json", encoding="utf-8")
        mgr = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        assert len(mgr) == 0

    def test_handles_non_list_file(self, exploration_dir, scenes_file):
        scenes_file.write_text('{"key": "value"}', encoding="utf-8")
        mgr = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        assert len(mgr) == 0


# ─── Add Scene Tests ─────────────────────────────────────────


class TestAddScene:
    """Tests for ExplorationManager.add_scene()."""

    def test_basic_add(self, mgr):
        scene = mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            description="A marketplace view",
        )
        assert scene.scene_id.startswith("SCN-")
        assert scene.location_id == "LOC-0001"
        assert scene.image_id == "IMG-0001"

    def test_persists_to_disk(self, mgr, scenes_file):
        mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
        )
        assert scenes_file.exists()
        data = json.loads(scenes_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["location_id"] == "LOC-0001"

    def test_multiple_scenes(self, mgr):
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0001")
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0002")
        mgr.add_scene(location_id="LOC-0002", image_id="IMG-0003")
        assert len(mgr) == 3

    def test_with_metadata(self, mgr):
        scene = mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            metadata={"prompt_mode": "system", "seed": 42},
        )
        assert scene.metadata["seed"] == 42

    def test_scene_types(self, mgr):
        for st in SCENE_TYPES:
            scene = mgr.add_scene(
                location_id="LOC-0001",
                image_id=f"IMG-{st}",
                scene_type=st,
            )
            assert scene.scene_type == st

    def test_validation_error(self, mgr):
        with pytest.raises(ExplorationValidationError):
            mgr.add_scene(location_id="", image_id="IMG-0001")


# ─── Get Scene Tests ─────────────────────────────────────────


class TestGetScene:
    """Tests for ExplorationManager.get_scene()."""

    def test_get_existing(self, mgr):
        scene = mgr.add_scene(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        retrieved = mgr.get_scene(scene.scene_id)
        assert retrieved.scene_id == scene.scene_id

    def test_not_found(self, mgr):
        with pytest.raises(SceneNotFoundError) as exc:
            mgr.get_scene("SCN-nonexistent")
        assert "SCN-nonexistent" in str(exc.value)


# ─── List Scenes Tests ───────────────────────────────────────


class TestListScenes:
    """Tests for ExplorationManager.list_scenes()."""

    def test_list_all(self, mgr):
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0001")
        mgr.add_scene(location_id="LOC-0002", image_id="IMG-0002")
        scenes = mgr.list_scenes()
        assert len(scenes) == 2

    def test_filter_by_location(self, mgr):
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0001")
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0002")
        mgr.add_scene(location_id="LOC-0002", image_id="IMG-0003")
        scenes = mgr.list_scenes("LOC-0001")
        assert len(scenes) == 2
        assert all(s.location_id == "LOC-0001" for s in scenes)

    def test_filter_by_type(self, mgr):
        mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            scene_type="overview",
        )
        mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0002",
            scene_type="feature",
        )
        scenes = mgr.list_scenes("LOC-0001", scene_type="feature")
        assert len(scenes) == 1
        assert scenes[0].scene_type == "feature"

    def test_empty_location(self, mgr):
        scenes = mgr.list_scenes("LOC-9999")
        assert scenes == []

    def test_sorted_newest_first(self, mgr):
        import time

        s1 = mgr.add_scene(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        time.sleep(0.01)
        s2 = mgr.add_scene(
            location_id="LOC-0001", image_id="IMG-0002"
        )
        scenes = mgr.list_scenes("LOC-0001")
        assert scenes[0].scene_id == s2.scene_id  # Newest first

    def test_count_scenes(self, mgr):
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0001")
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0002")
        mgr.add_scene(location_id="LOC-0002", image_id="IMG-0003")
        assert mgr.count_scenes("LOC-0001") == 2
        assert mgr.count_scenes("LOC-0002") == 1
        assert mgr.count_scenes("LOC-9999") == 0


# ─── Delete Scene Tests ──────────────────────────────────────


class TestDeleteScene:
    """Tests for ExplorationManager.delete_scene()."""

    def test_delete_existing(self, mgr):
        scene = mgr.add_scene(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        mgr.delete_scene(scene.scene_id)
        assert len(mgr) == 0

    def test_delete_not_found(self, mgr):
        with pytest.raises(SceneNotFoundError):
            mgr.delete_scene("SCN-nonexistent")

    def test_delete_persists(self, mgr, scenes_file):
        scene = mgr.add_scene(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        mgr.delete_scene(scene.scene_id)
        data = json.loads(scenes_file.read_text(encoding="utf-8"))
        assert len(data) == 0

    def test_delete_for_location(self, mgr):
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0001")
        mgr.add_scene(location_id="LOC-0001", image_id="IMG-0002")
        mgr.add_scene(location_id="LOC-0002", image_id="IMG-0003")
        deleted = mgr.delete_scenes_for_location("LOC-0001")
        assert deleted == 2
        assert len(mgr) == 1

    def test_delete_for_location_none(self, mgr):
        deleted = mgr.delete_scenes_for_location("LOC-9999")
        assert deleted == 0


# ─── Navigation Tests ────────────────────────────────────────


class TestNavigation:
    """Tests for ExplorationManager.get_navigation_targets()."""

    def _setup_locations(self, tmp_path):
        """Create a location manager with a hierarchy."""
        from core.locations import LocationManager, LocationFeature

        loc_dir = tmp_path / "locations"
        loc_dir.mkdir()
        mgr = LocationManager(locations_dir=loc_dir)

        # Create a parent location
        parent = mgr.create(
            "Kingdom", "The great kingdom",
            author="Council",
        )

        # Create child locations
        child1 = mgr.create(
            "City A", "A major city",
            author="Council",
            parent_location_id=parent.id,
        )
        child2 = mgr.create(
            "City B", "Another city",
            author="Council",
            parent_location_id=parent.id,
        )

        # Create a grandchild
        grandchild = mgr.create(
            "District X", "A district in City A",
            author="Council",
            parent_location_id=child1.id,
        )

        return mgr, parent, child1, child2, grandchild

    def test_parent_navigation(self, tmp_path):
        loc_mgr, parent, child1, child2, grandchild = (
            self._setup_locations(tmp_path)
        )
        nav = ExplorationManager.get_navigation_targets(
            child1.id, loc_mgr,
        )
        assert nav["parent"] is not None
        assert nav["parent"].id == parent.id

    def test_children_navigation(self, tmp_path):
        loc_mgr, parent, child1, child2, grandchild = (
            self._setup_locations(tmp_path)
        )
        nav = ExplorationManager.get_navigation_targets(
            parent.id, loc_mgr,
        )
        assert len(nav["children"]) == 2
        child_ids = {c.id for c in nav["children"]}
        assert child1.id in child_ids
        assert child2.id in child_ids

    def test_siblings_navigation(self, tmp_path):
        loc_mgr, parent, child1, child2, grandchild = (
            self._setup_locations(tmp_path)
        )
        nav = ExplorationManager.get_navigation_targets(
            child1.id, loc_mgr,
        )
        assert len(nav["siblings"]) == 1
        assert nav["siblings"][0].id == child2.id

    def test_root_location_no_parent_or_siblings(self, tmp_path):
        loc_mgr, parent, child1, child2, grandchild = (
            self._setup_locations(tmp_path)
        )
        nav = ExplorationManager.get_navigation_targets(
            parent.id, loc_mgr,
        )
        assert nav["parent"] is None
        assert nav["siblings"] == []

    def test_grandchild_navigation(self, tmp_path):
        loc_mgr, parent, child1, child2, grandchild = (
            self._setup_locations(tmp_path)
        )
        nav = ExplorationManager.get_navigation_targets(
            grandchild.id, loc_mgr,
        )
        assert nav["parent"].id == child1.id
        assert nav["children"] == []
        assert nav["siblings"] == []

    def test_nonexistent_location(self, tmp_path):
        loc_mgr, *_ = self._setup_locations(tmp_path)
        nav = ExplorationManager.get_navigation_targets(
            "LOC-9999", loc_mgr,
        )
        assert nav["parent"] is None
        assert nav["children"] == []
        assert nav["siblings"] == []


# ─── Look Around Description Tests ───────────────────────────


class TestLookAroundDescription:
    """Tests for ExplorationManager.build_look_around_description()."""

    def test_basic_description(self):
        from core.locations import Location

        loc = Location(
            id="LOC-0001",
            name="Ironhaven",
            description="A fortified port city",
            author="Council",
        )
        desc = ExplorationManager.build_look_around_description(loc)
        assert "Ironhaven" in desc
        assert "fortified port city" in desc

    def test_with_lore(self):
        from core.locations import Location

        loc = Location(
            id="LOC-0001",
            name="Ironhaven",
            description="A port city",
            author="Council",
            lore="Founded by ancient mariners",
        )
        desc = ExplorationManager.build_look_around_description(loc)
        assert "ancient mariners" in desc

    def test_with_features(self):
        from core.locations import Location, LocationFeature

        loc = Location(
            id="LOC-0001",
            name="Ironhaven",
            description="A port city",
            author="Council",
            features=[
                LocationFeature(
                    name="Great Harbor",
                    description="A massive natural harbor",
                ),
                LocationFeature(
                    name="Iron Wall",
                    description="Impenetrable fortifications",
                ),
            ],
        )
        desc = ExplorationManager.build_look_around_description(loc)
        assert "Great Harbor" in desc
        assert "Iron Wall" in desc
        assert "massive natural harbor" in desc

    def test_with_tags(self):
        from core.locations import Location

        loc = Location(
            id="LOC-0001",
            name="Ironhaven",
            description="A port city",
            author="Council",
            tags=["coastal", "trading"],
        )
        desc = ExplorationManager.build_look_around_description(loc)
        assert "coastal" in desc
        assert "trading" in desc

    def test_minimal_location(self):
        from core.locations import Location

        loc = Location(
            id="LOC-0001",
            name="Empty",
            description="",
            author="Test",
        )
        desc = ExplorationManager.build_look_around_description(loc)
        assert "Empty" in desc


# ─── Persistence Tests ───────────────────────────────────────


class TestPersistence:
    """Tests for scene persistence across manager instances."""

    def test_scenes_survive_reload(self, exploration_dir, scenes_file):
        mgr1 = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        scene = mgr1.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            description="Test scene",
        )

        mgr2 = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        assert len(mgr2) == 1
        reloaded = mgr2.get_scene(scene.scene_id)
        assert reloaded.description == "Test scene"

    def test_delete_persists_across_reload(
        self, exploration_dir, scenes_file
    ):
        mgr1 = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        scene = mgr1.add_scene(
            location_id="LOC-0001", image_id="IMG-0001"
        )
        mgr1.delete_scene(scene.scene_id)

        mgr2 = ExplorationManager(
            scenes_file=scenes_file,
            exploration_dir=exploration_dir,
        )
        assert len(mgr2) == 0


# ─── Exception Tests ─────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_base_hierarchy(self):
        assert issubclass(SceneNotFoundError, ExplorationError)
        assert issubclass(ExplorationValidationError, ExplorationError)

    def test_scene_not_found_fields(self):
        err = SceneNotFoundError("SCN-test")
        assert err.scene_id == "SCN-test"

    def test_validation_error_single_string(self):
        err = ExplorationValidationError("bad input")
        assert err.errors == ["bad input"]

    def test_validation_error_list(self):
        err = ExplorationValidationError(["error 1", "error 2"])
        assert len(err.errors) == 2


# ─── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_description(self, mgr):
        scene = mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0001",
            description="The 城市 of 東京 — a mystical realm 🌸",
        )
        assert "城市" in scene.description
        assert "🌸" in scene.description

    def test_many_scenes_for_one_location(self, mgr):
        for i in range(20):
            mgr.add_scene(
                location_id="LOC-0001",
                image_id=f"IMG-{i:04d}",
            )
        assert mgr.count_scenes("LOC-0001") == 20
        scenes = mgr.list_scenes("LOC-0001")
        assert len(scenes) == 20

    def test_multiple_locations(self, mgr):
        for i in range(5):
            mgr.add_scene(
                location_id=f"LOC-{i:04d}",
                image_id=f"IMG-{i:04d}",
            )
        assert len(mgr) == 5
        for i in range(5):
            assert mgr.count_scenes(f"LOC-{i:04d}") == 1
