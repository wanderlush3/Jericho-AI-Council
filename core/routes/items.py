"""
Jericho — Items Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/items")
def api_items_list(
    status: str | None = Query(None),
    author: str | None = Query(None),
    tag: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List items with optional filters."""
    from core.items import ItemManager, is_injection_active
    from core.image_manager import ImageManager
    from config.settings import ITEM_INJECTION_MAX_LENGTH
    mgr = ItemManager()
    imgr = ImageManager()
    results = mgr.list_items(status=status, author=author, tag=tag)
    out = []
    for item in results:
        d = item.to_dict()
        d["injection_active"] = is_injection_active(item)
        d["injection_max_length"] = ITEM_INJECTION_MAX_LENGTH
        # Attach primary image URL if available
        primary_url = ""
        try:
            images = imgr.list_images("item", item.id)
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
        out.append(d)
    return out

@router.get("/api/items/{item_id}")
def api_item_detail(item_id: str) -> dict[str, Any]:
    """Get a single item."""
    from core.items import ItemManager, ItemNotFoundError, is_injection_active
    from config.settings import ITEM_INJECTION_MAX_LENGTH
    mgr = ItemManager()
    try:
        item = mgr.get(item_id)
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Item '{item_id}' not found.",
        )
    d = item.to_dict()
    d["injection_active"] = is_injection_active(item)
    d["injection_max_length"] = ITEM_INJECTION_MAX_LENGTH
    return d

@router.post("/api/items")
def api_item_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new item.

    Body: {"name": "...", "description": "...", "author": "...",
           "lore": "...", "properties": [...], "tags": [...],
           "rarity": "...", "tier": "..."}
    """
    from core.items import (
        ItemManager, ItemValidationError, ItemProperty,
    )

    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    author = body.get("author", "").strip()
    lore = body.get("lore", "").strip()
    raw_properties = body.get("properties", [])
    tags = body.get("tags", [])
    rarity = body.get("rarity", "").strip()
    tier = body.get("tier", "").strip()
    legality = body.get("legality", "").strip()

    if not name or not description or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'name', 'description', and 'author' are required.",
        )

    # Parse properties
    properties = []
    for p in raw_properties:
        try:
            properties.append(ItemProperty.create(
                name=p.get("name", ""),
                description=p.get("description", ""),
                property_type=p.get("property_type", "custom"),
            ))
        except ItemValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    mgr = ItemManager()
    try:
        item = mgr.create(
            name, description, author=author, lore=lore,
            properties=properties, tags=tags, rarity=rarity,
            tier=tier, legality=legality,
            llm_injection=body.get("llm_injection", "").strip(),
        )
    except ItemValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return item.to_dict()

@router.put("/api/items/{item_id}")
def api_item_update(item_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update mutable fields on an item.

    Body may contain: name, description, lore, tags, metadata, rarity.
    """
    from core.items import ItemManager, ItemNotFoundError, ItemValidationError
    mgr = ItemManager()
    try:
        item = mgr.update(item_id, **body)
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Item '{item_id}' not found.",
        )
    except ItemValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()

@router.put("/api/items/{item_id}/status")
def api_item_status(
    item_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Transition an item's lifecycle status.

    Body: {"status": "active"}
    """
    from core.items import (
        ItemManager, ItemNotFoundError,
        ItemValidationError, ItemLifecycleError,
    )

    new_status = body.get("status", "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="'status' is required.")

    mgr = ItemManager()
    try:
        item = mgr.update_status(item_id, new_status)
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Item '{item_id}' not found.",
        )
    except (ItemValidationError, ItemLifecycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()

# ── Stores ─────────────────────────────────────────────────

