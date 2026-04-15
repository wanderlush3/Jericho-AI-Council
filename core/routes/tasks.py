"""
Jericho — Tasks Routes
"""

from __future__ import annotations

import logging


import json as json_module
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

