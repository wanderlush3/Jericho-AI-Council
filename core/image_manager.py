"""
Jericho — Image Manager & Storage System (F-037b)

Filesystem-backed image storage organized by entity type and entity ID.

Images are stored under::

    data/images/{entity_type}/{entity_id}/
        images.json          ← per-entity metadata index
        img_0001.png         ← image file (sequential naming)
        img_0002.png
        ...

Each entity's ``images.json`` stores a list of :class:`EntityImage` records
describing every image associated with that entity.  Exactly one image per
entity can be designated as *primary* (used for thumbnails, avatars, etc.).

This module provides:

- **EntityImage** — frozen dataclass with metadata for a stored image.
- **ImageManager** — CRUD for images tied to entities, with primary-flag
  management, sequential ``IMG-XXXX`` global IDs, and filesystem operations.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import COMFYUI_IMAGES_DIR
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class ImageError(Exception):
    """Base exception for image management errors."""


class ImageNotFoundError(ImageError):
    """Raised when an image ID is not found."""

    def __init__(self, image_id: str) -> None:
        self.image_id = image_id
        super().__init__(f"Image not found: '{image_id}'")


class ImageValidationError(ImageError):
    """Raised when image data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


# ─── Valid Entity Types ──────────────────────────────────────

VALID_ENTITY_TYPES = frozenset({
    "character",
    "location",
    "item",
    "store",
    "council_member",
})

# ─── Supported Image Extensions ─────────────────────────────

SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})


# ─── Data Model ──────────────────────────────────────────────


@dataclass(frozen=True)
class EntityImage:
    """Metadata for a single image stored on disk.

    The actual image file lives at
    ``{images_dir}/{entity_type}/{entity_id}/{filename}``.
    """

    id: str                           # IMG-XXXX (global sequential ID)
    entity_type: str                  # e.g. "character", "location"
    entity_id: str                    # e.g. "CH-0001"
    filename: str                     # on-disk filename, e.g. "img_0001.png"
    original_filename: str = ""       # user-provided filename before rename
    prompt: str = ""                  # generation prompt (if AI-generated)
    negative_prompt: str = ""         # negative prompt (if AI-generated)
    is_primary: bool = False          # primary image for the entity
    file_size: int = 0                # bytes
    width: int = 0                    # pixels (0 = unknown)
    height: int = 0                   # pixels (0 = unknown)
    template_id: str = ""             # ComfyUI template used (TPL-XXXX)
    generation_job_id: str = ""       # Jericho generation job (GEN-XXXX)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityImage:
        return cls(
            id=data["id"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            filename=data["filename"],
            original_filename=data.get("original_filename", ""),
            prompt=data.get("prompt", ""),
            negative_prompt=data.get("negative_prompt", ""),
            is_primary=data.get("is_primary", False),
            file_size=data.get("file_size", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            template_id=data.get("template_id", ""),
            generation_job_id=data.get("generation_job_id", ""),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        entity_type: str,
        entity_id: str,
        filename: str,
        original_filename: str = "",
        prompt: str = "",
        negative_prompt: str = "",
        is_primary: bool = False,
        file_size: int = 0,
        width: int = 0,
        height: int = 0,
        template_id: str = "",
        generation_job_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EntityImage:
        """Factory with auto-timestamp and input validation."""
        errors: list[str] = []
        if not id.strip():
            errors.append("Image ID is required.")
        if not entity_type.strip():
            errors.append("Entity type is required.")
        if not entity_id.strip():
            errors.append("Entity ID is required.")
        if not filename.strip():
            errors.append("Filename is required.")
        if errors:
            raise ImageValidationError(errors)

        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id.strip(),
            entity_type=entity_type.strip(),
            entity_id=entity_id.strip(),
            filename=filename.strip(),
            original_filename=original_filename.strip() if original_filename else "",
            prompt=prompt,
            negative_prompt=negative_prompt,
            is_primary=is_primary,
            file_size=file_size,
            width=width,
            height=height,
            template_id=template_id.strip() if template_id else "",
            generation_job_id=generation_job_id.strip() if generation_job_id else "",
            created_at=now,
            metadata=metadata or {},
        )


# ─── Image Manager ───────────────────────────────────────────


class ImageManager:
    """Filesystem-backed image storage with per-entity metadata.

    Directory layout::

        {images_dir}/
            character/
                CH-0001/
                    images.json
                    img_0001.png
                    img_0002.png
                CH-0002/
                    images.json
                    img_0003.png
            location/
                LOC-0001/
                    images.json
                    img_0004.png

    The ``images.json`` file in each entity directory is a JSON array of
    :class:`EntityImage` dicts.  A global counter file at the images root
    tracks the next ``IMG-XXXX`` ID to assign.

    Usage::

        mgr = ImageManager()
        img = mgr.save_image(
            image_data=raw_bytes,
            entity_type="character",
            entity_id="CH-0001",
            original_filename="portrait.png",
            prompt="a noble knight",
        )
        print(img.id)             # "IMG-0001"
        print(img.is_primary)     # True (first image is auto-primary)
        path = mgr.get_image_path(img.id)
    """

    _ID_PREFIX = "IMG"
    _FILENAME_PREFIX = "img"
    _METADATA_FILE = "images.json"
    _COUNTER_FILE = ".next_id"
    _IMG_ID_PATTERN = re.compile(r"^IMG-(\d{4})$")
    _FILE_COUNTER_PATTERN = re.compile(r"^img_(\d{4})\.\w+$")

    def __init__(self, images_dir: Path | None = None) -> None:
        self._dir = images_dir or COMFYUI_IMAGES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ───────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Save Image ───────────────────────────────────────────

    def save_image(
        self,
        image_data: bytes,
        *,
        entity_type: str,
        entity_id: str,
        original_filename: str = "",
        prompt: str = "",
        negative_prompt: str = "",
        is_primary: bool | None = None,
        width: int = 0,
        height: int = 0,
        template_id: str = "",
        generation_job_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EntityImage:
        """Save an image to disk and create a metadata record.

        Args:
            image_data: Raw image bytes (PNG, JPEG, or WebP).
            entity_type: Type of entity (character, location, etc.).
            entity_id: Entity identifier (e.g. "CH-0001").
            original_filename: Original filename (used to detect extension).
            prompt: Generation prompt (if AI-generated).
            negative_prompt: Negative prompt (if AI-generated).
            is_primary: If None, auto-set to True for first image.
            width: Image width in pixels (0 = unknown).
            height: Image height in pixels (0 = unknown).
            template_id: ComfyUI template used (TPL-XXXX).
            generation_job_id: Generation job ID (GEN-XXXX).
            metadata: Additional metadata dict.

        Returns:
            The created EntityImage metadata record.

        Raises:
            ImageValidationError: If entity_type or entity_id is empty,
                or image_data is empty.
        """
        # ── Validate ──────────────────────────────────────────
        errors: list[str] = []
        if not entity_type.strip():
            errors.append("Entity type is required.")
        if not entity_id.strip():
            errors.append("Entity ID is required.")
        if not image_data:
            errors.append("Image data is required (empty bytes).")
        if errors:
            raise ImageValidationError(errors)

        entity_type = entity_type.strip()
        entity_id = entity_id.strip()

        # ── Ensure entity directory exists ────────────────────
        entity_dir = self._entity_dir(entity_type, entity_id)
        entity_dir.mkdir(parents=True, exist_ok=True)

        # ── Determine file extension ──────────────────────────
        ext = self._detect_extension(original_filename, image_data)

        # ── Generate sequential filename ─────────────────────
        filename = self._next_filename(entity_dir, ext)

        # ── Write image bytes to disk ────────────────────────
        image_path = entity_dir / filename
        image_path.write_bytes(image_data)

        # ── Load existing metadata ───────────────────────────
        existing = self._load_entity_metadata(entity_type, entity_id)

        # ── Auto-primary: first image becomes primary ────────
        if is_primary is None:
            is_primary = len(existing) == 0

        # ── If marking as primary, clear others ──────────────
        if is_primary:
            existing = self._clear_primary(existing)

        # ── Create EntityImage record ────────────────────────
        image_id = self._next_id()
        image = EntityImage.create(
            id=image_id,
            entity_type=entity_type,
            entity_id=entity_id,
            filename=filename,
            original_filename=original_filename.strip() if original_filename else "",
            prompt=prompt,
            negative_prompt=negative_prompt,
            is_primary=is_primary,
            file_size=len(image_data),
            width=width,
            height=height,
            template_id=template_id,
            generation_job_id=generation_job_id,
            metadata=metadata,
        )

        # ── Append to metadata and save ──────────────────────
        existing.append(image)
        self._save_entity_metadata(entity_type, entity_id, existing)
        return image

    # ── Get Image ────────────────────────────────────────────

    def get(self, image_id: str) -> EntityImage:
        """Retrieve a single image's metadata by its global ID.

        This scans all entity directories to find the image.

        Raises:
            ImageNotFoundError: If the image ID does not exist.
        """
        for entity_type_dir in self._dir.iterdir():
            if not entity_type_dir.is_dir():
                continue
            for entity_dir in entity_type_dir.iterdir():
                if not entity_dir.is_dir():
                    continue
                meta_path = entity_dir / self._METADATA_FILE
                if not meta_path.exists():
                    continue
                images = self._load_entity_metadata(
                    entity_type_dir.name, entity_dir.name,
                )
                for img in images:
                    if img.id == image_id:
                        return img
        raise ImageNotFoundError(image_id)

    # ── List Images ──────────────────────────────────────────

    def list_images(
        self,
        entity_type: str,
        entity_id: str,
        *,
        primary_only: bool = False,
    ) -> list[EntityImage]:
        """List all images for a specific entity.

        Args:
            entity_type: Type of entity (character, location, etc.).
            entity_id: Entity identifier (e.g. "CH-0001").
            primary_only: If True, return only the primary image(s).

        Returns:
            List of EntityImage records, sorted by creation time.
        """
        images = self._load_entity_metadata(entity_type, entity_id)
        if primary_only:
            images = [img for img in images if img.is_primary]
        return images

    # ── Get Primary Image ────────────────────────────────────

    def get_primary_image(
        self, entity_type: str, entity_id: str,
    ) -> EntityImage | None:
        """Get the primary image for an entity, or None if none set."""
        images = self.list_images(entity_type, entity_id, primary_only=True)
        return images[0] if images else None

    # ── Set Primary ──────────────────────────────────────────

    def set_primary(self, image_id: str) -> EntityImage:
        """Designate an image as the primary image for its entity.

        Clears the primary flag from all other images of the same entity.

        Returns:
            The updated EntityImage record.

        Raises:
            ImageNotFoundError: If the image ID does not exist.
        """
        # Find the image by scanning
        target = self.get(image_id)  # raises ImageNotFoundError

        # Load all images for this entity
        images = self._load_entity_metadata(target.entity_type, target.entity_id)

        # Clear primary, then set the target
        updated: list[EntityImage] = []
        result: EntityImage | None = None
        for img in images:
            if img.id == image_id:
                new_img = EntityImage.from_dict({**img.to_dict(), "is_primary": True})
                updated.append(new_img)
                result = new_img
            else:
                new_img = EntityImage.from_dict({**img.to_dict(), "is_primary": False})
                updated.append(new_img)

        self._save_entity_metadata(target.entity_type, target.entity_id, updated)
        assert result is not None
        return result

    # ── Delete Image ─────────────────────────────────────────

    def delete(self, image_id: str) -> None:
        """Delete an image file and its metadata record.

        If the deleted image was primary, the next image (if any)
        is automatically promoted to primary.

        Raises:
            ImageNotFoundError: If the image ID does not exist.
        """
        target = self.get(image_id)  # raises ImageNotFoundError

        # Remove the file from disk
        image_path = self._entity_dir(target.entity_type, target.entity_id) / target.filename
        if image_path.exists():
            image_path.unlink()

        # Update metadata
        images = self._load_entity_metadata(target.entity_type, target.entity_id)
        was_primary = target.is_primary
        images = [img for img in images if img.id != image_id]

        # Auto-promote if the deleted image was primary
        if was_primary and images:
            first = images[0]
            images[0] = EntityImage.from_dict({**first.to_dict(), "is_primary": True})

        self._save_entity_metadata(target.entity_type, target.entity_id, images)

    # ── Get Image Path ───────────────────────────────────────

    def get_image_path(self, image_id: str) -> Path:
        """Get the filesystem path for an image.

        Returns:
            The absolute Path to the image file.

        Raises:
            ImageNotFoundError: If the image ID does not exist.
        """
        img = self.get(image_id)  # raises ImageNotFoundError
        return self._entity_dir(img.entity_type, img.entity_id) / img.filename

    # ── Count Images ─────────────────────────────────────────

    def count_images(self, entity_type: str, entity_id: str) -> int:
        """Return the number of images for an entity."""
        return len(self._load_entity_metadata(entity_type, entity_id))

    # ── Delete All Entity Images ─────────────────────────────

    def delete_entity_images(self, entity_type: str, entity_id: str) -> int:
        """Delete all images for an entity.

        Returns:
            The number of images deleted.
        """
        images = self._load_entity_metadata(entity_type, entity_id)
        count = len(images)
        if count == 0:
            return 0

        entity_dir = self._entity_dir(entity_type, entity_id)
        if entity_dir.exists():
            shutil.rmtree(entity_dir)
        return count

    # ── Internal: Entity Directory ───────────────────────────

    def _entity_dir(self, entity_type: str, entity_id: str) -> Path:
        """Build the path for an entity's image directory."""
        return self._dir / entity_type / entity_id

    # ── Internal: Sequential IDs ─────────────────────────────

    def _next_id(self) -> str:
        """Generate the next sequential ``IMG-XXXX`` ID.

        Uses a counter file at the images root to track the sequence.
        Falls back to scanning all metadata files if the counter is
        missing or inconsistent.
        """
        counter_path = self._dir / self._COUNTER_FILE
        next_num = 1

        if counter_path.exists():
            try:
                next_num = int(counter_path.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                next_num = self._scan_max_id() + 1
        else:
            next_num = self._scan_max_id() + 1

        image_id = f"{self._ID_PREFIX}-{next_num:04d}"
        atomic_write(counter_path, str(next_num + 1))
        return image_id

    def _scan_max_id(self) -> int:
        """Scan all metadata files to find the highest IMG-XXXX number."""
        max_num = 0
        for entity_type_dir in self._dir.iterdir():
            if not entity_type_dir.is_dir() or entity_type_dir.name.startswith("."):
                continue
            for entity_dir in entity_type_dir.iterdir():
                if not entity_dir.is_dir():
                    continue
                meta_path = entity_dir / self._METADATA_FILE
                if not meta_path.exists():
                    continue
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    for entry in data:
                        match = self._IMG_ID_PATTERN.match(entry.get("id", ""))
                        if match:
                            max_num = max(max_num, int(match.group(1)))
                except (json.JSONDecodeError, KeyError, OSError):
                    continue
        return max_num

    # ── Internal: Sequential Filenames ───────────────────────

    def _next_filename(self, entity_dir: Path, extension: str) -> str:
        """Generate the next sequential ``img_XXXX.ext`` filename."""
        max_num = 0
        for f in entity_dir.iterdir():
            match = self._FILE_COUNTER_PATTERN.match(f.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        next_num = max_num + 1
        return f"{self._FILENAME_PREFIX}_{next_num:04d}{extension}"

    # ── Internal: File Extension Detection ───────────────────

    @staticmethod
    def _detect_extension(
        original_filename: str, image_data: bytes,
    ) -> str:
        """Detect image extension from filename or magic bytes."""
        # Try from original filename first
        if original_filename:
            ext = Path(original_filename).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                return ext

        # Fall back to magic bytes
        if image_data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if image_data[:2] == b"\xff\xd8":
            return ".jpg"
        if image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
            return ".webp"

        # Default to PNG
        return ".png"

    # ── Internal: Metadata Read/Write ────────────────────────

    def _load_entity_metadata(
        self, entity_type: str, entity_id: str,
    ) -> list[EntityImage]:
        """Load the images.json metadata for a specific entity."""
        meta_path = self._entity_dir(entity_type, entity_id) / self._METADATA_FILE
        if not meta_path.exists():
            return []
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return [EntityImage.from_dict(entry) for entry in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_entity_metadata(
        self,
        entity_type: str,
        entity_id: str,
        images: list[EntityImage],
    ) -> None:
        """Write the images.json metadata for a specific entity."""
        entity_dir = self._entity_dir(entity_type, entity_id)
        entity_dir.mkdir(parents=True, exist_ok=True)
        meta_path = entity_dir / self._METADATA_FILE
        content = json.dumps(
            [img.to_dict() for img in images],
            indent=2,
            ensure_ascii=False,
        )
        atomic_write(meta_path, content)

    # ── Internal: Clear Primary Flag ─────────────────────────

    @staticmethod
    def _clear_primary(images: list[EntityImage]) -> list[EntityImage]:
        """Return a copy of the list with all is_primary flags cleared."""
        return [
            EntityImage.from_dict({**img.to_dict(), "is_primary": False})
            if img.is_primary else img
            for img in images
        ]

    # ── Repr ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"ImageManager(dir={str(self._dir)!r})"
