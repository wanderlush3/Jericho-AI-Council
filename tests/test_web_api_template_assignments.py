"""
Tests for per-entity-type template assignment API endpoints (F-039).

Tests the REST API layer for template assignments:
- GET/POST/DELETE assignments
- Recommended template endpoint
- Template test endpoint
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── Fixtures ──────────────────────────────────────────────────


class FakeTemplate:
    """Minimal template object for testing."""

    def __init__(self, id, name="", entity_type="", desc=""):
        self.id = id
        self.name = name
        self.entity_type = entity_type
        self.description = desc
        self.placeholders = ["prompt", "negative", "seed", "width", "height"]
        self.workflow_json = {"nodes": []}
        self.author = ""
        self.created_at = ""
        self.updated_at = ""

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "placeholders": self.placeholders,
            "workflow_json": self.workflow_json,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@pytest.fixture
def tmp_assignments_file(tmp_path):
    return tmp_path / "template_assignments.json"


@pytest.fixture
def fake_templates():
    return {
        "TPL-0001": FakeTemplate("TPL-0001", "Portrait", "character"),
        "TPL-0002": FakeTemplate("TPL-0002", "Landscape", "location"),
        "TPL-0003": FakeTemplate("TPL-0003", "General"),
    }


@pytest.fixture(autouse=True)
def patch_settings_and_managers(tmp_assignments_file, fake_templates, monkeypatch):
    """Patch settings and managers for all tests."""
    # Clean up any leftover assignments file from previous tests
    if tmp_assignments_file.exists():
        tmp_assignments_file.unlink()

    tpl_dir = tmp_assignments_file.parent / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    # Patch at both the config level AND the already-imported module level
    monkeypatch.setattr(
        "config.settings.COMFYUI_TEMPLATE_ASSIGNMENTS_FILE",
        tmp_assignments_file,
    )
    monkeypatch.setattr(
        "config.settings.COMFYUI_TEMPLATES_DIR",
        tpl_dir,
    )
    monkeypatch.setattr(
        "core.comfyui_client.COMFYUI_TEMPLATES_DIR",
        tpl_dir,
    )
    monkeypatch.setattr(
        "core.template_assignments.COMFYUI_TEMPLATE_ASSIGNMENTS_FILE",
        tmp_assignments_file,
    )

    # Write fake templates to disk
    for tpl_id, tpl in fake_templates.items():
        tpl_file = tpl_dir / f"{tpl_id}.json"
        tpl_file.write_text(json.dumps(tpl.to_dict()), encoding="utf-8")


@pytest.fixture
def client():
    """Create a test client for the web API."""
    from core.web_api import create_app
    from starlette.testclient import TestClient

    app = create_app()
    return TestClient(app)


# ─── TestGetAssignments ────────────────────────────────────────


class TestGetAssignments:
    """Tests for GET /api/settings/comfyui/template-assignments."""

    def test_returns_all_entity_types(self, client):
        resp = client.get("/api/settings/comfyui/template-assignments")
        assert resp.status_code == 200
        data = resp.json()
        assert "character" in data
        assert "location" in data
        assert "item" in data
        assert "store" in data

    def test_initially_empty(self, client):
        resp = client.get("/api/settings/comfyui/template-assignments")
        data = resp.json()
        assert all(v == "" for v in data.values())


# ─── TestSaveAssignments ──────────────────────────────────────


class TestSaveAssignments:
    """Tests for POST /api/settings/comfyui/template-assignments."""

    def test_save_single(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-0001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["assignments"]["character"] == "TPL-0001"

    def test_save_multiple(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments",
            json={
                "character": "TPL-0001",
                "location": "TPL-0002",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assignments"]["character"] == "TPL-0001"
        assert data["assignments"]["location"] == "TPL-0002"

    def test_persists_across_requests(self, client):
        client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-0001"},
        )
        resp = client.get("/api/settings/comfyui/template-assignments")
        assert resp.json()["character"] == "TPL-0001"

    def test_invalid_template(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-9999"},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_ignores_invalid_entity_types(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments",
            json={
                "character": "TPL-0001",
                "unicorn": "TPL-0002",  # Invalid, should be ignored
            },
        )
        assert resp.status_code == 200
        assert "unicorn" not in resp.json()["assignments"]

    def test_clear_via_empty_string(self, client):
        client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-0001"},
        )
        resp = client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["assignments"]["character"] == ""


# ─── TestClearAssignment ──────────────────────────────────────


class TestClearAssignment:
    """Tests for DELETE /api/settings/comfyui/template-assignments/{entity_type}."""

    def test_clear(self, client):
        client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-0001"},
        )
        resp = client.delete(
            "/api/settings/comfyui/template-assignments/character"
        )
        assert resp.status_code == 200
        assert resp.json()["cleared"] == "character"
        assert resp.json()["assignments"]["character"] == ""

    def test_clear_already_empty(self, client):
        resp = client.delete(
            "/api/settings/comfyui/template-assignments/location"
        )
        assert resp.status_code == 200

    def test_clear_invalid_entity_type(self, client):
        resp = client.delete(
            "/api/settings/comfyui/template-assignments/invalid"
        )
        assert resp.status_code == 400


# ─── TestRecommendedTemplate ─────────────────────────────────


class TestRecommendedTemplate:
    """Tests for GET /api/settings/comfyui/recommended-template/{entity_type}."""

    def test_assignment_source(self, client):
        client.post(
            "/api/settings/comfyui/template-assignments",
            json={"character": "TPL-0003"},  # Explicitly assign General
        )
        resp = client.get(
            "/api/settings/comfyui/recommended-template/character"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_type"] == "character"
        assert data["template_id"] == "TPL-0003"
        assert data["source"] == "assignment"

    def test_entity_type_match_source(self, client):
        # Ensure no explicit assignment exists
        client.delete(
            "/api/settings/comfyui/template-assignments/character"
        )
        resp = client.get(
            "/api/settings/comfyui/recommended-template/character"
        )
        assert resp.status_code == 200
        data = resp.json()
        # Without an explicit assignment, should find a template
        assert data["template_id"] != ""
        # Source should be entity_type_match or fallback
        assert data["source"] in ("entity_type_match", "fallback")

    def test_fallback_source(self, client):
        resp = client.get(
            "/api/settings/comfyui/recommended-template/item"
        )
        assert resp.status_code == 200
        data = resp.json()
        # No entity_type match for "item", falls back to first
        assert data["template_id"] != ""
        assert data["source"] == "fallback"


# ─── TestTemplateTest ─────────────────────────────────────────


class TestTemplateTest:
    """Tests for POST /api/settings/comfyui/template-assignments/test/{template_id}."""

    def test_valid_template(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments/test/TPL-0001"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["template_id"] == "TPL-0001"
        assert data["name"] == "Portrait"

    def test_nonexistent_template(self, client):
        resp = client.post(
            "/api/settings/comfyui/template-assignments/test/TPL-9999"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "not found" in data["error"]
