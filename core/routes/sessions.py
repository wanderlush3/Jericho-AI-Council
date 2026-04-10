"""
Jericho — Sessions Routes
"""

from __future__ import annotations


import json as json_module
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse


from core.routes._helpers import _make_discussion_manager

router = APIRouter()

@router.get("/api/council-sessions")
def api_council_sessions_list(
    status: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List council sessions with optional status filter."""
    from core.council_session import CouncilSessionManager
    mgr = CouncilSessionManager()
    sessions = mgr.list_sessions(status=status)
    return [s.to_dict() for s in sessions]

@router.get("/api/council-sessions/{session_id}")
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

@router.post("/api/council-sessions")
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

@router.post("/api/council-sessions/{session_id}/discuss-stream")
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

@router.post("/api/council-sessions/{session_id}/close")
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

@router.get("/api/council-sessions/{session_id}/scheduled-message")
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

@router.post("/api/council-sessions/{session_id}/scheduled-message")
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

@router.post("/api/council-sessions/{session_id}/handoff-proposal")
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

