"""
Jericho — Status Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/status")
def api_status() -> dict[str, Any]:
    """Project overview — counts of members, proposals, votes, characters."""
    data: dict[str, Any] = {}

    try:
        from core.registry import CouncilRegistry
        registry = CouncilRegistry().load()
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
        from core.proposals import ProposalManager
        pmgr = ProposalManager()
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
        from core.voting import VotingEngine
        engine = VotingEngine()
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
        from core.characters import CharacterManager
        cmgr = CharacterManager()
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
        from core.locations import LocationManager
        lmgr = LocationManager()
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
        from core.items import ItemManager
        imgr = ItemManager()
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
        from core.laws import LawManager
        lawmgr = LawManager()
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
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        evo_mgr = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
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
        from core.registry import CouncilRegistry
        registry = CouncilRegistry().load()
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
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager()
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
        from core.stores import StoreManager
        smgr = StoreManager()
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

