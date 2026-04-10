"""
Tests for F-037e — Entity Image Gallery API endpoints.
"""

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────

# Minimal 1x1 PNG (67 bytes)
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal 1x1 JPEG (107 bytes — smallest valid JFIF)
TINY_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
    0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
    0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08,
    0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C,
    0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D,
    0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20,
    0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27,
    0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
    0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4,
    0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF,
    0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
    0x00, 0x7B, 0x40, 0x1B, 0xFF, 0xD9,
])


def _b64(data: bytes, mime: str = "image/png") -> str:
    """Encode bytes as a data URL string."""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _upload(client, entity_type="character", entity_id="CH-0001", **extra):
    """Upload a test PNG and return the response."""
    payload = {"image_data": _b64(TINY_PNG), **extra}
    return client.post(f"/api/images/{entity_type}/{entity_id}", json=payload)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def tmp_images(tmp_path):
    """Provide a temporary images directory."""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    return img_dir


@pytest.fixture()
def client(tmp_path, tmp_images, monkeypatch):
    """Create a test client with isolated images directory."""
    monkeypatch.setattr("config.settings.COMFYUI_IMAGES_DIR", tmp_images)
    monkeypatch.setattr("core.image_manager.COMFYUI_IMAGES_DIR", tmp_images)
    monkeypatch.setattr("config.settings.ENV_FILE", tmp_path / ".env")
    (tmp_path / ".env").write_text("", encoding="utf-8")

    from core.web_api import create_app
    app = create_app()
    return TestClient(app)


# ── List Images ──────────────────────────────────────────────────


class TestImagesList:
    """Tests for GET /api/images/{entity_type}/{entity_id}."""

    def test_list_empty(self, client):
        resp = client.get("/api/images/character/CH-0001")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_upload(self, client):
        _upload(client)
        resp = client.get("/api/images/character/CH-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["entity_type"] == "character"
        assert data[0]["entity_id"] == "CH-0001"
        assert data[0]["is_primary"] is True
        assert "url" in data[0]

    def test_list_multiple(self, client):
        _upload(client)
        _upload(client)
        _upload(client)
        resp = client.get("/api/images/character/CH-0001")
        assert len(resp.json()) == 3

    def test_list_different_entities(self, client):
        _upload(client, entity_id="CH-0001")
        _upload(client, entity_id="CH-0002")
        resp1 = client.get("/api/images/character/CH-0001")
        resp2 = client.get("/api/images/character/CH-0002")
        assert len(resp1.json()) == 1
        assert len(resp2.json()) == 1

    def test_list_invalid_entity_type(self, client):
        resp = client.get("/api/images/invalid_type/X-0001")
        assert resp.status_code == 400
        assert "Invalid entity type" in resp.json()["detail"]

    def test_list_url_format(self, client):
        _upload(client)
        data = client.get("/api/images/character/CH-0001").json()
        assert data[0]["url"].startswith("/api/images/file/IMG-")


# ── Upload Image ─────────────────────────────────────────────────


class TestImagesUpload:
    """Tests for POST /api/images/{entity_type}/{entity_id}."""

    def test_upload_basic(self, client):
        resp = _upload(client)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "IMG-0001"
        assert data["entity_type"] == "character"
        assert data["entity_id"] == "CH-0001"
        assert data["is_primary"] is True
        assert "url" in data

    def test_upload_sequential_ids(self, client):
        r1 = _upload(client)
        r2 = _upload(client)
        assert r1.json()["id"] == "IMG-0001"
        assert r2.json()["id"] == "IMG-0002"

    def test_upload_first_is_primary(self, client):
        r = _upload(client)
        assert r.json()["is_primary"] is True

    def test_upload_second_not_primary(self, client):
        _upload(client)
        r2 = _upload(client)
        assert r2.json()["is_primary"] is False

    def test_upload_with_prompt(self, client):
        r = _upload(client, prompt="a noble knight", negative_prompt="blurry")
        data = r.json()
        assert data["prompt"] == "a noble knight"
        assert data["negative_prompt"] == "blurry"

    def test_upload_with_template_id(self, client):
        r = _upload(client, template_id="TPL-0001")
        assert r.json()["template_id"] == "TPL-0001"

    def test_upload_with_original_filename(self, client):
        r = _upload(client, original_filename="portrait.png")
        assert r.json()["original_filename"] == "portrait.png"

    def test_upload_explicit_primary(self, client):
        _upload(client)  # auto-primary
        r2 = _upload(client, is_primary=True)
        assert r2.json()["is_primary"] is True
        # First should no longer be primary
        images = client.get("/api/images/character/CH-0001").json()
        primaries = [i for i in images if i["is_primary"]]
        assert len(primaries) == 1
        assert primaries[0]["id"] == "IMG-0002"

    def test_upload_missing_image_data(self, client):
        resp = client.post("/api/images/character/CH-0001", json={})
        assert resp.status_code == 400
        assert "image_data" in resp.json()["detail"]

    def test_upload_empty_image_data(self, client):
        resp = client.post(
            "/api/images/character/CH-0001",
            json={"image_data": ""},
        )
        assert resp.status_code == 400

    def test_upload_invalid_base64(self, client):
        resp = client.post(
            "/api/images/character/CH-0001",
            json={"image_data": "not-valid-base64!!!"},
        )
        assert resp.status_code == 400
        assert "base64" in resp.json()["detail"].lower()

    def test_upload_invalid_entity_type(self, client):
        resp = client.post(
            "/api/images/bogus/X-0001",
            json={"image_data": _b64(TINY_PNG)},
        )
        assert resp.status_code == 400
        assert "Invalid entity type" in resp.json()["detail"]

    def test_upload_location(self, client):
        resp = _upload(client, entity_type="location", entity_id="LOC-0001")
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "location"

    def test_upload_item(self, client):
        resp = _upload(client, entity_type="item", entity_id="ITM-0001")
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "item"

    def test_upload_store(self, client):
        resp = _upload(client, entity_type="store", entity_id="STR-0001")
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "store"

    def test_upload_file_on_disk(self, client, tmp_images):
        _upload(client)
        # Verify image file exists on disk
        char_dir = tmp_images / "character" / "CH-0001"
        assert char_dir.exists()
        img_files = [f for f in char_dir.iterdir() if f.name.startswith("img_")]
        assert len(img_files) == 1

    def test_upload_data_url_with_prefix(self, client):
        """Data URLs with 'data:image/png;base64,' prefix should work."""
        resp = client.post(
            "/api/images/character/CH-0001",
            json={"image_data": _b64(TINY_PNG, "image/png")},
        )
        assert resp.status_code == 200

    def test_upload_raw_base64_without_prefix(self, client):
        """Raw base64 without data URL prefix should also work."""
        encoded = base64.b64encode(TINY_PNG).decode("ascii")
        resp = client.post(
            "/api/images/character/CH-0001",
            json={"image_data": encoded},
        )
        assert resp.status_code == 200


# ── Serve Image ──────────────────────────────────────────────────


class TestImagesServe:
    """Tests for GET /api/images/file/{image_id}."""

    def test_serve_png(self, client):
        upload = _upload(client)
        image_id = upload.json()["id"]
        resp = client.get(f"/api/images/file/{image_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    def test_serve_not_found(self, client):
        resp = client.get("/api/images/file/IMG-9999")
        assert resp.status_code == 404

    def test_serve_returns_correct_bytes(self, client):
        _upload(client)
        resp = client.get("/api/images/file/IMG-0001")
        # Should contain PNG magic bytes
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


# ── Set Primary ──────────────────────────────────────────────────


class TestImagesSetPrimary:
    """Tests for POST /api/images/{image_id}/set-primary."""

    def test_set_primary(self, client):
        _upload(client)
        _upload(client)
        resp = client.post("/api/images/set-primary/IMG-0002")
        assert resp.status_code == 200
        assert resp.json()["is_primary"] is True

        # Verify old primary was cleared
        images = client.get("/api/images/character/CH-0001").json()
        primaries = [i for i in images if i["is_primary"]]
        assert len(primaries) == 1
        assert primaries[0]["id"] == "IMG-0002"

    def test_set_primary_already_primary(self, client):
        _upload(client)
        resp = client.post("/api/images/set-primary/IMG-0001")
        assert resp.status_code == 200
        assert resp.json()["is_primary"] is True

    def test_set_primary_not_found(self, client):
        resp = client.post("/api/images/set-primary/IMG-9999")
        assert resp.status_code == 404


# ── Delete Image ─────────────────────────────────────────────────


class TestImagesDelete:
    """Tests for DELETE /api/images/{image_id}."""

    def test_delete_single(self, client):
        _upload(client)
        resp = client.delete("/api/images/delete/IMG-0001")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        images = client.get("/api/images/character/CH-0001").json()
        assert len(images) == 0

    def test_delete_promotes_primary(self, client):
        """Deleting the primary image should auto-promote the next one."""
        _upload(client)
        _upload(client)
        client.delete("/api/images/delete/IMG-0001")

        images = client.get("/api/images/character/CH-0001").json()
        assert len(images) == 1
        assert images[0]["is_primary"] is True

    def test_delete_not_found(self, client):
        resp = client.delete("/api/images/delete/IMG-9999")
        assert resp.status_code == 404

    def test_delete_file_removed(self, client, tmp_images):
        _upload(client)
        char_dir = tmp_images / "character" / "CH-0001"
        before = len([f for f in char_dir.iterdir() if f.name.startswith("img_")])
        assert before == 1

        client.delete("/api/images/delete/IMG-0001")
        after = len([f for f in char_dir.iterdir() if f.name.startswith("img_")])
        assert after == 0


# ── Image Info ───────────────────────────────────────────────────


class TestImagesInfo:
    """Tests for GET /api/images/{image_id}/info."""

    def test_info_basic(self, client):
        _upload(client, prompt="a knight", negative_prompt="ugly")
        resp = client.get("/api/images/info/IMG-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "IMG-0001"
        assert data["prompt"] == "a knight"
        assert data["negative_prompt"] == "ugly"
        assert data["entity_type"] == "character"
        assert "url" in data

    def test_info_not_found(self, client):
        resp = client.get("/api/images/info/IMG-9999")
        assert resp.status_code == 404

    def test_info_includes_template_id(self, client):
        _upload(client, template_id="TPL-0042")
        data = client.get("/api/images/info/IMG-0001").json()
        assert data["template_id"] == "TPL-0042"


# ── Lifecycle Integration ────────────────────────────────────────


class TestImageLifecycle:
    """End-to-end lifecycle tests."""

    def test_full_lifecycle(self, client):
        """Upload → list → set primary → delete → verify."""
        # Upload two images
        r1 = _upload(client, prompt="First image")
        r2 = _upload(client, prompt="Second image")
        assert r1.json()["is_primary"] is True
        assert r2.json()["is_primary"] is False

        # List should show both
        images = client.get("/api/images/character/CH-0001").json()
        assert len(images) == 2

        # Set second as primary
        client.post("/api/images/set-primary/IMG-0002")
        images = client.get("/api/images/character/CH-0001").json()
        id_to_primary = {i["id"]: i["is_primary"] for i in images}
        assert id_to_primary["IMG-0001"] is False
        assert id_to_primary["IMG-0002"] is True

        # Delete first
        client.delete("/api/images/delete/IMG-0001")
        images = client.get("/api/images/character/CH-0001").json()
        assert len(images) == 1
        assert images[0]["id"] == "IMG-0002"
        assert images[0]["is_primary"] is True

        # Info on remaining
        info = client.get("/api/images/info/IMG-0002").json()
        assert info["prompt"] == "Second image"

        # Serve the image
        resp = client.get("/api/images/file/IMG-0002")
        assert resp.status_code == 200

    def test_multi_entity_isolation(self, client):
        """Images for different entities stay isolated."""
        _upload(client, entity_type="character", entity_id="CH-0001")
        _upload(client, entity_type="location", entity_id="LOC-0001")
        _upload(client, entity_type="item", entity_id="ITM-0001")

        assert len(client.get("/api/images/character/CH-0001").json()) == 1
        assert len(client.get("/api/images/location/LOC-0001").json()) == 1
        assert len(client.get("/api/images/item/ITM-0001").json()) == 1
