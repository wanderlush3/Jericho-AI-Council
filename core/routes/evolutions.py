"""
Jericho — Evolutions Routes
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.manager_cache import (
    get_character_manager,
    get_proposal_manager,
    get_voting_engine,
)

log = logging.getLogger(__name__)


router = APIRouter()


def _get_evo():
    """Build a CharacterEvolution wired to cached managers."""
    from core.character_evolution import CharacterEvolution
    return CharacterEvolution(
        character_manager=get_character_manager(),
        proposal_manager=get_proposal_manager(),
        voting_engine=get_voting_engine(),
    )


@router.get("/api/evolutions")
def api_evolutions_list(
    character_id: str | None = Query(None),
    status: str | None = Query(None),
    author: str | None = Query(None),
    target_type: str | None = Query(None),
    overlay_status: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List evolution records with optional filters."""
    evo = _get_evo()
    items = evo.list_evolutions(
        character_id=character_id, status=status, author=author,
        target_type=target_type, overlay_status=overlay_status,
    )
    return [r.to_dict() for r in items]

@router.get("/api/evolutions/timelines")
def api_evolutions_timelines() -> list[dict[str, Any]]:
    """List evolution timelines for all head characters."""
    from core.evolution_history import EvolutionHistory

    chars = get_character_manager()
    evo = _get_evo()
    history = EvolutionHistory(
        character_manager=chars,
        evolution_manager=evo,
    )
    timelines = history.list_timelines()
    return [t.to_dict() for t in timelines]

@router.get("/api/evolutions/timelines/{character_id}")
def api_evolutions_timeline_detail(character_id: str) -> dict[str, Any]:
    """Get evolution timeline for a specific character."""
    from core.characters import CharacterNotFoundError
    from core.evolution_history import EvolutionHistory

    chars = get_character_manager()
    evo = _get_evo()
    history = EvolutionHistory(
        character_manager=chars,
        evolution_manager=evo,
    )
    try:
        timeline = history.build_timeline(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    return timeline.to_dict()

@router.get("/api/evolutions/diff")
def api_evolutions_diff(
    old: str = Query(...),
    new: str = Query(...),
) -> dict[str, Any]:
    """Diff two character versions."""
    from core.characters import CharacterNotFoundError
    from core.evolution_history import EvolutionHistory

    chars = get_character_manager()
    evo = _get_evo()
    history = EvolutionHistory(
        character_manager=chars,
        evolution_manager=evo,
    )
    try:
        diffs = history.diff_versions(old, new)
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"old_id": old, "new_id": new, "diffs": diffs}

@router.get("/api/evolutions/active-overlays")
def api_evolution_active_overlays_list() -> list[dict[str, Any]]:
    """List all targets with active evolution overlays."""
    evo = _get_evo()
    return evo.list_targets_with_active_overlays()

@router.get("/api/evolutions/active-overlay/{target_id}")
def api_evolution_active_overlay(
    target_id: str,
    target_type: str = Query("character"),
) -> dict[str, Any] | None:
    """Get the active overlay for a target entity."""
    evo = _get_evo()
    overlay = evo.get_active_overlay(target_id, target_type)
    if overlay is None:
        return {"active_overlay": None}
    return {"active_overlay": overlay.to_dict()}

@router.get("/api/evolutions/{evolution_id}")
def api_evolution_detail(evolution_id: str) -> dict[str, Any]:
    """Get a single evolution record."""
    from core.character_evolution import EvolutionNotFoundError

    evo = _get_evo()
    try:
        record = evo.get(evolution_id)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    return record.to_dict()

@router.post("/api/evolutions")
def api_evolution_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new evolution in draft status.

    Body: {"character_id": "CH-0001", "author": "Sage",
           "changes": [{"change_type": "trait_add", "field_name": "brave",
                         "new_value": {...}, "rationale": "..."}]}
    """
    from core.characters import CharacterNotFoundError
    from core.character_evolution import (
        CharacterChange, EvolutionValidationError,
    )

    character_id = body.get("character_id", "").strip()
    author = body.get("author", "").strip()
    raw_changes = body.get("changes", [])

    if not character_id or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'character_id' and 'author' are required.",
        )

    # Build CharacterChange objects
    changes = []
    for rc in raw_changes:
        try:
            changes.append(CharacterChange.create(
                change_type=rc.get("change_type", ""),
                field_name=rc.get("field_name", ""),
                old_value=rc.get("old_value", ""),
                new_value=rc.get("new_value", ""),
                rationale=rc.get("rationale", ""),
            ))
        except EvolutionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    evo = _get_evo()

    # Support target_type: council_member uses a different code path
    target_type = body.get("target_type", "character")
    evo_name = body.get("name", "")

    if target_type == "council_member":
        member_name = body.get("member_name", "").strip()
        if not member_name:
            raise HTTPException(
                status_code=400,
                detail="Field 'member_name' is required for council_member evolutions.",
            )
        try:
            record = evo.create_council_evolution(
                member_name, author=author, changes=changes, name=evo_name,
            )
        except EvolutionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        try:
            record = evo.create_evolution(
                character_id, author=author, changes=changes,
                name=evo_name, target_type=target_type,
            )
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except EvolutionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return record.to_dict()

@router.post("/api/evolutions/{evolution_id}/submit")
def api_evolution_submit(evolution_id: str) -> dict[str, Any]:
    """Submit evolution for governance review (draft → proposed)."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionStateError,
    )

    evo = _get_evo()
    try:
        record = evo.submit_for_review(evolution_id)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

@router.post("/api/evolutions/{evolution_id}/open-voting")
def api_evolution_open_voting(evolution_id: str) -> dict[str, Any]:
    """Open voting on evolution (proposed → voting)."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionStateError,
    )

    evo = _get_evo()
    try:
        record = evo.open_voting(evolution_id)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

@router.post("/api/evolutions/{evolution_id}/resolve")
def api_evolution_resolve(evolution_id: str) -> dict[str, Any]:
    """Resolve voting (voting → decided/rejected)."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionStateError,
    )

    evo = _get_evo()
    try:
        record = evo.resolve(evolution_id)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

@router.post("/api/evolutions/{evolution_id}/apply")
def api_evolution_apply(evolution_id: str) -> dict[str, Any]:
    """Apply approved evolution (decided → applied)."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionStateError,
    )

    evo = _get_evo()
    try:
        template = evo.apply_evolution(evolution_id)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record = evo.get(evolution_id)
    return {
        "evolution": record.to_dict(),
        "new_character": template.to_dict(),
    }

# ── Evolution Expansion Endpoints ─────────────────────────

@router.put("/api/evolutions/{evolution_id}/overlay-status")
def api_evolution_overlay_status(
    evolution_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Set the overlay status (draft/active/archived) for an evolution."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionOverlayError,
    )

    new_status = body.get("overlay_status", "").strip()
    if not new_status:
        raise HTTPException(
            status_code=400,
            detail="Field 'overlay_status' is required.",
        )

    evo = _get_evo()
    try:
        record = evo.update_overlay_status(evolution_id, new_status)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionOverlayError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

@router.post("/api/evolutions/{evolution_id}/rollback")
def api_evolution_rollback(
    evolution_id: str, body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a rollback evolution that reverses the specified evolution."""
    from core.character_evolution import (
        EvolutionNotFoundError, EvolutionStateError,
    )

    body = body or {}
    author = body.get("author", "")

    evo = _get_evo()
    try:
        record = evo.rollback(evolution_id, author=author)
    except EvolutionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Evolution '{evolution_id}' not found.",
        )
    except EvolutionStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

@router.post("/api/evolutions/rollback-to/{target_id}/{version_id}")
def api_evolution_rollback_to_version(
    target_id: str,
    version_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rollback a target to a specific historical version."""
    from core.characters import CharacterNotFoundError

    body = body or {}
    author = body.get("author", "system")
    target_type = body.get("target_type", "character")

    evo = _get_evo()
    try:
        record = evo.rollback_to_version(
            target_id, version_id, author=author, target_type=target_type,
        )
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version_id}' not found.",
        )
    return record.to_dict()

@router.post("/api/evolutions/from-proposal/{proposal_id}")
def api_evolution_from_proposal(
    proposal_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Auto-create an evolution from an approved proposal."""
    from core.character_evolution import EvolutionValidationError

    body = body or {}
    author = body.get("author", "")

    evo = _get_evo()
    try:
        record = evo.create_from_proposal(proposal_id, author=author)
    except EvolutionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record.to_dict()

# ── Council Sessions ──────────────────────────────────────
