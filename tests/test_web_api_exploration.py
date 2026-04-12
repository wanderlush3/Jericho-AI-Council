"""
Tests for Exploration API endpoints (F-040, F-042) — expanded coverage (F-046).

Covers:
- Explore list & detail endpoints
- Scene CRUD endpoints (add, list, delete, error paths)
- Look-around request validation (participants, templates)
- Explore chat lifecycle (active, create, inject-scene)
- Participant context builder unit tests
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


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

    def test_location_detail_keys(self, client, setup_locations):
        resp = client.get("/api/explore")
        data = resp.json()
        loc = data[0]
        expected = {
            "id", "name", "description", "tags", "status",
            "parent_location_id", "primary_image_url", "scene_count",
        }
        assert expected.issubset(set(loc.keys()))

    def test_scene_count_starts_at_zero(self, client, setup_locations):
        resp = client.get("/api/explore")
        data = resp.json()
        for loc in data:
            assert loc["scene_count"] == 0


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

    def test_parent_has_child_in_navigation(self, client, setup_locations):
        parent, child = setup_locations
        resp = client.get(f"/api/explore/{parent.id}")
        data = resp.json()
        nav = data["navigation"]
        child_names = [c["name"] for c in nav["children"]]
        assert "City" in child_names

    def test_detail_includes_coordinates(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.get(f"/api/explore/{parent.id}")
        data = resp.json()
        assert "coordinates" in data

    def test_detail_includes_lore(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.get(f"/api/explore/{parent.id}")
        data = resp.json()
        assert "lore" in data


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

    def test_scene_has_image_url(self, client, setup_locations):
        """Returned scene objects include a computed image_url."""
        parent, _ = setup_locations
        add_resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-abc", "scene_type": "overview"},
        )
        data = add_resp.json()
        assert "image_url" in data
        assert "IMG-abc" in data["image_url"]

    def test_list_scenes_filter_by_type(self, client, setup_locations):
        """List scenes with scene_type query filter."""
        parent, _ = setup_locations
        client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-1", "scene_type": "overview"},
        )
        client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-2", "scene_type": "feature"},
        )
        resp = client.get(
            f"/api/explore/{parent.id}/scenes?scene_type=overview",
        )
        data = resp.json()
        assert all(s["scene_type"] == "overview" for s in data)

    def test_delete_scene_wrong_location(self, client, setup_locations):
        """Deleting a scene under the wrong location returns 400."""
        parent, child = setup_locations
        add_resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "IMG-test", "scene_type": "overview"},
        )
        scene_id = add_resp.json()["scene_id"]

        # Try to delete under the child location
        resp = client.delete(
            f"/api/explore/{child.id}/scenes/{scene_id}",
        )
        assert resp.status_code == 400
        assert "does not belong" in resp.json()["detail"]

    def test_add_scene_with_metadata(self, client, setup_locations):
        """Scene creation accepts arbitrary metadata."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={
                "image_id": "IMG-meta",
                "scene_type": "overview",
                "metadata": {"generated_by": "pipeline"},
            },
        )
        assert resp.status_code == 200

    def test_list_scenes_empty_location(self, client, setup_locations):
        """Listing scenes for a location with no scenes returns empty list."""
        parent, _ = setup_locations
        resp = client.get(f"/api/explore/{parent.id}/scenes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_scene_empty_image_id_string(self, client, setup_locations):
        """Empty string image_id should be rejected."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/scenes",
            json={"image_id": "  ", "scene_type": "overview"},
        )
        assert resp.status_code == 400


# ─── Look-Around Validation ──────────────────────────────────


class TestLookAroundValidation:
    """Tests for POST /api/explore/{location_id}/look-around."""

    def test_not_found_location(self, client):
        resp = client.post("/api/explore/LOC-9999/look-around", json={})
        assert resp.status_code == 404

    def test_too_many_participants(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/look-around",
            json={
                "participants": [{"id": f"m{i}", "type": "council"} for i in range(11)],
            },
        )
        assert resp.status_code == 400
        assert "Too many participants" in resp.json()["detail"]

    def test_participants_not_list(self, client, setup_locations):
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/look-around",
            json={
                "participants": "not-a-list",
            },
        )
        assert resp.status_code == 400
        assert "must be a list" in resp.json()["detail"]

    def test_ten_participants_accepted(self, client, setup_locations):
        """Exactly 10 participants is accepted (no validation error for count)."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/look-around",
            json={
                "participants": [{"id": f"m{i}", "type": "council"} for i in range(10)],
            },
        )
        # Should not fail due to participant count (may fail for other reasons)
        if resp.status_code == 400:
            assert "participants" not in resp.json()["detail"].lower()


# ─── Explore Chat Endpoints ──────────────────────────────────


class TestExploreChatEndpoints:
    """Tests for explore chat lifecycle endpoints."""

    def test_chat_active_no_chats(self, client, setup_locations):
        """When no chats exist, active endpoint returns null chat_id."""
        parent, _ = setup_locations
        with patch("core.routes.explore._make_explore_chat") as mock_hc_fn:
            mock_hc = MagicMock()
            mock_hc.list_chats.return_value = []
            mock_hc_fn.return_value = mock_hc

            resp = client.get(f"/api/explore/{parent.id}/chat/active")
        assert resp.status_code == 200
        assert resp.json()["chat_id"] is None

    def test_chat_create_missing_participants(self, client, setup_locations):
        """Creating a chat with no participants returns 400."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/chat",
            json={"participants": []},
        )
        assert resp.status_code == 400
        assert "participant" in resp.json()["detail"].lower()

    def test_chat_create_no_body(self, client, setup_locations):
        """Creating a chat with no body returns 400."""
        parent, _ = setup_locations
        resp = client.post(f"/api/explore/{parent.id}/chat")
        assert resp.status_code == 400

    def test_chat_create_location_not_found(self, client, setup_locations):
        """Creating a chat for a non-existent location returns 404."""
        resp = client.post(
            "/api/explore/LOC-9999/chat",
            json={"participants": [{"id": "sage", "type": "council"}]},
        )
        assert resp.status_code == 404

    def test_inject_scene_missing_prompt(self, client, setup_locations):
        """Inject-scene with missing prompt_text returns 400."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/chat/EC-0001/inject-scene",
            json={},
        )
        assert resp.status_code == 400
        assert "prompt_text" in resp.json()["detail"]

    def test_inject_scene_empty_prompt(self, client, setup_locations):
        """Inject-scene with empty prompt_text returns 400."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/chat/EC-0001/inject-scene",
            json={"prompt_text": "   "},
        )
        assert resp.status_code == 400

    def test_send_stream_missing_content(self, client, setup_locations):
        """Send-stream with missing content returns 400."""
        parent, _ = setup_locations
        resp = client.post(
            f"/api/explore/{parent.id}/chat/EC-0001/send-stream",
            json={"content": ""},
        )
        assert resp.status_code == 400
        assert "content" in resp.json()["detail"].lower()


# ─── Participant Context Builder Tests ──────────────────────


class TestParticipantContextBuilder:
    """Unit tests for _build_participant_context."""

    def test_empty_participants(self):
        from core.routes.explore import _build_participant_context
        result = _build_participant_context([])
        assert result == ""

    def test_council_member_section_header(self):
        from core.routes.explore import _build_participant_context

        with patch("core.routes.explore.get_registry") as mock_reg:
            mock_member = MagicMock()
            mock_member.name = "Sage"
            mock_member.role = "Ethics"
            mock_member.description = "A wise advisor"
            mock_member.system_prompt = "You are Sage."
            mock_member.specialties = ["ethics", "philosophy"]

            mock_reg_inst = MagicMock()
            mock_reg_inst.list_members.return_value = [mock_member]
            mock_reg.return_value = mock_reg_inst

            result = _build_participant_context([
                {"id": "sage", "type": "council"},
            ])
        assert "Participants" in result
        assert "Sage" in result

    def test_character_section_present(self):
        from core.routes.explore import _build_participant_context

        mock_char = MagicMock()
        mock_char.name = "Aria"
        mock_char.description = "A brave explorer"
        mock_char.backstory = "Born in the wild."
        mock_char.traits = []
        mock_char.system_prompt = ""

        with patch("core.routes.explore.get_registry") as mock_reg, \
             patch("core.routes.explore.get_character_manager") as mock_cmgr:
            mock_reg_inst = MagicMock()
            mock_reg_inst.list_members.return_value = []
            mock_reg.return_value = mock_reg_inst

            mock_cmgr_inst = MagicMock()
            mock_cmgr_inst.get.return_value = mock_char
            mock_cmgr.return_value = mock_cmgr_inst

            result = _build_participant_context([
                {"id": "CH-0001", "type": "character"},
            ])
        assert "Aria" in result
        assert "Character" in result

    def test_world_context_section_present(self):
        """World context section header is always appended."""
        from core.routes.explore import _build_participant_context

        with patch("core.routes.explore.get_registry") as mock_reg, \
             patch("core.routes.explore.get_law_manager") as mock_law, \
             patch("core.routes.explore.get_location_manager") as mock_loc, \
             patch("core.routes.explore.get_item_manager") as mock_item:
            mock_reg_inst = MagicMock()
            mock_reg_inst.list_members.return_value = []
            mock_reg.return_value = mock_reg_inst
            mock_law.return_value.list_laws.return_value = []
            mock_loc.return_value.list_locations.return_value = []
            mock_item.return_value.list_items.return_value = []

            result = _build_participant_context([
                {"id": "sage", "type": "council"},
            ])
        assert "World Context" in result

    def test_unknown_member_shows_unavailable(self):
        """A council member not in the registry shows 'unavailable'."""
        from core.routes.explore import _build_participant_context

        with patch("core.routes.explore.get_registry") as mock_reg, \
             patch("core.routes.explore.get_law_manager") as mock_law, \
             patch("core.routes.explore.get_location_manager") as mock_loc, \
             patch("core.routes.explore.get_item_manager") as mock_item:
            mock_reg_inst = MagicMock()
            mock_reg_inst.list_members.return_value = []
            mock_reg.return_value = mock_reg_inst
            mock_law.return_value.list_laws.return_value = []
            mock_loc.return_value.list_locations.return_value = []
            mock_item.return_value.list_items.return_value = []

            result = _build_participant_context([
                {"id": "unknown_member", "type": "council"},
            ])
        assert "unavailable" in result.lower()

    def test_character_not_found_shows_not_found(self):
        """A character whose get() raises shows 'not found'."""
        from core.routes.explore import _build_participant_context

        with patch("core.routes.explore.get_registry") as mock_reg, \
             patch("core.routes.explore.get_character_manager") as mock_cmgr, \
             patch("core.routes.explore.get_law_manager") as mock_law, \
             patch("core.routes.explore.get_location_manager") as mock_loc, \
             patch("core.routes.explore.get_item_manager") as mock_item:
            mock_reg_inst = MagicMock()
            mock_reg_inst.list_members.return_value = []
            mock_reg.return_value = mock_reg_inst
            mock_cmgr_inst = MagicMock()
            mock_cmgr_inst.get.side_effect = Exception("Not found")
            mock_cmgr.return_value = mock_cmgr_inst
            mock_law.return_value.list_laws.return_value = []
            mock_loc.return_value.list_locations.return_value = []
            mock_item.return_value.list_items.return_value = []

            result = _build_participant_context([
                {"id": "CH-9999", "type": "character"},
            ])
        assert "not found" in result.lower()


# ─── Chat ID Generation ─────────────────────────────────────


class TestExploreChatIdGeneration:
    """Tests for _next_explore_chat_id."""

    def test_first_id(self, tmp_path):
        """First chat ID when no files exist."""
        from core.routes.explore import _next_explore_chat_id
        with patch("config.settings.CONVERSATIONS_DIR", tmp_path):
            result = _next_explore_chat_id()
        assert result == "EC-0001"

    def test_sequential_id(self, tmp_path):
        """Sequential after existing files."""
        from core.routes.explore import _next_explore_chat_id

        (tmp_path / "H-EC-0001.json").touch()
        (tmp_path / "H-EC-0002.json").touch()
        with patch("config.settings.CONVERSATIONS_DIR", tmp_path):
            result = _next_explore_chat_id()
        assert result == "EC-0003"
