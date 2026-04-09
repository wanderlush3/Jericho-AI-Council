"""
Tests for Exploration API endpoints (F-040).
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def exploration_dir(tmp_path):
    """Temp exploration directory."""
    d = tmp_path / "exploration"
    d.mkdir()
    return d


@pytest.fixture
def locations_dir(tmp_path):
    """Temp locations directory."""
    d = tmp_path / "locations"
    d.mkdir()
    return d


@pytest.fixture
def images_dir(tmp_path):
    """Temp images directory."""
    d = tmp_path / "images"
    d.mkdir()
    return d


@pytest.fixture
def loc_mgr(locations_dir):
    """LocationManager with temp dirs."""
    from core.locations import LocationManager
    return LocationManager(locations_dir=locations_dir)


@pytest.fixture
def setup_locations(loc_mgr):
    """Create a basic location hierarchy."""
    parent = loc_mgr.create(
        "Kingdom", "The great kingdom", author="Council",
    )
    # Activate the parent
    loc_mgr.update_status(parent.id, "active")

    child = loc_mgr.create(
        "City", "A major city", author="Council",
        parent_location_id=parent.id,
    )
    loc_mgr.update_status(child.id, "active")

    return parent, child


@pytest.fixture
def client(tmp_path, exploration_dir, locations_dir, images_dir, setup_locations):
    """Create a test FastAPI client with patched managers."""
    from core.exploration import ExplorationManager
    from core.locations import LocationManager
    from core.image_manager import ImageManager

    scenes_file = exploration_dir / "scenes.json"

    real_loc_mgr = LocationManager(locations_dir=locations_dir)
    real_expl_mgr = ExplorationManager(
        scenes_file=scenes_file,
        exploration_dir=exploration_dir,
    )
    real_img_mgr = ImageManager(images_dir=images_dir)

    # Patch only the constructors while preserving static methods
    with patch("core.locations.LocationManager", return_value=real_loc_mgr) as MockLocMgr, \
         patch("core.exploration.ExplorationManager", return_value=real_expl_mgr) as MockExplMgr, \
         patch("core.image_manager.ImageManager", return_value=real_img_mgr) as MockImgMgr:

        # Preserve static methods on the mock class
        MockExplMgr.get_navigation_targets = ExplorationManager.get_navigation_targets
        MockExplMgr.build_look_around_description = ExplorationManager.build_look_around_description

        from core.web_api import create_app
        app = create_app()
        yield TestClient(app)


# ─── Explore List Tests ──────────────────────────────────────


class TestExploreListEndpoint:
    """Tests for GET /api/explore."""

    def test_returns_locations(self, client, setup_locations):
        resp = client.get("/api/explore")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_location_fields(self, client, setup_locations):
        resp = client.get("/api/explore")
        data = resp.json()
        loc = data[0]
        assert "id" in loc
        assert "name" in loc
        assert "description" in loc
        assert "scene_count" in loc
        assert "primary_image_url" in loc


# ─── Explore Detail Tests ────────────────────────────────────


class TestExploreDetailEndpoint:
    """Tests for GET /api/explore/{location_id}."""

    def test_returns_location_data(self, client, setup_locations):
        parent, child = setup_locations
        resp = client.get(f"/api/explore/{parent.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Kingdom"
        assert "scenes" in data
        assert "navigation" in data
        assert "features" in data

    def test_navigation_data(self, client, setup_locations):
        parent, child = setup_locations
        resp = client.get(f"/api/explore/{child.id}")
        data = resp.json()
        nav = data["navigation"]
        assert nav["parent"] is not None
        assert nav["parent"]["name"] == "Kingdom"

    def test_not_found(self, client):
        resp = client.get("/api/explore/LOC-9999")
        assert resp.status_code == 404


# ─── Scene Endpoints Tests ───────────────────────────────────


class TestSceneEndpoints:
    """Tests for scene CRUD endpoints."""

    def test_add_scene(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={
                "image_id": "IMG-test",
                "scene_type": "overview",
                "description": "A panoramic view",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scene_id"].startswith("SCN-")
        assert data["location_id"] == parent.id

    def test_list_scenes(self, client, setup_locations):
        parent, _ = setup_locations
        # Add a scene first
        client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-test", "scene_type": "overview"},
        )
        resp = client.get(f"/api/explore/{parent.id}/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_delete_scene(self, client, setup_locations):
        parent, _ = setup_locations
        # Add a scene
        add_resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-test", "scene_type": "overview"},
        )
        scene_id = add_resp.json()["scene_id"]

        # Delete it
        del_resp = client.delete(
            f"/api/explore/{parent.id}/scenes/{scene_id}",
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] == scene_id

    def test_delete_scene_not_found(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.delete(
            f"/api/explore/{parent.id}/scenes/SCN-nonexistent",
        )
        assert resp.status_code == 404

    def test_add_scene_missing_image_id(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"scene_type": "overview"},
        )
        assert resp.status_code == 400
