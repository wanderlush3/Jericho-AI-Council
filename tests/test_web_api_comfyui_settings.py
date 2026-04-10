"""
Tests for F-037d — ComfyUI Settings & Templates Web UI API endpoints.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure ComfyUI env vars are clean for each test."""
    for var in [
        "JERICHO_COMFYUI_HOST",
        "JERICHO_COMFYUI_PORT",
        "JERICHO_COMFYUI_DEFAULT_STYLE",
    ]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def tmp_templates(tmp_path):
    """Provide a temporary templates directory and patch settings."""
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    return tpl_dir


@pytest.fixture()
def client(tmp_path, tmp_templates, monkeypatch):
    """Create a test client with isolated directories."""
    monkeypatch.setattr("config.settings.COMFYUI_TEMPLATES_DIR", tmp_templates)
    monkeypatch.setattr("core.comfyui_client.COMFYUI_TEMPLATES_DIR", tmp_templates)
    monkeypatch.setattr("config.settings.ENV_FILE", tmp_path / ".env")

    # Create minimal .env
    (tmp_path / ".env").write_text("", encoding="utf-8")

    from core.web_api import create_app
    app = create_app()
    return TestClient(app)


# ── Connection Config ────────────────────────────────────────────


class TestComfyUIConfig:
    """Tests for GET/POST /api/settings/comfyui."""

    def test_get_defaults(self, client):
        resp = client.get("/api/settings/comfyui")
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 8188

    def test_save_config(self, client):
        resp = client.post(
            "/api/settings/comfyui",
            json={"host": "192.168.1.100", "port": 9000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "192.168.1.100"
        assert data["port"] == 9000
        assert data["saved"] is True

        # Verify it persists
        resp2 = client.get("/api/settings/comfyui")
        assert resp2.json()["host"] == "192.168.1.100"
        assert resp2.json()["port"] == 9000

    def test_save_config_missing_host(self, client):
        resp = client.post(
            "/api/settings/comfyui",
            json={"host": "", "port": 8188},
        )
        assert resp.status_code == 400
        assert "host" in resp.json()["detail"].lower()

    def test_save_config_invalid_port(self, client):
        resp = client.post(
            "/api/settings/comfyui",
            json={"host": "127.0.0.1", "port": 99999},
        )
        assert resp.status_code == 400
        assert "Port" in resp.json()["detail"]

    def test_save_config_non_integer_port(self, client):
        resp = client.post(
            "/api/settings/comfyui",
            json={"host": "127.0.0.1", "port": "abc"},
        )
        assert resp.status_code == 400
        assert "integer" in resp.json()["detail"].lower()


# ── Connection Test ──────────────────────────────────────────────


class TestComfyUIConnectionTest:
    """Tests for POST /api/settings/comfyui/test."""

    def test_connection_success(self, client, monkeypatch):
        """Mock a successful ComfyUI connection."""
        mock_stats = {
            "system": {
                "gpus": [{"name": "NVIDIA RTX 4090", "vram_total": 25769803776}]
            }
        }

        async def mock_test_connection(self):
            return mock_stats

        monkeypatch.setattr(
            "core.comfyui_client.ComfyUIClient.test_connection",
            mock_test_connection,
        )

        resp = client.post("/api/settings/comfyui/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["system_stats"]["system"]["gpus"][0]["name"] == "NVIDIA RTX 4090"

    def test_connection_failure(self, client, monkeypatch):
        """Mock a failed ComfyUI connection."""
        from core.comfyui_client import ComfyUIConnectionError

        async def mock_test_fail(self):
            raise ComfyUIConnectionError(
                "Connection refused", host="127.0.0.1", port=8188
            )

        monkeypatch.setattr(
            "core.comfyui_client.ComfyUIClient.test_connection",
            mock_test_fail,
        )

        resp = client.post("/api/settings/comfyui/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert "refused" in data["error"].lower()


# ── Templates CRUD ───────────────────────────────────────────────

SAMPLE_WORKFLOW = {
    "1": {
        "class_type": "KSampler",
        "inputs": {
            "seed": "%seed%",
            "steps": 20,
            "cfg": 7.0,
            "positive": "%prompt%",
            "negative": "%negative%",
        },
    },
}


class TestComfyUITemplates:
    """Tests for /api/settings/comfyui/templates CRUD."""

    def test_list_empty(self, client):
        resp = client.get("/api/settings/comfyui/templates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_template(self, client):
        resp = client.post(
            "/api/settings/comfyui/templates",
            json={
                "name": "Test Workflow",
                "workflow_json": SAMPLE_WORKFLOW,
                "description": "A test workflow",
                "entity_type": "character",
                "author": "TestUser",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "TPL-0001"
        assert data["name"] == "Test Workflow"
        assert data["entity_type"] == "character"
        assert "prompt" in data["placeholders"]
        assert "negative" in data["placeholders"]
        assert "seed" in data["placeholders"]

    def test_create_and_list(self, client):
        client.post(
            "/api/settings/comfyui/templates",
            json={"name": "WF1", "workflow_json": SAMPLE_WORKFLOW},
        )
        client.post(
            "/api/settings/comfyui/templates",
            json={"name": "WF2", "workflow_json": {"nodes": {}}},
        )

        resp = client.get("/api/settings/comfyui/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # List summaries should NOT include workflow_json
        assert "workflow_json" not in data[0]

    def test_filter_by_entity_type(self, client):
        client.post(
            "/api/settings/comfyui/templates",
            json={
                "name": "Char WF",
                "workflow_json": SAMPLE_WORKFLOW,
                "entity_type": "character",
            },
        )
        client.post(
            "/api/settings/comfyui/templates",
            json={
                "name": "Loc WF",
                "workflow_json": {"nodes": {}},
                "entity_type": "location",
            },
        )

        resp = client.get("/api/settings/comfyui/templates?entity_type=character")
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "Char WF"

    def test_get_template(self, client):
        create = client.post(
            "/api/settings/comfyui/templates",
            json={"name": "Full Detail", "workflow_json": SAMPLE_WORKFLOW},
        )
        tpl_id = create.json()["id"]

        resp = client.get(f"/api/settings/comfyui/templates/{tpl_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Full Detail"
        assert "workflow_json" in data
        assert data["workflow_json"] == SAMPLE_WORKFLOW

    def test_get_template_not_found(self, client):
        resp = client.get("/api/settings/comfyui/templates/TPL-9999")
        assert resp.status_code == 404

    def test_delete_template(self, client):
        create = client.post(
            "/api/settings/comfyui/templates",
            json={"name": "Delete Me", "workflow_json": {"x": 1}},
        )
        tpl_id = create.json()["id"]

        resp = client.delete(f"/api/settings/comfyui/templates/{tpl_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Should be gone now
        resp2 = client.get(f"/api/settings/comfyui/templates/{tpl_id}")
        assert resp2.status_code == 404

    def test_delete_template_not_found(self, client):
        resp = client.delete("/api/settings/comfyui/templates/TPL-9999")
        assert resp.status_code == 404

    def test_create_missing_name(self, client):
        resp = client.post(
            "/api/settings/comfyui/templates",
            json={"name": "", "workflow_json": SAMPLE_WORKFLOW},
        )
        assert resp.status_code == 400
        assert "name" in resp.json()["detail"].lower()

    def test_create_missing_workflow(self, client):
        resp = client.post(
            "/api/settings/comfyui/templates",
            json={"name": "Test", "workflow_json": None},
        )
        assert resp.status_code == 400
        assert "workflow_json" in resp.json()["detail"].lower()


# ── Style Presets ────────────────────────────────────────────────


class TestComfyUIStylePresets:
    """Tests for style preset endpoints."""

    def test_list_presets(self, client):
        resp = client.get("/api/settings/comfyui/style-presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 8
        names = {p["name"] for p in data}
        assert "Fantasy Art" in names
        assert "Anime" in names
        assert "Realistic" in names

    def test_get_default_style_empty(self, client):
        resp = client.get("/api/settings/comfyui/default-style")
        assert resp.status_code == 200
        assert resp.json()["style_key"] == ""

    def test_save_default_style(self, client):
        resp = client.post(
            "/api/settings/comfyui/default-style",
            json={"style_key": "Fantasy Art"},
        )
        assert resp.status_code == 200
        assert resp.json()["saved"] is True

        resp2 = client.get("/api/settings/comfyui/default-style")
        assert resp2.json()["style_key"] == "Fantasy Art"

    def test_save_default_style_empty(self, client):
        """Clearing the default style should work."""
        resp = client.post(
            "/api/settings/comfyui/default-style",
            json={"style_key": ""},
        )
        assert resp.status_code == 200

    def test_save_default_style_invalid(self, client):
        resp = client.post(
            "/api/settings/comfyui/default-style",
            json={"style_key": "NonExistentPreset"},
        )
        assert resp.status_code == 400
        assert "Unknown" in resp.json()["detail"]
