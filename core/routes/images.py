"""
Jericho — Images Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter()

@router.get("/api/images/file/{image_id}")
def api_images_serve(image_id: str):
    """Serve raw image bytes for display in <img> tags."""
    from core.image_manager import ImageManager, ImageNotFoundError

    mgr = ImageManager()
    try:
        path = mgr.get_image_path(image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing from disk.")

    # Determine media type from extension
    ext = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/png")
    return FileResponse(str(path), media_type=media_type)

@router.get("/api/images/info/{image_id}")
def api_images_info(image_id: str) -> dict[str, Any]:
    """Get full image metadata including prompt and generation info."""
    from core.image_manager import ImageManager, ImageNotFoundError

    mgr = ImageManager()
    try:
        img = mgr.get(image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
    d = img.to_dict()
    d["url"] = f"/api/images/file/{img.id}"
    return d

@router.post("/api/images/set-primary/{image_id}")
def api_images_set_primary(image_id: str) -> dict[str, Any]:
    """Set an image as the primary image for its entity."""
    from core.image_manager import ImageManager, ImageNotFoundError

    mgr = ImageManager()
    try:
        img = mgr.set_primary(image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
    d = img.to_dict()
    d["url"] = f"/api/images/file/{img.id}"
    return d

@router.delete("/api/images/delete/{image_id}")
def api_images_delete(image_id: str) -> dict[str, Any]:
    """Delete an image and its file from disk."""
    from core.image_manager import ImageManager, ImageNotFoundError

    mgr = ImageManager()
    try:
        mgr.delete(image_id)
    except ImageNotFoundError:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
    return {"deleted": True, "image_id": image_id}

@router.get("/api/images/{entity_type}/{entity_id}")
def api_images_list(entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    """List all images for an entity.

    Returns image metadata records sorted by creation time.
    Each record includes a ``url`` field for use in <img> tags.
    """
    from core.image_manager import ImageManager, VALID_ENTITY_TYPES

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. "
                   f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    mgr = ImageManager()
    images = mgr.list_images(entity_type, entity_id)
    result = []
    for img in images:
        d = img.to_dict()
        d["url"] = f"/api/images/file/{img.id}"
        result.append(d)
    return result

@router.post("/api/images/{entity_type}/{entity_id}")
def api_images_upload(
    entity_type: str, entity_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Upload a new image for an entity.

    Body: {
        "image_data": "data:image/png;base64,...",
        "original_filename": "portrait.png",   // optional
        "prompt": "a noble knight",             // optional
        "negative_prompt": "blurry",            // optional
        "is_primary": null,                     // optional, null = auto
        "template_id": "TPL-0001",              // optional
    }
    """
    import base64
    from core.image_manager import (
        ImageManager, ImageValidationError, VALID_ENTITY_TYPES,
    )

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. "
                   f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    image_data_str = body.get("image_data", "")
    if not image_data_str:
        raise HTTPException(status_code=400, detail="'image_data' is required.")

    # Parse base64 data URL
    try:
        if "," in image_data_str:
            image_data_str = image_data_str.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_data_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data.")

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Image data is empty.")

    original_filename = (body.get("original_filename") or "").strip()
    prompt = body.get("prompt", "")
    negative_prompt = body.get("negative_prompt", "")
    is_primary = body.get("is_primary")  # None = auto
    template_id = (body.get("template_id") or "").strip()

    mgr = ImageManager()
    try:
        img = mgr.save_image(
            raw_bytes,
            entity_type=entity_type,
            entity_id=entity_id,
            original_filename=original_filename,
            prompt=prompt,
            negative_prompt=negative_prompt,
            is_primary=is_primary,
            template_id=template_id,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    d = img.to_dict()
    d["url"] = f"/api/images/file/{img.id}"
    return d
