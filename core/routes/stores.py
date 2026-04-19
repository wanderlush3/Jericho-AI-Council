"""
Jericho — Stores Routes
"""

from __future__ import annotations

import logging


from typing import Any

from fastapi import APIRouter, HTTPException, Query


log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/stores")
def api_stores_list(
    status: str | None = Query(None),
    author: str | None = Query(None),
    tag: str | None = Query(None),
    store_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List stores with optional filters."""
    from core.stores import StoreManager
    from core.image_manager import ImageManager
    from config.settings import STORE_INJECTION_MAX_LENGTH
    mgr = StoreManager()
    imgr = ImageManager()
    results = mgr.list_stores(
        status=status, author=author, tag=tag, store_type=store_type,
    )
    out = []
    for store in results:
        d = store.to_dict()
        d["injection_max_length"] = STORE_INJECTION_MAX_LENGTH
        # Attach primary image URL if available
        primary_url = ""
        try:
            images = imgr.list_images("store", store.id)
            primary = next(
                (img for img in images if img.is_primary), None,
            )
            if primary:
                primary_url = f"/api/images/file/{primary.id}"
            elif images:
                primary_url = f"/api/images/file/{images[0].id}"
        except Exception:
            log.debug("Stores: failed to load primary image for %s", store.id, exc_info=True)
        d["primary_image_url"] = primary_url
        out.append(d)
    return out

@router.get("/api/stores/{store_id}")
def api_store_detail(store_id: str) -> dict[str, Any]:
    """Get a single store with full inventory."""
    from core.stores import StoreManager, StoreNotFoundError
    from config.settings import STORE_INJECTION_MAX_LENGTH
    mgr = StoreManager()
    try:
        store = mgr.get(store_id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    d = store.to_dict()
    d["injection_max_length"] = STORE_INJECTION_MAX_LENGTH
    return d

@router.post("/api/stores")
def api_store_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new store.

    Body: {"name": "...", "description": "...", "author": "...",
           "store_type": "blacksmith", "location_id": "", "owner": "",
           "tags": [...], "lore": "..."}
    """
    from core.stores import StoreManager, StoreValidationError

    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    author = (body.get("author") or "").strip()

    if not name or not description or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'name', 'description', and 'author' are required.",
        )

    # F-071: Disgraced entities cannot open stores
    from core.reputation_effects import can_open_stores, get_entity_tier
    author_tier = get_entity_tier(f"member:{author}")
    if not can_open_stores(author_tier):
        raise HTTPException(
            status_code=403,
            detail=f"Author '{author}' has a 'disgraced' reputation and cannot create stores. "
                   f"Improve reputation through positive actions first.",
        )

    mgr = StoreManager()
    try:
        store = mgr.create(
            name, description,
            author=author,
            store_type=(body.get("store_type") or "general").strip(),
            location_id=(body.get("location_id") or "").strip(),
            owner=(body.get("owner") or "").strip(),
            tags=body.get("tags") or [],
            lore=(body.get("lore") or "").strip(),
            llm_injection=(body.get("llm_injection") or "").strip(),
        )
    except StoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return store.to_dict()

@router.put("/api/stores/{store_id}")
def api_store_update(store_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update mutable fields on a store.

    Body may contain: name, description, lore, tags, metadata,
    location_id, owner, store_type.
    """
    from core.stores import StoreManager, StoreNotFoundError, StoreValidationError
    mgr = StoreManager()
    try:
        store = mgr.update(store_id, **body)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except StoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store.to_dict()

@router.post("/api/stores/{store_id}/status")
def api_store_status(
    store_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Transition a store's lifecycle status.

    Body: {"status": "active"}
    """
    from core.stores import (
        StoreManager, StoreNotFoundError,
        StoreValidationError, StoreLifecycleError,
    )

    new_status = (body.get("status") or "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="'status' is required.")

    mgr = StoreManager()
    try:
        store = mgr.update_status(store_id, new_status)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except (StoreValidationError, StoreLifecycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store.to_dict()

@router.post("/api/stores/{store_id}/inventory")
def api_store_add_inventory(
    store_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Add an item to a store's inventory.

    Body: {"item_id": "ITEM-0001", "price_gold": 10,
           "price_silver": 0, "price_bronze": 0, "quantity": -1}
    """
    from core.stores import (
        StoreManager, StoreNotFoundError,
        StoreValidationError, StoreItem,
    )

    item_id = (body.get("item_id") or "").strip()
    if not item_id:
        raise HTTPException(
            status_code=400, detail="'item_id' is required.",
        )

    mgr = StoreManager()
    try:
        si = StoreItem.create(
            item_id,
            price_gold=int(body.get("price_gold", 0)),
            price_silver=int(body.get("price_silver", 0)),
            price_bronze=int(body.get("price_bronze", 0)),
            quantity=int(body.get("quantity", -1)),
        )
        store = mgr.add_inventory_item(store_id, si)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except StoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store.to_dict()

@router.delete("/api/stores/{store_id}/inventory/{item_id}")
def api_store_remove_inventory(
    store_id: str, item_id: str,
) -> dict[str, Any]:
    """Remove an item from a store's inventory."""
    from core.stores import StoreManager, StoreNotFoundError, StoreValidationError

    mgr = StoreManager()
    try:
        store = mgr.remove_inventory_item(store_id, item_id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except StoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store.to_dict()

@router.put("/api/stores/{store_id}/inventory/{item_id}")
def api_store_update_inventory(
    store_id: str, item_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Update price/quantity of an inventory entry.

    Body may contain: price_gold, price_silver, price_bronze, quantity.
    """
    from core.stores import StoreManager, StoreNotFoundError, StoreValidationError

    mgr = StoreManager()
    try:
        store = mgr.update_inventory_item(store_id, item_id, **body)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except StoreValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store.to_dict()

@router.post("/api/stores/{store_id}/purchase")
def api_store_purchase(
    store_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Purchase an item from a store.

    Body: {"item_id": "ITEM-0001", "buyer_account_id": "ACCT-user-human",
           "buyer_entity_id": "member:Human"}  // optional, for reputation price

    Debits the buyer's treasury account and credits the store owner.
    Decrements quantity if not unlimited.
    F-071: Applies reputation-based price modifier to the buyer's cost.
    """
    from core.stores import (
        StoreManager, StoreNotFoundError, StorePurchaseError,
    )
    from core.treasury import TreasuryManager

    item_id = (body.get("item_id") or "").strip()
    buyer_account_id = (body.get("buyer_account_id") or "").strip()
    buyer_entity_id = (body.get("buyer_entity_id") or "").strip()

    if not item_id or not buyer_account_id:
        raise HTTPException(
            status_code=400,
            detail="'item_id' and 'buyer_account_id' are required.",
        )

    # F-071: Look up buyer's reputation tier for price adjustment
    price_modifier = 1.0
    buyer_tier = "neutral"
    if buyer_entity_id:
        from core.reputation_effects import get_entity_tier, get_price_modifier
        buyer_tier = get_entity_tier(buyer_entity_id)
        price_modifier = get_price_modifier(buyer_tier)

    mgr = StoreManager()
    tmgr = TreasuryManager()
    try:
        result = mgr.purchase(
            store_id, item_id, buyer_account_id, tmgr,
            price_modifier=price_modifier,
        )
    except StoreNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Store '{store_id}' not found.",
        )
    except StorePurchaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # F-071: Include reputation price modifier info in response
    result["reputation_price_modifier"] = round(price_modifier, 2)
    result["buyer_reputation_tier"] = buyer_tier
    return result


# ── Analytics ─────────────────────────────────────────────

