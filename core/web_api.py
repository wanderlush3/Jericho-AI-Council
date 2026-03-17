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
                    reason=reason[:500],
                    weight=member.vote_weight,
                )
                try:
                    engine.cast_vote(proposal_id, vote)
                except Exception:
                    pass  # duplicate vote, skip

                vote_results.append({
                    "voter": member.name,
                    "choice": choice,
                    "reason": reason[:200],
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

        return {
            "proposal": pmgr.get(proposal_id).to_dict(),
            "vote_record": record.to_dict(),
            "tally": tally.to_dict(),
            "individual_votes": vote_results,
        }

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

    # ── Characters ────────────────────────────────────────────

    @application.get("/api/characters")
    def api_characters_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List characters with optional filters."""
        from core.characters import CharacterManager
        mgr = CharacterManager()
        items = mgr.list_characters(status=status, author=author, tag=tag)
        return [c.to_dict() for c in items]

    @application.get("/api/characters/{character_id}")
    def api_character_detail(character_id: str) -> dict[str, Any]:
        """Get a single character template."""
        from core.characters import CharacterManager, CharacterNotFoundError
        mgr = CharacterManager()
        try:
            c = mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        return c.to_dict()

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

    @application.get("/api/settings/models")
    def api_models_status() -> list[dict[str, Any]]:
        """Return configured model for each API provider."""
        from core.api_keys import APIKeyManager
        mgr = APIKeyManager()
        return mgr.all_model_status()

    @application.post("/api/settings/models")
    def api_models_save(body: dict[str, Any]) -> dict[str, Any]:
        """Save a model name.  Body: {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet"}."""
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
        """Create a new chat. Body: {\"member_name\": \"Sage\", \"title\": \"Ethics Q&A\", \"topic\": \"...\"}."""
        from core.human_chat import HumanChat, HumanChatValidationError
        from core.registry import CouncilRegistry
        from core.api_client import APIClient

        member_name = body.get("member_name", "").strip()
        title = body.get("title", "").strip()
        topic = body.get("topic", "").strip()

        if not member_name or not title:
            raise HTTPException(
                status_code=400,
                detail="Both 'member_name' and 'title' are required.",
            )

        registry = CouncilRegistry().load()
        client = APIClient()
        hc = HumanChat(registry=registry, api_client=client)

        chat_id = _next_chat_id()
        try:
            rec = hc.create_chat(
                chat_id, title, member_name=member_name, topic=topic,
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
