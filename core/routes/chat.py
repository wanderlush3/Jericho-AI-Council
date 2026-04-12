"""
Jericho — Chat Routes
"""

from __future__ import annotations


import json as json_module
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from core.manager_cache import (
    get_api_client,
    get_memory_influence,
    get_proposal_manager,
    get_registry,
)


router = APIRouter()

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
    """Instantiate HumanChat with cached registry, API client, and memory influence."""
    from core.human_chat import HumanChat

    return HumanChat(
        registry=get_registry(),
        api_client=get_api_client(),
        conversations_dir=conversations_dir,
        memory_influence=get_memory_influence(),
    )

def _make_discussion_manager(
    proposal_manager: "ProposalManager | None" = None,
) -> "DiscussionManager":
    """Instantiate DiscussionManager with cached dependencies."""
    from core.discussion import DiscussionManager

    pmgr = proposal_manager if proposal_manager is not None else get_proposal_manager()
    return DiscussionManager(
        registry=get_registry(),
        api_client=get_api_client(),
        proposal_manager=pmgr,
        memory_influence=get_memory_influence(),
    )

@router.get("/api/chat")
def api_chat_list(
    member: str | None = Query(None),
    closed: bool | None = Query(None),
) -> list[dict[str, Any]]:
    """List human-to-agent chats with optional filters."""
    hc = _make_human_chat()
    chats = hc.list_chats(member=member, closed=closed)
    return [c.to_dict() for c in chats]

@router.get("/api/chat/{chat_id}")
def api_chat_detail(chat_id: str) -> dict[str, Any]:
    """Get a single chat record with messages."""
    from core.human_chat import HumanChatNotFoundError

    hc = _make_human_chat()
    try:
        rec = hc.get(chat_id)
    except HumanChatNotFoundError:
        raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")
    return rec.to_dict()

@router.post("/api/chat")
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

@router.post("/api/chat/{chat_id}/send")
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

@router.post("/api/chat/{chat_id}/add-member")
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

@router.post("/api/chat/{chat_id}/remove-member")
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

@router.post("/api/chat/{chat_id}/add-character")
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

@router.post("/api/chat/{chat_id}/remove-character")
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

@router.post("/api/chat/{chat_id}/pause")
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

@router.post("/api/chat/{chat_id}/resume")
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

@router.post("/api/chat/{chat_id}/continue")
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

@router.post("/api/chat/{chat_id}/send-stream")
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
            t_start = time.monotonic()
            async for member_name, response, record in hc.get_agent_response_streaming(chat_id):
                t_end = time.monotonic()
                response_time_ms = round((t_end - t_start) * 1000)
                last_record = record
                content_text = response.content or ""
                event_data = json_module.dumps({
                    "speaker": member_name,
                    "content": content_text,
                    "model": response.model,
                    "provider": response.provider,
                    "response_time_ms": response_time_ms,
                })
                yield f"event: message\ndata: {event_data}\n\n"
                # Reset timer for the next participant
                t_start = time.monotonic()

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

@router.post("/api/chat/{chat_id}/continue-stream")
async def api_chat_continue_stream(chat_id: str):
    """Stream one round of AI-to-AI responses via SSE."""
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    async def event_generator():
        try:
            hc = _make_human_chat()

            t_start = time.monotonic()
            async for member_name, response, record in hc.continue_conversation_streaming(chat_id):
                t_end = time.monotonic()
                response_time_ms = round((t_end - t_start) * 1000)
                content_text = response.content or ""
                event_data = json_module.dumps({
                    "speaker": member_name,
                    "content": content_text,
                    "model": response.model,
                    "provider": response.provider,
                    "response_time_ms": response_time_ms,
                })
                yield f"event: message\ndata: {event_data}\n\n"
                # Reset timer for the next participant
                t_start = time.monotonic()

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

@router.post("/api/chat/{chat_id}/close")
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

