"""
Jericho — Locations Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/locations")
def api_locations_list(
    status: str | None = Query(None),
    author: str | None = Query(None),
    tag: str | None = Query(None),
    parent_location_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List locations with optional filters."""
    from core.locations import LocationManager
    from core.image_manager import ImageManager
    mgr = LocationManager()
    imgr = ImageManager()
    items = mgr.list_locations(
        status=status, author=author, tag=tag,
        parent_location_id=parent_location_id,
    )
    result = []
    for loc in items:
        d = loc.to_dict()
        # Attach primary image URL if available
        primary_url = ""
        try:
            images = imgr.list_images("location", loc.id)
            primary = next(
                (img for img in images if img.is_primary), None,
            )
            if primary:
                primary_url = f"/api/images/file/{primary.id}"
            elif images:
                primary_url = f"/api/images/file/{images[0].id}"
        except Exception:
            pass
        d["primary_image_url"] = primary_url
        result.append(d)
    return result

@router.get("/api/locations/{location_id}")
def api_location_detail(location_id: str) -> dict[str, Any]:
    """Get a single location."""
    from core.locations import LocationManager, LocationNotFoundError
    mgr = LocationManager()
    try:
        loc = mgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )
    return loc.to_dict()

@router.post("/api/locations")
def api_location_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new location.

    Body: {"name": "...", "description": "...", "author": "...",
           "lore": "...", "features": [...], "tags": [...],
           "parent_location_id": "...", "coordinates": "..."}
    """
    from core.locations import (
        LocationManager, LocationValidationError, LocationFeature,
    )

    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    author = body.get("author", "").strip()
    lore = body.get("lore", "").strip()
    raw_features = body.get("features", [])
    tags = body.get("tags", [])
    parent = body.get("parent_location_id", "")
    coords = body.get("coordinates", "")

    if not name or not description or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'name', 'description', and 'author' are required.",
        )

    # Parse features
    features = []
    for f in raw_features:
        try:
            features.append(LocationFeature.create(
                name=f.get("name", ""),
                description=f.get("description", ""),
                feature_type=f.get("feature_type", "custom"),
            ))
        except LocationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    mgr = LocationManager()
    try:
        loc = mgr.create(
            name, description, author=author, lore=lore,
            features=features, tags=tags,
            parent_location_id=parent, coordinates=coords,
        )
    except LocationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return loc.to_dict()

@router.put("/api/locations/{location_id}")
def api_location_update(location_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update mutable fields on a location.

    Body may contain: name, description, lore, tags, metadata,
    parent_location_id, coordinates.
    """
    from core.locations import LocationManager, LocationNotFoundError, LocationValidationError
    mgr = LocationManager()
    try:
        loc = mgr.update(location_id, **body)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )
    except LocationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return loc.to_dict()

@router.put("/api/locations/{location_id}/status")
def api_location_status(
    location_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Transition a location's lifecycle status.

    Body: {"status": "active"}
    """
    from core.locations import (
        LocationManager, LocationNotFoundError,
        LocationValidationError, LocationLifecycleError,
    )

    new_status = body.get("status", "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="'status' is required.")

    mgr = LocationManager()
    try:
        loc = mgr.update_status(location_id, new_status)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )
    except (LocationValidationError, LocationLifecycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return loc.to_dict()

# ── Items ─────────────────────────────────────────────────

