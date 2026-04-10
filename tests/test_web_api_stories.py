"""
Tests for Story API endpoints (F-041).
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
