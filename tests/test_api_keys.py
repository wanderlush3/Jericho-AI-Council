"""
Tests for Jericho Secure API Key Manager (F-023).

All tests use ``tmp_path`` fixtures — no real keys or .env files are touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.api_keys import APIKeyManager


# ─── Unit Tests: APIKeyManager ─────────────────────────────────


class TestMaskKey:
    """Tests for key obfuscation."""

    def test_mask_normal_key(self):
        assert APIKeyManager.mask_key("sk-abc123xyz") == "sk-a…yz"

    def test_mask_short_key(self):
        assert APIKeyManager.mask_key("abc") == "••••"

    def test_mask_exact_boundary(self):
        assert APIKeyManager.mask_key("abcdef") == "••••"

    def test_mask_seven_chars(self):
        assert APIKeyManager.mask_key("abcdefg") == "abcd…fg"


class TestSaveAndLoad:
    """Tests for encrypt/decrypt round-trip."""

    def test_save_and_load_openrouter(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        result = mgr.save_key("openrouter", "sk-test-key-12345")

        assert result["configured"] is True
        assert result["masked"] == "sk-t…45"
        assert result["provider"] == "openrouter"

        loaded = mgr.load_key("openrouter")
        assert loaded == "sk-test-key-12345"

    def test_save_and_load_mancer(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("mancer", "mn-abcdef-99")

        loaded = mgr.load_key("mancer")
        assert loaded == "mn-abcdef-99"

    def test_save_and_load_lmstudio(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        result = mgr.save_key("lmstudio", "lm-key-test-42")

        assert result["configured"] is True
        assert result["provider"] == "lmstudio"

        loaded = mgr.load_key("lmstudio")
        assert loaded == "lm-key-test-42"

    def test_key_is_encrypted_on_disk(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# header\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("openrouter", "sk-secret-value-xyz")

        raw_contents = env_file.read_text(encoding="utf-8")
        # The raw key must NOT appear in the file
        assert "sk-secret-value-xyz" not in raw_contents
        # The encrypted Fernet token should be there
        assert "gAAAAA" in raw_contents

    def test_load_nonexistent_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# nothing\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        assert mgr.load_key("openrouter") is None

    def test_load_placeholder_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "JERICHO_OPENROUTER_API_KEY=your-openrouter-key-here\n",
            encoding="utf-8",
        )

        mgr = APIKeyManager(env_path=env_file)
        assert mgr.load_key("openrouter") is None

    def test_overwrite_existing_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "JERICHO_OPENROUTER_API_KEY=old-encrypted-value\n",
            encoding="utf-8",
        )

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("openrouter", "sk-new-key")

        loaded = mgr.load_key("openrouter")
        assert loaded == "sk-new-key"

    def test_preserves_comments_and_other_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# Jericho keys\n"
            "JERICHO_OPENROUTER_API_KEY=your-openrouter-key-here\n"
            "SOME_OTHER_VAR=hello\n",
            encoding="utf-8",
        )

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("openrouter", "sk-test")

        contents = env_file.read_text(encoding="utf-8")
        assert "# Jericho keys" in contents
        assert "SOME_OTHER_VAR=hello" in contents


class TestDeleteKey:
    """Tests for key removal."""

    def test_delete_configured_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("openrouter", "sk-to-delete")
        result = mgr.delete_key("openrouter")

        assert result["configured"] is False
        assert result["masked"] is None
        assert mgr.load_key("openrouter") is None


class TestKeyStatus:
    """Tests for status reporting."""

    def test_status_not_configured(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        status = mgr.key_status("openrouter")

        assert status["configured"] is False
        assert status["masked"] is None

    def test_status_configured(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("mancer", "mn-key-abc")
        status = mgr.key_status("mancer")

        assert status["configured"] is True
        assert "mn-k" in status["masked"]

    def test_all_status(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        mgr.save_key("openrouter", "sk-test-123")
        statuses = mgr.all_status()

        assert len(statuses) == 3
        providers = {s["provider"] for s in statuses}
        assert "openrouter" in providers
        assert "mancer" in providers
        assert "lmstudio" in providers


class TestInvalidProvider:
    """Tests for unknown provider handling."""

    def test_save_invalid_provider(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        with pytest.raises(ValueError, match="Unknown provider"):
            mgr.save_key("invalid-provider", "key")

    def test_status_invalid_provider(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n", encoding="utf-8")

        mgr = APIKeyManager(env_path=env_file)
        with pytest.raises(ValueError, match="Unknown provider"):
            mgr.key_status("invalid-provider")


# ─── Web API Tests ─────────────────────────────────────────────


@pytest.fixture
def api_client(tmp_path):
    """TestClient with mocked env path."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# test keys\n"
        "JERICHO_OPENROUTER_API_KEY=your-openrouter-key-here\n"
        "JERICHO_MANCER_API_KEY=your-mancer-key-here\n"
        "JERICHO_LMSTUDIO_API_KEY=your-lmstudio-key-here\n",
        encoding="utf-8",
    )

    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Test</h1>", encoding="utf-8")

    with (
        patch("core.api_keys.ENV_FILE", env_file),
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
    ):
        from core.web_api import create_app
        app = create_app()
        yield TestClient(app)


class TestSettingsEndpoints:
    """Tests for the /api/settings/keys endpoints."""

    def test_get_keys_status(self, api_client):
        resp = api_client.get("/api/settings/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert all(not k["configured"] for k in data)

    def test_save_key(self, api_client):
        resp = api_client.post(
            "/api/settings/keys",
            json={"provider": "openrouter", "api_key": "sk-test-12345"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert "sk-t" in data["masked"]
        assert "12345" not in data["masked"]

    def test_save_key_then_status_configured(self, api_client):
        api_client.post(
            "/api/settings/keys",
            json={"provider": "mancer", "api_key": "mn-abc-xyz"},
        )
        resp = api_client.get("/api/settings/keys")
        data = resp.json()
        mancer = next(k for k in data if k["provider"] == "mancer")
        assert mancer["configured"] is True

    def test_delete_key(self, api_client):
        api_client.post(
            "/api/settings/keys",
            json={"provider": "openrouter", "api_key": "sk-to-remove"},
        )
        resp = api_client.delete("/api/settings/keys/openrouter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_save_missing_fields(self, api_client):
        resp = api_client.post(
            "/api/settings/keys",
            json={"provider": "openrouter"},
        )
        assert resp.status_code == 400

    def test_save_invalid_provider(self, api_client):
        resp = api_client.post(
            "/api/settings/keys",
            json={"provider": "foobar", "api_key": "abc"},
        )
        assert resp.status_code == 400

    def test_delete_invalid_provider(self, api_client):
        resp = api_client.delete("/api/settings/keys/foobar")
        assert resp.status_code == 400

    def test_raw_key_never_in_response(self, api_client):
        raw = "sk-super-secret-never-leak-this-key"
        api_client.post(
            "/api/settings/keys",
            json={"provider": "openrouter", "api_key": raw},
        )

        resp = api_client.get("/api/settings/keys")
        body = resp.text
        assert raw not in body
