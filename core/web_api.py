"""
Jericho — Web Dashboard API (F-021)

FastAPI application serving JSON endpoints that wrap existing managers,
plus static files for the single-page dashboard frontend.

Launch via CLI: ``jericho web``
Or directly:  ``uvicorn core.web_api:app --port 8080``
"""

from __future__ import annotations

import json as json_module
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from config.settings import (
    CHARACTERS_DIR,
    COUNCIL_MEMBERS_DIR,
    EVOLUTION_DIR,
    PROPOSALS_DIR,
    TREASURY_DIR,
    VOTES_DIR,
    WEB_STATIC_DIR,
)

# ─── App Factory ──────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    application = FastAPI(
        title="Jericho AI Council",
        description="Web dashboard for the Jericho AI Council governance system.",
        version="0.1.0",
    )

    # Decrypt API keys at startup so APIClient reads the real keys
    # (load_dotenv only loads the encrypted Fernet tokens into os.environ)
    # Also load model overrides so APIClient can apply them.
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    mgr.load_all()
    for provider in mgr.PROVIDERS:
        mgr.load_model(provider)

    # ── Status ────────────────────────────────────────────────

    @application.get("/api/status")
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

    @application.get("/api/narrative-bulletins")
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

    # ── Council ───────────────────────────────────────────────

    @application.get("/api/council")
    def api_council_list() -> list[dict[str, Any]]:
        """List all council members."""
        from core.registry import CouncilRegistry
        from config.settings import COUNCIL_AVATARS_DIR
        registry = CouncilRegistry().load()
        members = registry.list_members()
        result = []
        for m in members:
            d = {
                "name": m.name,
                "role": m.role,
                "description": m.description,
                "personality": m.personality,
                "api_provider": m.api_provider,
                "model": m.model,
                "vote_weight": m.vote_weight,
                "specialties": m.specialties,
                "system_prompt": m.system_prompt,
            }
            avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
            if avatar_file.exists():
                d["avatar_url"] = f"/api/council/{m.name}/avatar"
            result.append(d)
        return result

    @application.get("/api/council/candidates")
    def api_council_candidates() -> list[dict[str, Any]]:
        """List active characters that are not already council members.

        Returns characters eligible for promotion to council membership.
        Only active characters whose names don't match an existing
        council member (case-insensitive) are included.
        """
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager
        from config.settings import CHARACTER_AVATARS_DIR

        registry = CouncilRegistry().load()
        cmgr = CharacterManager()
        active_chars = cmgr.list_characters(status="active")

        # Build set of existing council member names (lowercase)
        council_names = {m.name.lower() for m in registry.list_members()}

        candidates = []
        for c in active_chars:
            if c.name.lower() not in council_names:
                d = {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "status": c.status,
                    "api_provider": c.api_provider,
                    "model": c.model,
                    "system_prompt": c.system_prompt,
                }
                avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
                if avatar_file.exists():
                    d["avatar_url"] = f"/api/characters/{c.id}/avatar"
                candidates.append(d)
        return candidates

    @application.post("/api/council/promote")
    def api_council_promote(body: dict[str, Any]) -> dict[str, Any]:
        """Promote a character to council member.

        Body: {
            "character_id": "CH-0001",
            "role": "Innovation Advisor",
            "role_description": "Explores new ideas and advises on creative solutions",
            "api_provider": "openrouter",   // optional, defaults to character's
            "model": "anthropic/claude-3.5-sonnet"  // optional, defaults to character's
        }

        Creates a new YAML profile in council/members/ and returns
        the new council member data.
        """
        import yaml as yaml_mod
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager, CharacterNotFoundError

        character_id = body.get("character_id", "").strip()
        role = body.get("role", "").strip()
        role_description = body.get("role_description", "").strip()

        errors = []
        if not character_id:
            errors.append("'character_id' is required")
        if not role:
            errors.append("'role' is required")
        if not role_description:
            errors.append("'role_description' is required")
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

        # Load character
        cmgr = CharacterManager()
        try:
            character = cmgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )

        if character.status != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Character '{character.name}' is not active (status: {character.status}).",
            )

        # Check not already on council
        registry = CouncilRegistry().load()
        if character.name.lower() in {m.name.lower() for m in registry.list_members()}:
            raise HTTPException(
                status_code=400,
                detail=f"'{character.name}' is already a council member.",
            )

        # Determine provider & model
        api_provider = body.get("api_provider", "").strip() or character.api_provider
        model = body.get("model", "").strip() or character.model
        if model == "Default":
            model = "anthropic/claude-3.5-sonnet"

        # Build YAML data
        member_data = {
            "name": character.name,
            "role": role,
            "description": role_description,
            "api_provider": api_provider,
            "model": model,
            "vote_weight": 1.0,
            "system_prompt": character.system_prompt or f"You are {character.name}, the {role} on the Jericho Council.",
        }

        # Write YAML to council/members/
        filename = f"{character.name.lower().replace(' ', '_')}.yaml"
        member_filepath = COUNCIL_MEMBERS_DIR / filename
        comment = f"# Council Member: {character.name} — {role}\n"
        yaml_body = yaml_mod.dump(
            member_data, default_flow_style=False,
            allow_unicode=True, sort_keys=False,
        )
        with open(member_filepath, "w", encoding="utf-8") as f:
            f.write(comment)
            f.write(yaml_body)

        return {
            "status": "ok",
            "name": character.name,
            "role": role,
            "description": role_description,
            "api_provider": api_provider,
            "model": model,
            "vote_weight": 1.0,
            "system_prompt": member_data["system_prompt"],
            "member_file": filename,
        }

    @application.get("/api/council/{name}")
    def api_council_detail(name: str) -> dict[str, Any]:
        """Get a single council member by name."""
        from core.registry import CouncilRegistry, MemberNotFoundError
        from config.settings import COUNCIL_AVATARS_DIR
        registry = CouncilRegistry().load()
        try:
            m = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")
        d = {
            "name": m.name,
            "role": m.role,
            "description": m.description,
            "personality": m.personality,
            "api_provider": m.api_provider,
            "model": m.model,
            "vote_weight": m.vote_weight,
            "specialties": m.specialties,
            "system_prompt": m.system_prompt,
        }
        avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
        if avatar_file.exists():
            d["avatar_url"] = f"/api/council/{m.name}/avatar"
        return d

    @application.put("/api/council/{name}")
    def api_council_update(name: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update editable fields of a council member.

        Body may contain: name, api_provider, model, vote_weight,
        system_prompt, traits, communication_style, decision_approach.
        Read-only fields (role, description, specialties) are rejected.
        """
        from core.registry import CouncilRegistry, MemberNotFoundError
        registry = CouncilRegistry().load()
        try:
            updated = registry.update_member(name, body)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "name": updated.name,
            "role": updated.role,
            "description": updated.description,
            "personality": updated.personality,
            "api_provider": updated.api_provider,
            "model": updated.model,
            "vote_weight": updated.vote_weight,
            "specialties": updated.specialties,
            "system_prompt": updated.system_prompt,
        }

    @application.post("/api/council/{name}/avatar")
    async def api_council_avatar_upload(name: str) -> dict[str, Any]:
        """Upload an avatar PNG for a council member.

        Accepts multipart form data with fields:
          - file: the PNG image
          - zoom: zoom level (float, default 1.0)
          - offsetX: horizontal offset (float, default 0)
          - offsetY: vertical offset (float, default 0)
        """
        from fastapi import Request
        from config.settings import COUNCIL_AVATARS_DIR
        from core.registry import CouncilRegistry, MemberNotFoundError
        import base64

        # Verify the member exists
        registry = CouncilRegistry().load()
        try:
            member = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

        # This endpoint is called via JS fetch with JSON body containing base64 data
        # since we need zoom metadata alongside the image.
        return {"detail": "Use the JSON endpoint instead."}

    @application.post("/api/council/{name}/avatar-upload")
    def api_council_avatar_upload_json(name: str, body: dict[str, Any]) -> dict[str, Any]:
        """Upload avatar as base64 JSON.

        Body: {"image_data": "data:image/png;base64,...", "zoom": 1.0, "offsetX": 0, "offsetY": 0}
        """
        import base64
        from config.settings import COUNCIL_AVATARS_DIR
        from core.registry import CouncilRegistry, MemberNotFoundError

        registry = CouncilRegistry().load()
        try:
            member = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

        image_data = body.get("image_data", "")
        zoom = body.get("zoom", 1.0)
        offset_x = body.get("offsetX", 0)
        offset_y = body.get("offsetY", 0)

        if not image_data:
            raise HTTPException(status_code=400, detail="'image_data' is required.")

        # Parse base64 data URL
        try:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data.")

        # Ensure avatars directory exists
        COUNCIL_AVATARS_DIR.mkdir(parents=True, exist_ok=True)

        # Save the PNG
        avatar_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.png"
        with open(avatar_path, "wb") as f:
            f.write(raw_bytes)

        # Save zoom metadata
        meta_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.json"
        import json as json_mod
        with open(meta_path, "w", encoding="utf-8") as f:
            json_mod.dump({"zoom": zoom, "offsetX": offset_x, "offsetY": offset_y}, f)

        return {
            "status": "ok",
            "avatar_url": f"/api/council/{member.name}/avatar",
        }

    @application.get("/api/council/{name}/avatar")
    def api_council_avatar_get(name: str):
        """Serve a council member's avatar PNG."""
        from config.settings import COUNCIL_AVATARS_DIR
        from core.registry import CouncilRegistry, MemberNotFoundError

        registry = CouncilRegistry().load()
        try:
            member = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

        avatar_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.png"
        if not avatar_path.exists():
            raise HTTPException(status_code=404, detail="No avatar uploaded for this member.")

        return FileResponse(str(avatar_path), media_type="image/png")

    @application.get("/api/council/{name}/avatar-meta")
    def api_council_avatar_meta(name: str) -> dict[str, Any]:
        """Get avatar zoom metadata for a council member."""
        from config.settings import COUNCIL_AVATARS_DIR
        from core.registry import CouncilRegistry, MemberNotFoundError

        registry = CouncilRegistry().load()
        try:
            member = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

        meta_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.json"
        if not meta_path.exists():
            return {"zoom": 1.0, "offsetX": 0, "offsetY": 0}

        import json as json_mod
        with open(meta_path, "r", encoding="utf-8") as f:
            return json_mod.load(f)

    # ── Proposals ─────────────────────────────────────────────

    @application.get("/api/proposals")
    def api_proposals_list(
        status: str | None = Query(None),
        category: str | None = Query(None),
        author: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List proposals with optional filters."""
        from core.proposals import ProposalManager
        mgr = ProposalManager()
        items = mgr.list_proposals(status=status, category=category, author=author)
        return [p.to_dict() for p in items]

    @application.get("/api/proposals/{proposal_id}")
    def api_proposal_detail(proposal_id: str) -> dict[str, Any]:
        """Get a single proposal."""
        from core.proposals import ProposalManager, ProposalNotFoundError
        mgr = ProposalManager()
        try:
            p = mgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
        return p.to_dict()

    @application.post("/api/proposals")
    def api_proposal_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new proposal and auto-open it with a discussion.

        Body: {"author": "Sage", "title": "...", "description": "...",
               "category": "ethics", "body": "...",
               "character_data": {...}}  // optional, for character proposals
        """
        from core.proposals import ProposalManager, ProposalValidationError

        author = body.get("author", "").strip()
        title = body.get("title", "").strip()
        description = body.get("description", "").strip()
        category = body.get("category", "").strip()
        proposal_body = body.get("body", "").strip()

        if not author or not title or not description or not category:
            raise HTTPException(
                status_code=400,
                detail="Fields 'author', 'title', 'description', and 'category' are required.",
            )

        # If this is a character proposal, stash character_data in metadata
        metadata = None
        character_data = body.get("character_data")
        if category == "character" and character_data and isinstance(character_data, dict):
            metadata = {"character_data": character_data}

        # If this is a location proposal, stash location_data in metadata
        location_data = body.get("location_data")
        if category == "location" and location_data and isinstance(location_data, dict):
            metadata = {"location_data": location_data}

        # If this is an item proposal, stash item_data in metadata
        item_data = body.get("item_data")
        if category == "item" and item_data and isinstance(item_data, dict):
            metadata = {"item_data": item_data}

        # If this is a law proposal, stash law_data in metadata
        law_data = body.get("law_data")
        if category == "law" and law_data and isinstance(law_data, dict):
            metadata = {"law_data": law_data}

        pmgr = ProposalManager()
        try:
            proposal = pmgr.create(
                title, description, author=author, category=category,
                body=proposal_body, metadata=metadata,
            )
            # Auto-transition to open
            proposal = pmgr.update_status(proposal.id, "open")
        except ProposalValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Create a discussion with all council members
        discussion_info = None
        try:
            from core.discussion import DiscussionManager
            from core.registry import CouncilRegistry

            dmgr = _make_discussion_manager(pmgr)
            participants = CouncilRegistry().load().list_names()
            disc_id = proposal.id  # use proposal ID as discussion ID
            disc = dmgr.create_discussion(
                disc_id, proposal.id, f"Discussion: {title}",
                participants=participants, round_count=5,
            )
            discussion_info = disc.to_dict()
        except Exception as exc:
            # Discussion creation is optional; don't fail the proposal
            discussion_info = {"error": str(exc)}

        result = proposal.to_dict()
        result["discussion"] = discussion_info
        return result

    @application.post("/api/proposals/{proposal_id}/discuss-stream")
    async def api_proposal_discuss_stream(proposal_id: str):
        """Run one discussion round and stream contributions via SSE."""
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.discussion import (
            DiscussionManager, DiscussionNotFoundError, DiscussionStateError,
        )
        from core.api_client import ChatMessage
        from core.memory_influence import MemoryInfluence

        async def event_generator():
            try:
                pmgr = ProposalManager()
                dmgr = _make_discussion_manager(pmgr)

                # Load the discussion and proposal
                record = dmgr.get(proposal_id)
                proposal = pmgr.get(record.proposal_id)

                if record.status != "open":
                    err = json_module.dumps({"detail": "Discussion is closed."})
                    yield f"event: error\ndata: {err}\n\n"
                    return

                if record.current_round >= record.round_count:
                    err = json_module.dumps({"detail": "All discussion rounds complete."})
                    yield f"event: error\ndata: {err}\n\n"
                    return

                round_number = record.current_round + 1
                new_contributions = []
                mi = MemoryInfluence()
                keywords = MemoryInfluence.extract_keywords(
                    f"{proposal.title} {proposal.description}"
                )

                from core.registry import CouncilRegistry
                from core.api_client import APIClient
                registry = CouncilRegistry().load()
                client = APIClient()

                # Inject scheduled user message if present
                meta = dict(record.metadata)
                scheduled_msg = meta.pop("scheduled_message", None)
                if scheduled_msg and isinstance(scheduled_msg, str) and scheduled_msg.strip():
                    from core.discussion import DiscussionContribution
                    user_contribution = DiscussionContribution.create(
                        speaker="User",
                        content=scheduled_msg.strip(),
                        round_number=round_number,
                        metadata={"type": "scheduled_message"},
                    )
                    new_contributions.append(user_contribution)

                    # Stream the user message
                    user_event = json_module.dumps({
                        "speaker": "User",
                        "content": scheduled_msg.strip(),
                        "round": round_number,
                        "model": "",
                        "provider": "user",
                    })
                    yield f"event: message\ndata: {user_event}\n\n"

                    import asyncio as _asyncio
                    await _asyncio.sleep(0.3)

                for name in record.participants:
                    member = registry.get(name)

                    # Build memory context
                    memory_text = ""
                    ctx = mi.build_context(member.name, keywords)
                    if ctx.formatted_text:
                        memory_text = ctx.formatted_text

                    # Build prompt
                    from core.discussion import _build_discussion_prompt
                    all_contribs = list(record.contributions) + new_contributions
                    prompt = _build_discussion_prompt(
                        member, proposal, all_contribs, round_number,
                        memory_context_text=memory_text,
                    )
                    messages = [ChatMessage(role="user", content=prompt)]
                    response = await client.chat(member, messages)

                    from core.discussion import DiscussionContribution
                    contribution = DiscussionContribution.create(
                        speaker=member.name,
                        content=response.content,
                        round_number=round_number,
                        metadata={
                            "model": response.model,
                            "provider": response.provider,
                        },
                    )
                    new_contributions.append(contribution)

                    # Stream this contribution
                    event_data = json_module.dumps({
                        "speaker": member.name,
                        "content": response.content,
                        "round": round_number,
                        "model": response.model,
                        "provider": response.provider,
                    })
                    yield f"event: message\ndata: {event_data}\n\n"

                    # Small delay between responses
                    import asyncio
                    await asyncio.sleep(0.5)

                # Save the updated record
                from core.discussion import DiscussionRecord
                all_contributions = list(record.contributions) + new_contributions
                updated_record = DiscussionRecord(
                    discussion_id=record.discussion_id,
                    proposal_id=record.proposal_id,
                    title=record.title,
                    participants=list(record.participants),
                    contributions=all_contributions,
                    round_count=record.round_count,
                    current_round=round_number,
                    status=record.status,
                    summary=record.summary,
                    created_at=record.created_at,
                    closed_at=record.closed_at,
                    metadata=meta,
                )
                dmgr._save(updated_record)

                # Send final state
                done_data = json_module.dumps({
                    "discussion": updated_record.to_dict(),
                    "round_completed": round_number,
                })
                yield f"event: done\ndata: {done_data}\n\n"

            except DiscussionNotFoundError:
                err = json_module.dumps({"detail": f"No discussion for proposal '{proposal_id}'."})
                yield f"event: error\ndata: {err}\n\n"
            except Exception as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/proposals/{proposal_id}/discuss-pause")
    def api_proposal_discuss_pause(proposal_id: str) -> dict[str, Any]:
        """Close/pause the discussion on a proposal."""
        from core.proposals import ProposalManager
        from core.discussion import (
            DiscussionManager, DiscussionNotFoundError, DiscussionStateError,
        )

        pmgr = ProposalManager()
        dmgr = _make_discussion_manager(pmgr)

        try:
            record = dmgr.close_discussion(proposal_id)
        except DiscussionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No discussion for proposal '{proposal_id}'.",
            )
        except DiscussionStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Transition proposal to under_review
        try:
            pmgr.update_status(proposal_id, "under_review")
        except Exception:
            pass  # non-critical

        return record.to_dict()

    @application.get("/api/proposals/{proposal_id}/scheduled-message")
    def api_proposal_scheduled_message_get(proposal_id: str) -> dict[str, Any]:
        """Get the scheduled user message for the next discussion round."""
        from core.proposals import ProposalManager
        from core.discussion import DiscussionNotFoundError

        pmgr = ProposalManager()
        dmgr = _make_discussion_manager(pmgr)

        try:
            record = dmgr.get(proposal_id)
        except DiscussionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No discussion for proposal '{proposal_id}'.",
            )

        msg = (record.metadata or {}).get("scheduled_message", None)
        return {"message": msg}

    @application.post("/api/proposals/{proposal_id}/scheduled-message")
    def api_proposal_scheduled_message_set(
        proposal_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Set or clear a user message for the next discussion round.

        Body: {"message": "Your message here..."}
        Send an empty string to clear.
        """
        from core.proposals import ProposalManager
        from core.discussion import (
            DiscussionNotFoundError, DiscussionStateError, DiscussionRecord,
        )

        pmgr = ProposalManager()
        dmgr = _make_discussion_manager(pmgr)

        try:
            record = dmgr.get(proposal_id)
        except DiscussionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No discussion for proposal '{proposal_id}'.",
            )

        if record.status != "open":
            raise HTTPException(
                status_code=400,
                detail="Cannot schedule a message on a closed discussion.",
            )

        message = (body.get("message", "") or "").strip()
        meta = dict(record.metadata)
        if message:
            meta["scheduled_message"] = message
        else:
            meta.pop("scheduled_message", None)

        updated = DiscussionRecord(
            discussion_id=record.discussion_id,
            proposal_id=record.proposal_id,
            title=record.title,
            participants=list(record.participants),
            contributions=list(record.contributions),
            round_count=record.round_count,
            current_round=record.current_round,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=meta,
        )
        dmgr._save(updated)

        return {
            "status": "ok",
            "message": message or None,
            "scheduled": bool(message),
        }

    @application.post("/api/proposals/{proposal_id}/send-to-review")
    def api_proposal_send_to_review(proposal_id: str) -> dict[str, Any]:
        """Close/pause discussion and transition proposal to open_to_review.

        This is the "Send to Review" action that ends the discussion and
        lets the user prepare a final proposal before calling a vote.
        """
        from core.proposals import (
            ProposalManager, ProposalNotFoundError,
            ProposalLifecycleError, ProposalValidationError,
        )
        from core.discussion import (
            DiscussionManager, DiscussionNotFoundError, DiscussionStateError,
        )

        pmgr = ProposalManager()

        # Close the discussion first
        try:
            dmgr = _make_discussion_manager(pmgr)
            dmgr.close_discussion(proposal_id)
        except (DiscussionNotFoundError, DiscussionStateError):
            pass  # may already be closed or not exist

        # Transition proposal to open_to_review
        try:
            proposal = pmgr.update_status(proposal_id, "open_to_review")
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )
        except (ProposalLifecycleError, ProposalValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return proposal.to_dict()

    @application.put("/api/proposals/{proposal_id}/final-proposal")
    def api_proposal_final_proposal(
        proposal_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Save the edited final proposal before calling a vote.

        Only allowed when proposal status is 'open_to_review'.
        Body may contain: title, description, body, metadata.
        """
        from core.proposals import (
            ProposalManager, ProposalNotFoundError,
            ProposalValidationError,
        )

        pmgr = ProposalManager()
        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        if proposal.status != "open_to_review":
            raise HTTPException(
                status_code=400,
                detail=f"Final proposal can only be edited when status is 'open_to_review' (current: '{proposal.status}').",
            )

        # Build update fields from body
        update_fields: dict[str, Any] = {}
        if "title" in body:
            update_fields["title"] = body["title"]
        if "description" in body:
            update_fields["description"] = body["description"]
        if "body" in body:
            update_fields["body"] = body["body"]
        if "metadata" in body:
            update_fields["metadata"] = body["metadata"]

        if not update_fields:
            return proposal.to_dict()

        try:
            updated = pmgr.update(proposal_id, **update_fields)
        except ProposalValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return updated.to_dict()

    @application.post("/api/proposals/{proposal_id}/vote")
    async def api_proposal_vote(proposal_id: str) -> dict[str, Any]:
        """Run a full vote: open voting, have each council member cast
        an AI-generated vote, close voting, return tally.
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, Vote, VotingStateError
        from core.discussion import DiscussionNotFoundError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient, ChatMessage

        pmgr = ProposalManager()
        registry = CouncilRegistry().load()
        client = APIClient()
        engine = VotingEngine()

        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        # Load discussion summary if available
        discussion_context = ""
        try:
            dmgr = _make_discussion_manager(pmgr)
            disc = dmgr.get(proposal_id)
            if disc.summary:
                discussion_context = f"\n\n## Discussion Summary\n{disc.summary}"
            # Include last contributions
            for c in disc.contributions[-6:]:
                discussion_context += f"\n**{c.speaker}** (round {c.round_number}): {c.content}"
        except DiscussionNotFoundError:
            pass

        # Open voting
        try:
            engine.open_voting(proposal_id)
        except VotingStateError:
            # Already exists - that's fine for re-votes
            pass

        # Have each council member vote
        members = registry.list_members()
        vote_results = []

        for member in members:
            # Build memory context for this member
            from core.memory_influence import MemoryInfluence
            mi = MemoryInfluence()
            vote_keywords = MemoryInfluence.extract_keywords(
                f"{proposal.title} {proposal.description} {proposal.category}"
            )
            ctx = mi.build_context(member.name, vote_keywords)
            memory_block = ""
            if ctx.formatted_text:
                memory_block = f"\n\n{ctx.formatted_text}\n"

            vote_prompt = (
                f"## Vote Required: {proposal.title}\n"
                f"**Proposal ID:** {proposal.id}\n"
                f"**Category:** {proposal.category}\n"
                f"**Author:** {proposal.author}\n"
                f"**Description:** {proposal.description}\n"
                f"{discussion_context}"
                f"{memory_block}\n\n"
                f"---\n"
                f"You are **{member.name}** ({member.role}). "
                f"You must now vote on this proposal.\n\n"
                f"Respond with EXACTLY this format (first line is your vote, "
                f"rest is your reasoning):\n"
                f"VOTE: for\n"
                f"or\n"
                f"VOTE: against\n"
                f"or\n"
                f"VOTE: abstain\n\n"
                f"Then explain your reasoning briefly."
            )

            messages = [ChatMessage(role="user", content=vote_prompt)]

            try:
                response = await client.chat(member, messages)
                content = response.content or ""

                # Parse vote from response
                choice = "abstain"  # default
                reason = content
                content_lower = content.lower()
                if "vote: for" in content_lower or "vote:for" in content_lower:
                    choice = "for"
                elif "vote: against" in content_lower or "vote:against" in content_lower:
                    choice = "against"
                elif "vote: abstain" in content_lower or "vote:abstain" in content_lower:
                    choice = "abstain"

                # Extract reason (everything after the VOTE: line)
                import re
                reason_match = re.split(r"VOTE:\s*\w+\s*\n?", content, flags=re.IGNORECASE)
                if len(reason_match) > 1:
                    reason = reason_match[-1].strip()

                vote = Vote.create(
                    voter=member.name,
                    choice=choice,
                    reason=reason,
                    weight=member.vote_weight,
                )
                try:
                    engine.cast_vote(proposal_id, vote)
                except Exception:
                    pass  # duplicate vote, skip

                vote_results.append({
                    "voter": member.name,
                    "choice": choice,
                    "reason": reason,
                })
            except Exception as exc:
                vote_results.append({
                    "voter": member.name,
                    "choice": "abstain",
                    "reason": f"Error: {str(exc)[:100]}",
                })

        # Close voting
        try:
            engine.close_voting(proposal_id)
        except Exception:
            pass

        # Transition proposal to decided
        try:
            pmgr.update_status(proposal_id, "decided")
        except Exception:
            pass

        # Get final tally
        tally = engine.tally(proposal_id)
        record = engine.get(proposal_id)

        result = {
            "proposal": pmgr.get(proposal_id).to_dict(),
            "vote_record": record.to_dict(),
            "tally": tally.to_dict(),
            "individual_votes": vote_results,
        }

        # Evolution handoff: signal the frontend when an evolution proposal passes
        decided_proposal = pmgr.get(proposal_id)
        if decided_proposal.category == "evolution" and tally.approved:
            result["evolution_handoff"] = {
                "status": "ready",
                "message": "Approved evolution proposal — proceed in the Evolution section to create and apply changes.",
            }

        # Character handoff: signal the frontend when a character proposal passes
        if decided_proposal.category == "character" and tally.approved:
            result["character_handoff"] = {
                "status": "ready",
                "message": "Approved character proposal — create a draft character from the proposal data.",
            }

        # Location handoff: signal the frontend when a location proposal passes
        if decided_proposal.category == "location" and tally.approved:
            result["location_handoff"] = {
                "status": "ready",
                "message": "Approved location proposal — create a draft location from the proposal data.",
            }

        # Item handoff: signal the frontend when an item proposal passes
        if decided_proposal.category == "item" and tally.approved:
            result["item_handoff"] = {
                "status": "ready",
                "message": "Approved item proposal — create a draft item from the proposal data.",
            }

        # Law handoff: signal the frontend when a law proposal passes
        if decided_proposal.category == "law" and tally.approved:
            result["law_handoff"] = {
                "status": "ready",
                "message": "Approved law proposal — create a draft law from the proposal data.",
            }

        return result

    @application.post("/api/proposals/{proposal_id}/withdraw")
    def api_proposal_withdraw(
        proposal_id: str, body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Withdraw a proposal. Body: {"author": "Sage"}."""
        from core.proposals import (
            ProposalManager, ProposalNotFoundError,
            ProposalValidationError, ProposalLifecycleError,
        )

        author = ""
        if body:
            author = body.get("author", "").strip()
        if not author:
            raise HTTPException(
                status_code=400, detail="'author' is required.",
            )

        pmgr = ProposalManager()
        try:
            proposal = pmgr.withdraw(proposal_id, author)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )
        except (ProposalValidationError, ProposalLifecycleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return proposal.to_dict()

    @application.post("/api/proposals/{proposal_id}/handoff-character")
    def api_proposal_handoff_character(proposal_id: str) -> dict[str, Any]:
        """Create a draft character from an approved character proposal.

        Reads character_data from proposal.metadata and creates a new
        CharacterTemplate in draft status.  The proposal must be:
          - category == 'character'
          - status == 'decided'
          - vote tally == approved
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, VoteNotFoundError
        from core.characters import (
            CharacterManager, CharacterValidationError, Trait,
        )

        pmgr = ProposalManager()
        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        if proposal.category != "character":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' is not a character proposal (category: {proposal.category}).",
            )

        if proposal.status != "decided":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' has not been decided yet (status: {proposal.status}).",
            )

        # Verify vote was approved
        engine = VotingEngine()
        try:
            tally = engine.tally(proposal_id)
        except VoteNotFoundError:
            raise HTTPException(
                status_code=400,
                detail=f"No vote record found for proposal '{proposal_id}'.",
            )

        if not tally.approved:
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' was not approved.",
            )

        # Extract character_data from proposal metadata
        cd = (proposal.metadata or {}).get("character_data", {})
        char_name = cd.get("name", "").strip() or proposal.title
        char_desc = proposal.description  # description = character description
        char_author = proposal.author
        backstory = cd.get("backstory", "").strip()
        system_prompt = cd.get("system_prompt", "").strip()
        greeting = cd.get("greeting", "").strip()
        tags = cd.get("tags", [])
        example_messages = cd.get("example_messages", [])
        api_provider = cd.get("api_provider", "openrouter").strip()
        model = cd.get("model", "Default").strip()

        # Parse traits
        raw_traits = cd.get("traits", [])
        traits: list[Trait] = []
        for t in raw_traits:
            try:
                traits.append(Trait.create(
                    trait_type=t.get("trait_type", "personality"),
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    intensity=float(t.get("intensity", 0.5)),
                ))
            except CharacterValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        # Require at least one trait — if none provided, add a default
        if not traits:
            traits = [Trait.create("personality", "Undefined", "Awaiting trait definition", 0.5)]

        cmgr = CharacterManager()
        try:
            character = cmgr.create(
                char_name, char_desc, author=char_author,
                backstory=backstory, traits=traits,
                system_prompt=system_prompt, greeting=greeting,
                example_messages=example_messages or None,
                tags=tags or None,
                metadata={"source_proposal": proposal_id},
            )
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = character.to_dict()
        result["source_proposal"] = proposal_id
        return result

    @application.post("/api/proposals/{proposal_id}/handoff-location")
    def api_proposal_handoff_location(proposal_id: str) -> dict[str, Any]:
        """Create a draft location from an approved location proposal.

        Reads location_data from proposal.metadata and creates a new
        Location in draft status.  The proposal must be:
          - category == 'location'
          - status == 'decided'
          - vote tally == approved
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, VoteNotFoundError
        from core.locations import (
            LocationManager, LocationValidationError, LocationFeature,
        )

        pmgr = ProposalManager()
        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        if proposal.category != "location":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' is not a location proposal (category: {proposal.category}).",
            )

        if proposal.status != "decided":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' has not been decided yet (status: {proposal.status}).",
            )

        # Verify vote was approved
        engine = VotingEngine()
        try:
            tally = engine.tally(proposal_id)
        except VoteNotFoundError:
            raise HTTPException(
                status_code=400,
                detail=f"No vote record found for proposal '{proposal_id}'.",
            )

        if not tally.approved:
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' was not approved.",
            )

        # Extract location_data from proposal metadata
        ld = (proposal.metadata or {}).get("location_data", {})
        loc_name = ld.get("name", "").strip() or proposal.title
        loc_desc = ld.get("description", "").strip() or proposal.description
        loc_author = proposal.author
        lore = ld.get("lore", "").strip()
        tags = ld.get("tags", [])
        coordinates = ld.get("coordinates", "").strip()

        # Parse features
        raw_features = ld.get("features", [])
        features: list[LocationFeature] = []
        for f in raw_features:
            try:
                features.append(LocationFeature.create(
                    name=f.get("name", ""),
                    description=f.get("description", ""),
                    feature_type=f.get("feature_type", "custom"),
                ))
            except LocationValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        lmgr = LocationManager()
        try:
            location = lmgr.create(
                loc_name, loc_desc, author=loc_author,
                lore=lore, features=features,
                tags=tags or None, coordinates=coordinates,
                metadata={"source_proposal": proposal_id},
            )
        except LocationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = location.to_dict()
        result["source_proposal"] = proposal_id
        return result

    @application.post("/api/proposals/{proposal_id}/handoff-item")
    def api_proposal_handoff_item(proposal_id: str) -> dict[str, Any]:
        """Create a draft item from an approved item proposal.

        Reads item_data from proposal.metadata and creates a new
        Item in draft status.  The proposal must be:
          - category == 'item'
          - status == 'decided'
          - vote tally == approved
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, VoteNotFoundError
        from core.items import (
            ItemManager, ItemValidationError, ItemProperty,
        )

        pmgr = ProposalManager()
        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        if proposal.category != "item":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' is not an item proposal (category: {proposal.category}).",
            )

        if proposal.status != "decided":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' has not been decided yet (status: {proposal.status}).",
            )

        # Verify vote was approved
        engine = VotingEngine()
        try:
            tally = engine.tally(proposal_id)
        except VoteNotFoundError:
            raise HTTPException(
                status_code=400,
                detail=f"No vote record found for proposal '{proposal_id}'.",
            )

        if not tally.approved:
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' was not approved.",
            )

        # Extract item_data from proposal metadata
        idata = (proposal.metadata or {}).get("item_data", {})
        item_name = idata.get("name", "").strip() or proposal.title
        item_desc = idata.get("description", "").strip() or proposal.description
        item_author = proposal.author
        lore = idata.get("lore", "").strip()
        tags = idata.get("tags", [])
        rarity = idata.get("rarity", "").strip()
        tier = idata.get("tier", "").strip()
        legality = idata.get("legality", "").strip()

        # Parse properties
        raw_properties = idata.get("properties", [])
        properties: list[ItemProperty] = []
        for p in raw_properties:
            try:
                properties.append(ItemProperty.create(
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    property_type=p.get("property_type", "custom"),
                ))
            except ItemValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        imgr = ItemManager()
        try:
            item = imgr.create(
                item_name, item_desc, author=item_author,
                lore=lore, properties=properties,
                tags=tags or None, rarity=rarity,
                tier=tier, legality=legality,
                metadata={"source_proposal": proposal_id},
            )
        except ItemValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = item.to_dict()
        result["source_proposal"] = proposal_id
        return result

    @application.post("/api/proposals/{proposal_id}/handoff-law")
    def api_proposal_handoff_law(proposal_id: str) -> dict[str, Any]:
        """Create a draft law from an approved law proposal.

        Reads law_data from proposal.metadata and creates a new
        Law in draft status.  The proposal must be:
          - category == 'law'
          - status == 'decided'
          - vote tally == approved
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, VoteNotFoundError
        from core.laws import LawManager, LawValidationError

        pmgr = ProposalManager()
        try:
            proposal = pmgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Proposal '{proposal_id}' not found.",
            )

        if proposal.category != "law":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' is not a law proposal (category: {proposal.category}).",
            )

        if proposal.status != "decided":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' has not been decided yet (status: {proposal.status}).",
            )

        # Verify vote was approved
        engine = VotingEngine()
        try:
            tally = engine.tally(proposal_id)
        except VoteNotFoundError:
            raise HTTPException(
                status_code=400,
                detail=f"No vote record found for proposal '{proposal_id}'.",
            )

        if not tally.approved:
            raise HTTPException(
                status_code=400,
                detail=f"Proposal '{proposal_id}' was not approved.",
            )

        # Extract law_data from proposal metadata
        ld = (proposal.metadata or {}).get("law_data", {})
        law_title = ld.get("title", "").strip() or proposal.title
        law_desc = ld.get("description", "").strip() or proposal.description
        law_author = proposal.author
        law_body = ld.get("body", "").strip() or proposal.body
        tags = ld.get("tags", [])

        lmgr = LawManager()
        try:
            law = lmgr.create(
                law_title, law_desc, author=law_author,
                body=law_body, source_proposal_id=proposal_id,
                tags=tags or None,
                metadata={"source_proposal": proposal_id},
            )
        except LawValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = law.to_dict()
        result["source_proposal"] = proposal_id
        return result

    # ── Discussion Info ───────────────────────────────────────

    @application.get("/api/proposals/{proposal_id}/discussion")
    def api_proposal_discussion(proposal_id: str) -> dict[str, Any]:
        """Get the discussion record for a proposal."""
        from core.discussion import DiscussionNotFoundError

        dmgr = _make_discussion_manager()

        try:
            record = dmgr.get(proposal_id)
        except DiscussionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No discussion for proposal '{proposal_id}'.",
            )

        return record.to_dict()

    # ── Votes ─────────────────────────────────────────────────

    @application.get("/api/votes")
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
                rec_dict["tally"] = None
            result.append(rec_dict)
        return result

    @application.get("/api/votes/{proposal_id}")
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

    @application.post("/api/votes/{proposal_id}/veto")
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

    @application.post("/api/votes/{proposal_id}/lift-veto")
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

    @application.get("/api/characters")
    def api_characters_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List characters with optional filters."""
        from core.characters import CharacterManager
        from config.settings import CHARACTER_AVATARS_DIR
        mgr = CharacterManager()
        items = mgr.list_characters(status=status, author=author, tag=tag)
        result = []
        for c in items:
            d = c.to_dict()
            avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
            if avatar_file.exists():
                d["avatar_url"] = f"/api/characters/{c.id}/avatar"
            result.append(d)
        return result

    @application.get("/api/characters/{character_id}")
    def api_character_detail(character_id: str) -> dict[str, Any]:
        """Get a single character template."""
        from core.characters import CharacterManager, CharacterNotFoundError
        from config.settings import CHARACTER_AVATARS_DIR
        mgr = CharacterManager()
        try:
            c = mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        d = c.to_dict()
        avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
        if avatar_file.exists():
            d["avatar_url"] = f"/api/characters/{c.id}/avatar"
        return d

    @application.post("/api/characters")
    def api_character_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new character.

        Body: {"name": "...", "description": "...", "author": "...",
               "backstory": "...", "system_prompt": "...", "greeting": "...",
               "example_messages": [...], "tags": [...],
               "traits": [{"trait_type": "...", "name": "...",
                            "description": "...", "intensity": 0.8}]}
        """
        from core.characters import (
            CharacterManager, CharacterValidationError, Trait,
        )

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        author = body.get("author", "").strip()
        backstory = body.get("backstory", "").strip()
        system_prompt = body.get("system_prompt", "").strip()
        greeting = body.get("greeting", "").strip()
        example_messages = body.get("example_messages", [])
        tags = body.get("tags", [])
        raw_traits = body.get("traits", [])
        api_provider = body.get("api_provider", "openrouter").strip() or "openrouter"
        model = body.get("model", "Default").strip() or "Default"

        if not name or not description or not author:
            raise HTTPException(
                status_code=400,
                detail="Fields 'name', 'description', and 'author' are required.",
            )

        # Parse traits
        traits: list[Trait] = []
        for t in raw_traits:
            try:
                traits.append(Trait.create(
                    trait_type=t.get("trait_type", "personality"),
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    intensity=float(t.get("intensity", 0.5)),
                ))
            except CharacterValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        mgr = CharacterManager()
        try:
            char = mgr.create(
                name, description, author=author, backstory=backstory,
                traits=traits or None, system_prompt=system_prompt,
                greeting=greeting, example_messages=example_messages or None,
                tags=tags or None,
                api_provider=api_provider, model=model,
            )
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return char.to_dict()

    @application.put("/api/characters/{character_id}")
    def api_character_update(
        character_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update mutable fields on a character.

        Body may contain: name, description, backstory, system_prompt,
        greeting, example_messages, tags, metadata.
        """
        from core.characters import (
            CharacterManager, CharacterNotFoundError, CharacterValidationError,
        )
        mgr = CharacterManager()
        try:
            char = mgr.update(character_id, **body)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return char.to_dict()

    @application.put("/api/characters/{character_id}/status")
    def api_character_status(
        character_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Transition a character's lifecycle status.

        Body: {"status": "active"}
        """
        from core.characters import (
            CharacterManager, CharacterNotFoundError,
            CharacterValidationError, CharacterLifecycleError,
        )

        new_status = body.get("status", "").strip()
        if not new_status:
            raise HTTPException(status_code=400, detail="'status' is required.")

        mgr = CharacterManager()
        try:
            char = mgr.update_status(character_id, new_status)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except (CharacterValidationError, CharacterLifecycleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return char.to_dict()

    @application.post("/api/characters/{character_id}/avatar-upload")
    def api_character_avatar_upload(
        character_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Upload avatar as base64 JSON.

        Body: {"image_data": "data:image/png;base64,..."}
        """
        import base64
        from config.settings import CHARACTER_AVATARS_DIR
        from core.characters import CharacterManager, CharacterNotFoundError

        mgr = CharacterManager()
        try:
            mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )

        image_data = body.get("image_data", "")
        if not image_data:
            raise HTTPException(status_code=400, detail="'image_data' is required.")

        try:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data.")

        CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
        with open(avatar_path, "wb") as f:
            f.write(raw_bytes)

        return {
            "status": "ok",
            "avatar_url": f"/api/characters/{character_id}/avatar",
        }

    @application.get("/api/characters/{character_id}/avatar")
    def api_character_avatar_get(character_id: str):
        """Serve a character's avatar PNG."""
        from config.settings import CHARACTER_AVATARS_DIR
        from core.characters import CharacterManager, CharacterNotFoundError

        mgr = CharacterManager()
        try:
            mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )

        avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
        if not avatar_path.exists():
            raise HTTPException(
                status_code=404, detail="No avatar uploaded for this character.",
            )

        return FileResponse(str(avatar_path), media_type="image/png")

    @application.get("/api/characters/{character_id}/export-png")
    def api_character_export_png(character_id: str):
        """Export a character as a PNG with embedded TavernCard v2 metadata.

        If the character has an avatar, that image is used as the base PNG.
        Otherwise a minimal placeholder PNG is generated.
        """
        from config.settings import CHARACTER_AVATARS_DIR
        from core.characters import CharacterManager, CharacterNotFoundError
        from core.png_embed import (
            embed_character_in_png, create_minimal_png,
        )

        mgr = CharacterManager()
        try:
            char = mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )

        # Use avatar if exists, otherwise minimal placeholder
        avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
        if avatar_path.exists():
            png_bytes = avatar_path.read_bytes()
        else:
            png_bytes = create_minimal_png()

        result_bytes = embed_character_in_png(png_bytes, char)

        from starlette.responses import Response
        safe_name = char.name.replace(" ", "_").replace("/", "_")
        return Response(
            content=result_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}.png"',
            },
        )

    @application.post("/api/characters/{character_id}/export-png")
    def api_character_export_png_upload(
        character_id: str, body: dict[str, Any],
    ):
        """Export a character as a PNG with embedded TavernCard v2 metadata,
        using a user-supplied PNG as the base image.

        Body: {"image_data": "data:image/png;base64,..."}
        Returns the embedded PNG named jericho_<character_name>.png.
        """
        import base64
        from core.characters import CharacterManager, CharacterNotFoundError
        from core.png_embed import embed_character_in_png

        mgr = CharacterManager()
        try:
            char = mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )

        image_data = body.get("image_data", "")
        if not image_data:
            raise HTTPException(status_code=400, detail="'image_data' is required.")

        try:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            png_bytes = base64.b64decode(image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data.")

        if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid PNG.")

        result_bytes = embed_character_in_png(png_bytes, char)

        from starlette.responses import Response
        safe_name = char.name.replace(" ", "_").replace("/", "_")
        filename = f"jericho_{safe_name}.png"
        return Response(
            content=result_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # ── Character Traits ──────────────────────────────────────

    @application.post("/api/characters/{character_id}/traits")
    def api_character_add_trait(
        character_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a trait to a character.

        Body: {"trait_type": "personality", "name": "Curious",
               "description": "Always asking questions", "intensity": 0.8}
        """
        from core.characters import (
            CharacterManager, CharacterNotFoundError,
            CharacterValidationError, Trait,
        )

        mgr = CharacterManager()
        try:
            trait = Trait.create(
                trait_type=body.get("trait_type", "personality"),
                name=body.get("name", "").strip(),
                description=body.get("description", "").strip(),
                intensity=float(body.get("intensity", 0.5)),
            )
            char = mgr.add_trait(character_id, trait)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return char.to_dict()

    @application.delete("/api/characters/{character_id}/traits/{trait_name}")
    def api_character_remove_trait(
        character_id: str, trait_name: str,
    ) -> dict[str, Any]:
        """Remove a trait from a character by name."""
        from core.characters import (
            CharacterManager, CharacterNotFoundError,
            CharacterValidationError,
        )

        mgr = CharacterManager()
        try:
            char = mgr.remove_trait(character_id, trait_name)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return char.to_dict()

    # ── Tasks ─────────────────────────────────────────────────

    @application.get("/api/tasks")
    def api_tasks_list(
        status: str | None = Query(None),
        assignee: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List tasks with optional filters."""
        from core.tasks import TaskManager

        mgr = TaskManager()
        tasks = mgr.list_tasks(status=status, assignee=assignee)
        return [t.to_dict() for t in tasks]

    @application.get("/api/tasks/{task_id}")
    def api_task_detail(task_id: str) -> dict[str, Any]:
        """Get a single task by ID."""
        from core.tasks import TaskManager, TaskNotFoundError

        mgr = TaskManager()
        try:
            task = mgr.get(task_id)
        except TaskNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found.",
            )
        return task.to_dict()

    @application.post("/api/tasks")
    def api_tasks_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new task.

        Body: {name, description, reason, assignees: [...]}
        """
        from core.tasks import TaskManager, TaskValidationError

        name = (body.get("name", "") or "").strip()
        description = (body.get("description", "") or "").strip()
        reason = (body.get("reason", "") or "").strip()
        assignees = body.get("assignees", [])

        mgr = TaskManager()
        try:
            task = mgr.create(
                name=name,
                description=description,
                reason=reason,
                assignees=assignees,
            )
        except TaskValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return task.to_dict()

    @application.put("/api/tasks/{task_id}")
    def api_task_update(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update mutable fields of a task."""
        from core.tasks import (
            TaskManager, TaskNotFoundError, TaskValidationError,
        )

        mgr = TaskManager()
        try:
            task = mgr.update(task_id, **body)
        except TaskNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found.",
            )
        except TaskValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return task.to_dict()

    @application.put("/api/tasks/{task_id}/status")
    def api_task_status(
        task_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Change task status. Body: {\"status\": \"active\"}."""
        from core.tasks import (
            TaskManager, TaskNotFoundError,
            TaskValidationError, TaskLifecycleError,
        )

        new_status = (body.get("status", "") or "").strip()
        if not new_status:
            raise HTTPException(
                status_code=400, detail="'status' is required.",
            )

        mgr = TaskManager()
        try:
            task = mgr.update_status(task_id, new_status)
        except TaskNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found.",
            )
        except (TaskValidationError, TaskLifecycleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return task.to_dict()

    @application.post("/api/tasks/do-tasks")
    async def api_tasks_do_tasks() -> StreamingResponse:
        """Execute all active tasks via SSE.

        For each active task, for each assignee, send a prompt that
        additively layers the task context on top of existing memory
        and context injections.  Each assignee narrates completing
        the task over up to 5 rounds.  After all rounds, the task
        transitions to 'completed'.
        """
        from core.tasks import TaskManager, Task, TaskMessage
        from core.api_client import APIClient, ChatMessage
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager
        from core.memory_influence import MemoryInfluence
        from core.memory import AgentMemory, MemoryEntry
        from config.settings import TASK_MAX_ROUNDS
        import asyncio

        async def event_generator():
            try:
                tmgr = TaskManager()
                active_tasks = tmgr.list_tasks(status="active")

                if not active_tasks:
                    err = json_module.dumps({"detail": "No active tasks."})
                    yield f"event: error\ndata: {err}\n\n"
                    return

                registry = CouncilRegistry().load()
                client = APIClient()
                mi = MemoryInfluence()

                # Pre-load characters for character assignees
                try:
                    cmgr = CharacterManager()
                    all_chars = cmgr.list_characters(status="active")
                    char_map = {c.name.lower(): c for c in all_chars}
                except Exception:
                    char_map = {}

                # Council member names for lookup
                member_names = {
                    m.name.lower(): m for m in registry.list_members()
                }

                for task in active_tasks:
                    # Signal task start
                    task_start = json_module.dumps({
                        "type": "task_start",
                        "task_id": task.id,
                        "task_name": task.name,
                        "assignees": task.assignees,
                    })
                    yield f"event: task_start\ndata: {task_start}\n\n"

                    new_messages: list[TaskMessage] = []
                    keywords = MemoryInfluence.extract_keywords(
                        f"{task.name} {task.description} {task.reason}"
                    )

                    for round_num in range(1, TASK_MAX_ROUNDS + 1):
                        for assignee_name in task.assignees:
                            assignee_lower = assignee_name.lower()

                            # Determine if this is a council member or character
                            member = member_names.get(assignee_lower)
                            character = char_map.get(assignee_lower)

                            if not member and not character:
                                # Skip unknown assignees
                                continue

                            # Build additive memory context
                            memory_text = ""
                            ctx = mi.build_context(
                                member.name if member else assignee_name,
                                keywords,
                            )
                            if ctx.formatted_text:
                                memory_text = ctx.formatted_text

                            # Build task prompt — additive on top of existing
                            # context (memory + beliefs + world)
                            prior_narration = ""
                            all_msgs = list(task.messages) + new_messages
                            relevant = [
                                m for m in all_msgs
                                if m.speaker.lower() == assignee_lower
                            ]
                            if relevant:
                                prior_narration = "\n".join(
                                    f"[Round {m.round_number}]: {m.content}"
                                    for m in relevant[-3:]
                                )

                            task_prompt = (
                                f"{memory_text}\n\n"
                                f"---\n\n"
                                f"## Active Task Assignment\n"
                                f"**Task:** {task.name}\n"
                                f"**Description:** {task.description}\n"
                                f"**Reason:** {task.reason}\n"
                                f"**Round:** {round_num} of {TASK_MAX_ROUNDS}\n\n"
                            )

                            if prior_narration:
                                task_prompt += (
                                    f"### Your Previous Progress\n"
                                    f"{prior_narration}\n\n"
                                )

                            if round_num < TASK_MAX_ROUNDS:
                                task_prompt += (
                                    f"You are **{assignee_name}**. "
                                    f"Narrate yourself working on and making progress towards completing this task. "
                                    f"Stay in character. Describe your actions, thoughts, and progress. "
                                    f"This is round {round_num} of {TASK_MAX_ROUNDS}."
                                )
                            else:
                                task_prompt += (
                                    f"You are **{assignee_name}**. "
                                    f"This is the FINAL round ({round_num} of {TASK_MAX_ROUNDS}). "
                                    f"Narrate yourself completing this task. "
                                    f"Wrap up your work and describe the final outcome. "
                                    f"Stay in character."
                                )

                            messages = [ChatMessage(role="user", content=task_prompt)]

                            try:
                                if member:
                                    response = await client.chat(member, messages)
                                elif character:
                                    # Build a pseudo-member for character
                                    from core.registry import CouncilMember
                                    char_member = CouncilMember(
                                        name=character.name,
                                        role="Character",
                                        description=character.description,
                                        personality={},
                                        api_provider=character.metadata.get(
                                            "api_provider", "openrouter"
                                        ),
                                        model=character.metadata.get(
                                            "model", "Default"
                                        ),
                                        vote_weight=0.0,
                                        specialties=[],
                                        system_prompt=character.system_prompt
                                        or f"You are {character.name}. {character.description}",
                                        source_file="",
                                    )
                                    response = await client.chat(char_member, messages)
                                else:
                                    continue

                                content = response.content or ""

                                msg = TaskMessage.create(
                                    speaker=assignee_name,
                                    content=content,
                                    round_number=round_num,
                                    model=response.model,
                                    provider=response.provider,
                                    task_id=task.id,
                                )
                                new_messages.append(msg)

                                # Persist to assignee's individual memory
                                try:
                                    mem = AgentMemory(assignee_name)
                                    mem.append_session_event(
                                        MemoryEntry.create(
                                            session_id=f"task-{task.id}",
                                            event_type="task_narration",
                                            content=content,
                                            source=assignee_name,
                                            metadata={
                                                "task_id": task.id,
                                                "task_name": task.name,
                                                "round": round_num,
                                                "model": response.model,
                                                "provider": response.provider,
                                            },
                                        )
                                    )
                                except Exception:
                                    pass  # non-fatal

                                # Stream this message
                                event_data = json_module.dumps({
                                    "type": "message",
                                    "task_id": task.id,
                                    "speaker": assignee_name,
                                    "content": content,
                                    "round": round_num,
                                    "model": response.model,
                                    "provider": response.provider,
                                })
                                yield f"event: message\ndata: {event_data}\n\n"

                            except Exception as exc:
                                error_data = json_module.dumps({
                                    "type": "error",
                                    "task_id": task.id,
                                    "speaker": assignee_name,
                                    "detail": str(exc)[:200],
                                })
                                yield f"event: message\ndata: {error_data}\n\n"

                            await asyncio.sleep(0.5)

                    # Save messages and mark completed
                    all_messages = list(task.messages) + new_messages
                    d = task.to_dict()
                    d["messages"] = [m.to_dict() for m in all_messages]
                    d["current_round"] = TASK_MAX_ROUNDS
                    d["status"] = "completed"
                    from core.tasks import Task as TaskModel
                    updated = TaskModel.from_dict(d)
                    tmgr._save(updated)

                    task_done = json_module.dumps({
                        "type": "task_done",
                        "task_id": task.id,
                        "task_name": task.name,
                        "status": "completed",
                        "total_messages": len(new_messages),
                    })
                    yield f"event: task_done\ndata: {task_done}\n\n"

                # All tasks done
                done_data = json_module.dumps({
                    "type": "all_done",
                    "tasks_completed": len(active_tasks),
                })
                yield f"event: done\ndata: {done_data}\n\n"

            except Exception as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Locations ─────────────────────────────────────────────

    @application.get("/api/locations")
    def api_locations_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
        parent_location_id: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List locations with optional filters."""
        from core.locations import LocationManager
        mgr = LocationManager()
        items = mgr.list_locations(
            status=status, author=author, tag=tag,
            parent_location_id=parent_location_id,
        )
        return [loc.to_dict() for loc in items]

    @application.get("/api/locations/{location_id}")
    def api_location_detail(location_id: str) -> dict[str, Any]:
        """Get a single location."""
        from core.locations import LocationManager, LocationNotFoundError
        mgr = LocationManager()
        try:
            loc = mgr.get(location_id)
        except LocationNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_id}' not found.",
            )
        return loc.to_dict()

    @application.post("/api/locations")
    def api_location_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new location.

        Body: {"name": "...", "description": "...", "author": "...",
               "lore": "...", "features": [...], "tags": [...],
               "parent_location_id": "...", "coordinates": "..."}
        """
        from core.locations import (
            LocationManager, LocationValidationError, LocationFeature,
        )

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        author = body.get("author", "").strip()
        lore = body.get("lore", "").strip()
        raw_features = body.get("features", [])
        tags = body.get("tags", [])
        parent = body.get("parent_location_id", "")
        coords = body.get("coordinates", "")

        if not name or not description or not author:
            raise HTTPException(
                status_code=400,
                detail="Fields 'name', 'description', and 'author' are required.",
            )

        # Parse features
        features = []
        for f in raw_features:
            try:
                features.append(LocationFeature.create(
                    name=f.get("name", ""),
                    description=f.get("description", ""),
                    feature_type=f.get("feature_type", "custom"),
                ))
            except LocationValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        mgr = LocationManager()
        try:
            loc = mgr.create(
                name, description, author=author, lore=lore,
                features=features, tags=tags,
                parent_location_id=parent, coordinates=coords,
            )
        except LocationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return loc.to_dict()

    @application.put("/api/locations/{location_id}")
    def api_location_update(location_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update mutable fields on a location.

        Body may contain: name, description, lore, tags, metadata,
        parent_location_id, coordinates.
        """
        from core.locations import LocationManager, LocationNotFoundError, LocationValidationError
        mgr = LocationManager()
        try:
            loc = mgr.update(location_id, **body)
        except LocationNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_id}' not found.",
            )
        except LocationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return loc.to_dict()

    @application.put("/api/locations/{location_id}/status")
    def api_location_status(
        location_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Transition a location's lifecycle status.

        Body: {"status": "active"}
        """
        from core.locations import (
            LocationManager, LocationNotFoundError,
            LocationValidationError, LocationLifecycleError,
        )

        new_status = body.get("status", "").strip()
        if not new_status:
            raise HTTPException(status_code=400, detail="'status' is required.")

        mgr = LocationManager()
        try:
            loc = mgr.update_status(location_id, new_status)
        except LocationNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_id}' not found.",
            )
        except (LocationValidationError, LocationLifecycleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return loc.to_dict()

    # ── Items ─────────────────────────────────────────────────

    @application.get("/api/items")
    def api_items_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List items with optional filters."""
        from core.items import ItemManager
        mgr = ItemManager()
        results = mgr.list_items(status=status, author=author, tag=tag)
        return [item.to_dict() for item in results]

    @application.get("/api/items/{item_id}")
    def api_item_detail(item_id: str) -> dict[str, Any]:
        """Get a single item."""
        from core.items import ItemManager, ItemNotFoundError
        mgr = ItemManager()
        try:
            item = mgr.get(item_id)
        except ItemNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Item '{item_id}' not found.",
            )
        return item.to_dict()

    @application.post("/api/items")
    def api_item_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new item.

        Body: {"name": "...", "description": "...", "author": "...",
               "lore": "...", "properties": [...], "tags": [...],
               "rarity": "...", "tier": "..."}
        """
        from core.items import (
            ItemManager, ItemValidationError, ItemProperty,
        )

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        author = body.get("author", "").strip()
        lore = body.get("lore", "").strip()
        raw_properties = body.get("properties", [])
        tags = body.get("tags", [])
        rarity = body.get("rarity", "").strip()
        tier = body.get("tier", "").strip()
        legality = body.get("legality", "").strip()

        if not name or not description or not author:
            raise HTTPException(
                status_code=400,
                detail="Fields 'name', 'description', and 'author' are required.",
            )

        # Parse properties
        properties = []
        for p in raw_properties:
            try:
                properties.append(ItemProperty.create(
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    property_type=p.get("property_type", "custom"),
                ))
            except ItemValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        mgr = ItemManager()
        try:
            item = mgr.create(
                name, description, author=author, lore=lore,
                properties=properties, tags=tags, rarity=rarity,
                tier=tier, legality=legality,
            )
        except ItemValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return item.to_dict()

    @application.put("/api/items/{item_id}")
    def api_item_update(item_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update mutable fields on an item.

        Body may contain: name, description, lore, tags, metadata, rarity.
        """
        from core.items import ItemManager, ItemNotFoundError, ItemValidationError
        mgr = ItemManager()
        try:
            item = mgr.update(item_id, **body)
        except ItemNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Item '{item_id}' not found.",
            )
        except ItemValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return item.to_dict()

    @application.put("/api/items/{item_id}/status")
    def api_item_status(
        item_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Transition an item's lifecycle status.

        Body: {"status": "active"}
        """
        from core.items import (
            ItemManager, ItemNotFoundError,
            ItemValidationError, ItemLifecycleError,
        )

        new_status = body.get("status", "").strip()
        if not new_status:
            raise HTTPException(status_code=400, detail="'status' is required.")

        mgr = ItemManager()
        try:
            item = mgr.update_status(item_id, new_status)
        except ItemNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Item '{item_id}' not found.",
            )
        except (ItemValidationError, ItemLifecycleError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return item.to_dict()

    # ── Stores ─────────────────────────────────────────────────

    @application.get("/api/stores")
    def api_stores_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
        store_type: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List stores with optional filters."""
        from core.stores import StoreManager
        mgr = StoreManager()
        results = mgr.list_stores(
            status=status, author=author, tag=tag, store_type=store_type,
        )
        return [s.to_dict() for s in results]

    @application.get("/api/stores/{store_id}")
    def api_store_detail(store_id: str) -> dict[str, Any]:
        """Get a single store with full inventory."""
        from core.stores import StoreManager, StoreNotFoundError
        mgr = StoreManager()
        try:
            store = mgr.get(store_id)
        except StoreNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Store '{store_id}' not found.",
            )
        return store.to_dict()

    @application.post("/api/stores")
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
            )
        except StoreValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return store.to_dict()

    @application.put("/api/stores/{store_id}")
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

    @application.post("/api/stores/{store_id}/status")
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

    @application.post("/api/stores/{store_id}/inventory")
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

    @application.delete("/api/stores/{store_id}/inventory/{item_id}")
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

    @application.put("/api/stores/{store_id}/inventory/{item_id}")
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

    @application.post("/api/stores/{store_id}/purchase")
    def api_store_purchase(
        store_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Purchase an item from a store.

        Body: {"item_id": "ITEM-0001", "buyer_account_id": "ACCT-user-human"}

        Debits the buyer's treasury account and credits the store owner.
        Decrements quantity if not unlimited.
        """
        from core.stores import (
            StoreManager, StoreNotFoundError, StorePurchaseError,
        )
        from core.treasury import TreasuryManager

        item_id = (body.get("item_id") or "").strip()
        buyer_account_id = (body.get("buyer_account_id") or "").strip()

        if not item_id or not buyer_account_id:
            raise HTTPException(
                status_code=400,
                detail="'item_id' and 'buyer_account_id' are required.",
            )

        mgr = StoreManager()
        tmgr = TreasuryManager()
        try:
            result = mgr.purchase(store_id, item_id, buyer_account_id, tmgr)
        except StoreNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Store '{store_id}' not found.",
            )
        except StorePurchaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result


    # ── Analytics ─────────────────────────────────────────────

    @application.get("/api/analytics")
    def api_analytics() -> dict[str, Any]:
        """Full analytics report."""
        from core.analytics import SessionAnalytics
        from core.proposals import ProposalManager
        from core.voting import VotingEngine

        pmgr = ProposalManager()
        engine = VotingEngine()
        sa = SessionAnalytics(proposal_manager=pmgr, voting_engine=engine)
        report = sa.full_report()
        return report.to_dict()

    # ── Settings / API Keys ───────────────────────────────────

    @application.get("/api/settings/keys")
    def api_keys_status() -> list[dict[str, Any]]:
        """Return configuration status for each API provider (never raw keys)."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        return mgr.all_status()

    @application.post("/api/settings/keys")
    def api_keys_save(body: dict[str, Any]) -> dict[str, Any]:
        """Encrypt and save an API key.  Body: {"provider": "openrouter", "api_key": "sk-..."}."""
        from core.api_keys import APIKeyManager
        provider = body.get("provider", "").strip().lower()
        raw_key = body.get("api_key", "").strip()

        if not provider or not raw_key:
            raise HTTPException(status_code=400, detail="Both 'provider' and 'api_key' are required.")

        mgr = APIKeyManager()
        try:
            result = mgr.save_key(provider, raw_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    @application.delete("/api/settings/keys/{provider}")
    def api_keys_delete(provider: str) -> dict[str, Any]:
        """Remove a configured API key."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        try:
            result = mgr.delete_key(provider)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    # ── Settings / Models ─────────────────────────────────────
    # NOTE: Settings models are the *fallback default*. A council member's
    # own model takes priority unless set to "Default".

    @application.get("/api/settings/models")
    def api_models_status() -> list[dict[str, Any]]:
        """Return configured default model for each API provider."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        return mgr.all_model_status()

    @application.post("/api/settings/models")
    def api_models_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save a default model name.  Body: {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet"}."""
        from core.api_keys import APIKeyManager
        provider = body.get("provider", "").strip().lower()
        model = body.get("model", "").strip()

        if not provider or not model:
            raise HTTPException(status_code=400, detail="Both 'provider' and 'model' are required.")

        mgr = APIKeyManager()
        try:
            result = mgr.save_model(provider, model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    @application.get("/api/settings/mancer-models")
    def api_mancer_models() -> list[str]:
        """Return the list of valid Mancer model options for dropdown menus."""
        from config.settings import MANCER_MODEL_OPTIONS
        return list(MANCER_MODEL_OPTIONS)

    @application.get("/api/settings/openrouter-models")
    def api_openrouter_models() -> list[str]:
        """Return the list of valid OpenRouter model options for dropdown menus."""
        from config.settings import OPENROUTER_MODEL_OPTIONS
        return list(OPENROUTER_MODEL_OPTIONS)

    @application.get("/api/settings/lmstudio-models")
    def api_lmstudio_models() -> list[str]:
        """Return the list of valid LM Studio model options for dropdown menus."""
        from config.settings import LMSTUDIO_MODEL_OPTIONS
        return list(LMSTUDIO_MODEL_OPTIONS)

    @application.get("/api/settings/summarization")
    def api_summarization_config() -> dict[str, Any]:
        """Return the current summarization LLM configuration."""
        from config.settings import (
            DEFAULT_SUMMARIZATION_PROVIDER,
            DEFAULT_SUMMARIZATION_MODEL,
            SUMMARIZATION_PROVIDER_ENV,
            SUMMARIZATION_MODEL_ENV,
        )
        import os
        provider = (
            os.environ.get(SUMMARIZATION_PROVIDER_ENV, "").strip()
            or DEFAULT_SUMMARIZATION_PROVIDER
        )
        model = (
            os.environ.get(SUMMARIZATION_MODEL_ENV, "").strip()
            or DEFAULT_SUMMARIZATION_MODEL
        )
        return {"provider": provider, "model": model}

    @application.post("/api/settings/summarization")
    def api_summarization_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save summarization provider and model.

        Body: {"provider": "openrouter", "model": "mistralai/mistral-small-2603"}
        """
        from core.api_keys import APIKeyManager
        provider = body.get("provider", "").strip().lower()
        model = body.get("model", "").strip()

        if not provider or not model:
            raise HTTPException(
                status_code=400,
                detail="Both 'provider' and 'model' are required.",
            )
        if provider not in ("openrouter", "mancer", "lmstudio"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{provider}'. Must be 'openrouter', 'mancer', or 'lmstudio'.",
            )

        from config.settings import (
            SUMMARIZATION_PROVIDER_ENV,
            SUMMARIZATION_MODEL_ENV,
        )
        import os
        os.environ[SUMMARIZATION_PROVIDER_ENV] = provider
        os.environ[SUMMARIZATION_MODEL_ENV] = model

        # Also persist to .env via APIKeyManager
        mgr = APIKeyManager()
        mgr.save_env_value(SUMMARIZATION_PROVIDER_ENV, provider)
        mgr.save_env_value(SUMMARIZATION_MODEL_ENV, model)

        return {"provider": provider, "model": model, "saved": True}

    @application.get("/api/settings/summarization-models")
    def api_summarization_models(
        provider: str = Query("openrouter"),
    ) -> list[str]:
        """Return the list of summarization model options for a provider."""
        from config.settings import (
            SUMMARIZATION_OPENROUTER_MODELS,
            SUMMARIZATION_MANCER_MODELS,
        )
        if provider == "mancer":
            return list(SUMMARIZATION_MANCER_MODELS)
        if provider == "lmstudio":
            from config.settings import SUMMARIZATION_LMSTUDIO_MODELS
            return list(SUMMARIZATION_LMSTUDIO_MODELS)
        return list(SUMMARIZATION_OPENROUTER_MODELS)

    # ── Settings / User Description ───────────────────────────

    @application.get("/api/settings/user-description")
    def api_user_description_get() -> dict[str, Any]:
        """Return the user's self-description."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        return {"description": mgr.get_user_description()}

    @application.post("/api/settings/user-description")
    def api_user_description_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save the user's self-description.  Body: {"description": "..."}."""
        from core.api_keys import APIKeyManager
        text = body.get("description", "")

        mgr = APIKeyManager()
        try:
            result = mgr.save_user_description(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    # ── Settings / User Name ─────────────────────────────────

    @application.get("/api/settings/user-name")
    def api_user_name_get() -> dict[str, Any]:
        """Return the user's display name."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        return {"name": mgr.get_user_name()}

    @application.post("/api/settings/user-name")
    def api_user_name_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save the user's display name.  Body: {"name": "..."}."""
        from core.api_keys import APIKeyManager
        name = body.get("name", "")

        mgr = APIKeyManager()
        try:
            result = mgr.save_user_name(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return result

    # ── Settings / ComfyUI ────────────────────────────────────

    @application.get("/api/settings/comfyui")
    def api_comfyui_config_get() -> dict[str, Any]:
        """Return current ComfyUI connection configuration."""
        from config.settings import (
            COMFYUI_DEFAULT_HOST,
            COMFYUI_DEFAULT_PORT,
            COMFYUI_HOST_ENV,
            COMFYUI_PORT_ENV,
        )
        import os
        host = os.environ.get(COMFYUI_HOST_ENV, "").strip() or COMFYUI_DEFAULT_HOST
        port_str = os.environ.get(COMFYUI_PORT_ENV, "").strip()
        try:
            port = int(port_str) if port_str else COMFYUI_DEFAULT_PORT
        except ValueError:
            port = COMFYUI_DEFAULT_PORT
        return {"host": host, "port": port}

    @application.post("/api/settings/comfyui")
    def api_comfyui_config_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save ComfyUI connection config.

        Body: {"host": "127.0.0.1", "port": 8188}
        """
        from config.settings import COMFYUI_HOST_ENV, COMFYUI_PORT_ENV
        from core.api_keys import APIKeyManager
        import os

        host = (body.get("host") or "").strip()
        port_raw = body.get("port", "")
        if not host:
            raise HTTPException(status_code=400, detail="'host' is required.")
        try:
            port = int(port_raw)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="'port' must be an integer.")
        if port < 1 or port > 65535:
            raise HTTPException(
                status_code=400,
                detail=f"Port must be between 1 and 65535, got {port}.",
            )

        os.environ[COMFYUI_HOST_ENV] = host
        os.environ[COMFYUI_PORT_ENV] = str(port)

        mgr = APIKeyManager()
        mgr.save_env_value(COMFYUI_HOST_ENV, host)
        mgr.save_env_value(COMFYUI_PORT_ENV, str(port))

        return {"host": host, "port": port, "saved": True}

    @application.post("/api/settings/comfyui/test")
    def api_comfyui_test() -> dict[str, Any]:
        """Test connection to ComfyUI server.

        Uses the currently configured host/port.
        """
        import asyncio
        from config.settings import (
            COMFYUI_DEFAULT_HOST,
            COMFYUI_DEFAULT_PORT,
            COMFYUI_HOST_ENV,
            COMFYUI_PORT_ENV,
        )
        from core.comfyui_client import (
            ComfyUIClient,
            ComfyUIConfig,
            ComfyUIConnectionError,
        )
        import os

        host = os.environ.get(COMFYUI_HOST_ENV, "").strip() or COMFYUI_DEFAULT_HOST
        port_str = os.environ.get(COMFYUI_PORT_ENV, "").strip()
        try:
            port = int(port_str) if port_str else COMFYUI_DEFAULT_PORT
        except ValueError:
            port = COMFYUI_DEFAULT_PORT

        config = ComfyUIConfig(host=host, port=port)

        async def _test():
            async with ComfyUIClient(config, timeout=5.0) as client:
                return await client.test_connection()

        try:
            stats = asyncio.run(_test())
            return {
                "connected": True,
                "host": host,
                "port": port,
                "system_stats": stats,
            }
        except ComfyUIConnectionError as exc:
            return {
                "connected": False,
                "host": host,
                "port": port,
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "connected": False,
                "host": host,
                "port": port,
                "error": f"Unexpected error: {exc}",
            }

    @application.get("/api/settings/comfyui/templates")
    def api_comfyui_templates_list(
        entity_type: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List all workflow templates."""
        from core.comfyui_client import WorkflowTemplateManager
        mgr = WorkflowTemplateManager()
        templates = mgr.list_templates(entity_type=entity_type)
        # Return summary (omit full workflow_json for list view)
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "entity_type": t.entity_type,
                "author": t.author,
                "placeholders": t.placeholders,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in templates
        ]

    @application.post("/api/settings/comfyui/templates")
    def api_comfyui_template_create(body: dict[str, Any]) -> dict[str, Any]:
        """Upload a new workflow template.

        Body: {"name": "...", "workflow_json": {...},
               "description": "", "entity_type": "", "author": ""}
        """
        from core.comfyui_client import (
            WorkflowTemplateManager,
            TemplateValidationError,
        )
        name = (body.get("name") or "").strip()
        workflow_json = body.get("workflow_json")
        description = (body.get("description") or "").strip()
        entity_type = (body.get("entity_type") or "").strip()
        author = (body.get("author") or "").strip()

        if not name:
            raise HTTPException(status_code=400, detail="'name' is required.")
        if not workflow_json or not isinstance(workflow_json, dict):
            raise HTTPException(
                status_code=400,
                detail="'workflow_json' must be a non-empty JSON object.",
            )

        mgr = WorkflowTemplateManager()
        try:
            tpl = mgr.create(
                name,
                description=description,
                workflow_json=workflow_json,
                entity_type=entity_type,
                author=author,
            )
        except TemplateValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return tpl.to_dict()

    @application.get("/api/settings/comfyui/templates/{template_id}")
    def api_comfyui_template_get(template_id: str) -> dict[str, Any]:
        """Get a single workflow template with full JSON."""
        from core.comfyui_client import (
            WorkflowTemplateManager,
            TemplateNotFoundError,
        )
        mgr = WorkflowTemplateManager()
        try:
            tpl = mgr.get(template_id)
        except TemplateNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Template '{template_id}' not found.",
            )
        return tpl.to_dict()

    @application.delete("/api/settings/comfyui/templates/{template_id}")
    def api_comfyui_template_delete(template_id: str) -> dict[str, Any]:
        """Delete a workflow template."""
        from core.comfyui_client import (
            WorkflowTemplateManager,
            TemplateNotFoundError,
        )
        mgr = WorkflowTemplateManager()
        try:
            mgr.delete(template_id)
        except TemplateNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Template '{template_id}' not found.",
            )
        return {"deleted": True, "template_id": template_id}

    @application.get("/api/settings/comfyui/style-presets")
    def api_comfyui_style_presets() -> list[dict[str, Any]]:
        """List available prompt style presets (builtins + custom).

        Each entry includes: key, name, description, positive_suffix,
        negative_prefix, is_builtin flag.
        """
        from core.prompt_builder import (
            DEFAULT_STYLE_PRESETS, CustomStylePresetManager,
        )

        results = []

        # Built-in presets
        for key in sorted(DEFAULT_STYLE_PRESETS):
            p = DEFAULT_STYLE_PRESETS[key]
            results.append({
                "key": key,
                "name": p.name,
                "description": p.description,
                "positive_suffix": p.positive_suffix,
                "negative_prefix": p.negative_prefix,
                "is_builtin": True,
            })

        # Custom presets
        try:
            mgr = CustomStylePresetManager()
            for rec in mgr.list_presets():
                results.append({
                    "id": rec["id"],
                    "key": rec["key"],
                    "name": rec["name"],
                    "description": rec.get("description", ""),
                    "positive_suffix": rec.get("positive_suffix", ""),
                    "negative_prefix": rec.get("negative_prefix", ""),
                    "is_builtin": False,
                    "created_at": rec.get("created_at", ""),
                })
        except Exception:
            pass

        return results

    @application.get("/api/settings/comfyui/default-style")
    def api_comfyui_default_style_get() -> dict[str, Any]:
        """Return the current default style preset key."""
        from config.settings import COMFYUI_DEFAULT_STYLE_ENV
        import os
        key = os.environ.get(COMFYUI_DEFAULT_STYLE_ENV, "").strip()
        return {"style_key": key or ""}

    @application.post("/api/settings/comfyui/default-style")
    def api_comfyui_default_style_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save the default style preset key.

        Body: {"style_key": "fantasy_art"}
        """
        from config.settings import COMFYUI_DEFAULT_STYLE_ENV
        from core.api_keys import APIKeyManager
        import os

        style_key = (body.get("style_key") or "").strip()

        # Validate if non-empty
        if style_key:
            from core.prompt_builder import get_style_preset
            if get_style_preset(style_key) is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown style preset '{style_key}'.",
                )

        os.environ[COMFYUI_DEFAULT_STYLE_ENV] = style_key
        mgr = APIKeyManager()
        mgr.save_env_value(COMFYUI_DEFAULT_STYLE_ENV, style_key)

        return {"style_key": style_key, "saved": True}

    # ── Custom Style Presets CRUD (F-037g) ────────────────────

    @application.get("/api/settings/comfyui/presets")
    def api_custom_presets_list() -> list[dict[str, Any]]:
        """List all custom style presets (excludes builtins)."""
        from core.prompt_builder import CustomStylePresetManager
        mgr = CustomStylePresetManager()
        results = []
        for rec in mgr.list_presets():
            # Exclude the StylePreset object (not JSON-serializable)
            entry = {k: v for k, v in rec.items() if k != "preset"}
            results.append(entry)
        return results

    @application.post("/api/settings/comfyui/presets")
    def api_custom_presets_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a custom style preset.

        Body: {
            "key": "cyberpunk",
            "name": "Cyberpunk",
            "description": "Neon-lit dystopian cityscapes",
            "positive_suffix": "cyberpunk, neon, rain",
            "negative_prefix": "nature, medieval, fantasy"
        }
        """
        from core.prompt_builder import (
            CustomStylePresetManager, PromptValidationError,
        )
        mgr = CustomStylePresetManager()
        try:
            record = mgr.create(
                key=body.get("key", ""),
                name=body.get("name", ""),
                description=body.get("description", ""),
                positive_suffix=body.get("positive_suffix", ""),
                negative_prefix=body.get("negative_prefix", ""),
            )
        except PromptValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return record

    @application.get("/api/settings/comfyui/presets/{preset_id}")
    def api_custom_presets_get(preset_id: str) -> dict[str, Any]:
        """Get a custom style preset by ID."""
        from core.prompt_builder import (
            CustomStylePresetManager, PromptValidationError,
        )
        mgr = CustomStylePresetManager()
        try:
            return mgr.get(preset_id)
        except PromptValidationError:
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{preset_id}' not found.",
            )

    @application.put("/api/settings/comfyui/presets/{preset_id}")
    def api_custom_presets_update(
        preset_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a custom style preset.

        Body: Any subset of {name, description, positive_suffix, negative_prefix}
        """
        from core.prompt_builder import (
            CustomStylePresetManager, PromptValidationError,
        )
        mgr = CustomStylePresetManager()
        kwargs: dict[str, Any] = {}
        if "name" in body:
            kwargs["name"] = body["name"]
        if "description" in body:
            kwargs["description"] = body["description"]
        if "positive_suffix" in body:
            kwargs["positive_suffix"] = body["positive_suffix"]
        if "negative_prefix" in body:
            kwargs["negative_prefix"] = body["negative_prefix"]

        try:
            return mgr.update(preset_id, **kwargs)
        except PromptValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @application.delete("/api/settings/comfyui/presets/{preset_id}")
    def api_custom_presets_delete(preset_id: str) -> dict[str, Any]:
        """Delete a custom style preset."""
        from core.prompt_builder import (
            CustomStylePresetManager, PromptValidationError,
        )
        mgr = CustomStylePresetManager()
        try:
            mgr.delete(preset_id)
        except PromptValidationError:
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{preset_id}' not found.",
            )
        return {"deleted": True, "preset_id": preset_id}

    @application.get("/api/settings/comfyui/presets/export")
    def api_custom_presets_export() -> list[dict[str, Any]]:
        """Export all custom presets as JSON."""
        from core.prompt_builder import CustomStylePresetManager
        mgr = CustomStylePresetManager()
        return mgr.export_json()

    @application.post("/api/settings/comfyui/presets/import")
    def api_custom_presets_import(
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Import presets from JSON.

        Body: {"presets": [{key, name, description, positive_suffix, negative_prefix}, ...]}
        """
        from core.prompt_builder import CustomStylePresetManager
        mgr = CustomStylePresetManager()
        presets_data = body.get("presets", [])
        if not isinstance(presets_data, list):
            raise HTTPException(
                status_code=400,
                detail="'presets' must be a list.",
            )
        created = mgr.import_json(presets_data)
        return {
            "imported_count": len(created),
            "presets": created,
        }

    # ── Per-Entity-Type Template Assignments (F-039) ──────────

    @application.get("/api/settings/comfyui/template-assignments")
    def api_template_assignments_get() -> dict[str, str]:
        """Get all per-entity-type template assignments.

        Returns: {"character": "TPL-0001", "location": "", ...}
        """
        from core.template_assignments import TemplateAssignmentManager
        from core.comfyui_client import WorkflowTemplateManager

        mgr = TemplateAssignmentManager(
            template_manager=WorkflowTemplateManager(),
        )
        return mgr.get_all_assignments()

    @application.post("/api/settings/comfyui/template-assignments")
    def api_template_assignments_save(
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Save per-entity-type template assignments.

        Body: {"character": "TPL-0001", "location": "TPL-0002", ...}

        Only valid entity types are accepted; others are ignored.
        """
        from core.template_assignments import (
            TemplateAssignmentManager,
            TemplateAssignmentValidationError,
        )
        from core.comfyui_client import WorkflowTemplateManager

        mgr = TemplateAssignmentManager(
            template_manager=WorkflowTemplateManager(),
        )
        try:
            result = mgr.set_all_assignments(body)
        except TemplateAssignmentValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {"assignments": result, "saved": True}

    @application.delete(
        "/api/settings/comfyui/template-assignments/{entity_type}"
    )
    def api_template_assignments_clear(
        entity_type: str,
    ) -> dict[str, Any]:
        """Clear the template assignment for an entity type."""
        from core.template_assignments import (
            TemplateAssignmentManager,
            TemplateAssignmentValidationError,
        )
        from core.comfyui_client import WorkflowTemplateManager

        mgr = TemplateAssignmentManager(
            template_manager=WorkflowTemplateManager(),
        )
        try:
            result = mgr.clear_assignment(entity_type)
        except TemplateAssignmentValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {"assignments": result, "cleared": entity_type}

    @application.get(
        "/api/settings/comfyui/recommended-template/{entity_type}"
    )
    def api_recommended_template(entity_type: str) -> dict[str, Any]:
        """Get the recommended template for an entity type.

        Uses the smart fallback chain:
        1. Explicit assignment
        2. First template with matching entity_type field
        3. First template overall

        Returns: {"entity_type": "...", "template_id": "...", "source": "..."}
        """
        from core.template_assignments import TemplateAssignmentManager
        from core.comfyui_client import WorkflowTemplateManager

        tmgr = WorkflowTemplateManager()
        mgr = TemplateAssignmentManager(template_manager=tmgr)

        # Determine which fallback was used
        assigned = mgr.get_all_assignments().get(entity_type, "")
        recommended = mgr.get_recommended_template(entity_type)

        if assigned and assigned == recommended:
            source = "assignment"
        elif recommended:
            # Check if it came from entity_type match
            matching = tmgr.list_templates(entity_type=entity_type)
            if matching and matching[0].id == recommended:
                source = "entity_type_match"
            else:
                source = "fallback"
        else:
            source = "none"

        return {
            "entity_type": entity_type,
            "template_id": recommended,
            "source": source,
        }

    @application.post(
        "/api/settings/comfyui/template-assignments/test/{template_id}"
    )
    def api_template_test(template_id: str) -> dict[str, Any]:
        """Test a template's validity and placeholder coverage.

        Returns info about which placeholders the template has
        and whether critical ones (prompt, negative, seed, etc.) are present.
        """
        from core.template_assignments import (
            TemplateAssignmentManager,
            TemplateAssignmentValidationError,
        )
        from core.comfyui_client import WorkflowTemplateManager

        mgr = TemplateAssignmentManager(
            template_manager=WorkflowTemplateManager(),
        )
        try:
            return mgr.test_template(template_id)
        except TemplateAssignmentValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # ── Chat ─────────────────────────────────────────────────

    def _next_chat_id() -> str:
        """Generate the next sequential WC-XXXX chat ID."""
        from config.settings import CONVERSATIONS_DIR
        existing = sorted(CONVERSATIONS_DIR.glob("H-WC-*.json"))
        if not existing:
            return "WC-0001"
        last = existing[-1].stem  # e.g. "H-WC-0042"
        num = int(last.split("-")[-1]) + 1
        return f"WC-{num:04d}"

    def _make_human_chat(
        conversations_dir: Path | None = None,
    ) -> "HumanChat":
        """Instantiate HumanChat with a real registry, API client, and memory influence."""
        from core.api_client import APIClient
        from core.human_chat import HumanChat
        from core.memory_influence import MemoryInfluence
        from core.registry import CouncilRegistry

        registry = CouncilRegistry().load()
        client = APIClient()
        return HumanChat(
            registry=registry,
            api_client=client,
            conversations_dir=conversations_dir,
            memory_influence=MemoryInfluence(),
        )

    def _make_discussion_manager(
        proposal_manager: "ProposalManager | None" = None,
    ) -> "DiscussionManager":
        """Instantiate DiscussionManager with memory influence."""
        from core.api_client import APIClient
        from core.discussion import DiscussionManager
        from core.memory_influence import MemoryInfluence
        from core.proposals import ProposalManager
        from core.registry import CouncilRegistry

        registry = CouncilRegistry().load()
        client = APIClient()
        pmgr = proposal_manager if proposal_manager is not None else ProposalManager()
        return DiscussionManager(
            registry=registry,
            api_client=client,
            proposal_manager=pmgr,
            memory_influence=MemoryInfluence(),
        )

    @application.get("/api/chat")
    def api_chat_list(
        member: str | None = Query(None),
        closed: bool | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List human-to-agent chats with optional filters."""
        hc = _make_human_chat()
        chats = hc.list_chats(member=member, closed=closed)
        return [c.to_dict() for c in chats]

    @application.get("/api/chat/{chat_id}")
    def api_chat_detail(chat_id: str) -> dict[str, Any]:
        """Get a single chat record with messages."""
        from core.human_chat import HumanChatNotFoundError

        hc = _make_human_chat()
        try:
            rec = hc.get(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        return rec.to_dict()

    @application.post("/api/chat")
    def api_chat_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new chat. Body: {\"member_name\": \"Sage\", \"title\": \"...\", \"topic\": \"...\", \"character_id\": \"CH-0001\"}."""
        from core.human_chat import HumanChatValidationError

        member_name = body.get("member_name", "").strip()
        character_id = body.get("character_id", "").strip()
        title = body.get("title", "").strip()
        topic = body.get("topic", "").strip()

        if not title:
            raise HTTPException(
                status_code=400,
                detail="'title' is required.",
            )
        if not member_name and not character_id:
            raise HTTPException(
                status_code=400,
                detail="Either 'member_name' or 'character_id' is required.",
            )

        hc = _make_human_chat()

        chat_id = _next_chat_id()
        try:
            rec = hc.create_chat(
                chat_id, title,
                member_name=member_name,
                character_id=character_id,
                topic=topic,
            )
        except HumanChatValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/send")
    async def api_chat_send(chat_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send a human message and get the agent response(s). Body: {\"content\": \"...\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="'content' is required.")

        hc = _make_human_chat()

        try:
            # Auto-resume if paused (sending a message implies intent to continue)
            rec = hc.get(chat_id)
            if rec.paused:
                hc.resume_chat(chat_id)

            hc.send_human_message(chat_id, content)
            rec, resp = await hc.get_agent_response(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except HumanChatError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {
            "chat": rec.to_dict(),
            "agent_response": resp.content,
        }

    @application.post("/api/chat/{chat_id}/add-member")
    def api_chat_add_member(chat_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Add a council member to the chat. Body: {\"member_name\": \"Sage\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError, HumanChatValidationError

        member_name = body.get("member_name", "").strip()
        if not member_name:
            raise HTTPException(status_code=400, detail="'member_name' is required.")

        hc = _make_human_chat()

        try:
            rec = hc.add_council_member(chat_id, member_name)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except (HumanChatError, HumanChatValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/remove-member")
    def api_chat_remove_member(chat_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Remove a council member from the chat. Body: {\"member_name\": \"Sage\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError, HumanChatValidationError

        member_name = body.get("member_name", "").strip()
        if not member_name:
            raise HTTPException(status_code=400, detail="'member_name' is required.")

        hc = _make_human_chat()

        try:
            rec = hc.remove_council_member(chat_id, member_name)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except (HumanChatError, HumanChatValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/add-character")
    def api_chat_add_character(chat_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Add a character to the chat. Body: {\"character_id\": \"CH-0001\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError, HumanChatValidationError

        character_id = body.get("character_id", "").strip()
        if not character_id:
            raise HTTPException(status_code=400, detail="'character_id' is required.")

        hc = _make_human_chat()

        try:
            rec = hc.add_character(chat_id, character_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except (HumanChatError, HumanChatValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/remove-character")
    def api_chat_remove_character(chat_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Remove a character from the chat. Body: {\"character_id\": \"CH-0001\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError, HumanChatValidationError

        character_id = body.get("character_id", "").strip()
        if not character_id:
            raise HTTPException(status_code=400, detail="'character_id' is required.")

        hc = _make_human_chat()

        try:
            rec = hc.remove_character(chat_id, character_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except (HumanChatError, HumanChatValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/pause")
    def api_chat_pause(chat_id: str) -> dict[str, Any]:
        """Pause a chat to stop agent responses."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        hc = _make_human_chat()

        try:
            rec = hc.pause_chat(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except HumanChatError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/resume")
    def api_chat_resume(chat_id: str) -> dict[str, Any]:
        """Resume a paused chat."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        hc = _make_human_chat()

        try:
            rec = hc.resume_chat(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except HumanChatError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    @application.post("/api/chat/{chat_id}/continue")
    async def api_chat_continue(chat_id: str) -> dict[str, Any]:
        """Trigger one round of AI-to-AI responses (all members respond in turn)."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        hc = _make_human_chat()

        try:
            rec, responses = await hc.continue_conversation(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except HumanChatError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {
            "chat": rec.to_dict(),
            "responses": [r.content for r in responses],
        }

    @application.post("/api/chat/{chat_id}/send-stream")
    async def api_chat_send_stream(chat_id: str, body: dict[str, Any]):
        """Send a human message and stream agent responses via SSE."""
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="'content' is required.")

        async def event_generator():
            try:
                hc = _make_human_chat()

                # Auto-resume if paused
                rec = hc.get(chat_id)
                if rec.paused:
                    hc.resume_chat(chat_id)

                hc.send_human_message(chat_id, content)

                last_record = None
                async for member_name, response, record in hc.get_agent_response_streaming(chat_id):
                    last_record = record
                    content_text = response.content or ""
                    event_data = json_module.dumps({
                        "speaker": member_name,
                        "content": content_text,
                        "model": response.model,
                        "provider": response.provider,
                    })
                    yield f"event: message\ndata: {event_data}\n\n"

                # Send final state
                final_record = hc.get(chat_id)
                done_data = json_module.dumps({"chat": final_record.to_dict()})
                yield f"event: done\ndata: {done_data}\n\n"

            except HumanChatNotFoundError:
                err = json_module.dumps({"detail": f"Chat '{chat_id}' not found."})
                yield f"event: error\ndata: {err}\n\n"
            except (HumanChatError, Exception) as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/chat/{chat_id}/continue-stream")
    async def api_chat_continue_stream(chat_id: str):
        """Stream one round of AI-to-AI responses via SSE."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        async def event_generator():
            try:
                hc = _make_human_chat()

                async for member_name, response, record in hc.continue_conversation_streaming(chat_id):
                    content_text = response.content or ""
                    event_data = json_module.dumps({
                        "speaker": member_name,
                        "content": content_text,
                        "model": response.model,
                        "provider": response.provider,
                    })
                    yield f"event: message\ndata: {event_data}\n\n"

                # Send final state
                final_record = hc.get(chat_id)
                done_data = json_module.dumps({"chat": final_record.to_dict()})
                yield f"event: done\ndata: {done_data}\n\n"

            except HumanChatNotFoundError:
                err = json_module.dumps({"detail": f"Chat '{chat_id}' not found."})
                yield f"event: error\ndata: {err}\n\n"
            except (HumanChatError, Exception) as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/chat/{chat_id}/close")
    def api_chat_close(chat_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Close a chat. Optional body: {\"summary\": \"...\"}."""
        from core.human_chat import HumanChatNotFoundError, HumanChatError

        summary = ""
        if body:
            summary = body.get("summary", "").strip()

        hc = _make_human_chat()

        try:
            rec = hc.close_chat(chat_id, summary=summary)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        except HumanChatError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return rec.to_dict()

    # ── Memories ──────────────────────────────────────────────

    @application.get("/api/memories")
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

    @application.get("/api/memories/shared")
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

    @application.get("/api/memories/law-shared")
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

    @application.get("/api/memories/{member}")
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

    @application.delete("/api/memories/{member}/beliefs")
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

    @application.delete("/api/memories/shared/decisions")
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

    @application.get("/api/laws")
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

    @application.get("/api/laws/{law_id}")
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

    @application.post("/api/laws")
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

    @application.put("/api/laws/{law_id}")
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

    @application.put("/api/laws/{law_id}/status")
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

    @application.get("/api/evolutions")
    def api_evolutions_list(
        character_id: str | None = Query(None),
        status: str | None = Query(None),
        author: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List evolution records with optional filters."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import CharacterEvolution

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
        items = evo.list_evolutions(
            character_id=character_id, status=status, author=author,
        )
        return [r.to_dict() for r in items]

    @application.get("/api/evolutions/timelines")
    def api_evolutions_timelines() -> list[dict[str, Any]]:
        """List evolution timelines for all head characters."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import CharacterEvolution
        from core.evolution_history import EvolutionHistory

        chars = CharacterManager()
        evo = CharacterEvolution(
            character_manager=chars,
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
        history = EvolutionHistory(
            character_manager=chars,
            evolution_manager=evo,
        )
        timelines = history.list_timelines()
        return [t.to_dict() for t in timelines]

    @application.get("/api/evolutions/timelines/{character_id}")
    def api_evolutions_timeline_detail(character_id: str) -> dict[str, Any]:
        """Get evolution timeline for a specific character."""
        from core.characters import CharacterManager, CharacterNotFoundError
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import CharacterEvolution
        from core.evolution_history import EvolutionHistory

        chars = CharacterManager()
        evo = CharacterEvolution(
            character_manager=chars,
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
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

    @application.get("/api/evolutions/diff")
    def api_evolutions_diff(
        old: str = Query(...),
        new: str = Query(...),
    ) -> dict[str, Any]:
        """Diff two character versions."""
        from core.characters import CharacterManager, CharacterNotFoundError
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import CharacterEvolution
        from core.evolution_history import EvolutionHistory

        chars = CharacterManager()
        evo = CharacterEvolution(
            character_manager=chars,
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
        history = EvolutionHistory(
            character_manager=chars,
            evolution_manager=evo,
        )
        try:
            diffs = history.diff_versions(old, new)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"old_id": old, "new_id": new, "diffs": diffs}

    @application.get("/api/evolutions/{evolution_id}")
    def api_evolution_detail(evolution_id: str) -> dict[str, Any]:
        """Get a single evolution record."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, EvolutionNotFoundError,
        )

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
        try:
            record = evo.get(evolution_id)
        except EvolutionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Evolution '{evolution_id}' not found.",
            )
        return record.to_dict()

    @application.post("/api/evolutions")
    def api_evolution_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new evolution in draft status.

        Body: {"character_id": "CH-0001", "author": "Sage",
               "changes": [{"change_type": "trait_add", "field_name": "brave",
                             "new_value": {...}, "rationale": "..."}]}
        """
        from core.characters import CharacterManager, CharacterNotFoundError
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, CharacterChange,
            EvolutionValidationError,
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

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )

        try:
            record = evo.create_evolution(
                character_id, author=author, changes=changes,
            )
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        except EvolutionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return record.to_dict()

    @application.post("/api/evolutions/{evolution_id}/submit")
    def api_evolution_submit(evolution_id: str) -> dict[str, Any]:
        """Submit evolution for governance review (draft → proposed)."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, EvolutionNotFoundError, EvolutionStateError,
        )

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
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

    @application.post("/api/evolutions/{evolution_id}/open-voting")
    def api_evolution_open_voting(evolution_id: str) -> dict[str, Any]:
        """Open voting on evolution (proposed → voting)."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, EvolutionNotFoundError, EvolutionStateError,
        )

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
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

    @application.post("/api/evolutions/{evolution_id}/resolve")
    def api_evolution_resolve(evolution_id: str) -> dict[str, Any]:
        """Resolve voting (voting → decided/rejected)."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, EvolutionNotFoundError, EvolutionStateError,
        )

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
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

    @application.post("/api/evolutions/{evolution_id}/apply")
    def api_evolution_apply(evolution_id: str) -> dict[str, Any]:
        """Apply approved evolution (decided → applied)."""
        from core.characters import CharacterManager
        from core.proposals import ProposalManager
        from core.voting import VotingEngine
        from core.character_evolution import (
            CharacterEvolution, EvolutionNotFoundError, EvolutionStateError,
        )

        evo = CharacterEvolution(
            character_manager=CharacterManager(),
            proposal_manager=ProposalManager(),
            voting_engine=VotingEngine(),
        )
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

    # ── Council Sessions ──────────────────────────────────────

    @application.get("/api/council-sessions")
    def api_council_sessions_list(
        status: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List council sessions with optional status filter."""
        from core.council_session import CouncilSessionManager
        mgr = CouncilSessionManager()
        sessions = mgr.list_sessions(status=status)
        return [s.to_dict() for s in sessions]

    @application.get("/api/council-sessions/{session_id}")
    def api_council_session_detail(session_id: str) -> dict[str, Any]:
        """Get a single council session."""
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
        )
        mgr = CouncilSessionManager()
        try:
            session = mgr.get(session_id)
        except CouncilSessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Council session '{session_id}' not found.",
            )
        return session.to_dict()

    @application.post("/api/council-sessions")
    def api_council_session_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new council session.

        Body: {"title": "...", "topic": "...", "agenda": "...",
               "category": "governance", "round_count": 5}
        """
        from core.council_session import (
            CouncilSessionManager, CouncilSessionValidationError,
        )
        from core.registry import CouncilRegistry

        title = body.get("title", "").strip()
        topic = body.get("topic", "").strip()
        agenda = body.get("agenda", "").strip()
        category = body.get("category", "governance").strip()
        round_count = int(body.get("round_count", 5))

        if not title or not topic:
            raise HTTPException(
                status_code=400,
                detail="Fields 'title' and 'topic' are required.",
            )

        # Get all council members as default participants
        registry = CouncilRegistry().load()
        participants = registry.list_names()

        mgr = CouncilSessionManager()
        try:
            session = mgr.create_session(
                title, topic,
                agenda=agenda,
                participants=participants,
                round_count=round_count,
                proposed_category=category,
            )
        except CouncilSessionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return session.to_dict()

    @application.post("/api/council-sessions/{session_id}/discuss-stream")
    async def api_council_session_discuss_stream(session_id: str):
        """Run one discussion round on a council session via SSE."""
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
            CouncilSessionStateError, CouncilSessionRecord,
        )
        from core.discussion import DiscussionContribution
        from core.api_client import APIClient, ChatMessage
        from core.memory_influence import MemoryInfluence

        async def event_generator():
            try:
                mgr = CouncilSessionManager()
                record = mgr.get(session_id)

                if record.status != "open":
                    err = json_module.dumps({"detail": "Session is closed."})
                    yield f"event: error\ndata: {err}\n\n"
                    return

                if record.current_round >= record.round_count:
                    err = json_module.dumps({"detail": "All discussion rounds complete."})
                    yield f"event: error\ndata: {err}\n\n"
                    return

                round_number = record.current_round + 1
                new_contributions = []
                mi = MemoryInfluence()
                keywords = MemoryInfluence.extract_keywords(
                    f"{record.title} {record.topic}"
                )

                from core.registry import CouncilRegistry
                registry = CouncilRegistry().load()
                client = APIClient()

                # Inject scheduled user message if present
                meta = dict(record.metadata)
                scheduled_msg = meta.pop("scheduled_message", None)
                if scheduled_msg and isinstance(scheduled_msg, str) and scheduled_msg.strip():
                    user_contribution = DiscussionContribution.create(
                        speaker="User",
                        content=scheduled_msg.strip(),
                        round_number=round_number,
                        metadata={"type": "scheduled_message"},
                    )
                    new_contributions.append(user_contribution)

                    # Stream the user message
                    user_event = json_module.dumps({
                        "speaker": "User",
                        "content": scheduled_msg.strip(),
                        "round": round_number,
                        "model": "",
                        "provider": "user",
                    })
                    yield f"event: message\ndata: {user_event}\n\n"

                    import asyncio as _asyncio
                    await _asyncio.sleep(0.3)

                for name in record.participants:
                    member = registry.get(name)

                    # Build memory context
                    memory_text = ""
                    ctx = mi.build_context(member.name, keywords)
                    if ctx.formatted_text:
                        memory_text = ctx.formatted_text

                    # Build session discussion prompt
                    prompt = _build_session_prompt(
                        member, record,
                        list(record.contributions) + new_contributions,
                        round_number,
                        memory_context_text=memory_text,
                    )
                    messages = [ChatMessage(role="user", content=prompt)]
                    response = await client.chat(member, messages)

                    contribution = DiscussionContribution.create(
                        speaker=member.name,
                        content=response.content,
                        round_number=round_number,
                        metadata={
                            "model": response.model,
                            "provider": response.provider,
                        },
                    )
                    new_contributions.append(contribution)

                    # Stream this contribution
                    event_data = json_module.dumps({
                        "speaker": member.name,
                        "content": response.content,
                        "round": round_number,
                        "model": response.model,
                        "provider": response.provider,
                    })
                    yield f"event: message\ndata: {event_data}\n\n"

                    import asyncio
                    await asyncio.sleep(0.5)

                # Save the updated record
                all_contributions = list(record.contributions) + new_contributions
                updated_record = CouncilSessionRecord(
                    session_id=record.session_id,
                    title=record.title,
                    topic=record.topic,
                    agenda=record.agenda,
                    participants=list(record.participants),
                    contributions=all_contributions,
                    round_count=record.round_count,
                    current_round=round_number,
                    status=record.status,
                    summary=record.summary,
                    created_at=record.created_at,
                    closed_at=record.closed_at,
                    proposed_category=record.proposed_category,
                    proposed_title=record.proposed_title,
                    proposed_description=record.proposed_description,
                    metadata=meta,
                )
                mgr.save(updated_record)

                done_data = json_module.dumps({
                    "session": updated_record.to_dict(),
                    "round_completed": round_number,
                })
                yield f"event: done\ndata: {done_data}\n\n"

            except CouncilSessionNotFoundError:
                err = json_module.dumps({"detail": f"Council session '{session_id}' not found."})
                yield f"event: error\ndata: {err}\n\n"
            except Exception as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/council-sessions/{session_id}/close")
    def api_council_session_close(session_id: str) -> dict[str, Any]:
        """Close a council session."""
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
            CouncilSessionStateError,
        )
        mgr = CouncilSessionManager()
        try:
            record = mgr.close_session(session_id)
        except CouncilSessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Council session '{session_id}' not found.",
            )
        except CouncilSessionStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return record.to_dict()

    @application.get("/api/council-sessions/{session_id}/scheduled-message")
    def api_council_session_scheduled_message_get(
        session_id: str,
    ) -> dict[str, Any]:
        """Get the scheduled user message for the next session round."""
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
        )
        mgr = CouncilSessionManager()
        try:
            record = mgr.get(session_id)
        except CouncilSessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Council session '{session_id}' not found.",
            )
        msg = (record.metadata or {}).get("scheduled_message", None)
        return {"message": msg}

    @application.post("/api/council-sessions/{session_id}/scheduled-message")
    def api_council_session_scheduled_message_set(
        session_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Set or clear a user message for the next session round.

        Body: {"message": "Your message here..."}
        Send an empty string to clear.
        """
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
            CouncilSessionRecord,
        )
        mgr = CouncilSessionManager()
        try:
            record = mgr.get(session_id)
        except CouncilSessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Council session '{session_id}' not found.",
            )

        if record.status != "open":
            raise HTTPException(
                status_code=400,
                detail="Cannot schedule a message on a closed session.",
            )

        message = (body.get("message", "") or "").strip()
        meta = dict(record.metadata)
        if message:
            meta["scheduled_message"] = message
        else:
            meta.pop("scheduled_message", None)

        updated = CouncilSessionRecord(
            session_id=record.session_id,
            title=record.title,
            topic=record.topic,
            agenda=record.agenda,
            participants=list(record.participants),
            contributions=list(record.contributions),
            round_count=record.round_count,
            current_round=record.current_round,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            proposed_category=record.proposed_category,
            proposed_title=record.proposed_title,
            proposed_description=record.proposed_description,
            metadata=meta,
        )
        mgr.save(updated)

        return {
            "status": "ok",
            "message": message or None,
            "scheduled": bool(message),
        }

    @application.post("/api/council-sessions/{session_id}/handoff-proposal")
    def api_council_session_handoff(
        session_id: str, body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a proposal from a closed council session.

        Body (optional overrides):
            {"title": "...", "description": "...", "category": "...",
             "author": "Sage"}

        If author is omitted, uses the first participant.
        """
        from core.council_session import (
            CouncilSessionManager, CouncilSessionNotFoundError,
            CouncilSessionStateError,
        )
        from core.proposals import ProposalManager, ProposalValidationError

        mgr = CouncilSessionManager()
        body = body or {}

        try:
            session = mgr.get(session_id)
        except CouncilSessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Council session '{session_id}' not found.",
            )

        if session.status != "closed":
            raise HTTPException(
                status_code=400,
                detail=f"Session must be closed before handoff (status: {session.status}).",
            )

        # Build proposal data from session
        try:
            proposal_data = mgr.build_proposal_data(
                session_id,
                title=body.get("title"),
                description=body.get("description"),
                category=body.get("category"),
            )
        except CouncilSessionStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        author = body.get("author", "").strip()
        if not author:
            # Use the first participant as default author
            author = session.participants[0] if session.participants else "Council"

        pmgr = ProposalManager()
        try:
            proposal = pmgr.create(
                proposal_data["title"],
                proposal_data["description"],
                author=author,
                category=proposal_data["category"],
                body=proposal_data["body"],
                metadata=proposal_data.get("metadata"),
            )
            # Auto-transition to open
            proposal = pmgr.update_status(proposal.id, "open")
        except ProposalValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Create a discussion for the new proposal
        discussion_info = None
        try:
            from core.registry import CouncilRegistry
            dmgr = _make_discussion_manager(pmgr)
            participants = CouncilRegistry().load().list_names()
            disc = dmgr.create_discussion(
                proposal.id, proposal.id,
                f"Discussion: {proposal.title}",
                participants=participants, round_count=5,
            )
            discussion_info = disc.to_dict()
        except Exception as exc:
            discussion_info = {"error": str(exc)}

        result = proposal.to_dict()
        result["discussion"] = discussion_info
        result["source_session"] = session_id
        return result

    def _build_session_prompt(
        member,
        session,
        contributions,
        round_number,
        memory_context_text="",
    ):
        """Build a discussion prompt for a council session."""
        parts = [
            f"## Council Session: {session.title}",
            f"**Topic:** {session.topic}",
        ]
        if session.agenda:
            parts.append(f"**Agenda:** {session.agenda}")

        if contributions:
            parts.append("\n### Discussion So Far")
            for c in contributions[-10:]:
                parts.append(
                    f"**{c.speaker}** (round {c.round_number}): {c.content}"
                )

        if memory_context_text:
            parts.append(f"\n{memory_context_text}")

        parts.append(
            f"\n---\n"
            f"You are **{member.name}** ({member.role}). This is round "
            f"{round_number} of the council session.\n"
            f"Share your perspective on this topic. Consider how it relates "
            f"to your area of expertise and the council's mission. "
            f"Be concise but substantive."
        )
        return "\n".join(parts)

    # ── Treasury / Obelisk ────────────────────────────────────

    @application.get("/api/treasury")
    def api_treasury_list(
        type: str | None = Query(None, alias="type"),
    ) -> list[dict[str, Any]]:
        """List all treasury accounts, optionally filtered by type."""
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager()
        accounts = tmgr.list_accounts(account_type=type)
        return [a.to_dict() for a in accounts]

    @application.get("/api/treasury/{account_id}")
    def api_treasury_detail(account_id: str) -> dict[str, Any]:
        """Get a single treasury account."""
        from core.treasury import TreasuryManager, AccountNotFoundError
        tmgr = TreasuryManager()
        try:
            acct = tmgr.get(account_id)
        except AccountNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Treasury account '{account_id}' not found.",
            )
        return acct.to_dict()

    @application.post("/api/treasury/initialize")
    def api_treasury_initialize() -> dict[str, Any]:
        """Create default accounts for all known entities."""
        from core.treasury import TreasuryManager
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager

        tmgr = TreasuryManager()
        registry = CouncilRegistry().load()
        cmgr = CharacterManager()
        created = tmgr.initialize_defaults(
            registry=registry, character_manager=cmgr
        )
        return {
            "status": "ok",
            "created_count": len(created),
            "accounts": [a.to_dict() for a in created],
        }

    @application.post("/api/treasury/{account_id}/credit")
    def api_treasury_credit(
        account_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Add funds to an account.  Body: {gold, silver, bronze}."""
        from core.treasury import (
            TreasuryManager, AccountNotFoundError, TreasuryValidationError,
        )
        tmgr = TreasuryManager()
        try:
            acct = tmgr.credit(
                account_id,
                gold=int(body.get("gold", 0)),
                silver=int(body.get("silver", 0)),
                bronze=int(body.get("bronze", 0)),
            )
        except AccountNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Treasury account '{account_id}' not found.",
            )
        except TreasuryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return acct.to_dict()

    @application.post("/api/treasury/{account_id}/debit")
    def api_treasury_debit(
        account_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove funds from an account.  Body: {gold, silver, bronze}."""
        from core.treasury import (
            TreasuryManager, AccountNotFoundError,
            InsufficientFundsError, TreasuryValidationError,
        )
        tmgr = TreasuryManager()
        try:
            acct = tmgr.debit(
                account_id,
                gold=int(body.get("gold", 0)),
                silver=int(body.get("silver", 0)),
                bronze=int(body.get("bronze", 0)),
            )
        except AccountNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Treasury account '{account_id}' not found.",
            )
        except InsufficientFundsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except TreasuryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return acct.to_dict()

    @application.post("/api/treasury/transfer")
    def api_treasury_transfer(body: dict[str, Any]) -> dict[str, Any]:
        """Transfer funds between accounts.

        Body: {from: account_id, to: account_id, gold, silver, bronze}

        Tax is automatically collected on eligible transfers.
        """
        from core.treasury import (
            TreasuryManager, AccountNotFoundError,
            InsufficientFundsError, TreasuryValidationError,
        )
        from core.taxation import TaxationManager
        from_id = body.get("from", "").strip()
        to_id = body.get("to", "").strip()
        if not from_id or not to_id:
            raise HTTPException(
                status_code=400,
                detail="'from' and 'to' account IDs are required.",
            )
        tax_mgr = TaxationManager()
        tmgr = TreasuryManager(taxation_manager=tax_mgr)
        try:
            from_acct, to_acct = tmgr.transfer(
                from_id, to_id,
                gold=int(body.get("gold", 0)),
                silver=int(body.get("silver", 0)),
                bronze=int(body.get("bronze", 0)),
            )
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except InsufficientFundsError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except TreasuryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "from": from_acct.to_dict(),
            "to": to_acct.to_dict(),
        }

    # ── Taxation ──────────────────────────────────────────────

    @application.get("/api/tax/policy")
    def api_tax_policy_get() -> dict[str, Any]:
        """Get the current tax policy."""
        from core.taxation import TaxationManager
        mgr = TaxationManager()
        return mgr.get_policy().to_dict()

    @application.put("/api/tax/policy")
    def api_tax_policy_update(body: dict[str, Any]) -> dict[str, Any]:
        """Update the tax policy.

        Body: {rate?: float, enabled?: bool, exempt_account_types?: list}
        """
        from core.taxation import TaxationManager, TaxationValidationError
        mgr = TaxationManager()
        kwargs: dict[str, Any] = {}
        if "rate" in body:
            kwargs["rate"] = float(body["rate"])
        if "enabled" in body:
            kwargs["enabled"] = bool(body["enabled"])
        if "exempt_account_types" in body:
            kwargs["exempt_account_types"] = list(body["exempt_account_types"])
        try:
            policy = mgr.update_policy(**kwargs)
        except TaxationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return policy.to_dict()

    @application.get("/api/tax/events")
    def api_tax_events(
        limit: int | None = Query(None),
        from_account: str | None = Query(None),
        to_account: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List tax collection events."""
        from core.taxation import TaxationManager
        mgr = TaxationManager()
        events = mgr.list_events(
            limit=limit, from_account=from_account, to_account=to_account,
        )
        return [e.to_dict() for e in events]

    @application.get("/api/tax/summary")
    def api_tax_summary() -> dict[str, Any]:
        """Total tax collected across all time."""
        from core.taxation import TaxationManager
        mgr = TaxationManager()
        total = mgr.get_total_collected()
        policy = mgr.get_policy()
        return {
            "total_collected": total,
            "policy": policy.to_dict(),
            "event_count": len(mgr.list_events()),
        }

    # ── Salary Payroll (hidden, runs at startup) ──────────────

    try:
        from core.salary import SalaryManager
        SalaryManager().check_and_pay()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Salary: startup payroll check failed")

    # ── Entity Image Gallery (F-037e) ────────────────────────

    # NOTE: Specific routes (file, set-primary, info) MUST be registered
    # before the generic {entity_type}/{entity_id} catch-all routes.

    @application.get("/api/images/file/{image_id}")
    def api_images_serve(image_id: str):
        """Serve raw image bytes for display in <img> tags."""
        from core.image_manager import ImageManager, ImageNotFoundError

        mgr = ImageManager()
        try:
            path = mgr.get_image_path(image_id)
        except ImageNotFoundError:
            raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")

        if not path.exists():
            raise HTTPException(status_code=404, detail="Image file missing from disk.")

        # Determine media type from extension
        ext = path.suffix.lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        media_type = media_types.get(ext, "image/png")
        return FileResponse(str(path), media_type=media_type)

    @application.get("/api/images/info/{image_id}")
    def api_images_info(image_id: str) -> dict[str, Any]:
        """Get full image metadata including prompt and generation info."""
        from core.image_manager import ImageManager, ImageNotFoundError

        mgr = ImageManager()
        try:
            img = mgr.get(image_id)
        except ImageNotFoundError:
            raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
        d = img.to_dict()
        d["url"] = f"/api/images/file/{img.id}"
        return d

    @application.post("/api/images/set-primary/{image_id}")
    def api_images_set_primary(image_id: str) -> dict[str, Any]:
        """Set an image as the primary image for its entity."""
        from core.image_manager import ImageManager, ImageNotFoundError

        mgr = ImageManager()
        try:
            img = mgr.set_primary(image_id)
        except ImageNotFoundError:
            raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
        d = img.to_dict()
        d["url"] = f"/api/images/file/{img.id}"
        return d

    @application.delete("/api/images/delete/{image_id}")
    def api_images_delete(image_id: str) -> dict[str, Any]:
        """Delete an image and its file from disk."""
        from core.image_manager import ImageManager, ImageNotFoundError

        mgr = ImageManager()
        try:
            mgr.delete(image_id)
        except ImageNotFoundError:
            raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
        return {"deleted": True, "image_id": image_id}

    @application.get("/api/images/{entity_type}/{entity_id}")
    def api_images_list(entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        """List all images for an entity.

        Returns image metadata records sorted by creation time.
        Each record includes a ``url`` field for use in <img> tags.
        """
        from core.image_manager import ImageManager, VALID_ENTITY_TYPES

        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type '{entity_type}'. "
                       f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
            )

        mgr = ImageManager()
        images = mgr.list_images(entity_type, entity_id)
        result = []
        for img in images:
            d = img.to_dict()
            d["url"] = f"/api/images/file/{img.id}"
            result.append(d)
        return result

    @application.post("/api/images/{entity_type}/{entity_id}")
    def api_images_upload(
        entity_type: str, entity_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Upload a new image for an entity.

        Body: {
            "image_data": "data:image/png;base64,...",
            "original_filename": "portrait.png",   // optional
            "prompt": "a noble knight",             // optional
            "negative_prompt": "blurry",            // optional
            "is_primary": null,                     // optional, null = auto
            "template_id": "TPL-0001",              // optional
        }
        """
        import base64
        from core.image_manager import (
            ImageManager, ImageValidationError, VALID_ENTITY_TYPES,
        )

        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type '{entity_type}'. "
                       f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
            )

        image_data_str = body.get("image_data", "")
        if not image_data_str:
            raise HTTPException(status_code=400, detail="'image_data' is required.")

        # Parse base64 data URL
        try:
            if "," in image_data_str:
                image_data_str = image_data_str.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data_str)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data.")

        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Image data is empty.")

        original_filename = (body.get("original_filename") or "").strip()
        prompt = body.get("prompt", "")
        negative_prompt = body.get("negative_prompt", "")
        is_primary = body.get("is_primary")  # None = auto
        template_id = (body.get("template_id") or "").strip()

        mgr = ImageManager()
        try:
            img = mgr.save_image(
                raw_bytes,
                entity_type=entity_type,
                entity_id=entity_id,
                original_filename=original_filename,
                prompt=prompt,
                negative_prompt=negative_prompt,
                is_primary=is_primary,
                template_id=template_id,
            )
        except ImageValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        d = img.to_dict()
        d["url"] = f"/api/images/file/{img.id}"
        return d


    # ── Generation Pipeline (F-037f) ─────────────────────────

    # Module-level pipeline singleton — created once, persists across requests
    _generation_pipeline = None

    def _get_pipeline():
        """Lazily create the GenerationPipeline singleton."""
        nonlocal _generation_pipeline
        if _generation_pipeline is None:
            from core.generation_pipeline import GenerationPipeline
            from core.comfyui_client import WorkflowTemplateManager
            from core.image_manager import ImageManager
            from core.prompt_builder import PromptBuilder
            _generation_pipeline = GenerationPipeline(
                template_manager=WorkflowTemplateManager(),
                image_manager=ImageManager(),
                prompt_builder=PromptBuilder(),
            )
        return _generation_pipeline

    def _explore_primary_image(imgr: Any, entity_type: str, entity_id: str) -> str:
        """Get primary image URL for an entity, or empty string."""
        try:
            images = imgr.list_images(entity_type, entity_id)
            primary = next(
                (img for img in images if img.is_primary), None,
            )
            if primary:
                return f"/api/images/file/{primary.id}"
            elif images:
                return f"/api/images/file/{images[0].id}"
        except Exception:
            pass
        return ""

    @application.post("/api/generate/prompts")
    async def api_generate_prompts(body: dict[str, Any]) -> dict[str, Any]:
        """Preview prompts for council_vote mode (or any mode).

        This generates prompts WITHOUT queueing to ComfyUI —
        used by the frontend to show prompt options before generating.

        Body: same as /api/generate/{entity_type}/{entity_id}

        Returns: {"prompts": [{"positive": "...", "negative": "...", "member_name": "..."}, ...]}
        """
        from core.prompt_builder import (
            PromptBuilder, PromptRequest, PromptResult,
            get_style_preset, PromptValidationError,
        )
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        prompt_mode = body.get("prompt_mode", "system")
        member_name = body.get("member_name", "")
        user_prompt = body.get("user_prompt", "")
        style_preset_key = body.get("style_preset_key", "")
        participants = body.get("participants", [])
        entity_type = body.get("entity_type", "")
        entity_id = body.get("entity_id", "")

        style_preset = None
        if style_preset_key:
            style_preset = get_style_preset(style_preset_key)

        try:
            prompt_request = PromptRequest.create(
                prompt_mode,
                entity_type=entity_type,
                entity_id=entity_id,
                member_name=member_name,
                user_prompt=user_prompt,
                style_preset=style_preset,
                participants=participants if participants else None,
            )
        except PromptValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Build prompt builder with live connections
        try:
            from core.character_manager import CharacterManager
            from core.location_manager import LocationManager
            from core.items import ItemManager
            from core.stores import StoreManager

            registry = CouncilRegistry().load()
            client = APIClient()
            builder = PromptBuilder(
                api_client=client,
                registry=registry,
                character_manager=CharacterManager(),
                location_manager=LocationManager(),
                item_manager=ItemManager(),
                store_manager=StoreManager(),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize prompt builder: {exc}",
            )

        try:
            result = await builder.generate(prompt_request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Prompt generation failed: {exc}",
            )

        if isinstance(result, list):
            prompts = [
                {
                    "positive": r.positive,
                    "negative": r.negative,
                    "member_name": r.member_name,
                    "mode": r.mode,
                }
                for r in result
            ]
        else:
            prompts = [{
                "positive": result.positive,
                "negative": result.negative,
                "member_name": result.member_name,
                "mode": result.mode,
            }]

        return {"prompts": prompts}

    @application.post("/api/generate/cancel/{job_id}")
    def api_generate_cancel(job_id: str) -> dict[str, Any]:
        """Cancel a running generation job."""
        from core.generation_pipeline import GenerationNotFoundError

        pipeline = _get_pipeline()
        try:
            progress = pipeline.cancel_job(job_id)
        except GenerationNotFoundError:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        return progress.to_dict()

    @application.get("/api/generate/stream/{job_id}")
    async def api_generate_stream(job_id: str) -> StreamingResponse:
        """SSE stream of generation progress for a job.

        Events:
            - event: progress — {job_id, stage, progress_pct, message, prompt_positive, prompt_negative}
            - event: done     — {job_id, stage: "completed", image_id, ...}
            - event: error    — {job_id, stage: "failed", error, ...}
        """
        from core.generation_pipeline import GenerationNotFoundError

        pipeline = _get_pipeline()

        async def event_generator():
            try:
                async for progress in pipeline.run_job(job_id):
                    data = json_module.dumps(progress.to_dict())
                    if progress.stage == "completed":
                        yield f"event: done\ndata: {data}\n\n"
                    elif progress.stage in ("failed", "cancelled"):
                        yield f"event: error\ndata: {data}\n\n"
                    else:
                        yield f"event: progress\ndata: {data}\n\n"
            except GenerationNotFoundError:
                err = json_module.dumps({"detail": f"Job '{job_id}' not found."})
                yield f"event: error\ndata: {err}\n\n"
            except Exception as exc:
                err = json_module.dumps({"detail": str(exc)})
                yield f"event: error\ndata: {err}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/api/generate/jobs")
    def api_generate_jobs(
        active_only: bool = Query(False),
    ) -> list[dict[str, Any]]:
        """List all generation jobs."""
        pipeline = _get_pipeline()
        return pipeline.list_jobs(active_only=active_only)

    @application.get("/api/generate/jobs/{job_id}")
    def api_generate_job_detail(job_id: str) -> dict[str, Any]:
        """Get details for a single generation job."""
        from core.generation_pipeline import GenerationNotFoundError

        pipeline = _get_pipeline()
        try:
            return pipeline.get_job(job_id)
        except GenerationNotFoundError:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    @application.post("/api/generate/batch")
    async def api_generate_batch(body: dict[str, Any]) -> dict[str, Any]:
        """Batch generate images for multiple entities of the same type.

        Body: {
            "entity_type": "character",
            "entity_ids": ["CH-0001", "CH-0002", ...],
            "template_id": "TPL-0001",
            "prompt_mode": "system",
            "member_name": "",
            "user_prompt": "",
            "style_preset_key": "",
            "participants": [],
            "selected_prompt_index": 0,
            "width": 512,
            "height": 512,
            "seed": 0
        }

        Returns: {"job_ids": ["GEN-0001", ...], "count": N}
        """
        from core.generation_pipeline import (
            GenerationRequest, GenerationValidationError,
            GenerationQueueFullError,
        )
        from core.image_manager import VALID_ENTITY_TYPES

        entity_type = (body.get("entity_type") or "").strip()
        entity_ids = body.get("entity_ids", [])
        template_id = (body.get("template_id") or "").strip()

        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type '{entity_type}'. "
                       f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
            )

        if not entity_ids or not isinstance(entity_ids, list):
            raise HTTPException(
                status_code=400,
                detail="'entity_ids' must be a non-empty list.",
            )

        if len(entity_ids) > 10:
            raise HTTPException(
                status_code=400,
                detail=f"Batch size {len(entity_ids)} exceeds maximum of 10.",
            )

        if not template_id:
            raise HTTPException(
                status_code=400,
                detail="'template_id' is required.",
            )

        # Build a GenerationRequest for each entity
        requests = []
        for eid in entity_ids:
            try:
                req = GenerationRequest.create(
                    entity_type=entity_type,
                    entity_id=str(eid).strip(),
                    template_id=template_id,
                    prompt_mode=body.get("prompt_mode", "system"),
                    member_name=body.get("member_name", ""),
                    user_prompt=body.get("user_prompt", ""),
                    style_preset_key=body.get("style_preset_key", ""),
                    participants=body.get("participants", []),
                    selected_prompt_index=body.get("selected_prompt_index", 0),
                    width=body.get("width", 512),
                    height=body.get("height", 512),
                    seed=body.get("seed", 0),
                )
                requests.append(req)
            except GenerationValidationError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Validation error for entity '{eid}': {exc}",
                )

        pipeline = _get_pipeline()
        try:
            job_ids = pipeline.start_batch_generation(requests)
        except GenerationQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except GenerationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {"job_ids": job_ids, "count": len(job_ids)}

    # NOTE: This catch-all route MUST come AFTER specific /api/generate/ routes
    # to avoid route matching conflicts (e.g. "cancel" matching as entity_type).
    @application.post("/api/generate/{entity_type}/{entity_id}")
    async def api_generate_start(
        entity_type: str, entity_id: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """Start an image generation job for an entity.

        Body: {
            "template_id": "TPL-0001",
            "prompt_mode": "system",       // system|character|raw_user|user_refined|council_vote
            "member_name": "",             // required for character/user_refined
            "user_prompt": "",             // required for raw_user/user_refined
            "style_preset_key": "",        // optional, e.g. "fantasy_art"
            "participants": [],            // required for council_vote (2+ names)
            "selected_prompt_index": 0,    // for council_vote: which prompt to use
            "width": 512,
            "height": 512,
            "seed": 0                      // 0 = random
        }

        Returns: {"job_id": "GEN-0001", "status": "queued"}
        """
        from core.generation_pipeline import (
            GenerationRequest, GenerationValidationError,
            GenerationQueueFullError,
        )
        from core.image_manager import VALID_ENTITY_TYPES

        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity type '{entity_type}'. "
                       f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
            )

        template_id = (body.get("template_id") or "").strip()
        if not template_id:
            raise HTTPException(status_code=400, detail="'template_id' is required.")

        try:
            request = GenerationRequest.create(
                entity_type=entity_type,
                entity_id=entity_id,
                template_id=template_id,
                prompt_mode=body.get("prompt_mode", "system"),
                member_name=body.get("member_name", ""),
                user_prompt=body.get("user_prompt", ""),
                style_preset_key=body.get("style_preset_key", ""),
                participants=body.get("participants", []),
                selected_prompt_index=body.get("selected_prompt_index", 0),
                width=body.get("width", 512),
                height=body.get("height", 512),
                seed=body.get("seed", 0),
            )
        except GenerationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        pipeline = _get_pipeline()
        try:
            job_id = pipeline.start_generation(request)
        except GenerationQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except GenerationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {"job_id": job_id, "status": "queued"}

    # ── Participants (F-042) ─────────────────────────────────

    _PARTICIPANT_MAX = 10

    @application.get("/api/participants/available")
    def api_participants_available() -> list[dict[str, Any]]:
        """Return a merged list of council members and active characters.

        Each entry has: id, name, type ('council'|'character'),
        description, avatar_url.  Used by Explore and Story UIs
        to populate the participant selector.
        """
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager
        from config.settings import COUNCIL_AVATARS_DIR, CHARACTER_AVATARS_DIR

        result: list[dict[str, Any]] = []

        # Council members
        try:
            registry = CouncilRegistry().load()
            for m in registry.list_members():
                avatar_url = ""
                avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
                if avatar_file.exists():
                    avatar_url = f"/api/council/{m.name}/avatar"
                result.append({
                    "id": m.name.lower(),
                    "name": m.name,
                    "type": "council",
                    "description": m.description or m.role,
                    "role": m.role,
                    "avatar_url": avatar_url,
                })
        except Exception:
            pass

        # Active characters
        try:
            cmgr = CharacterManager()
            for c in cmgr.list_characters(status="active"):
                avatar_url = ""
                avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
                if avatar_file.exists():
                    avatar_url = f"/api/characters/{c.id}/avatar"
                result.append({
                    "id": c.id,
                    "name": c.name,
                    "type": "character",
                    "description": c.description or "",
                    "role": "",
                    "avatar_url": avatar_url,
                })
        except Exception:
            pass

        return result

    def _build_participant_context(
        participants: list[dict[str, Any]],
    ) -> str:
        """Build rich markdown context for selected participants.

        Injects:
        - Council members: persona, core beliefs, relevant memories
        - Characters: full description, backstory, traits, system prompt
        - Shared world context: active laws, locations, items

        Args:
            participants: List of {"id": "...", "type": "council"|"character"}

        Returns:
            Markdown text suitable for prompt injection.
        """
        if not participants:
            return ""

        parts: list[str] = []
        parts.append("\n## Present Participants\n")

        # Separate by type
        council_ids = [
            p["id"] for p in participants if p.get("type") == "council"
        ]
        character_ids = [
            p["id"] for p in participants if p.get("type") == "character"
        ]

        # ── Council Members ──
        if council_ids:
            try:
                from core.registry import CouncilRegistry
                registry = CouncilRegistry().load()
                members_map = {
                    m.name.lower(): m for m in registry.list_members()
                }
            except Exception:
                members_map = {}

            # Memory influence engine (may not be available)
            mi = None
            try:
                from core.memory_influence import MemoryInfluence
                mi = MemoryInfluence(embedding_provider=None)
            except Exception:
                pass

            for cid in council_ids:
                member = members_map.get(cid.lower())
                if not member:
                    parts.append(f"### 🏛️ Council Member: {cid}")
                    parts.append("*(Member data unavailable)*\n")
                    continue

                parts.append(f"### 🏛️ Council Member: {member.name}")
                parts.append(f"**Role:** {member.role}")
                if member.description:
                    parts.append(f"**Description:** {member.description}")
                if member.system_prompt:
                    prompt_preview = member.system_prompt[:500]
                    parts.append(
                        f"**Persona:** {prompt_preview}"
                        + ("…" if len(member.system_prompt) > 500 else "")
                    )
                if member.specialties:
                    parts.append(
                        f"**Specialties:** {', '.join(member.specialties)}"
                    )

                # Inject core beliefs and memories via MemoryInfluence
                if mi:
                    try:
                        ctx = mi.build_context(
                            member.name,
                            ["exploration", "location", "scene"],
                        )
                        if ctx.beliefs:
                            parts.append("\n**Core Beliefs:**")
                            for sb in ctx.beliefs[:5]:
                                parts.append(
                                    f"- **{sb.belief.topic}**: "
                                    f"{sb.belief.content}"
                                )
                        if ctx.memories:
                            parts.append("\n**Relevant Memories:**")
                            for sm in ctx.memories[:5]:
                                parts.append(
                                    f"- [{sm.entry.event_type}] "
                                    f"{sm.entry.content}"
                                )
                    except Exception:
                        pass

                parts.append("")  # blank separator

        # ── Characters ──
        if character_ids:
            try:
                from core.characters import CharacterManager
                cmgr = CharacterManager()
            except Exception:
                cmgr = None

            for char_id in character_ids:
                if cmgr is None:
                    parts.append(f"### 🎭 Character: {char_id}")
                    parts.append("*(Character data unavailable)*\n")
                    continue

                try:
                    char = cmgr.get(char_id)
                except Exception:
                    parts.append(f"### 🎭 Character: {char_id}")
                    parts.append("*(Character not found)*\n")
                    continue

                parts.append(f"### 🎭 Character: {char.name}")
                if char.description:
                    parts.append(f"**Description:** {char.description}")
                if char.backstory:
                    backstory_preview = char.backstory[:500]
                    parts.append(
                        f"**Backstory:** {backstory_preview}"
                        + ("…" if len(char.backstory) > 500 else "")
                    )
                if char.traits:
                    trait_strs = [
                        f"{t.name} ({t.trait_type}, "
                        f"{int(t.intensity * 100)}%)"
                        for t in char.traits[:8]
                    ]
                    parts.append(f"**Traits:** {', '.join(trait_strs)}")
                if char.system_prompt:
                    prompt_preview = char.system_prompt[:500]
                    parts.append(
                        f"**Persona:** {prompt_preview}"
                        + ("…" if len(char.system_prompt) > 500 else "")
                    )
                parts.append("")

        # ── Shared World Context ──
        parts.append("\n## World Context\n")

        # Active Laws
        try:
            from core.laws import LawManager
            lmgr = LawManager()
            active_laws = lmgr.list_laws(status="active")
            if active_laws:
                parts.append("### Active Laws")
                for law in active_laws[:10]:
                    parts.append(
                        f"- **{law.title}**: {law.description[:200]}"
                    )
                parts.append("")
        except Exception:
            pass

        # Active Locations
        try:
            from core.locations import LocationManager
            loc_mgr = LocationManager()
            active_locs = loc_mgr.list_locations(status="active")
            if active_locs:
                parts.append("### Known Locations")
                for loc in active_locs[:10]:
                    line = f"- **{loc.name}**: {loc.description[:150]}"
                    if loc.lore:
                        line += f" — {loc.lore[:100]}"
                    parts.append(line)
                parts.append("")
        except Exception:
            pass

        # Active Items
        try:
            from core.items import ItemManager
            imr = ItemManager()
            active_items = imr.list_items(status="active")
            if active_items:
                parts.append("### Known Items")
                for item in active_items[:10]:
                    line = f"- **{item.name}**: {item.description[:150]}"
                    if item.rarity:
                        line += f" [{item.rarity}]"
                    parts.append(line)
                parts.append("")
        except Exception:
            pass

        return "\n".join(parts)

    # ── Exploration (F-040) ───────────────────────────────────

    @application.get("/api/explore")
    def api_explore_list() -> list[dict[str, Any]]:
        """List all active locations with exploration data.

        Returns location info, scene counts, and primary image URLs.
        """
        from core.locations import LocationManager
        from core.exploration import ExplorationManager
        from core.image_manager import ImageManager

        lmgr = LocationManager()
        emgr = ExplorationManager()
        imgr = ImageManager()

        locations = lmgr.list_locations(status="active")
        result = []
        for loc in locations:
            # Get primary image
            primary_url = ""
            try:
                images = imgr.list_images("location", loc.id)
                primary = next(
                    (img for img in images if img.is_primary), None,
                )
                if primary:
                    primary_url = f"/api/images/file/{primary.id}"
                elif images:
                    primary_url = f"/api/images/file/{images[0].id}"
            except Exception:
                pass

            result.append({
                "id": loc.id,
                "name": loc.name,
                "description": loc.description,
                "tags": loc.tags,
                "status": loc.status,
                "parent_location_id": loc.parent_location_id,
                "primary_image_url": primary_url,
                "scene_count": emgr.count_scenes(loc.id),
            })
        return result

    @application.get("/api/explore/{location_id}")
    def api_explore_detail(location_id: str) -> dict[str, Any]:
        """Get full exploration data for a location.

        Returns location info, all scenes, navigation targets, and images.
        """
        from core.locations import LocationManager, LocationNotFoundError
        from core.exploration import ExplorationManager
        from core.image_manager import ImageManager

        lmgr = LocationManager()
        emgr = ExplorationManager()
        imgr = ImageManager()

        try:
            loc = lmgr.get(location_id)
        except LocationNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_id}' not found.",
            )

        # Scenes
        scenes = emgr.list_scenes(location_id)
        scene_dicts = []
        for s in scenes:
            sd = s.to_dict()
            sd["image_url"] = f"/api/images/file/{s.image_id}"
            scene_dicts.append(sd)

        # Navigation targets
        nav = ExplorationManager.get_navigation_targets(
            location_id, lmgr,
        )
        nav_data: dict[str, Any] = {"parent": None, "children": [], "siblings": []}
        if nav["parent"]:
            p = nav["parent"]
            p_img = _explore_primary_image(imgr, "location", p.id)
            nav_data["parent"] = {
                "id": p.id, "name": p.name,
                "description": p.description,
                "primary_image_url": p_img,
            }
        for child in nav["children"]:
            c_img = _explore_primary_image(imgr, "location", child.id)
            nav_data["children"].append({
                "id": child.id, "name": child.name,
                "description": child.description,
                "primary_image_url": c_img,
            })
        for sib in nav["siblings"]:
            s_img = _explore_primary_image(imgr, "location", sib.id)
            nav_data["siblings"].append({
                "id": sib.id, "name": sib.name,
                "description": sib.description,
                "primary_image_url": s_img,
            })

        # Primary image
        primary_url = _explore_primary_image(imgr, "location", location_id)

        # Location features
        features = []
        for f in (loc.features or []):
            features.append({
                "name": f.name,
                "description": f.description,
                "feature_type": getattr(f, "feature_type", "custom"),
            })

        return {
            "id": loc.id,
            "name": loc.name,
            "description": loc.description,
            "lore": loc.lore,
            "tags": loc.tags,
            "status": loc.status,
            "coordinates": loc.coordinates,
            "parent_location_id": loc.parent_location_id,
            "features": features,
            "primary_image_url": primary_url,
            "scenes": scene_dicts,
            "navigation": nav_data,
        }

    @application.post("/api/explore/{location_id}/look-around")
    def api_explore_look_around(
        location_id: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger 'Look Around' scene generation for a location.

        Uses the generation pipeline to create a scene image based on
        the location's description, lore, and features.

        Optional body: {
            "scene_type": "overview",      // scene type to record
            "template_id": "TPL-XXXX",     // override template
            "style_preset_key": "",        // style preset
            "width": 512, "height": 512,
            "participants": [              // F-042: optional participants
                {"id": "sage", "type": "council"},
                {"id": "CH-0001", "type": "character"}
            ]
        }

        Returns: {"job_id": "GEN-XXXX", "status": "queued",
                  "location_id": "LOC-XXXX"}
        """
        from core.locations import LocationManager, LocationNotFoundError
        from core.exploration import ExplorationManager
        from core.generation_pipeline import (
            GenerationRequest, GenerationValidationError,
            GenerationQueueFullError,
        )

        body = body or {}

        # F-042: Validate participants
        participants = body.get("participants", [])
        if participants:
            if not isinstance(participants, list):
                raise HTTPException(
                    status_code=400,
                    detail="'participants' must be a list.",
                )
            if len(participants) > _PARTICIPANT_MAX:
                raise HTTPException(
                    status_code=400,
                    detail=f"Too many participants ({len(participants)}). "
                           f"Maximum is {_PARTICIPANT_MAX}.",
                )

        lmgr = LocationManager()
        try:
            loc = lmgr.get(location_id)
        except LocationNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_id}' not found.",
            )

        # Build look-around description for the prompt
        context = ExplorationManager.build_look_around_description(loc)

        # F-042: Enrich context with participant identities + world state
        if participants:
            participant_context = _build_participant_context(participants)
            if participant_context:
                context = context + "\n\n" + participant_context

        # Get template — prefer body override, then recommended,
        # then fall back to error
        template_id = (body.get("template_id") or "").strip()
        if not template_id:
            try:
                from core.template_assignments import TemplateAssignmentManager
                tam = TemplateAssignmentManager()
                rec = tam.get_recommended_template("location")
                template_id = rec.get("template_id", "")
            except Exception:
                pass
        if not template_id:
            raise HTTPException(
                status_code=400,
                detail="No template specified and no default template "
                       "assigned for locations. Set one in Settings → "
                       "ComfyUI → Template Assignments.",
            )

        scene_type = body.get("scene_type", "overview")
        width = body.get("width", 512)
        height = body.get("height", 512)

        try:
            request = GenerationRequest.create(
                entity_type="location",
                entity_id=location_id,
                template_id=template_id,
                prompt_mode="system",
                user_prompt=context,
                style_preset_key=body.get("style_preset_key", ""),
                width=width,
                height=height,
                seed=body.get("seed", 0),
                metadata={
                    "exploration": True,
                    "scene_type": scene_type,
                    "participants": [
                        {"id": p.get("id"), "type": p.get("type")}
                        for p in participants
                    ] if participants else [],
                },
            )
        except GenerationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        pipeline = _get_pipeline()
        try:
            job_id = pipeline.start_generation(request)
        except GenerationQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc))

        return {
            "job_id": job_id,
            "status": "queued",
            "location_id": location_id,
        }

    @application.get("/api/explore/{location_id}/scenes")
    def api_explore_scenes(
        location_id: str,
        scene_type: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List exploration scenes for a location."""
        from core.exploration import ExplorationManager

        emgr = ExplorationManager()
        scenes = emgr.list_scenes(location_id, scene_type=scene_type)
        result = []
        for s in scenes:
            sd = s.to_dict()
            sd["image_url"] = f"/api/images/file/{s.image_id}"
            result.append(sd)
        return result

    @application.delete("/api/explore/{location_id}/scenes/{scene_id}")
    def api_explore_delete_scene(
        location_id: str,
        scene_id: str,
    ) -> dict[str, Any]:
        """Delete an exploration scene."""
        from core.exploration import ExplorationManager, SceneNotFoundError

        emgr = ExplorationManager()
        try:
            scene = emgr.get_scene(scene_id)
        except SceneNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Scene '{scene_id}' not found.",
            )
        if scene.location_id != location_id:
            raise HTTPException(
                status_code=400,
                detail=f"Scene '{scene_id}' does not belong to "
                       f"location '{location_id}'.",
            )
        emgr.delete_scene(scene_id)
        return {"status": "ok", "deleted": scene_id}

    @application.post("/api/explore/{location_id}/scenes")
    def api_explore_add_scene(
        location_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Manually add a scene for a location.

        Body: {"image_id": "IMG-XXXX", "scene_type": "overview",
               "description": "..."}
        """
        from core.exploration import (
            ExplorationManager, ExplorationValidationError,
        )

        emgr = ExplorationManager()
        image_id = (body.get("image_id") or "").strip()
        if not image_id:
            raise HTTPException(
                status_code=400, detail="'image_id' is required.",
            )

        try:
            scene = emgr.add_scene(
                location_id=location_id,
                image_id=image_id,
                scene_type=body.get("scene_type", "overview"),
                description=body.get("description", ""),
                metadata=body.get("metadata", {}),
            )
        except ExplorationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        result = scene.to_dict()
        result["image_url"] = f"/api/images/file/{scene.image_id}"
        return result

    # ── Stories (F-041) ──────────────────────────────────────

    @application.get("/api/stories")
    def api_stories_list(
        status: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List all stories, optionally filtered by status."""
        from core.story import StoryManager

        smgr = StoryManager()
        stories = smgr.list_stories(status=status)
        result = []
        for s in stories:
            result.append({
                "story_id": s.story_id,
                "title": s.title,
                "synopsis": s.synopsis,
                "author": s.author,
                "status": s.status,
                "style_preset_key": s.style_preset_key,
                "template_id": s.template_id,
                "chapter_count": len(s.chapters),
                "scene_count": sum(
                    len(ch.scenes) for ch in s.chapters
                ),
                "illustration_count": sum(
                    1 for ch in s.chapters
                    for sc in ch.scenes if sc.image_id
                ),
                "entity_refs": s.entity_refs,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            })
        return result

    @application.post("/api/stories")
    def api_stories_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new story.

        Body: {"title": "...", "synopsis": "...", "author": "...",
               "style_preset_key": "", "template_id": ""}
        """
        from core.story import StoryManager, StoryValidationError

        title = (body.get("title") or "").strip()
        if not title:
            raise HTTPException(
                status_code=400, detail="'title' is required.",
            )

        smgr = StoryManager()
        try:
            story = smgr.create(
                title,
                body.get("synopsis", ""),
                author=body.get("author", ""),
                style_preset_key=body.get("style_preset_key", ""),
                template_id=body.get("template_id", ""),
                metadata=body.get("metadata"),
            )
        except StoryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return story.to_dict()

    @application.get("/api/stories/{story_id}")
    def api_stories_detail(story_id: str) -> dict[str, Any]:
        """Get a full story with chapters and scenes."""
        from core.story import StoryManager, StoryNotFoundError

        smgr = StoryManager()
        try:
            story = smgr.get(story_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )

        d = story.to_dict()
        # Enrich scenes with image URLs
        for ch in d.get("chapters", []):
            for sc in ch.get("scenes", []):
                if sc.get("image_id"):
                    sc["image_url"] = f"/api/images/file/{sc['image_id']}"
                else:
                    sc["image_url"] = ""
        return d

    @application.put("/api/stories/{story_id}")
    def api_stories_update(
        story_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update story fields.

        Body: {"title": "...", "synopsis": "...",
               "style_preset_key": "...", "template_id": "..."}
        """
        from core.story import (
            StoryManager, StoryNotFoundError, StoryValidationError,
        )

        smgr = StoryManager()
        try:
            updated = smgr.update(
                story_id,
                title=body.get("title"),
                synopsis=body.get("synopsis"),
                style_preset_key=body.get("style_preset_key"),
                template_id=body.get("template_id"),
                metadata=body.get("metadata"),
            )
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except StoryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return updated.to_dict()

    @application.put("/api/stories/{story_id}/status")
    def api_stories_update_status(
        story_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Transition a story's lifecycle status.

        Body: {"status": "active"}
        """
        from core.story import (
            StoryManager, StoryNotFoundError,
            StoryValidationError, StoryLifecycleError,
        )

        new_status = (body.get("status") or "").strip()
        if not new_status:
            raise HTTPException(
                status_code=400, detail="'status' is required.",
            )

        smgr = StoryManager()
        try:
            updated = smgr.update_status(story_id, new_status)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except StoryLifecycleError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except StoryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return updated.to_dict()

    @application.delete("/api/stories/{story_id}")
    def api_stories_delete(story_id: str) -> dict[str, Any]:
        """Delete a story."""
        from core.story import StoryManager, StoryNotFoundError

        smgr = StoryManager()
        try:
            smgr.delete(story_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        return {"status": "ok", "deleted": story_id}

    # ── Stories: Chapters ────────────────────────────────────

    @application.post("/api/stories/{story_id}/chapters")
    def api_stories_add_chapter(
        story_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a chapter to a story.

        Body: {"title": "Chapter 1", "synopsis": "..."}
        """
        from core.story import (
            StoryManager, StoryNotFoundError, StoryValidationError,
        )

        smgr = StoryManager()
        try:
            chapter = smgr.add_chapter(
                story_id,
                title=body.get("title", ""),
                synopsis=body.get("synopsis", ""),
                metadata=body.get("metadata"),
            )
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except StoryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return chapter.to_dict()

    @application.put("/api/stories/{story_id}/chapters/{chapter_id}")
    def api_stories_update_chapter(
        story_id: str,
        chapter_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a chapter's title or synopsis.

        Body: {"title": "...", "synopsis": "..."}
        """
        from core.story import (
            StoryManager, StoryNotFoundError, ChapterNotFoundError,
        )

        smgr = StoryManager()
        try:
            chapter = smgr.update_chapter(
                story_id, chapter_id,
                title=body.get("title"),
                synopsis=body.get("synopsis"),
            )
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except ChapterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )

        return chapter.to_dict()

    @application.delete("/api/stories/{story_id}/chapters/{chapter_id}")
    def api_stories_delete_chapter(
        story_id: str,
        chapter_id: str,
    ) -> dict[str, Any]:
        """Delete a chapter and all its scenes."""
        from core.story import (
            StoryManager, StoryNotFoundError, ChapterNotFoundError,
        )

        smgr = StoryManager()
        try:
            smgr.delete_chapter(story_id, chapter_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except ChapterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        return {"status": "ok", "deleted": chapter_id}

    # ── Stories: Scenes ──────────────────────────────────────

    @application.post(
        "/api/stories/{story_id}/chapters/{chapter_id}/scenes",
    )
    def api_stories_add_scene(
        story_id: str,
        chapter_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a scene to a chapter.

        Body: {"narrative_text": "...", "characters": ["CH-0001"],
               "location_id": "LOC-0001", "mood": "tense"}
        """
        from core.story import (
            StoryManager, StoryNotFoundError,
            ChapterNotFoundError, StoryValidationError,
        )

        smgr = StoryManager()
        try:
            scene = smgr.add_scene(
                story_id, chapter_id,
                narrative_text=body.get("narrative_text", ""),
                characters=body.get("characters"),
                location_id=body.get("location_id", ""),
                mood=body.get("mood", ""),
                metadata=body.get("metadata"),
            )
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except ChapterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        except StoryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return scene.to_dict()

    @application.put(
        "/api/stories/{story_id}/chapters/{chapter_id}/scenes/{scene_id}",
    )
    def api_stories_update_scene(
        story_id: str,
        chapter_id: str,
        scene_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a scene's fields.

        Body: {"narrative_text": "...", "characters": [...],
               "location_id": "...", "mood": "..."}
        """
        from core.story import (
            StoryManager, StoryNotFoundError,
            ChapterNotFoundError, SceneNotFoundError,
        )

        smgr = StoryManager()
        try:
            scene = smgr.update_scene(
                story_id, chapter_id, scene_id,
                narrative_text=body.get("narrative_text"),
                characters=body.get("characters"),
                location_id=body.get("location_id"),
                mood=body.get("mood"),
                image_id=body.get("image_id"),
                prompt_used=body.get("prompt_used"),
            )
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except ChapterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        except SceneNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Scene '{scene_id}' not found.",
            )

        d = scene.to_dict()
        if scene.image_id:
            d["image_url"] = f"/api/images/file/{scene.image_id}"
        return d

    @application.delete(
        "/api/stories/{story_id}/chapters/{chapter_id}/scenes/{scene_id}",
    )
    def api_stories_delete_scene(
        story_id: str,
        chapter_id: str,
        scene_id: str,
    ) -> dict[str, Any]:
        """Delete a scene."""
        from core.story import (
            StoryManager, StoryNotFoundError,
            ChapterNotFoundError, SceneNotFoundError,
        )

        smgr = StoryManager()
        try:
            smgr.delete_scene(story_id, chapter_id, scene_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )
        except ChapterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        except SceneNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Scene '{scene_id}' not found.",
            )
        return {"status": "ok", "deleted": scene_id}

    # ── Stories: Narrate & Illustrate ────────────────────────

    @application.post(
        "/api/stories/{story_id}/chapters/{chapter_id}"
        "/scenes/{scene_id}/narrate",
    )
    async def api_stories_narrate_scene(
        story_id: str,
        chapter_id: str,
        scene_id: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate LLM narration for a scene.

        Uses the story/chapter context and entity data to build a
        rich prompt, then calls the LLM to generate narrative prose.

        Optional body: {
            "provider": "openrouter",
            "model": "...",
            "participants": [
                {"id": "sage", "type": "council"},
                {"id": "CH-0001", "type": "character"}
            ]
        }

        Returns: {"narrative_text": "...", "model": "...", "provider": "..."}
        """
        from core.story import (
            StoryManager, StoryNotFoundError,
            ChapterNotFoundError, SceneNotFoundError,
        )
        from core.api_client import APIClient, ChatMessage
        from core.characters import CharacterManager
        from core.locations import LocationManager

        body = body or {}

        # F-043: Validate participants
        participants = body.get("participants", [])
        if participants:
            if not isinstance(participants, list):
                raise HTTPException(
                    status_code=400,
                    detail="'participants' must be a list.",
                )
            if len(participants) > _PARTICIPANT_MAX:
                raise HTTPException(
                    status_code=400,
                    detail=f"Too many participants ({len(participants)}). "
                           f"Maximum is {_PARTICIPANT_MAX}.",
                )

        smgr = StoryManager()

        try:
            story = smgr.get(story_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )

        # Find chapter and scene
        chapter = None
        scene = None
        for ch in story.chapters:
            if ch.chapter_id == chapter_id:
                chapter = ch
                for sc in ch.scenes:
                    if sc.scene_id == scene_id:
                        scene = sc
                        break
                break

        if chapter is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        if scene is None:
            raise HTTPException(
                status_code=404,
                detail=f"Scene '{scene_id}' not found.",
            )

        # Build the narration prompt with entity context
        prompt = StoryManager.build_scene_narration_prompt(
            story, chapter, scene,
            character_manager=CharacterManager(),
            location_manager=LocationManager(),
        )

        # F-043: Enrich prompt with participant context
        if participants:
            participant_context = _build_participant_context(participants)
            if participant_context:
                prompt = prompt + "\n\n" + participant_context

        # Call LLM
        client = APIClient()
        from core.registry import CouncilMember

        provider = body.get("provider", "openrouter")
        model = body.get("model", "mistralai/mistral-small-2603")
        narrator = CouncilMember(
            name="Narrator",
            role="Story Narrator",
            description="An expert storyteller",
            api_provider=provider,
            model=model,
            system_prompt=(
                "You are a masterful storyteller. Write vivid, "
                "atmospheric prose fiction. Respond with only the "
                "narrative text — no commentary or meta-text."
            ),
        )
        messages = [ChatMessage(role="user", content=prompt)]
        response = await client.chat(narrator, messages)

        # Save narrative to scene
        smgr.update_scene(
            story_id, chapter_id, scene_id,
            narrative_text=response.content,
        )

        return {
            "narrative_text": response.content,
            "model": response.model,
            "provider": response.provider,
        }

    @application.post(
        "/api/stories/{story_id}/chapters/{chapter_id}"
        "/scenes/{scene_id}/illustrate",
    )
    def api_stories_illustrate_scene(
        story_id: str,
        chapter_id: str,
        scene_id: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger illustration generation for a scene.

        Uses the scene's narrative and entity context to generate
        an image via the ComfyUI pipeline.

        Optional body: {
            "template_id": "TPL-XXXX",
            "style_preset_key": "fantasy_art",
            "width": 768, "height": 512,
            "participants": [
                {"id": "sage", "type": "council"},
                {"id": "CH-0001", "type": "character"}
            ]
        }

        Returns: {"job_id": "GEN-XXXX", "status": "queued"}
        """
        from core.story import (
            StoryManager, StoryNotFoundError,
            ChapterNotFoundError, SceneNotFoundError,
        )
        from core.generation_pipeline import (
            GenerationRequest, GenerationValidationError,
            GenerationQueueFullError,
        )

        body = body or {}

        # F-043: Validate participants
        participants = body.get("participants", [])
        if participants:
            if not isinstance(participants, list):
                raise HTTPException(
                    status_code=400,
                    detail="'participants' must be a list.",
                )
            if len(participants) > _PARTICIPANT_MAX:
                raise HTTPException(
                    status_code=400,
                    detail=f"Too many participants ({len(participants)}). "
                           f"Maximum is {_PARTICIPANT_MAX}.",
                )

        smgr = StoryManager()

        try:
            story = smgr.get(story_id)
        except StoryNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Story '{story_id}' not found.",
            )

        # Find chapter and scene
        chapter = None
        scene = None
        for ch in story.chapters:
            if ch.chapter_id == chapter_id:
                chapter = ch
                for sc in ch.scenes:
                    if sc.scene_id == scene_id:
                        scene = sc
                        break
                break

        if chapter is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter '{chapter_id}' not found.",
            )
        if scene is None:
            raise HTTPException(
                status_code=404,
                detail=f"Scene '{scene_id}' not found.",
            )

        # Build prompt from narrative + context
        prompt_parts = []
        if scene.narrative_text:
            prompt_parts.append(
                f"Illustrate: {scene.narrative_text[:500]}"
            )
        if scene.mood:
            prompt_parts.append(f"Mood: {scene.mood}")
        if not prompt_parts:
            prompt_parts.append(
                f"Scene from story '{story.title}', "
                f"chapter '{chapter.title or 'Untitled'}'"
            )

        user_prompt = " | ".join(prompt_parts)

        # F-043: Enrich prompt with participant context
        if participants:
            participant_context = _build_participant_context(participants)
            if participant_context:
                user_prompt = user_prompt + "\n\n" + participant_context

        # Determine template
        template_id = (body.get("template_id") or "").strip()
        if not template_id and story.template_id:
            template_id = story.template_id
        if not template_id:
            try:
                from core.template_assignments import (
                    TemplateAssignmentManager,
                )
                tam = TemplateAssignmentManager()
                # Use location template if scene has a location,
                # otherwise fall back to character
                entity_type = (
                    "location" if scene.location_id else "character"
                )
                rec = tam.get_recommended_template(entity_type)
                template_id = rec.get("template_id", "")
            except Exception:
                pass
        if not template_id:
            raise HTTPException(
                status_code=400,
                detail="No template specified and no default template "
                       "could be determined. Specify 'template_id' in "
                       "the request body or set a default in Settings.",
            )

        # Build generation request
        entity_type = "location" if scene.location_id else "character"
        entity_id = scene.location_id or (
            scene.characters[0] if scene.characters else "story"
        )

        try:
            request = GenerationRequest.create(
                entity_type=entity_type,
                entity_id=entity_id,
                template_id=template_id,
                prompt_mode="raw_user",
                user_prompt=user_prompt,
                style_preset_key=(
                    body.get("style_preset_key")
                    or story.style_preset_key
                    or ""
                ),
                width=body.get("width", 768),
                height=body.get("height", 512),
                seed=body.get("seed", 0),
                metadata={
                    "story_illustration": True,
                    "story_id": story_id,
                    "chapter_id": chapter_id,
                    "scene_id": scene_id,
                    "participants": [
                        {"id": p.get("id"), "type": p.get("type")}
                        for p in participants
                    ] if participants else [],
                },
            )
        except GenerationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        pipeline = _get_pipeline()
        try:
            job_id = pipeline.start_generation(request)
        except GenerationQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc))

        return {
            "job_id": job_id,
            "status": "queued",
            "story_id": story_id,
            "chapter_id": chapter_id,
            "scene_id": scene_id,
        }

    # ── Static Files ──────────────────────────────────────────

    static_dir = WEB_STATIC_DIR
    if static_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    @application.get("/")
    def serve_index() -> FileResponse:
        """Serve the SPA index.html."""
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found.")
        return FileResponse(str(index))

    return application


# Module-level app instance for ``uvicorn core.web_api:app``
app = create_app()
