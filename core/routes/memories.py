"""
Jericho — Memories Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/memories")
def api_memories_list() -> list[dict[str, Any]]:
    """List all council members with their memory statistics."""
    from core.memory import AgentMemory
    from core.registry import CouncilRegistry
    from config.settings import COUNCIL_AVATARS_DIR

    registry = CouncilRegistry().load()
    members = registry.list_members()
    result = []
    for m in members:
        amem = AgentMemory(m.name)
        beliefs = amem.read_core_beliefs()
        events = amem.read_session_log()
        d: dict[str, Any] = {
            "name": m.name,
            "role": m.role,
            "belief_count": len(beliefs),
            "event_count": len(events),
        }
        avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
        if avatar_file.exists():
            d["avatar_url"] = f"/api/council/{m.name}/avatar"
        result.append(d)
    return result

@router.get("/api/memories/shared")
def api_memories_shared() -> dict[str, Any]:
    """Get shared council memory: decisions and narrative history."""
    from core.memory import SharedMemory

    shared = SharedMemory()
    decisions = shared.read_decisions()
    history = shared.read_history()
    return {
        "decisions": decisions,
        "decision_count": len(decisions),
        "history": history,
    }

# ── Law Shared Memory ────────────────────────────────────

@router.get("/api/memories/law-shared")
def api_law_shared_memory() -> dict[str, Any]:
    """Return active laws from the Law Shared Memory."""
    from core.memory import LawSharedMemory

    lsm = LawSharedMemory()
    laws = lsm.read_active_laws()
    context = lsm.get_law_context()

    return {
        "active_laws": laws,
        "law_count": len(laws),
        "context": context,
    }

@router.get("/api/memories/{member}")
def api_memory_detail(
    member: str,
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Get a council member's core beliefs and recent session events."""
    from core.memory import AgentMemory
    from core.registry import CouncilRegistry, MemberNotFoundError

    registry = CouncilRegistry().load()
    try:
        m = registry.get(member)
    except MemberNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Council member '{member}' not found.",
        )

    amem = AgentMemory(m.name)
    beliefs = amem.read_core_beliefs()
    recent = amem.get_recent_memories(limit=limit)

    return {
        "name": m.name,
        "beliefs": [b.to_dict() for b in beliefs],
        "belief_count": len(beliefs),
        "events": [e.to_dict() for e in recent],
        "event_count": len(amem.read_session_log()),
    }

@router.delete("/api/memories/{member}/beliefs")
def api_memory_delete_belief(
    member: str,
    topic: str = Query(None),
) -> dict[str, Any]:
    """Remove a core belief by topic."""
    from core.memory import AgentMemory
    from core.registry import CouncilRegistry, MemberNotFoundError

    if not topic:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'topic' is required.",
        )

    registry = CouncilRegistry().load()
    try:
        m = registry.get(member)
    except MemberNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Council member '{member}' not found.",
        )

    amem = AgentMemory(m.name)
    removed = amem.remove_core_belief(topic)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No belief with topic '{topic}' found for {m.name}.",
        )

    beliefs = amem.read_core_beliefs()
    return {
        "status": "deleted",
        "topic": topic,
        "remaining_beliefs": len(beliefs),
    }

@router.delete("/api/memories/shared/decisions")
def api_memory_delete_shared_decision(
    index: int | None = Query(None),
) -> dict[str, Any]:
    """Remove a shared council decision by 0-based index."""
    from core.memory import SharedMemory

    if index is None or index < 0:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'index' is required and must be >= 0.",
        )

    shared = SharedMemory()
    try:
        removed = shared.remove_decision(index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "status": "deleted",
        "removed": removed,
        "remaining": len(shared.read_decisions()),
    }

# ── Laws ─────────────────────────────────────────────────

