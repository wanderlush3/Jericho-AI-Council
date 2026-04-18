"""
Jericho — Reputation API Routes (F-069)

Endpoints for viewing and managing entity reputation scores.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.manager_cache import get_reputation_manager, invalidate_reputation_manager
from core.reputation import (
    REPUTATION_EVENT_TYPES,
    ReputationValidationError,
)
from config.settings import DEFAULT_REPUTATION_STANCES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reputation", tags=["reputation"])


# ─── Request Models ───────────────────────────────────────────


class RecordEventRequest(BaseModel):
    """Body for POST /api/reputation/{entity_id}/events."""

    event_type: str = "custom"
    points: int | None = None
    reason: str = ""
    source_id: str = ""


# ─── Endpoints ────────────────────────────────────────────────


@router.get("")
def list_reputation() -> list[dict[str, Any]]:
    """Return reputation leaderboard — all entities sorted by decayed score."""
    mgr = get_reputation_manager()
    board = mgr.get_leaderboard()
    return [s.to_dict() for s in board]


@router.get("/stances")
def get_default_stances() -> dict[str, str]:
    """Return the configured default reputation stances."""
    return dict(DEFAULT_REPUTATION_STANCES)


@router.get("/{entity_id:path}/events")
def get_entity_events(entity_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return event history for a specific entity, most recent first."""
    mgr = get_reputation_manager()
    events = mgr.get_events(entity_id, limit=limit)
    return [e.to_dict() for e in events]


@router.get("/{entity_id:path}")
def get_entity_reputation(entity_id: str) -> dict[str, Any]:
    """Return reputation score + tier for a specific entity."""
    mgr = get_reputation_manager()
    score = mgr.get_score(entity_id)
    return score.to_dict()


@router.post("/{entity_id:path}/events")
def record_event(entity_id: str, body: RecordEventRequest) -> dict[str, Any]:
    """Record a manual reputation event for an entity."""
    mgr = get_reputation_manager()
    try:
        event = mgr.record_event(
            entity_id,
            body.event_type,
            points=body.points,
            reason=body.reason,
            source_id=body.source_id,
        )
    except ReputationValidationError as exc:
        raise HTTPException(status_code=400, detail="; ".join(exc.errors))

    return {
        "event": event.to_dict(),
        "score": mgr.get_score(entity_id).to_dict(),
    }
