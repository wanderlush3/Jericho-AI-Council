"""
Jericho — Items Routes
"""

from __future__ import annotations

import logging


from typing import Any

from fastapi import APIRouter, HTTPException, Query


log = logging.getLogger(__name__)

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
            log.debug("Failed to load item details for enrichment", exc_info=True)
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
            owned_by=body.get("owned_by", []),
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

@router.put("/api/items/{item_id}/owned-by")
def api_item_set_owned_by(
    item_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Set the full owned_by list on an item.

    Body: {"owned_by": [{"name": "...", "type": "user|character|council_member"}]}
    """
    from core.items import ItemManager, ItemNotFoundError, ItemValidationError
    mgr = ItemManager()
    owned_by = body.get("owned_by", [])
    try:
        item = mgr.update(item_id, owned_by=owned_by)
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Item '{item_id}' not found.",
        )
    except ItemValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item.to_dict()

@router.post("/api/items/{item_id}/gift")
def api_item_gift(item_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Gift an item from one owner to another.

    Body: {
        "from_owner": {"name": "...", "type": "user|character|council_member"},
        "to_owner": {"name": "...", "type": "user|character|council_member"},
        "message": "optional gift message"
    }

    Creates a closed chat record acknowledging the gift.
    """
    from core.items import (
        ItemManager, ItemNotFoundError, ItemValidationError, GiftRecord,
    )

    from_owner = body.get("from_owner")
    to_owner = body.get("to_owner")
    message = body.get("message", "").strip()

    if not from_owner or not isinstance(from_owner, dict):
        raise HTTPException(
            status_code=400,
            detail="'from_owner' is required and must be an object with 'name' and 'type'.",
        )
    if not to_owner or not isinstance(to_owner, dict):
        raise HTTPException(
            status_code=400,
            detail="'to_owner' is required and must be an object with 'name' and 'type'.",
        )

    mgr = ItemManager()
    try:
        gift = mgr.gift_item(
            item_id,
            from_owner=from_owner,
            to_owner=to_owner,
            message=message,
        )
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Item '{item_id}' not found.",
        )
    except ItemValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # F-070: Record reputation events for gift giver and receiver
    from core.reputation_hooks import on_gift_given
    on_gift_given(gift)

    # Create a closed chat record acknowledging the gift
    chat_record = _create_gift_chat(gift)

    # Reload item for response
    updated_item = mgr.get(item_id)

    return {
        "item": updated_item.to_dict(),
        "gift": gift.to_dict(),
        "chat_id": chat_record.get("chat_id", ""),
    }


def _create_gift_chat(gift: "GiftRecord") -> dict[str, Any]:
    """Create a closed system chat record acknowledging a gift.

    This writes a lightweight conversation to disk using the existing
    HumanChat JSON format — no AI calls are made.
    """
    import json as json_mod
    from datetime import datetime, timezone
    from config.settings import CONVERSATIONS_DIR

    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate chat ID
    existing = sorted(CONVERSATIONS_DIR.glob("H-GIFT-*.json"))
    if not existing:
        chat_num = 1
    else:
        last = existing[-1].stem  # e.g. "H-GIFT-0042"
        chat_num = int(last.split("-")[-1]) + 1
    chat_id = f"GIFT-{chat_num:04d}"

    from_name = gift.from_owner.get("name", "Unknown")
    to_name = gift.to_owner.get("name", "Unknown")
    now = datetime.now(timezone.utc).isoformat()

    gift_msg = gift.message or f"I'd like you to have this."
    accept_msg = f"Thank you for the {gift.item_name}!"

    record = {
        "chat_id": chat_id,
        "title": f"🎁 Gift: {gift.item_name}",
        "member_name": "",
        "topic": f"Gift of {gift.item_name} from {from_name} to {to_name}",
        "messages": [
            {
                "role": "agent",
                "speaker": from_name,
                "content": f"🎁 *gifts {gift.item_name}*\n\n{gift_msg}",
                "timestamp": now,
                "metadata": {"gift": True, "item_id": gift.item_id},
            },
            {
                "role": "agent",
                "speaker": to_name,
                "content": accept_msg,
                "timestamp": now,
                "metadata": {"gift_response": True, "item_id": gift.item_id},
            },
        ],
        "summary": f"{from_name} gifted {gift.item_name} to {to_name}.",
        "created_at": now,
        "closed_at": now,
        "metadata": {
            "gift": True,
            "item_id": gift.item_id,
            "from_owner": gift.from_owner,
            "to_owner": gift.to_owner,
        },
        "council_members": [],
        "characters": [],
        "paused": False,
    }

    path = CONVERSATIONS_DIR / f"H-{chat_id}.json"
    from core.utils import atomic_write
    atomic_write(path, json_mod.dumps(record, indent=2, ensure_ascii=False) + "\n")

    return record


# ── Stores ─────────────────────────────────────────────────

