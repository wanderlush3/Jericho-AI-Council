"""
Jericho — Laws Routes
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Query



log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/laws")
def api_laws_list(
    status: str | None = Query(None),
    author: str | None = Query(None),
    tag: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List laws with optional filters."""
    from core.laws import LawManager
    mgr = LawManager()
    items = mgr.list_laws(status=status, author=author, tag=tag)
    return [law.to_dict() for law in items]

@router.get("/api/laws/{law_id}")
def api_law_detail(law_id: str) -> dict[str, Any]:
    """Get a single law."""
    from core.laws import LawManager, LawNotFoundError
    mgr = LawManager()
    try:
        law = mgr.get(law_id)
    except LawNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Law '{law_id}' not found.",
        )
    return law.to_dict()

@router.post("/api/laws")
def api_law_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new law.

    Body: {"title": "...", "description": "...", "author": "...",
           "body": "...", "tags": [...]}
    """
    from core.laws import LawManager, LawValidationError

    title = body.get("title", "").strip()
    description = body.get("description", "").strip()
    author = body.get("author", "").strip()
    law_body = body.get("body", "").strip()
    tags = body.get("tags", [])

    if not title or not description or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'title', 'description', and 'author' are required.",
        )

    mgr = LawManager()
    try:
        law = mgr.create(
            title, description, author=author,
            body=law_body, tags=tags or None,
        )
    except LawValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return law.to_dict()

@router.put("/api/laws/{law_id}")
def api_law_update(law_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update mutable fields on a law.

    Body may contain: title, description, body, tags, metadata.
    """
    from core.laws import LawManager, LawNotFoundError, LawValidationError

    mgr = LawManager()
    try:
        updated = mgr.update(law_id, **body)
    except LawNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Law '{law_id}' not found.",
        )
    except LawValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return updated.to_dict()

@router.put("/api/laws/{law_id}/status")
def api_law_status(law_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Transition a law to a new status.

    Body: {"status": "active"} or {"status": "archived"}
    Automatically syncs the Law Shared Memory.
    """
    from core.laws import (
        LawManager, LawNotFoundError,
        LawLifecycleError, LawValidationError,
    )
    from core.memory import LawSharedMemory

    new_status = body.get("status", "").strip()
    if not new_status:
        raise HTTPException(
            status_code=400, detail="'status' is required.",
        )

    mgr = LawManager()
    try:
        updated = mgr.update_status(law_id, new_status)
    except LawNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Law '{law_id}' not found.",
        )
    except (LawLifecycleError, LawValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Sync law shared memory whenever status changes
    _sync_law_shared_memory(mgr)

    return updated.to_dict()

def _sync_law_shared_memory(mgr=None):
    """Helper to sync active laws into LawSharedMemory."""
    from core.laws import LawManager
    from core.memory import LawSharedMemory

    if mgr is None:
        mgr = LawManager()
    active_laws = mgr.list_laws(status="active")
    lsm = LawSharedMemory()
    lsm.sync_active_laws([law.to_dict() for law in active_laws])

# ── Evolutions ────────────────────────────────────────────

