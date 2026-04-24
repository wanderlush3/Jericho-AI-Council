"""
Jericho — Memories Routes
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.manager_cache import get_registry



log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/memories")
def api_memories_list() -> list[dict[str, Any]]:
    """List all council members and characters with their memory statistics."""
    from core.memory import AgentMemory
    from config.settings import COUNCIL_AVATARS_DIR, CHARACTER_AVATARS_DIR
    from core.manager_cache import get_character_manager
    from core.chat_helpers import character_memory_name

    registry = get_registry()
    members = registry.list_members()
    # Single directory scan for avatar existence (Category 5)
    existing_avatars = {
        f.stem.lower() for f in COUNCIL_AVATARS_DIR.glob("*.png")
    } if COUNCIL_AVATARS_DIR.exists() else set()
    result = []

    # Council member memories
    for m in members:
        amem = AgentMemory(m.name)
        beliefs = amem.read_core_beliefs()
        events = amem.read_session_log()
        d: dict[str, Any] = {
            "name": m.name,
            "role": m.role,
            "type": "council_member",
            "belief_count": len(beliefs),
            "event_count": len(events),
        }
        if m.name.lower() in existing_avatars:
            d["avatar_url"] = f"/api/council/{m.name}/avatar"
        result.append(d)

    # Character memories (F-074)
    try:
        cmgr = get_character_manager()
        characters = cmgr.list_characters()
        for c in characters:
            mem_name = character_memory_name(c.name)
            amem = AgentMemory(mem_name)
            beliefs = amem.read_core_beliefs()
            events = amem.read_session_log()
            d = {
                "name": c.name,
                "memory_key": mem_name,
                "role": c.description,
                "type": "character",
                "character_id": c.id,
                "character_status": c.status,
                "belief_count": len(beliefs),
                "event_count": len(events),
            }
            avatar_path = CHARACTER_AVATARS_DIR / f"{c.id}.png"
            if avatar_path.exists():
                d["avatar_url"] = f"/api/characters/{c.id}/avatar"
            result.append(d)
    except Exception:
        log.debug("memories: failed to load character memories", exc_info=True)

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
    """Get a council member's or character's core beliefs and recent session events."""
    from core.memory import AgentMemory
    from core.registry import MemberNotFoundError

    resolved = _resolve_memory_owner(member)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Memory owner '{member}' not found (not a council member or character).",
        )

    display_name, mem_key, owner_type = resolved
    amem = AgentMemory(mem_key)
    beliefs = amem.read_core_beliefs()
    recent = amem.get_recent_memories(limit=limit)

    # F-075: enriched counts
    contested_count = len(amem.read_contested_memories())
    summarized_count = len(amem.read_summarized_log())
    session_count = len(amem.get_unique_session_ids())

    # F-077: embedding/scoring status
    from core.embeddings import get_embedding_provider
    from core.memory_influence import _effective_embedding_config
    provider = get_embedding_provider()
    emb_mode, _, _ = _effective_embedding_config()

    return {
        "name": display_name,
        "type": owner_type,
        "beliefs": [b.to_dict() for b in beliefs],
        "belief_count": len(beliefs),
        "events": [e.to_dict() for e in recent],
        "event_count": len(amem.read_session_log()),
        "contested_count": contested_count,
        "summarized_count": summarized_count,
        "session_count": session_count,
        "scoring_mode": emb_mode,
        "embeddings_available": provider.is_available,
        "embedding_model": provider.model_name,
    }

@router.delete("/api/memories/{member}/beliefs")
def api_memory_delete_belief(
    member: str,
    topic: str = Query(None),
) -> dict[str, Any]:
    """Remove a core belief by topic."""
    from core.memory import AgentMemory

    if not topic:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'topic' is required.",
        )

    resolved = _resolve_memory_owner(member)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Memory owner '{member}' not found (not a council member or character).",
        )

    display_name, mem_key, _ = resolved
    amem = AgentMemory(mem_key)
    removed = amem.remove_core_belief(topic)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No belief with topic '{topic}' found for {display_name}.",
        )

    beliefs = amem.read_core_beliefs()
    return {
        "status": "deleted",
        "topic": topic,
        "remaining_beliefs": len(beliefs),
    }

# ── Contested Memory List (F-075) ─────────────────────────

@router.get("/api/memories/{member}/contested")
def api_memory_contested_list(member: str) -> dict[str, Any]:
    """Return all contested memory records for a member."""
    from core.memory import AgentMemory

    resolved = _resolve_memory_owner(member)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Memory owner '{member}' not found.",
        )

    _, mem_key, _ = resolved
    amem = AgentMemory(mem_key)
    records = amem.read_contested_memories()
    return {
        "contested": records,
        "count": len(records),
    }

# ── Summarized Memory List (F-075) ────────────────────────

@router.get("/api/memories/{member}/summarized")
def api_memory_summarized_list(member: str) -> dict[str, Any]:
    """Return all summarized entries for a member."""
    from core.memory import AgentMemory

    resolved = _resolve_memory_owner(member)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Memory owner '{member}' not found.",
        )

    _, mem_key, _ = resolved
    amem = AgentMemory(mem_key)
    entries = amem.read_summarized_log()
    return {
        "summarized": [e.to_dict() for e in entries],
        "count": len(entries),
    }

# ── Summarization Trigger (F-075) ─────────────────────────

@router.post("/api/memories/{member}/summarize")
async def api_memory_summarize(member: str) -> dict[str, Any]:
    """Trigger LLM summarization of old sessions for a member.

    Returns the newly-created summary entries.
    """
    from core.memory import AgentMemory
    from core.memory_influence import MemoryInfluence

    resolved = _resolve_memory_owner(member)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Memory owner '{member}' not found.",
        )

    _, mem_key, _ = resolved
    amem = AgentMemory(mem_key)

    try:
        summaries = await MemoryInfluence.summarize_sessions_llm(amem)
    except Exception as exc:
        log.warning("Summarization failed for %s: %s", mem_key, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Summarization failed: {exc}",
        )

    return {
        "member": mem_key,
        "summaries_created": len(summaries),
        "summaries": [e.to_dict() for e in summaries],
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

# ── Helpers ──────────────────────────────────────────────


def _resolve_memory_owner(
    member: str,
) -> tuple[str, str, str] | None:
    """Resolve a member name/memory_key to (display_name, memory_key, type).

    Tries council member first, then character by memory_key, then
    character by exact name match.

    Returns None if no match found.
    """
    from core.registry import MemberNotFoundError
    from core.chat_helpers import character_memory_name
    from core.manager_cache import get_character_manager

    # 1. Try council member
    registry = get_registry()
    try:
        m = registry.get(member)
        return (m.name, m.name, "council_member")
    except MemberNotFoundError:
        pass

    # 2. Try character by memory_key (e.g., "atlas_memory")
    try:
        cmgr = get_character_manager()
        for c in cmgr.list_characters():
            if character_memory_name(c.name) == member.strip().lower():
                return (c.name, character_memory_name(c.name), "character")
    except Exception:
        log.debug("memories._resolve: failed character lookup", exc_info=True)

    # 3. Try character by name directly (e.g., "Atlas")
    try:
        cmgr = get_character_manager()
        for c in cmgr.list_characters():
            if c.name.lower() == member.strip().lower():
                return (c.name, character_memory_name(c.name), "character")
    except Exception:
        log.debug("memories._resolve: failed character name lookup", exc_info=True)

    return None


# ── Laws ─────────────────────────────────────────────────

