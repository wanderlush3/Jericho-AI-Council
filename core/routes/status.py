"""
Jericho — Status Routes
"""

from __future__ import annotations


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
        data["stores"] = {"count": 0, "by_status": {}}

    return data

# ── Narrative Bulletins ───────────────────────────────────

@router.get("/api/narrative-bulletins")
def api_narrative_bulletins() -> list[dict[str, Any]]:
    """Generate emergent narrative bulletins from recent events."""
    from core.narrative_engine import NarrativeEngine
    from config.settings import NARRATIVE_MAX_BULLETINS, NARRATIVE_MAX_AGE_DAYS

    engine = NarrativeEngine(
        max_bulletins=NARRATIVE_MAX_BULLETINS,
        max_age_days=NARRATIVE_MAX_AGE_DAYS,
    )
    bulletins = engine.generate_bulletins()
    return [b.to_dict() for b in bulletins]
