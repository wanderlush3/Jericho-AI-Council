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

        return data

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
               "category": "ethics", "body": "..."}
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

        pmgr = ProposalManager()
        try:
            proposal = pmgr.create(
                title, description, author=author, category=category,
                body=proposal_body,
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
            from core.api_client import APIClient

            registry = CouncilRegistry().load()
            client = APIClient()
            dmgr = DiscussionManager(
                registry=registry,
                api_client=client,
                proposal_manager=pmgr,
            )
            participants = registry.list_names()
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
        from core.registry import CouncilRegistry
        from core.api_client import APIClient, ChatMessage

        async def event_generator():
            try:
                pmgr = ProposalManager()
                registry = CouncilRegistry().load()
                client = APIClient()
                dmgr = DiscussionManager(
                    registry=registry,
                    api_client=client,
                    proposal_manager=pmgr,
                )

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

                for name in record.participants:
                    member = registry.get(name)

                    # Build prompt
                    from core.discussion import _build_discussion_prompt
                    all_contribs = list(record.contributions) + new_contributions
                    prompt = _build_discussion_prompt(
                        member, proposal, all_contribs, round_number,
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
                    metadata=dict(record.metadata),
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
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        pmgr = ProposalManager()
        registry = CouncilRegistry().load()
        client = APIClient()
        dmgr = DiscussionManager(
            registry=registry,
            api_client=client,
            proposal_manager=pmgr,
        )

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

    @application.post("/api/proposals/{proposal_id}/vote")
    async def api_proposal_vote(proposal_id: str) -> dict[str, Any]:
        """Run a full vote: open voting, have each council member cast
        an AI-generated vote, close voting, return tally.
        """
        from core.proposals import ProposalManager, ProposalNotFoundError
        from core.voting import VotingEngine, Vote, VotingStateError
        from core.discussion import DiscussionManager, DiscussionNotFoundError
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
            dmgr = DiscussionManager(
                registry=registry,
                api_client=client,
                proposal_manager=pmgr,
            )
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
            vote_prompt = (
                f"## Vote Required: {proposal.title}\n"
                f"**Proposal ID:** {proposal.id}\n"
                f"**Category:** {proposal.category}\n"
                f"**Author:** {proposal.author}\n"
                f"**Description:** {proposal.description}\n"
                f"{discussion_context}\n\n"
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

    # ── Discussion Info ───────────────────────────────────────

    @application.get("/api/proposals/{proposal_id}/discussion")
    def api_proposal_discussion(proposal_id: str) -> dict[str, Any]:
        """Get the discussion record for a proposal."""
        from core.proposals import ProposalManager
        from core.discussion import DiscussionManager, DiscussionNotFoundError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        pmgr = ProposalManager()
        registry = CouncilRegistry().load()
        client = APIClient()
        dmgr = DiscussionManager(
            registry=registry,
            api_client=client,
            proposal_manager=pmgr,
        )

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
        """Instantiate HumanChat with a real registry and API client."""
        from core.api_client import APIClient
        from core.human_chat import HumanChat
        from core.registry import CouncilRegistry

        registry = CouncilRegistry().load()
        client = APIClient()
        return HumanChat(
            registry=registry,
            api_client=client,
            conversations_dir=conversations_dir,
        )

    @application.get("/api/chat")
    def api_chat_list(
        member: str | None = Query(None),
        closed: bool | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List human-to-agent chats with optional filters."""
        from core.human_chat import HumanChat
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)
        chats = hc.list_chats(member=member, closed=closed)
        return [c.to_dict() for c in chats]

    @application.get("/api/chat/{chat_id}")
    def api_chat_detail(chat_id: str) -> dict[str, Any]:
        """Get a single chat record with messages."""
        from core.human_chat import HumanChat, HumanChatNotFoundError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)
        try:
            rec = hc.get(chat_id)
        except HumanChatNotFoundError:
            raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
        return rec.to_dict()

    @application.post("/api/chat")
    def api_chat_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new chat. Body: {\"member_name\": \"Sage\", \"title\": \"...\", \"topic\": \"...\", \"character_id\": \"CH-0001\"}."""
        from core.human_chat import HumanChat, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

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

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="'content' is required.")

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        member_name = body.get("member_name", "").strip()
        if not member_name:
            raise HTTPException(status_code=400, detail="'member_name' is required.")

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        member_name = body.get("member_name", "").strip()
        if not member_name:
            raise HTTPException(status_code=400, detail="'member_name' is required.")

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        character_id = body.get("character_id", "").strip()
        if not character_id:
            raise HTTPException(status_code=400, detail="'character_id' is required.")

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        character_id = body.get("character_id", "").strip()
        if not character_id:
            raise HTTPException(status_code=400, detail="'character_id' is required.")

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
                registry = CouncilRegistry().load()
                client = APIClient()
                hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        async def event_generator():
            try:
                registry = CouncilRegistry().load()
                client = APIClient()
                hc = HumanChat(registry=registry, api_client=client)

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
        from core.human_chat import HumanChat, HumanChatNotFoundError, HumanChatError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        summary = ""
        if body:
            summary = body.get("summary", "").strip()

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

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
