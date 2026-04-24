"""
Jericho — Tasks Routes
"""

from __future__ import annotations

import logging


import json as json_module
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse


log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/tasks")
def api_tasks_list(
    status: str | None = Query(None),
    assignee: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List tasks with optional filters."""
    from core.tasks import TaskManager

    mgr = TaskManager()
    tasks = mgr.list_tasks(status=status, assignee=assignee)
    return [t.to_dict() for t in tasks]

@router.get("/api/tasks/{task_id}")
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

@router.post("/api/tasks")
def api_tasks_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new task.

    Body: {name, description, reason, assignees: [...],
           task_type: "standard"|"gift"|"purchase",
           gift_config: {...}, purchase_config: {...}}
    """
    from core.tasks import TaskManager, TaskValidationError

    name = (body.get("name", "") or "").strip()
    description = (body.get("description", "") or "").strip()
    reason = (body.get("reason", "") or "").strip()
    assignees = body.get("assignees", [])
    task_type = (body.get("task_type", "standard") or "standard").strip()
    gift_config = body.get("gift_config") or None
    purchase_config = body.get("purchase_config") or None

    mgr = TaskManager()
    try:
        task = mgr.create(
            name=name,
            description=description,
            reason=reason,
            assignees=assignees,
            task_type=task_type,
            gift_config=gift_config,
            purchase_config=purchase_config,
        )
    except TaskValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return task.to_dict()

@router.put("/api/tasks/{task_id}")
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

@router.put("/api/tasks/{task_id}/status")
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

@router.post("/api/tasks/do-tasks")
async def api_tasks_do_tasks() -> StreamingResponse:
    """Execute all active tasks via SSE.

    For each active task, for each assignee, send a prompt that
    additively layers the task context on top of existing memory
    and context injections.  Each assignee narrates completing
    the task over up to 5 rounds.  After all rounds, the task
    transitions to 'completed'.
    """
    from core.tasks import TaskManager, Task, TaskMessage
    from core.api_client import ChatMessage
    from core.memory_influence import MemoryInfluence
    from core.memory import AgentMemory, MemoryEntry
    from core.manager_cache import get_registry, get_api_client, get_character_manager
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

            registry = get_registry()
            client = get_api_client()
            mi = MemoryInfluence()

            # Pre-load characters for character assignees
            try:
                cmgr = get_character_manager()
                all_chars = cmgr.list_characters(status="active")
                char_map = {c.name.lower(): c for c in all_chars}
            except Exception:
                log.debug("Tasks: character manager unavailable", exc_info=True)
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
                                log.debug(
                                    "Tasks: failed to persist memory for %s",
                                    assignee_name, exc_info=True,
                                )

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

                # ── Gift execution for gift tasks ─────────────────
                gift_result_data = {}
                if task.task_type == "gift" and task.gift_config:
                    try:
                        gc = task.gift_config
                        from core.items import ItemManager
                        imgr = ItemManager()
                        gift_record = imgr.gift_item(
                            gc["item_id"],
                            from_owner=gc["from_owner"],
                            to_owner=gc["to_owner"],
                            message=gc.get("message", ""),
                        )

                        # Create gift chat record
                        from core.routes.items import _create_gift_chat
                        chat_record = _create_gift_chat(gift_record)

                        # Fire reputation hooks
                        from core.reputation_hooks import on_gift_given
                        on_gift_given(gift_record)

                        gift_result_data = {
                            "item_id": gift_record.item_id,
                            "item_name": gift_record.item_name,
                            "from_name": gift_record.from_owner.get("name", ""),
                            "to_name": gift_record.to_owner.get("name", ""),
                            "chat_id": chat_record.get("chat_id", ""),
                            "timestamp": gift_record.timestamp,
                        }

                        # Persist gift_result on the task
                        d2 = updated.to_dict()
                        d2["gift_result"] = gift_result_data
                        updated2 = TaskModel.from_dict(d2)
                        tmgr._save(updated2)

                        # Emit gift_complete SSE event
                        gift_evt = json_module.dumps({
                            "type": "gift_complete",
                            "task_id": task.id,
                            "task_name": task.name,
                            **gift_result_data,
                        })
                        yield f"event: gift_complete\ndata: {gift_evt}\n\n"

                    except Exception as gift_exc:
                        log.warning(
                            "Gift execution failed for task %s: %s",
                            task.id, gift_exc,
                        )
                        gift_err = json_module.dumps({
                            "type": "gift_error",
                            "task_id": task.id,
                            "detail": str(gift_exc)[:200],
                        })
                        yield f"event: gift_error\ndata: {gift_err}\n\n"

                # ── Purchase execution for purchase tasks ─────────
                purchase_result_data = {}
                if task.task_type == "purchase" and task.purchase_config:
                    try:
                        pc = task.purchase_config
                        store_id = pc["store_id"]
                        item_id = pc["item_id"]
                        buyer_account_id = pc["buyer_account_id"]
                        buyer_entity_id = pc.get("buyer_entity_id", "")
                        buyer_name = pc.get("buyer_name", "")
                        buyer_type = pc.get("buyer_type", "user")

                        # Look up buyer's reputation tier for price modifier
                        price_modifier = 1.0
                        buyer_tier = "neutral"
                        if buyer_entity_id:
                            try:
                                from core.reputation_effects import (
                                    get_entity_tier, get_price_modifier,
                                )
                                buyer_tier = get_entity_tier(buyer_entity_id)
                                price_modifier = get_price_modifier(buyer_tier)
                            except Exception:
                                log.debug(
                                    "Tasks: reputation lookup failed for %s",
                                    buyer_entity_id, exc_info=True,
                                )

                        # Execute the purchase
                        from core.stores import StoreManager
                        from core.treasury import TreasuryManager
                        smgr = StoreManager()
                        treasury = TreasuryManager()
                        purchase_result = smgr.purchase(
                            store_id, item_id, buyer_account_id, treasury,
                            price_modifier=price_modifier,
                        )

                        # Add item ownership to the buyer
                        from core.items import ItemManager
                        item_mgr = ItemManager()
                        try:
                            bought_item = item_mgr.get(item_id)
                            current_owners = list(bought_item.owned_by)
                            buyer_owner = {"name": buyer_name or buyer_account_id, "type": buyer_type}
                            # Only add if not already an owner
                            existing_keys = {
                                (o.get("name", "").lower(), o.get("type", ""))
                                for o in current_owners
                            }
                            buyer_key = (buyer_owner["name"].lower(), buyer_owner["type"])
                            if buyer_key not in existing_keys:
                                current_owners.append(buyer_owner)
                                item_mgr.update(item_id, owned_by=current_owners)
                        except Exception:
                            log.debug(
                                "Tasks: failed to add ownership for %s on %s",
                                buyer_name, item_id, exc_info=True,
                            )

                        # Fire reputation hooks
                        try:
                            from core.reputation_hooks import on_purchase
                            store_data = purchase_result.get("store", {})
                            item_data = purchase_result.get("item", {})
                            adjusted = purchase_result.get("adjusted_price", {})
                            on_purchase(
                                buyer_entity_id=buyer_entity_id,
                                item_name=bought_item.name if bought_item else item_id,
                                store_name=store_data.get("name", store_id),
                                price_gold=adjusted.get("gold", 0),
                            )
                        except Exception:
                            log.debug(
                                "Tasks: purchase reputation hook failed for %s",
                                task.id, exc_info=True,
                            )

                        adjusted_price = purchase_result.get("adjusted_price", {})
                        store_data = purchase_result.get("store", {})
                        item_data = purchase_result.get("item", {})

                        purchase_result_data = {
                            "store_id": store_id,
                            "store_name": store_data.get("name", ""),
                            "item_id": item_id,
                            "item_name": bought_item.name if bought_item else "",
                            "buyer_name": buyer_name,
                            "buyer_tier": buyer_tier,
                            "price_modifier": round(price_modifier, 2),
                            "adjusted_price": adjusted_price,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        # Persist purchase_result on the task
                        d3 = updated.to_dict()
                        d3["purchase_result"] = purchase_result_data
                        updated3 = TaskModel.from_dict(d3)
                        tmgr._save(updated3)

                        # Emit purchase_complete SSE event
                        purchase_evt = json_module.dumps({
                            "type": "purchase_complete",
                            "task_id": task.id,
                            "task_name": task.name,
                            **purchase_result_data,
                        })
                        yield f"event: purchase_complete\ndata: {purchase_evt}\n\n"

                    except Exception as purchase_exc:
                        log.warning(
                            "Purchase execution failed for task %s: %s",
                            task.id, purchase_exc,
                        )
                        purchase_err = json_module.dumps({
                            "type": "purchase_error",
                            "task_id": task.id,
                            "detail": str(purchase_exc)[:200],
                        })
                        yield f"event: purchase_error\ndata: {purchase_err}\n\n"

                task_done = json_module.dumps({
                    "type": "task_done",
                    "task_id": task.id,
                    "task_name": task.name,
                    "status": "completed",
                    "total_messages": len(new_messages),
                    "task_type": task.task_type,
                    "gift_result": gift_result_data if gift_result_data else None,
                    "purchase_result": purchase_result_data if purchase_result_data else None,
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

