"""
Jericho — Status Routes
"""

from __future__ import annotations

import logging


from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.manager_cache import (
    get_registry,
    get_character_manager,
    get_item_manager,
    get_law_manager,
    get_location_manager,
    get_proposal_manager,
    get_store_manager,
    get_treasury_manager,
    get_voting_engine,
)


log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/status")
def api_status() -> dict[str, Any]:
    """Project overview — counts of members, proposals, votes, characters."""
    data: dict[str, Any] = {}

    try:
        registry = get_registry()
        members = registry.list_members()
        providers: dict[str, int] = {}
        for m in members:
            providers[m.api_provider] = providers.get(m.api_provider, 0) + 1
        data["members"] = {
            "count": len(members),
            "providers": providers,
        }
    except Exception:
        log.debug("Status: failed to load members", exc_info=True)
        data["members"] = {"count": 0, "providers": {}}

    try:
        pmgr = get_proposal_manager()
        proposals = pmgr.list_proposals()
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for p in proposals:
            by_status[p.status] = by_status.get(p.status, 0) + 1
            by_category[p.category] = by_category.get(p.category, 0) + 1
        data["proposals"] = {
            "count": len(proposals),
            "by_status": by_status,
            "by_category": by_category,
        }
    except Exception:
        log.debug("Status: failed to load proposals", exc_info=True)
        data["proposals"] = {"count": 0, "by_status": {}, "by_category": {}}

    try:
        engine = get_voting_engine()
        records = engine.list_records()
        vote_statuses: dict[str, int] = {}
        for r in records:
            vote_statuses[r.status] = vote_statuses.get(r.status, 0) + 1
        data["votes"] = {
            "count": len(records),
            "by_status": vote_statuses,
        }
    except Exception:
        log.debug("Status: failed to load votes", exc_info=True)
        data["votes"] = {"count": 0, "by_status": {}}

    try:
        cmgr = get_character_manager()
        chars = cmgr.list_characters()
        char_statuses: dict[str, int] = {}
        for c in chars:
            char_statuses[c.status] = char_statuses.get(c.status, 0) + 1
        data["characters"] = {
            "count": len(chars),
            "by_status": char_statuses,
        }
    except Exception:
        log.debug("Status: failed to load characters", exc_info=True)
        data["characters"] = {"count": 0, "by_status": {}}

    try:
        lmgr = get_location_manager()
        locs = lmgr.list_locations()
        loc_statuses: dict[str, int] = {}
        for loc in locs:
            loc_statuses[loc.status] = loc_statuses.get(loc.status, 0) + 1
        data["locations"] = {
            "count": len(locs),
            "by_status": loc_statuses,
        }
    except Exception:
        log.debug("Status: failed to load locations", exc_info=True)
        data["locations"] = {"count": 0, "by_status": {}}

    try:
        imgr = get_item_manager()
        items_list = imgr.list_items()
        item_statuses: dict[str, int] = {}
        for it in items_list:
            item_statuses[it.status] = item_statuses.get(it.status, 0) + 1
        data["items"] = {
            "count": len(items_list),
            "by_status": item_statuses,
        }
    except Exception:
        log.debug("Status: failed to load items", exc_info=True)
        data["items"] = {"count": 0, "by_status": {}}

    try:
        lawmgr = get_law_manager()
        law_list = lawmgr.list_laws()
        law_statuses: dict[str, int] = {}
        for lw in law_list:
            law_statuses[lw.status] = law_statuses.get(lw.status, 0) + 1
        data["laws"] = {
            "count": len(law_list),
            "by_status": law_statuses,
        }
    except Exception:
        log.debug("Status: failed to load laws", exc_info=True)
        data["laws"] = {"count": 0, "by_status": {}}

    try:
        from core.character_evolution import CharacterEvolution
        evo_mgr = CharacterEvolution(
            character_manager=get_character_manager(),
            proposal_manager=get_proposal_manager(),
            voting_engine=get_voting_engine(),
        )
        evo_list = evo_mgr.list_evolutions()
        evo_statuses: dict[str, int] = {}
        for ev in evo_list:
            evo_statuses[ev.status] = evo_statuses.get(ev.status, 0) + 1
        data["evolutions"] = {
            "count": len(evo_list),
            "by_status": evo_statuses,
        }
    except Exception:
        log.debug("Status: failed to load evolutions", exc_info=True)
        data["evolutions"] = {"count": 0, "by_status": {}}

    try:
        from core.memory import AgentMemory, SharedMemory
        # Reuse the registry already loaded above (no double-load)
        registry = get_registry()
        member_names = registry.list_names()
        total_beliefs = 0
        total_events = 0
        for mname in member_names:
            amem = AgentMemory(mname)
            total_beliefs += len(amem.read_core_beliefs())
            total_events += len(amem.read_session_log())
        shared = SharedMemory()
        total_decisions = len(shared.read_decisions())
        data["memories"] = {
            "members_with_memories": len(member_names),
            "total_beliefs": total_beliefs,
            "total_events": total_events,
            "total_decisions": total_decisions,
        }
    except Exception:
        log.debug("Status: failed to load memories", exc_info=True)
        data["memories"] = {
            "members_with_memories": 0,
            "total_beliefs": 0,
            "total_events": 0,
            "total_decisions": 0,
        }

    try:
        tmgr = get_treasury_manager()
        accounts = tmgr.list_accounts()
        gov_accounts = [a for a in accounts if a.account_type == "government"]
        gov_balance = gov_accounts[0].balance.to_dict() if gov_accounts else {"gold": 0, "silver": 0, "bronze": 0}
        data["treasury"] = {
            "total_accounts": len(accounts),
            "government_balance": gov_balance,
        }
    except Exception:
        log.debug("Status: failed to load treasury", exc_info=True)
        data["treasury"] = {"total_accounts": 0, "government_balance": {"gold": 0, "silver": 0, "bronze": 0}}

    try:
        smgr = get_store_manager()
        store_list = smgr.list_stores()
        store_statuses: dict[str, int] = {}
        for st in store_list:
            store_statuses[st.status] = store_statuses.get(st.status, 0) + 1
        data["stores"] = {
            "count": len(store_list),
            "by_status": store_statuses,
        }
    except Exception:
        log.debug("Status: failed to load stores", exc_info=True)
        data["stores"] = {"count": 0, "by_status": {}}

    return data

# ── Narrative Bulletins ───────────────────────────────────

@router.get("/api/narrative-bulletins")
def api_narrative_bulletins() -> list[dict[str, Any]]:
    """Generate emergent narrative bulletins from recent events."""
    import os
    from core.narrative_engine import NarrativeEngine
    from config.settings import (
        NARRATIVE_MAX_BULLETINS, NARRATIVE_MAX_BULLETINS_ENV,
        NARRATIVE_MAX_AGE_DAYS, NARRATIVE_MAX_AGE_DAYS_ENV,
    )

    # Support runtime overrides from Settings UI
    raw_bulletins = os.environ.get(NARRATIVE_MAX_BULLETINS_ENV, "").strip()
    raw_age = os.environ.get(NARRATIVE_MAX_AGE_DAYS_ENV, "").strip()
    max_bulletins = int(raw_bulletins) if raw_bulletins else NARRATIVE_MAX_BULLETINS
    max_age_days = int(raw_age) if raw_age else NARRATIVE_MAX_AGE_DAYS

    engine = NarrativeEngine(
        max_bulletins=max_bulletins,
        max_age_days=max_age_days,
    )
    bulletins = engine.generate_bulletins()
    return [b.to_dict() for b in bulletins]


# ── Activity Feed ─────────────────────────────────────────────

_ACTIVITY_FEED_MAX = 30


@router.get("/api/activity-feed")
def api_activity_feed() -> list[dict[str, Any]]:
    """Unified reverse-chronological feed of recent system events."""
    events: list[dict[str, Any]] = []

    # -- Proposals --
    try:
        pmgr = get_proposal_manager()
        for p in pmgr.list_proposals():
            ts = getattr(p, "created_at", "") or getattr(p, "updated_at", "") or ""
            events.append({
                "type": "proposal",
                "icon": "📜",
                "title": f"Proposal: {p.title}",
                "description": f"{p.author} · {p.category} · {p.status}",
                "entity_id": p.id,
                "nav_target": "proposals",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load proposals", exc_info=True)

    # -- Characters --
    try:
        cmgr = get_character_manager()
        for c in cmgr.list_characters():
            ts = getattr(c, "created_at", "") or ""
            events.append({
                "type": "character",
                "icon": "🎭",
                "title": f"Character: {c.name}",
                "description": f"by {c.author} · {c.status}",
                "entity_id": c.id,
                "nav_target": "characters",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load characters", exc_info=True)

    # -- Locations --
    try:
        lmgr = get_location_manager()
        for loc in lmgr.list_locations():
            ts = getattr(loc, "created_at", "") or ""
            events.append({
                "type": "location",
                "icon": "🗺️",
                "title": f"Location: {loc.name}",
                "description": loc.status,
                "entity_id": loc.id,
                "nav_target": "locations",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load locations", exc_info=True)

    # -- Items --
    try:
        imgr = get_item_manager()
        for it in imgr.list_items():
            ts = getattr(it, "created_at", "") or ""
            events.append({
                "type": "item",
                "icon": "📦",
                "title": f"Item: {it.name}",
                "description": it.status,
                "entity_id": it.id,
                "nav_target": "items",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load items", exc_info=True)

    # -- Evolutions --
    try:
        from core.character_evolution import CharacterEvolution
        evo_mgr = CharacterEvolution(
            character_manager=get_character_manager(),
            proposal_manager=get_proposal_manager(),
            voting_engine=get_voting_engine(),
        )
        for ev in evo_mgr.list_evolutions():
            ts = getattr(ev, "created_at", "") or ""
            target_name = getattr(ev, "character_id", "unknown")
            events.append({
                "type": "evolution",
                "icon": "🧬",
                "title": f"Evolution: {target_name}",
                "description": f"by {ev.author} · {ev.status}",
                "entity_id": ev.id,
                "nav_target": "evolution",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load evolutions", exc_info=True)

    # -- Vote Records --
    try:
        engine = get_voting_engine()
        for rec in engine.list_records():
            ts = getattr(rec, "opened_at", "") or ""
            events.append({
                "type": "vote",
                "icon": "🗳️",
                "title": f"Vote: {rec.proposal_id}",
                "description": f"{rec.status} · {len(rec.votes)} votes cast",
                "entity_id": rec.proposal_id,
                "nav_target": "votes",
                "timestamp": ts,
            })
    except Exception:
        log.debug("Activity feed: failed to load votes", exc_info=True)

    # Sort newest-first; entries without timestamps sort last
    def _sort_key(e: dict[str, Any]) -> str:
        return e.get("timestamp") or ""

    events.sort(key=_sort_key, reverse=True)
    return events[:_ACTIVITY_FEED_MAX]


# ── System Health ─────────────────────────────────────────────


@router.get("/api/system-health")
def api_system_health() -> dict[str, Any]:
    """System health summary: LLM providers, embedding, entity counts."""
    health: dict[str, Any] = {}

    # -- LLM Provider Keys --
    try:
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        health["providers"] = mgr.all_status()
    except Exception:
        log.debug("System health: failed to load provider status", exc_info=True)
        health["providers"] = []

    # -- Embedding Status --
    try:
        import os
        from config.settings import (
            EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_NAME_ENV,
            EMBEDDING_MODE_ENV,
        )
        model_name = os.environ.get(EMBEDDING_MODEL_NAME_ENV, "").strip() or EMBEDDING_MODEL_NAME
        mode = os.environ.get(EMBEDDING_MODE_ENV, "").strip() or "hybrid"

        # Check if sentence_transformers is importable
        embedding_available = False
        try:
            import sentence_transformers  # noqa: F401
            embedding_available = True
        except ImportError:
            pass

        health["embedding"] = {
            "model": model_name,
            "mode": mode,
            "available": embedding_available,
        }
    except Exception:
        log.debug("System health: failed to check embedding status", exc_info=True)
        health["embedding"] = {"model": "unknown", "mode": "unknown", "available": False}

    # -- Entity Counts --
    try:
        counts: dict[str, int] = {}
        try:
            counts["members"] = len(get_registry().list_members())
        except Exception:
            counts["members"] = 0
        try:
            counts["proposals"] = len(get_proposal_manager().list_proposals())
        except Exception:
            counts["proposals"] = 0
        try:
            counts["characters"] = len(get_character_manager().list_characters())
        except Exception:
            counts["characters"] = 0
        try:
            counts["locations"] = len(get_location_manager().list_locations())
        except Exception:
            counts["locations"] = 0
        try:
            counts["items"] = len(get_item_manager().list_items())
        except Exception:
            counts["items"] = 0
        try:
            counts["votes"] = len(get_voting_engine().list_records())
        except Exception:
            counts["votes"] = 0
        health["entity_counts"] = counts
    except Exception:
        log.debug("System health: failed to compute entity counts", exc_info=True)
        health["entity_counts"] = {}

    return health

