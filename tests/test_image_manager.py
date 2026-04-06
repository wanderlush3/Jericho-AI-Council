"""
Tests for core.image_manager — Image Manager & Storage System (F-037b).

Tests the EntityImage dataclass, ImageManager CRUD operations, primary
image management, sequential IDs, extension detection, and edge cases.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from core.image_manager import (
    SUPPORTED_EXTENSIONS,
    VALID_ENTITY_TYPES,
    EntityImage,
    ImageError,
    ImageManager,
    ImageNotFoundError,
    ImageValidationError,
)


# ─── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def images_dir(tmp_path: Path) -> Path:
    """Provide a temporary images directory."""
    d = tmp_path / "images"
    d.mkdir()
    return d


@pytest.fixture
def mgr(images_dir: Path) -> ImageManager:
    """Provide an ImageManager using a temp directory."""
    return ImageManager(images_dir=images_dir)


# Sample image data (tiny valid PNG — 1x1 red pixel)
PNG_DATA = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

# JPEG magic bytes for extension detection tests
JPEG_DATA = b"\xff\xd8\xff\xe0" + b"\x00" * 100

# WebP magic bytes
WEBP_DATA = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100


# ─── EntityImage Dataclass ─────────────────────────────────


class TestEntityImage:
    """Tests for the EntityImage frozen dataclass."""

    def test_fields(self) -> None:
        img = EntityImage(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img_0001.png",
        )
        assert img.id == "IMG-0001"
        assert img.entity_type == "character"
        assert img.entity_id == "CH-0001"
        assert img.filename == "img_0001.png"

    def test_defaults(self) -> None:
        img = EntityImage(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img_0001.png",
        )
        assert img.original_filename == ""
        assert img.prompt == ""
        assert img.negative_prompt == ""
        assert img.is_primary is False
        assert img.file_size == 0
        assert img.width == 0
        assert img.height == 0
        assert img.template_id == ""
        assert img.generation_job_id == ""
        assert img.created_at == ""
        assert img.metadata == {}

    def test_frozen(self) -> None:
        img = EntityImage(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img_0001.png",
        )
        with pytest.raises(AttributeError):
            img.id = "IMG-0002"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        img = EntityImage(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img_0001.png",
            prompt="a noble knight",
            is_primary=True,
            file_size=1024,
            width=512,
            height=512,
            metadata={"source": "comfyui"},
        )
        data = img.to_dict()
        restored = EntityImage.from_dict(data)
        assert restored == img
        assert restored.to_dict() == data

    def test_create_factory(self) -> None:
        img = EntityImage.create(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img_0001.png",
            prompt="a noble knight",
            is_primary=True,
        )
        assert img.id == "IMG-0001"
        assert img.entity_type == "character"
        assert img.entity_id == "CH-0001"
        assert img.prompt == "a noble knight"
        assert img.is_primary is True
        assert img.created_at != ""  # auto-timestamp

    def test_create_factory_empty_id_raises(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            EntityImage.create(
                id="",
                entity_type="character",
                entity_id="CH-0001",
                filename="img.png",
            )
        assert "Image ID is required" in str(exc_info.value)

    def test_create_factory_empty_entity_type_raises(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            EntityImage.create(
                id="IMG-0001",
                entity_type="",
                entity_id="CH-0001",
                filename="img.png",
            )
        assert "Entity type is required" in str(exc_info.value)

    def test_create_factory_empty_entity_id_raises(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            EntityImage.create(
                id="IMG-0001",
                entity_type="character",
                entity_id="",
                filename="img.png",
            )
        assert "Entity ID is required" in str(exc_info.value)

    def test_create_factory_empty_filename_raises(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            EntityImage.create(
                id="IMG-0001",
                entity_type="character",
                entity_id="CH-0001",
                filename="",
            )
        assert "Filename is required" in str(exc_info.value)

    def test_create_factory_whitespace_stripping(self) -> None:
        img = EntityImage.create(
            id="  IMG-0001  ",
            entity_type="  character  ",
            entity_id="  CH-0001  ",
            filename="  img.png  ",
            original_filename="  portrait.png  ",
            template_id="  TPL-0001  ",
            generation_job_id="  GEN-0001  ",
        )
        assert img.id == "IMG-0001"
        assert img.entity_type == "character"
        assert img.entity_id == "CH-0001"
        assert img.filename == "img.png"
        assert img.original_filename == "portrait.png"
        assert img.template_id == "TPL-0001"
        assert img.generation_job_id == "GEN-0001"

    def test_from_dict_missing_optionals(self) -> None:
        data = {
            "id": "IMG-0001",
            "entity_type": "character",
            "entity_id": "CH-0001",
            "filename": "img_0001.png",
        }
        img = EntityImage.from_dict(data)
        assert img.prompt == ""
        assert img.is_primary is False
        assert img.metadata == {}

    def test_create_with_metadata(self) -> None:
        meta = {"model": "flux", "steps": 20}
        img = EntityImage.create(
            id="IMG-0001",
            entity_type="character",
            entity_id="CH-0001",
            filename="img.png",
            metadata=meta,
        )
        assert img.metadata == meta


# ─── ImageManager Init ───────────────────────────────────────


class TestImageManagerInit:
    """Tests for ImageManager initialization."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "new_images"
        assert not d.exists()
        mgr = ImageManager(images_dir=d)
        assert d.exists()
        assert mgr.directory == d

    def test_existing_directory(self, images_dir: Path) -> None:
        mgr = ImageManager(images_dir=images_dir)
        assert mgr.directory == images_dir

    def test_repr(self, mgr: ImageManager) -> None:
        r = repr(mgr)
        assert "ImageManager" in r
        assert "dir=" in r


# ─── Save Image ──────────────────────────────────────────────


class TestSaveImage:
    """Tests for ImageManager.save_image()."""

    def test_basic_save(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.id == "IMG-0001"
        assert img.entity_type == "character"
        assert img.entity_id == "CH-0001"
        assert img.filename.startswith("img_")
        assert img.filename.endswith(".png")
        assert img.file_size == len(PNG_DATA)
        assert img.created_at != ""

    def test_first_image_is_auto_primary(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.is_primary is True

    def test_second_image_not_primary(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img2.is_primary is False

    def test_explicit_primary(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        img2 = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            is_primary=True,
        )
        assert img2.is_primary is True
        # First image should no longer be primary
        images = mgr.list_images("character", "CH-0001")
        primary_count = sum(1 for i in images if i.is_primary)
        assert primary_count == 1
        assert images[1].is_primary is True

    def test_sequential_ids(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img3 = mgr.save_image(
            PNG_DATA, entity_type="location", entity_id="LOC-0001",
        )
        assert img1.id == "IMG-0001"
        assert img2.id == "IMG-0002"
        assert img3.id == "IMG-0003"

    def test_sequential_filenames(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img1.filename == "img_0001.png"
        assert img2.filename == "img_0002.png"

    def test_persistence(self, mgr: ImageManager) -> None:
        mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            prompt="a knight",
        )
        # Reload from disk
        mgr2 = ImageManager(images_dir=mgr.directory)
        images = mgr2.list_images("character", "CH-0001")
        assert len(images) == 1
        assert images[0].prompt == "a knight"

    def test_image_file_written(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        path = mgr.get_image_path(img.id)
        assert path.exists()
        assert path.read_bytes() == PNG_DATA

    def test_with_all_fields(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="portrait.png",
            prompt="a noble knight in armor",
            negative_prompt="blurry, low quality",
            width=512,
            height=768,
            template_id="TPL-0001",
            generation_job_id="GEN-0001",
            metadata={"model": "flux", "steps": 20},
        )
        assert img.original_filename == "portrait.png"
        assert img.prompt == "a noble knight in armor"
        assert img.negative_prompt == "blurry, low quality"
        assert img.width == 512
        assert img.height == 768
        assert img.template_id == "TPL-0001"
        assert img.generation_job_id == "GEN-0001"
        assert img.metadata == {"model": "flux", "steps": 20}

    def test_empty_entity_type_raises(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            mgr.save_image(PNG_DATA, entity_type="", entity_id="CH-0001")
        assert "Entity type is required" in str(exc_info.value)

    def test_empty_entity_id_raises(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            mgr.save_image(PNG_DATA, entity_type="character", entity_id="")
        assert "Entity ID is required" in str(exc_info.value)

    def test_empty_data_raises(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            mgr.save_image(
                b"", entity_type="character", entity_id="CH-0001",
            )
        assert "Image data is required" in str(exc_info.value)

    def test_whitespace_entity_type_raises(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            mgr.save_image(PNG_DATA, entity_type="   ", entity_id="CH-0001")
        assert "Entity type is required" in str(exc_info.value)


# ─── Get Image ───────────────────────────────────────────────


class TestGetImage:
    """Tests for ImageManager.get()."""

    def test_get_existing(self, mgr: ImageManager) -> None:
        saved = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        got = mgr.get(saved.id)
        assert got.id == saved.id
        assert got.entity_type == "character"
        assert got.entity_id == "CH-0001"

    def test_get_not_found(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageNotFoundError) as exc_info:
            mgr.get("IMG-9999")
        assert exc_info.value.image_id == "IMG-9999"

    def test_get_across_entities(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="location", entity_id="LOC-0001",
        )
        assert mgr.get(img1.id).entity_type == "character"
        assert mgr.get(img2.id).entity_type == "location"


# ─── List Images ─────────────────────────────────────────────


class TestListImages:
    """Tests for ImageManager.list_images()."""

    def test_list_empty(self, mgr: ImageManager) -> None:
        images = mgr.list_images("character", "CH-0001")
        assert images == []

    def test_list_all(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 3

    def test_list_primary_only(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        images = mgr.list_images("character", "CH-0001", primary_only=True)
        assert len(images) == 1
        assert images[0].is_primary is True

    def test_list_different_entities_isolated(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0002")
        imgs_1 = mgr.list_images("character", "CH-0001")
        imgs_2 = mgr.list_images("character", "CH-0002")
        assert len(imgs_1) == 1
        assert len(imgs_2) == 1


# ─── Get Primary Image ──────────────────────────────────────


class TestGetPrimaryImage:
    """Tests for ImageManager.get_primary_image()."""

    def test_no_images_returns_none(self, mgr: ImageManager) -> None:
        result = mgr.get_primary_image("character", "CH-0001")
        assert result is None

    def test_returns_primary(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        primary = mgr.get_primary_image("character", "CH-0001")
        assert primary is not None
        assert primary.id == img.id
        assert primary.is_primary is True

    def test_after_set_primary(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        mgr.set_primary(img2.id)
        primary = mgr.get_primary_image("character", "CH-0001")
        assert primary is not None
        assert primary.id == img2.id


# ─── Set Primary ────────────────────────────────────────────


class TestSetPrimary:
    """Tests for ImageManager.set_primary()."""

    def test_set_primary(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img1.is_primary is True
        assert img2.is_primary is False

        result = mgr.set_primary(img2.id)
        assert result.is_primary is True

        # Verify persistence
        images = mgr.list_images("character", "CH-0001")
        primary_ids = [i.id for i in images if i.is_primary]
        assert primary_ids == [img2.id]

    def test_set_primary_clears_others(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        img3 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        mgr.set_primary(img3.id)

        images = mgr.list_images("character", "CH-0001")
        primary_count = sum(1 for i in images if i.is_primary)
        assert primary_count == 1

    def test_set_primary_not_found(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageNotFoundError):
            mgr.set_primary("IMG-9999")

    def test_set_primary_idempotent(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img.is_primary is True
        result = mgr.set_primary(img.id)
        assert result.is_primary is True


# ─── Delete Image ────────────────────────────────────────────


class TestDeleteImage:
    """Tests for ImageManager.delete()."""

    def test_delete_removes_file(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        path = mgr.get_image_path(img.id)
        assert path.exists()
        mgr.delete(img.id)
        assert not path.exists()

    def test_delete_removes_metadata(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        mgr.delete(img.id)
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 0

    def test_delete_not_found(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageNotFoundError):
            mgr.delete("IMG-9999")

    def test_delete_primary_promotes_next(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img1.is_primary is True

        mgr.delete(img1.id)
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 1
        assert images[0].id == img2.id
        assert images[0].is_primary is True

    def test_delete_non_primary_no_promotion(self, mgr: ImageManager) -> None:
        img1 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        mgr.delete(img2.id)
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 1
        assert images[0].id == img1.id
        assert images[0].is_primary is True

    def test_delete_preserves_others(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        img2 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        img3 = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        mgr.delete(img2.id)
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 2
        ids = {i.id for i in images}
        assert img2.id not in ids


# ─── Get Image Path ──────────────────────────────────────────


class TestGetImagePath:
    """Tests for ImageManager.get_image_path()."""

    def test_returns_correct_path(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        path = mgr.get_image_path(img.id)
        expected = mgr.directory / "character" / "CH-0001" / img.filename
        assert path == expected

    def test_path_not_found(self, mgr: ImageManager) -> None:
        with pytest.raises(ImageNotFoundError):
            mgr.get_image_path("IMG-9999")


# ─── Count Images ───────────────────────────────────────────


class TestCountImages:
    """Tests for ImageManager.count_images()."""

    def test_count_empty(self, mgr: ImageManager) -> None:
        assert mgr.count_images("character", "CH-0001") == 0

    def test_count_multiple(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        assert mgr.count_images("character", "CH-0001") == 3


# ─── Delete Entity Images ───────────────────────────────────


class TestDeleteEntityImages:
    """Tests for ImageManager.delete_entity_images()."""

    def test_delete_all(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        count = mgr.delete_entity_images("character", "CH-0001")
        assert count == 2
        assert mgr.count_images("character", "CH-0001") == 0

    def test_delete_empty(self, mgr: ImageManager) -> None:
        count = mgr.delete_entity_images("character", "CH-9999")
        assert count == 0

    def test_preserves_other_entities(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0002")
        mgr.delete_entity_images("character", "CH-0001")
        assert mgr.count_images("character", "CH-0001") == 0
        assert mgr.count_images("character", "CH-0002") == 1


# ─── Extension Detection ────────────────────────────────────


class TestExtensionDetection:
    """Tests for file extension detection."""

    def test_from_original_filename_png(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="portrait.png",
        )
        assert img.filename.endswith(".png")

    def test_from_original_filename_jpg(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            JPEG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="photo.jpg",
        )
        assert img.filename.endswith(".jpg")

    def test_from_original_filename_jpeg(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            JPEG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="photo.jpeg",
        )
        assert img.filename.endswith(".jpeg")

    def test_from_original_filename_webp(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            WEBP_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="image.webp",
        )
        assert img.filename.endswith(".webp")

    def test_from_magic_bytes_png(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.filename.endswith(".png")

    def test_from_magic_bytes_jpeg(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            JPEG_DATA,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.filename.endswith(".jpg")

    def test_from_magic_bytes_webp(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            WEBP_DATA,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.filename.endswith(".webp")

    def test_unknown_defaults_to_png(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            b"\x00\x00\x00\x00" * 25,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.filename.endswith(".png")

    def test_unsupported_extension_falls_back_to_magic(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="image.bmp",  # BMP not supported
        )
        assert img.filename.endswith(".png")  # falls back to magic bytes


# ─── Constants ───────────────────────────────────────────────


class TestConstants:
    """Tests for module-level constants."""

    def test_valid_entity_types(self) -> None:
        assert "character" in VALID_ENTITY_TYPES
        assert "location" in VALID_ENTITY_TYPES
        assert "item" in VALID_ENTITY_TYPES
        assert "store" in VALID_ENTITY_TYPES
        assert "council_member" in VALID_ENTITY_TYPES

    def test_supported_extensions(self) -> None:
        assert ".png" in SUPPORTED_EXTENSIONS
        assert ".jpg" in SUPPORTED_EXTENSIONS
        assert ".jpeg" in SUPPORTED_EXTENSIONS
        assert ".webp" in SUPPORTED_EXTENSIONS

    def test_valid_entity_types_is_frozenset(self) -> None:
        assert isinstance(VALID_ENTITY_TYPES, frozenset)

    def test_supported_extensions_is_frozenset(self) -> None:
        assert isinstance(SUPPORTED_EXTENSIONS, frozenset)


# ─── Exceptions ──────────────────────────────────────────────


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_hierarchy(self) -> None:
        assert issubclass(ImageNotFoundError, ImageError)
        assert issubclass(ImageValidationError, ImageError)
        assert issubclass(ImageError, Exception)

    def test_not_found_fields(self) -> None:
        exc = ImageNotFoundError("IMG-0001")
        assert exc.image_id == "IMG-0001"
        assert "IMG-0001" in str(exc)

    def test_validation_error_single_string(self) -> None:
        exc = ImageValidationError("Bad input")
        assert exc.errors == ["Bad input"]
        assert "Bad input" in str(exc)

    def test_validation_error_list(self) -> None:
        exc = ImageValidationError(["Error 1", "Error 2"])
        assert exc.errors == ["Error 1", "Error 2"]
        assert "Error 1" in str(exc)
        assert "Error 2" in str(exc)


# ─── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_unicode_prompt(self, mgr: ImageManager) -> None:
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            prompt="一位高贵的骑士 🗡️",
            negative_prompt="ぼやけた、低品質",
        )
        # Reload and verify
        loaded = mgr.get(img.id)
        assert loaded.prompt == "一位高贵的骑士 🗡️"
        assert loaded.negative_prompt == "ぼやけた、低品質"

    def test_large_image_data(self, mgr: ImageManager) -> None:
        # 1MB of data with PNG header
        large_data = PNG_DATA + b"\x00" * (1024 * 1024)
        img = mgr.save_image(
            large_data,
            entity_type="character",
            entity_id="CH-0001",
        )
        assert img.file_size == len(large_data)
        path = mgr.get_image_path(img.id)
        assert path.stat().st_size == len(large_data)

    def test_many_images_per_entity(self, mgr: ImageManager) -> None:
        for i in range(20):
            mgr.save_image(
                PNG_DATA,
                entity_type="character",
                entity_id="CH-0001",
            )
        images = mgr.list_images("character", "CH-0001")
        assert len(images) == 20
        # Only one primary
        primary_count = sum(1 for i in images if i.is_primary)
        assert primary_count == 1

    def test_persistence_roundtrip(self, mgr: ImageManager) -> None:
        """Verify metadata survives a save-reload cycle."""
        saved = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            prompt="a wizard",
            negative_prompt="ugly",
            width=512,
            height=768,
            template_id="TPL-0001",
            generation_job_id="GEN-0001",
            metadata={"model": "flux"},
        )
        # New manager instance
        mgr2 = ImageManager(images_dir=mgr.directory)
        loaded = mgr2.get(saved.id)
        assert loaded.prompt == "a wizard"
        assert loaded.negative_prompt == "ugly"
        assert loaded.width == 512
        assert loaded.height == 768
        assert loaded.template_id == "TPL-0001"
        assert loaded.generation_job_id == "GEN-0001"
        assert loaded.metadata == {"model": "flux"}

    def test_corrupt_metadata_returns_empty(self, mgr: ImageManager) -> None:
        """Corrupt images.json should be handled gracefully."""
        entity_dir = mgr.directory / "character" / "CH-0001"
        entity_dir.mkdir(parents=True)
        (entity_dir / "images.json").write_text("NOT JSON!!!", encoding="utf-8")
        images = mgr.list_images("character", "CH-0001")
        assert images == []

    def test_multiple_entity_types(self, mgr: ImageManager) -> None:
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="location", entity_id="LOC-0001")
        mgr.save_image(PNG_DATA, entity_type="item", entity_id="ITEM-0001")
        mgr.save_image(PNG_DATA, entity_type="store", entity_id="STORE-0001")

        assert mgr.count_images("character", "CH-0001") == 1
        assert mgr.count_images("location", "LOC-0001") == 1
        assert mgr.count_images("item", "ITEM-0001") == 1
        assert mgr.count_images("store", "STORE-0001") == 1

    def test_id_continuity_after_reload(self, mgr: ImageManager) -> None:
        """IDs should continue from where they left off after reload."""
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        mgr.save_image(PNG_DATA, entity_type="character", entity_id="CH-0001")
        # New manager instance (simulates restart)
        mgr2 = ImageManager(images_dir=mgr.directory)
        img3 = mgr2.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        assert img3.id == "IMG-0003"

    def test_full_lifecycle(self, mgr: ImageManager) -> None:
        """End-to-end test: save, set primary, get, delete, verify."""
        # Save two images
        img1 = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            prompt="first image",
        )
        img2 = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            prompt="second image",
        )
        assert img1.is_primary is True
        assert img2.is_primary is False

        # Set second as primary
        mgr.set_primary(img2.id)
        primary = mgr.get_primary_image("character", "CH-0001")
        assert primary is not None
        assert primary.id == img2.id

        # Delete primary — first should auto-promote
        mgr.delete(img2.id)
        remaining = mgr.list_images("character", "CH-0001")
        assert len(remaining) == 1
        assert remaining[0].is_primary is True
        assert remaining[0].id == img1.id

        # Delete last image
        mgr.delete(img1.id)
        assert mgr.count_images("character", "CH-0001") == 0

    def test_explicit_non_primary_first_image(self, mgr: ImageManager) -> None:
        """Explicitly setting is_primary=False on first image should work."""
        img = mgr.save_image(
            PNG_DATA,
            entity_type="character",
            entity_id="CH-0001",
            is_primary=False,
        )
        assert img.is_primary is False
        primary = mgr.get_primary_image("character", "CH-0001")
        assert primary is None

    def test_delete_with_missing_file(self, mgr: ImageManager) -> None:
        """Deleting an image whose file is already gone should not crash."""
        img = mgr.save_image(
            PNG_DATA, entity_type="character", entity_id="CH-0001",
        )
        # Manually remove the file
        path = mgr.get_image_path(img.id)
        path.unlink()
        # Delete should still succeed (removes metadata)
        mgr.delete(img.id)
        assert mgr.count_images("character", "CH-0001") == 0
