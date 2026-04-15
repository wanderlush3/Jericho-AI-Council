"""
Jericho — Votes Routes
"""

from __future__ import annotations

import logging


from typing import Any

from fastapi import APIRouter, HTTPException, Query


log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/votes")
def api_votes_list(
    status: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List vote records with optional status filter."""
    from core.voting import VotingEngine
    engine = VotingEngine()
    records = engine.list_records(status=status)
    result = []
    for r in records:
        rec_dict = r.to_dict()
        try:
            tally = engine.tally(r.proposal_id)
            rec_dict["tally"] = tally.to_dict()
        except Exception:
            log.debug("Votes: failed to tally %s", r.proposal_id, exc_info=True)
            rec_dict["tally"] = None
        result.append(rec_dict)
    return result

@router.get("/api/votes/{proposal_id}")
def api_vote_detail(proposal_id: str) -> dict[str, Any]:
    """Get vote record and tally for a proposal."""
    from core.voting import VotingEngine, VoteNotFoundError
    engine = VotingEngine()
    try:
        record = engine.get(proposal_id)
        tally = engine.tally(proposal_id)
    except VoteNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No vote record for proposal '{proposal_id}'.",
        )
    result = record.to_dict()
    result["tally"] = tally.to_dict()
    return result

@router.post("/api/votes/{proposal_id}/veto")
def api_vote_veto(
    proposal_id: str, body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a human veto to a proposal's vote.

    Body (optional): {"reason": "..."}
    """
    from core.voting import (
        VotingEngine, VoteNotFoundError, VotingStateError,
    )
    engine = VotingEngine()
    reason = ""
    if body:
        reason = body.get("reason", "").strip()
    try:
        record = engine.veto(proposal_id, reason=reason)
        tally = engine.tally(proposal_id)
    except VoteNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No vote record for proposal '{proposal_id}'.",
        )
    except VotingStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = record.to_dict()
    result["tally"] = tally.to_dict()
    return result

@router.post("/api/votes/{proposal_id}/lift-veto")
def api_vote_lift_veto(proposal_id: str) -> dict[str, Any]:
    """Remove a human veto from a proposal's vote."""
    from core.voting import (
        VotingEngine, VoteNotFoundError, VotingStateError,
    )
    engine = VotingEngine()
    try:
        record = engine.lift_veto(proposal_id)
        tally = engine.tally(proposal_id)
    except VoteNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No vote record for proposal '{proposal_id}'.",
        )
    except VotingStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = record.to_dict()
    result["tally"] = tally.to_dict()
    return result

# ── Characters ────────────────────────────────────────────

