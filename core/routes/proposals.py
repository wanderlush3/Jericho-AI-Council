"""
Jericho — Proposals Routes
"""

from __future__ import annotations


import json as json_module
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from core.manager_cache import (
    get_api_client,
    get_character_manager,
    get_item_manager,
    get_law_manager,
    get_location_manager,
    get_proposal_manager,
    get_registry,
    get_voting_engine,
)

from core.routes._helpers import _make_discussion_manager

router = APIRouter()

# ── Proposals ─────────────────────────────────────────────

@router.get("/api/proposals")
def api_proposals_list(
    status: str | None = Query(None),
    category: str | None = Query(None),
    author: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List proposals with optional filters."""
    from core.proposals import ProposalManager
    mgr = get_proposal_manager()
    items = mgr.list_proposals(status=status, category=category, author=author)
    return [p.to_dict() for p in items]

@router.get("/api/proposals/{proposal_id}")
def api_proposal_detail(proposal_id: str) -> dict[str, Any]:
    """Get a single proposal."""
    from core.proposals import ProposalManager, ProposalNotFoundError
    mgr = get_proposal_manager()
    try:
        p = mgr.get(proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
    return p.to_dict()

@router.post("/api/proposals")
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

    pmgr = get_proposal_manager()
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
        participants = get_registry().list_names()
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

@router.post("/api/proposals/{proposal_id}/discuss-stream")
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
            pmgr = get_proposal_manager()
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

            registry = get_registry()
            client = get_api_client()

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

@router.post("/api/proposals/{proposal_id}/discuss-pause")
def api_proposal_discuss_pause(proposal_id: str) -> dict[str, Any]:
    """Close/pause the discussion on a proposal."""
    from core.proposals import ProposalManager
    from core.discussion import (
        DiscussionManager, DiscussionNotFoundError, DiscussionStateError,
    )

    pmgr = get_proposal_manager()
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

@router.get("/api/proposals/{proposal_id}/scheduled-message")
def api_proposal_scheduled_message_get(proposal_id: str) -> dict[str, Any]:
    """Get the scheduled user message for the next discussion round."""
    from core.proposals import ProposalManager
    from core.discussion import DiscussionNotFoundError

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/scheduled-message")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/send-to-review")
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

    pmgr = get_proposal_manager()

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

@router.put("/api/proposals/{proposal_id}/final-proposal")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/vote")
async def api_proposal_vote(proposal_id: str) -> dict[str, Any]:
    """Run a full vote: open voting, have each council member cast
    an AI-generated vote, close voting, return tally.
    """
    from core.proposals import ProposalManager, ProposalNotFoundError
    from core.voting import VotingEngine, Vote, VotingStateError
    from core.discussion import DiscussionNotFoundError
    from core.api_client import ChatMessage

    pmgr = get_proposal_manager()
    registry = get_registry()
    client = get_api_client()
    engine = get_voting_engine()

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

@router.post("/api/proposals/{proposal_id}/withdraw")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/handoff-character")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/handoff-location")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/handoff-item")
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

    pmgr = get_proposal_manager()
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

@router.post("/api/proposals/{proposal_id}/handoff-law")
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

    pmgr = get_proposal_manager()
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

@router.get("/api/proposals/{proposal_id}/discussion")
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

