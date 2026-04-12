"""
Tests for Story API endpoints (F-041, F-043) — expanded coverage (F-046).

Covers:
- Story CRUD (create, list, filter, get, update, status, delete)
- Chapter CRUD (add, update, delete, error paths)
- Scene CRUD (add, update, delete, enriched detail, error paths)
- Narrate with participants (validation, backward compat, edge cases)
- Illustrate with participants (validation, edge cases)
- Story chat lifecycle (active, create, inject-narration, round limits)
- Story chat round tracking helpers
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def stories_dir(tmp_path):
    """Temp stories directory."""
    d = tmp_path / "stories"
    d.mkdir()
    return d


@pytest.fixture
def client(tmp_path, stories_dir):
    """Create a test FastAPI client with patched StoryManager."""
    from core.story import StoryManager

    real_story_mgr = StoryManager(stories_dir=stories_dir)

    with patch("core.story.StoryManager", return_value=real_story_mgr):
        from core.web_api import create_app
        app = create_app()
        yield TestClient(app)


# ─── Story CRUD Tests ────────────────────────────────────────


class TestStoryCRUD:
    """Tests for story CRUD endpoints."""

    def test_create_story(self, client):
        resp = client.post("/api/stories", json={
            "title": "The Dark Tower",
            "synopsis": "A tale of a lone gunslinger",
            "author": "Admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["story_id"] == "ST-0001"
        assert data["title"] == "The Dark Tower"
        assert data["status"] == "draft"

    def test_create_story_missing_title(self, client):
        resp = client.post("/api/stories", json={"synopsis": "No title"})
        assert resp.status_code == 400

    def test_list_stories(self, client):
        client.post("/api/stories", json={"title": "Story A"})
        client.post("/api/stories", json={"title": "Story B"})
        resp = client.get("/api/stories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert "chapter_count" in data[0]
        assert "scene_count" in data[0]

    def test_list_stories_filter_status(self, client):
        resp1 = client.post("/api/stories", json={"title": "Draft Story"})
        resp2 = client.post("/api/stories", json={"title": "Active Story"})
        story_id = resp2.json()["story_id"]
        client.put(f"/api/stories/{story_id}/status", json={"status": "active"})

        resp = client.get("/api/stories?status=draft")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_story(self, client):
        create_resp = client.post("/api/stories", json={
            "title": "Fetch Me",
        })
        story_id = create_resp.json()["story_id"]
        resp = client.get(f"/api/stories/{story_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Fetch Me"

    def test_get_story_not_found(self, client):
        resp = client.get("/api/stories/ST-9999")
        assert resp.status_code == 404

    def test_update_story(self, client):
        create_resp = client.post("/api/stories", json={
            "title": "Original",
        })
        story_id = create_resp.json()["story_id"]
        resp = client.put(f"/api/stories/{story_id}", json={
            "title": "Renamed",
            "synopsis": "New synopsis",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

    def test_update_status(self, client):
        create_resp = client.post("/api/stories", json={
            "title": "Status Test",
        })
        story_id = create_resp.json()["story_id"]
        resp = client.put(f"/api/stories/{story_id}/status", json={
            "status": "active",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_update_status_invalid(self, client):
        create_resp = client.post("/api/stories", json={
            "title": "Invalid",
        })
        story_id = create_resp.json()["story_id"]
        resp = client.put(f"/api/stories/{story_id}/status", json={
            "status": "completed",  # draft → completed is invalid
        })
        assert resp.status_code == 400

    def test_delete_story(self, client):
        create_resp = client.post("/api/stories", json={
            "title": "Delete Me",
        })
        story_id = create_resp.json()["story_id"]
        resp = client.delete(f"/api/stories/{story_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == story_id
        # Verify gone
        resp2 = client.get(f"/api/stories/{story_id}")
        assert resp2.status_code == 404

    def test_update_not_found(self, client):
        resp = client.put(
            "/api/stories/ST-9999",
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_update_status_not_found(self, client):
        resp = client.put(
            "/api/stories/ST-9999/status",
            json={"status": "active"},
        )
        assert resp.status_code == 404

    def test_update_status_empty(self, client):
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.put(
            f"/api/stories/{story_id}/status",
            json={"status": ""},
        )
        assert resp.status_code == 400

    def test_delete_not_found(self, client):
        resp = client.delete("/api/stories/ST-9999")
        assert resp.status_code == 404

    def test_list_stories_empty(self, client):
        resp = client.get("/api/stories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_stories_detail_fields(self, client):
        """List response includes all expected summary fields."""
        client.post("/api/stories", json={
            "title": "Fields Check",
            "synopsis": "synop",
            "author": "admin",
        })
        resp = client.get("/api/stories")
        data = resp.json()[0]
        expected = {
            "story_id", "title", "synopsis", "author", "status",
            "chapter_count", "scene_count", "illustration_count",
        }
        assert expected.issubset(set(data.keys()))

    def test_create_with_optional_fields(self, client):
        resp = client.post("/api/stories", json={
            "title": "Styled Story",
            "synopsis": "A stylized tale",
            "author": "Writer",
            "style_preset_key": "fantasy_art",
            "template_id": "TPL-0001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["style_preset_key"] == "fantasy_art"
        assert data["template_id"] == "TPL-0001"

    def test_create_whitespace_title_rejected(self, client):
        resp = client.post("/api/stories", json={"title": "   "})
        assert resp.status_code == 400


# ─── Chapter CRUD Tests ─────────────────────────────────────


class TestChapterCRUD:
    """Tests for chapter endpoints."""

    def test_add_chapter(self, client):
        story_resp = client.post("/api/stories", json={"title": "Story"})
        story_id = story_resp.json()["story_id"]
        resp = client.post(f"/api/stories/{story_id}/chapters", json={
            "title": "Chapter One",
            "synopsis": "The beginning",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter_id"] == "CHP-0001"
        assert data["title"] == "Chapter One"

    def test_update_chapter(self, client):
        story_resp = client.post("/api/stories", json={"title": "Story"})
        story_id = story_resp.json()["story_id"]
        ch_resp = client.post(f"/api/stories/{story_id}/chapters", json={
            "title": "Old Title",
        })
        ch_id = ch_resp.json()["chapter_id"]
        resp = client.put(f"/api/stories/{story_id}/chapters/{ch_id}", json={
            "title": "New Title",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_delete_chapter(self, client):
        story_resp = client.post("/api/stories", json={"title": "Story"})
        story_id = story_resp.json()["story_id"]
        ch_resp = client.post(f"/api/stories/{story_id}/chapters", json={
            "title": "Delete This",
        })
        ch_id = ch_resp.json()["chapter_id"]
        resp = client.delete(f"/api/stories/{story_id}/chapters/{ch_id}")
        assert resp.status_code == 200

    def test_chapter_not_found(self, client):
        story_resp = client.post("/api/stories", json={"title": "Story"})
        story_id = story_resp.json()["story_id"]
        resp = client.delete(f"/api/stories/{story_id}/chapters/CHP-9999")
        assert resp.status_code == 404

    def test_chapter_story_not_found(self, client):
        resp = client.post(
            "/api/stories/ST-9999/chapters",
            json={"title": "Orphan Chapter"},
        )
        assert resp.status_code == 404

    def test_update_chapter_story_not_found(self, client):
        resp = client.put(
            "/api/stories/ST-9999/chapters/CHP-0001",
            json={"title": "New"},
        )
        assert resp.status_code == 404

    def test_update_chapter_not_found(self, client):
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.put(
            f"/api/stories/{story_id}/chapters/CHP-9999",
            json={"title": "New"},
        )
        assert resp.status_code == 404

    def test_multiple_chapters(self, client):
        s = client.post("/api/stories", json={"title": "Multi"})
        story_id = s.json()["story_id"]
        client.post(f"/api/stories/{story_id}/chapters", json={"title": "Ch1"})
        client.post(f"/api/stories/{story_id}/chapters", json={"title": "Ch2"})

        resp = client.get(f"/api/stories/{story_id}")
        assert len(resp.json()["chapters"]) == 2


# ─── Scene CRUD Tests ───────────────────────────────────────


class TestSceneCRUD:
    """Tests for scene endpoints."""

    def _setup_story_chapter(self, client):
        """Helper: create a story with a chapter, return (story_id, ch_id)."""
        story_resp = client.post("/api/stories", json={"title": "Story"})
        story_id = story_resp.json()["story_id"]
        ch_resp = client.post(f"/api/stories/{story_id}/chapters", json={
            "title": "Chapter",
        })
        ch_id = ch_resp.json()["chapter_id"]
        return story_id, ch_id

    def test_add_scene(self, client):
        story_id, ch_id = self._setup_story_chapter(client)
        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "tense", "location_id": "LOC-0001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scene_id"] == "SCE-0001"
        assert data["mood"] == "tense"

    def test_update_scene(self, client):
        story_id, ch_id = self._setup_story_chapter(client)
        sc_resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "calm"},
        )
        sc_id = sc_resp.json()["scene_id"]
        resp = client.put(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes/{sc_id}",
            json={"narrative_text": "The sun set slowly."},
        )
        assert resp.status_code == 200
        assert resp.json()["narrative_text"] == "The sun set slowly."

    def test_delete_scene(self, client):
        story_id, ch_id = self._setup_story_chapter(client)
        sc_resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={},
        )
        sc_id = sc_resp.json()["scene_id"]
        resp = client.delete(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes/{sc_id}",
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == sc_id

    def test_scene_not_found(self, client):
        story_id, ch_id = self._setup_story_chapter(client)
        resp = client.delete(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes/SCE-9999",
        )
        assert resp.status_code == 404

    def test_full_story_detail_with_scenes(self, client):
        """Test that GET /api/stories/{id} returns enriched scene data."""
        story_id, ch_id = self._setup_story_chapter(client)
        client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "mysterious"},
        )
        resp = client.get(f"/api/stories/{story_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chapters"]) == 1
        assert len(data["chapters"][0]["scenes"]) == 1
        scene = data["chapters"][0]["scenes"][0]
        assert "image_url" in scene

    def test_scene_image_url_when_image_id_set(self, client):
        """Scene image_url includes image_id when set."""
        story_id, ch_id = self._setup_story_chapter(client)
        sc = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "dark"},
        )
        sc_id = sc.json()["scene_id"]
        client.put(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes/{sc_id}",
            json={"image_id": "IMG-0042"},
        )
        resp = client.get(f"/api/stories/{story_id}")
        scene = resp.json()["chapters"][0]["scenes"][0]
        assert "IMG-0042" in scene["image_url"]

    def test_scene_image_url_empty_when_no_image(self, client):
        """Scene image_url is empty string when no image_id."""
        story_id, ch_id = self._setup_story_chapter(client)
        client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={},
        )
        resp = client.get(f"/api/stories/{story_id}")
        scene = resp.json()["chapters"][0]["scenes"][0]
        assert scene["image_url"] == ""

    def test_update_scene_image_url_in_response(self, client):
        """PUT scene with image_id returns image_url in response."""
        story_id, ch_id = self._setup_story_chapter(client)
        sc = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={},
        )
        sc_id = sc.json()["scene_id"]
        resp = client.put(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes/{sc_id}",
            json={"image_id": "IMG-0099"},
        )
        assert "IMG-0099" in resp.json()["image_url"]

    def test_update_scene_story_not_found(self, client):
        resp = client.put(
            "/api/stories/ST-9999/chapters/CHP-0001/scenes/SCE-0001",
            json={"mood": "x"},
        )
        assert resp.status_code == 404

    def test_update_scene_chapter_not_found(self, client):
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.put(
            f"/api/stories/{story_id}/chapters/CHP-9999/scenes/SCE-0001",
            json={"mood": "x"},
        )
        assert resp.status_code == 404

    def test_delete_scene_story_not_found(self, client):
        resp = client.delete(
            "/api/stories/ST-9999/chapters/CHP-0001/scenes/SCE-0001",
        )
        assert resp.status_code == 404

    def test_delete_scene_chapter_not_found(self, client):
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.delete(
            f"/api/stories/{story_id}/chapters/CHP-9999/scenes/SCE-0001",
        )
        assert resp.status_code == 404

    def test_add_scene_story_not_found(self, client):
        resp = client.post(
            "/api/stories/ST-9999/chapters/CHP-0001/scenes",
            json={"mood": "calm"},
        )
        assert resp.status_code == 404

    def test_add_scene_chapter_not_found(self, client):
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.post(
            f"/api/stories/{story_id}/chapters/CHP-9999/scenes",
            json={"mood": "calm"},
        )
        assert resp.status_code == 404

    def test_multiple_scenes_in_chapter(self, client):
        story_id, ch_id = self._setup_story_chapter(client)
        client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "a"},
        )
        client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "b"},
        )
        resp = client.get(f"/api/stories/{story_id}")
        scenes = resp.json()["chapters"][0]["scenes"]
        assert len(scenes) == 2


# ─── Participant Tests (F-043) ──────────────────────────────


class TestStoryParticipants:
    """Tests for F-043: Story Participant System integration."""

    def _setup_story_with_scene(self, client):
        """Create a story → chapter → scene, return IDs."""
        s = client.post("/api/stories", json={"title": "Participant Test"})
        story_id = s.json()["story_id"]
        ch = client.post(
            f"/api/stories/{story_id}/chapters",
            json={"title": "Chapter 1"},
        )
        ch_id = ch.json()["chapter_id"]
        sc = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}/scenes",
            json={"mood": "tense", "location_id": "LOC-0001"},
        )
        sc_id = sc.json()["scene_id"]
        return story_id, ch_id, sc_id

    # ── Narrate with participants ────────────────────────────

    def test_narrate_with_participants(self, client):
        """Narrate with participants should inject context into prompt."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "The shadow fell."
        mock_response.model = "mock-model"
        mock_response.provider = "mock"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={
                    "participants": [
                        {"id": "sage", "type": "council"},
                        {"id": "CH-0001", "type": "character"},
                    ],
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["narrative_text"] == "The shadow fell."

    def test_narrate_without_participants_backward_compat(self, client):
        """Narrate without participants should still work (backward compat)."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "Dawn breaks over the valley."
        mock_response.model = "mock-model"
        mock_response.provider = "mock"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={},
            )
        assert resp.status_code == 200
        assert resp.json()["narrative_text"] == "Dawn breaks over the valley."

    def test_narrate_with_empty_participants(self, client):
        """Narrate with empty participants array should work."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "Silence."
        mock_response.model = "mock-model"
        mock_response.provider = "mock"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={"participants": []},
            )
        assert resp.status_code == 200

    def test_narrate_max_ten_participants(self, client):
        """Narrate with exactly 10 participants should be accepted."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        ten_participants = [
            {"id": f"p{i}", "type": "council"} for i in range(10)
        ]

        mock_response = MagicMock()
        mock_response.content = "A crowd gathers."
        mock_response.model = "mock-model"
        mock_response.provider = "mock"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={"participants": ten_participants},
            )
        assert resp.status_code == 200

    def test_narrate_too_many_participants(self, client):
        """Narrate with 11+ participants should return 400."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        eleven_participants = [
            {"id": f"p{i}", "type": "council"} for i in range(11)
        ]

        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/{sc_id}/narrate",
            json={"participants": eleven_participants},
        )
        assert resp.status_code == 400
        assert "Too many participants" in resp.json()["detail"]

    def test_narrate_invalid_participants_type(self, client):
        """Narrate with non-list participants should return 400."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/{sc_id}/narrate",
            json={"participants": "not-a-list"},
        )
        assert resp.status_code == 400
        assert "must be a list" in resp.json()["detail"]

    def test_narrate_story_not_found(self, client):
        """Narrate on a non-existent story should return 404."""
        resp = client.post(
            "/api/stories/ST-9999/chapters/CHP-0001"
            "/scenes/SCE-0001/narrate",
            json={"participants": []},
        )
        assert resp.status_code == 404

    def test_narrate_chapter_not_found(self, client):
        """Narrate with wrong chapter should return 404."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "..."
        mock_response.model = "m"
        mock_response.provider = "p"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/CHP-9999"
                f"/scenes/{sc_id}/narrate",
                json={},
            )
        assert resp.status_code == 404
        assert "Chapter" in resp.json()["detail"]

    def test_narrate_scene_not_found(self, client):
        """Narrate with wrong scene should return 404."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "..."
        mock_response.model = "m"
        mock_response.provider = "p"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/SCE-9999/narrate",
                json={},
            )
        assert resp.status_code == 404
        assert "Scene" in resp.json()["detail"]

    def test_narrate_saves_to_scene(self, client):
        """Narrate endpoint should persist narrative_text to the scene."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "The hero stood tall."
        mock_response.model = "m"
        mock_response.provider = "p"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={},
            )

        # Verify scene was updated
        detail_resp = client.get(f"/api/stories/{story_id}")
        scene = detail_resp.json()["chapters"][0]["scenes"][0]
        assert scene["narrative_text"] == "The hero stood tall."

    def test_narrate_returns_model_info(self, client):
        """Narrate response includes model and provider."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        mock_response = MagicMock()
        mock_response.content = "test"
        mock_response.model = "test-model-42"
        mock_response.provider = "test-provider"

        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = client.post(
                f"/api/stories/{story_id}/chapters/{ch_id}"
                f"/scenes/{sc_id}/narrate",
                json={},
            )
        data = resp.json()
        assert data["model"] == "test-model-42"
        assert data["provider"] == "test-provider"

    # ── Illustrate with participants ─────────────────────────

    def test_illustrate_too_many_participants(self, client):
        """Illustrate with 11+ participants should return 400."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        eleven_participants = [
            {"id": f"p{i}", "type": "character"} for i in range(11)
        ]

        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/{sc_id}/illustrate",
            json={"participants": eleven_participants},
        )
        assert resp.status_code == 400
        assert "Too many participants" in resp.json()["detail"]

    def test_illustrate_invalid_participants_type(self, client):
        """Illustrate with non-list participants should return 400."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)

        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/{sc_id}/illustrate",
            json={"participants": {"not": "a list"}},
        )
        assert resp.status_code == 400
        assert "must be a list" in resp.json()["detail"]

    def test_illustrate_story_not_found(self, client):
        """Illustrate on a non-existent story should return 404."""
        resp = client.post(
            "/api/stories/ST-9999/chapters/CHP-0001"
            "/scenes/SCE-0001/illustrate",
            json={"participants": []},
        )
        assert resp.status_code == 404

    def test_illustrate_chapter_not_found(self, client):
        """Illustrate with wrong chapter returns 404."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)
        resp = client.post(
            f"/api/stories/{story_id}/chapters/CHP-9999"
            f"/scenes/{sc_id}/illustrate",
            json={},
        )
        assert resp.status_code == 404
        assert "Chapter" in resp.json()["detail"]

    def test_illustrate_scene_not_found(self, client):
        """Illustrate with wrong scene returns 404."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)
        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/SCE-9999/illustrate",
            json={},
        )
        assert resp.status_code == 404
        assert "Scene" in resp.json()["detail"]

    def test_illustrate_no_template_returns_error_or_queues(self, client):
        """Illustrate without any template source returns an error or queues."""
        story_id, ch_id, sc_id = self._setup_story_with_scene(client)
        resp = client.post(
            f"/api/stories/{story_id}/chapters/{ch_id}"
            f"/scenes/{sc_id}/illustrate",
            json={},
        )
        # Endpoint may return 400 if no template found, or 200 if a
        # default is resolved.  The key assertion is that it doesn't
        # crash (500).
        assert resp.status_code != 500


# ─── Story Chat Helpers ────────────────────────────────────


class TestStoryChatHelpers:
    """Unit tests for _get_story_round, _is_story_chat_at_limit, _increment_story_round."""

    def test_get_story_round_zero(self):
        """Returns 0 when no round in metadata."""
        from core.routes.stories import _get_story_round
        record = MagicMock()
        record.metadata = {}
        assert _get_story_round(record) == 0

    def test_get_story_round_value(self):
        """Returns the stored round number."""
        from core.routes.stories import _get_story_round
        record = MagicMock()
        record.metadata = {"story_round": 3}
        assert _get_story_round(record) == 3

    def test_get_story_round_none_metadata(self):
        """Returns 0 when metadata is None."""
        from core.routes.stories import _get_story_round
        record = MagicMock()
        record.metadata = None
        assert _get_story_round(record) == 0

    def test_is_at_limit_below(self):
        """Not at limit when round < max."""
        from core.routes.stories import _is_story_chat_at_limit
        record = MagicMock()
        record.metadata = {"story_round": 2, "story_max_rounds": 5}
        assert _is_story_chat_at_limit(record) is False

    def test_is_at_limit_equal(self):
        """At limit when round == max."""
        from core.routes.stories import _is_story_chat_at_limit
        record = MagicMock()
        record.metadata = {"story_round": 5, "story_max_rounds": 5}
        assert _is_story_chat_at_limit(record) is True

    def test_is_at_limit_above(self):
        """At limit when round > max."""
        from core.routes.stories import _is_story_chat_at_limit
        record = MagicMock()
        record.metadata = {"story_round": 7, "story_max_rounds": 5}
        assert _is_story_chat_at_limit(record) is True

    def test_is_at_limit_default_max(self):
        """Uses _STORY_CHAT_MAX_ROUNDS when no max in metadata."""
        from core.routes.stories import (
            _is_story_chat_at_limit, _STORY_CHAT_MAX_ROUNDS,
        )
        record = MagicMock()
        record.metadata = {"story_round": _STORY_CHAT_MAX_ROUNDS}
        assert _is_story_chat_at_limit(record) is True

    def test_is_at_limit_none_metadata(self):
        """Not at limit when metadata is None (round=0)."""
        from core.routes.stories import _is_story_chat_at_limit
        record = MagicMock()
        record.metadata = None
        assert _is_story_chat_at_limit(record) is False


# ─── Story Chat Endpoints ───────────────────────────────────


class TestStoryChatEndpoints:
    """Tests for story chat lifecycle endpoints."""

    def test_chat_active_no_chats(self, client):
        """Active chat returns null when no active story chat exists."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]

        with patch("core.routes.stories._make_story_chat") as mock_fn:
            mock_hc = MagicMock()
            mock_hc.list_chats.return_value = []
            mock_fn.return_value = mock_hc

            resp = client.get(f"/api/stories/{story_id}/chat/active")
        assert resp.status_code == 200
        assert resp.json()["chat_id"] is None

    def test_chat_create_missing_participants(self, client):
        """Creating a chat with no participants returns 400."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.post(
            f"/api/stories/{story_id}/chat",
            json={"participants": []},
        )
        assert resp.status_code == 400
        assert "participant" in resp.json()["detail"].lower()

    def test_chat_create_story_not_found(self, client):
        """Creating a chat for non-existent story returns 404."""
        resp = client.post(
            "/api/stories/ST-9999/chat",
            json={"participants": [{"id": "sage", "type": "council"}]},
        )
        assert resp.status_code == 404

    def test_inject_narration_missing_narration_text(self, client):
        """Inject narration without narration_text returns 400."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.post(
            f"/api/stories/{story_id}/chat/STC-0001/inject-narration",
            json={},
        )
        assert resp.status_code == 400
        assert "narration_text" in resp.json()["detail"]

    def test_inject_narration_empty_text(self, client):
        """Inject narration with whitespace-only text returns 400."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.post(
            f"/api/stories/{story_id}/chat/STC-0001/inject-narration",
            json={"narration_text": "   "},
        )
        assert resp.status_code == 400

    def test_send_stream_missing_content(self, client):
        """Send-stream with missing content returns 400."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]
        resp = client.post(
            f"/api/stories/{story_id}/chat/STC-0001/send-stream",
            json={"content": ""},
        )
        assert resp.status_code == 400
        assert "content" in resp.json()["detail"].lower()


# ─── Story Chat ID Generation ───────────────────────────────


class TestStoryChatIdGeneration:
    """Tests for _next_story_chat_id."""

    def test_first_id(self, tmp_path):
        """First chat ID when no files exist."""
        from core.routes.stories import _next_story_chat_id
        with patch("config.settings.CONVERSATIONS_DIR", tmp_path):
            result = _next_story_chat_id()
        assert result == "STC-0001"

    def test_sequential_id(self, tmp_path):
        """Sequential after existing files."""
        from core.routes.stories import _next_story_chat_id

        (tmp_path / "H-STC-0001.json").touch()
        (tmp_path / "H-STC-0005.json").touch()
        with patch("config.settings.CONVERSATIONS_DIR", tmp_path):
            result = _next_story_chat_id()
        assert result == "STC-0006"


# ─── Story Narrate Round ────────────────────────────────────


class TestNarrateRoundEndpoint:
    """Tests for POST /api/stories/{story_id}/chat/{chat_id}/narrate-round."""

    def test_narrate_round_chat_not_found(self, client):
        """Returns 404 when chat does not exist."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]

        with patch("core.routes.stories._make_story_chat") as mock_fn:
            from core.human_chat import HumanChatNotFoundError
            mock_hc = MagicMock()
            mock_hc.get.side_effect = HumanChatNotFoundError("STC-9999")
            mock_fn.return_value = mock_hc

            resp = client.post(
                f"/api/stories/{story_id}/chat/STC-9999/narrate-round",
                json={},
            )
        assert resp.status_code == 404

    def test_narrate_round_wrong_story(self, client):
        """Returns 400 when chat belongs to a different story."""
        s = client.post("/api/stories", json={"title": "S"})
        story_id = s.json()["story_id"]

        with patch("core.routes.stories._make_story_chat") as mock_fn:
            mock_hc = MagicMock()
            mock_rec = MagicMock()
            mock_rec.metadata = {"story_id": "ST-OTHER"}
            mock_hc.get.return_value = mock_rec
            mock_fn.return_value = mock_hc

            resp = client.post(
                f"/api/stories/{story_id}/chat/STC-0001/narrate-round",
                json={},
            )
        assert resp.status_code == 400
        assert "does not belong" in resp.json()["detail"]
