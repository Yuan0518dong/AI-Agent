import os
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable

from backend.app.services import (
    agent_draft_service,
    agent_service,
    agent_tool_registry_service,
    material_processing_service,
    material_store,
    store,
)


RETRYABLE_READ_TOOLS = {"search_materials", "answer_only"}


class ToolExecutionTimeout(TimeoutError):
    def __init__(self, tool_name: str, timeout_seconds: float, attempts: int, retryable: bool):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.retryable = retryable
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds:g}s "
            f"(attempts={attempts}, retryable={str(retryable).lower()})."
        )


def execute_action(
    action: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str = "",
    *,
    run_id: str | None = None,
    step_id: str | None = None,
    action_log_id: str | None = None,
) -> dict:
    if not agent_tool_registry_service.is_known_action(action.get("type", "")):
        raise ValueError("Unknown Agent action cannot be executed.")
    tool = agent_tool_registry_service.get_tool_for_action(action["type"])
    tool_name = action.get("toolName") or tool["name"]
    if tool_name != tool["name"]:
        raise ValueError("Action tool does not match the registered tool.")

    payload = action.get("payload") or {}
    agent_tool_registry_service.validate_tool_input(action["type"], payload)
    handlers = {
        "review_material": _review_material,
        "search_materials": _search_materials,
        "answer_with_sources": _answer_with_sources,
        "create_review_draft": _create_review_draft,
        "create_task_draft": _create_task_draft,
        "apply_confirmed_draft": _apply_confirmed_draft,
        "suggest_material_gap": _suggest_material_gap,
        "answer_only": _answer_only,
    }
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"No executor is registered for tool {tool_name}.")
    if tool_name in {"create_review_draft", "create_task_draft"}:
        call = lambda: handler(payload, goal_id, user_id, objective, run_id, step_id)
    elif tool_name == "apply_confirmed_draft":
        call = lambda: handler(payload, goal_id, user_id, objective, action_log_id)
    else:
        call = lambda: handler(payload, goal_id, user_id, objective)
    return _execute_with_timeout(tool_name, call)


def _execute_with_timeout(tool_name: str, call: Callable[[], dict]) -> dict:
    timeout_seconds = _tool_timeout_seconds()
    retryable = tool_name in RETRYABLE_READ_TOOLS
    attempts = 2 if retryable else 1
    for attempt in range(1, attempts + 1):
        try:
            result = _call_with_deadline(call, timeout_seconds)
        except ToolExecutionTimeout:
            if attempt == attempts:
                raise ToolExecutionTimeout(tool_name, timeout_seconds, attempt, retryable) from None
            continue
        if attempt > 1:
            result = {
                **result,
                "execution": {
                    "attemptCount": attempt,
                    "retryReason": "read_tool_timeout",
                },
            }
        return result
    raise AssertionError("Tool execution policy did not return or raise.")


def _call_with_deadline(call: Callable[[], dict], timeout_seconds: float) -> dict:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-tool")
    request_context = copy_context()
    future = executor.submit(request_context.run, call)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise ToolExecutionTimeout("unknown", timeout_seconds, 1, False) from None
    except Exception:
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=True)


def _tool_timeout_seconds() -> float:
    try:
        timeout_seconds = float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "20"))
    except ValueError:
        return 20.0
    return timeout_seconds if timeout_seconds > 0 else 20.0


def _answer_with_sources(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
) -> dict:
    goal = store.get_goal(goal_id, user_id) if goal_id else None
    material_id = payload.get("materialId")
    if material_id:
        material = material_store.get_material(material_id, user_id)
        if not material:
            raise ValueError("Answer tool material was not found in the current user scope.")
        if goal_id and material.get("goalId") != goal_id:
            raise ValueError("Answer tool material does not belong to the current goal.")

    answer = agent_service.answer_and_record(
        question=payload["question"].strip(),
        goal=goal,
        material_id=material_id,
        limit=int(payload.get("limit") or 3),
        user_id=user_id,
    )
    return {
        "observation": (
            f"Generated a grounded answer with {len(answer['references'])} reference(s); "
            f"confidence is {answer['confidence']}."
        ),
        "data": answer,
        "terminal": False,
    }


def _search_materials(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
) -> dict:
    query = payload["query"].strip()
    limit = int(payload.get("limit") or 5)
    requested_material_ids = set(payload.get("materialIds") or [])
    matches = material_store.search_chunks(query, limit=20, user_id=user_id)
    if goal_id:
        matches = [match for match in matches if match.get("goalId") == goal_id]
    if requested_material_ids:
        matches = [match for match in matches if match["materialId"] in requested_material_ids]

    references = [
        {
            "materialId": match["materialId"],
            "materialTitle": match["materialTitle"],
            "chunkIndex": match["chunkIndex"],
            "content": match["content"],
            "score": match["score"],
            "searchMode": match.get("searchMode", "keyword"),
        }
        for match in matches[:limit]
    ]
    modes = sorted({reference["searchMode"] for reference in references})
    return {
        "observation": (
            f"Retrieved {len(references)} material reference(s) for query '{query}' "
            f"using {', '.join(modes) if modes else 'no matching'} retrieval."
        ),
        "data": {
            "query": query,
            "references": references,
            "hasResults": bool(references),
            "objective": objective,
        },
        "terminal": False,
    }


def _review_material(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
) -> dict:
    requested_ids = payload.get("materialIds") or []
    materials = material_store.list_materials(goal_id, user_id)
    if requested_ids:
        requested = set(requested_ids)
        materials = [material for material in materials if material["id"] in requested]

    inspected = []
    generated_chunks = 0
    generated_summaries = 0
    for material in materials:
        chunks = material_store.list_chunks_for_material(material["id"])
        summary = material_store.get_material_summary(material["id"])
        if not chunks:
            chunks = material_processing_service.generate_material_chunks(material, user_id)
            generated_chunks += 1
        if not summary:
            summary = material_processing_service.summarize_material(material, user_id)
            generated_summaries += 1
        inspected.append(
            {
                "materialId": material["id"],
                "title": material["title"],
                "chunkCount": len(chunks),
                "hasSummary": summary is not None,
            }
        )
    return {
        "observation": (
            f"Inspected {len(inspected)} material(s); generated chunks for "
            f"{generated_chunks} and summaries for {generated_summaries}."
        ),
        "data": {
            "materials": inspected,
            "generatedChunkSets": generated_chunks,
            "generatedSummaries": generated_summaries,
            "objective": objective,
        },
        "terminal": False,
    }


def _create_review_draft(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
    run_id: str | None,
    step_id: str | None,
) -> dict:
    requested_material_ids = payload.get("materialIds") or []
    if not requested_material_ids:
        raise ValueError("Review draft requires at least one scoped material ID.")
    materials = []
    for material_id in requested_material_ids:
        material = material_store.get_material(material_id, user_id)
        if not material:
            raise ValueError("Review draft material was not found in the current user scope.")
        if goal_id and material.get("goalId") != goal_id:
            raise ValueError("Review draft material does not belong to the current goal.")
        materials.append(material)

    if not materials:
        raise ValueError("Review draft requires at least one scoped material.")

    draft_payloads = []
    for material in materials:
        material_id = material["id"]
        summary = material_store.get_material_summary(material_id) or {}
        key_points = summary.get("keyPoints") or []
        key_point = str(key_points[0]).strip() if key_points else ""
        draft_payloads.append(
            {
                "materialId": material_id,
                "front": f"What is a key idea in {material['title']}?",
                "back": key_point or f"Summarize the key idea in {material['title']}.",
                "sourceReason": (
                    f"Generated from the summary of '{material['title']}'."
                    if key_point
                    else f"Generated from material '{material['title']}' because it needs review."
                ),
            }
        )
    drafts, created_count, reused_count = _persist_drafts(
        "review",
        draft_payloads,
        user_id,
        goal_id,
        run_id,
        step_id,
        "create_review_draft",
    )
    return {
        "observation": _draft_observation("review", created_count, reused_count),
        "data": {
            "drafts": drafts,
            "createdCount": created_count,
            "reusedCount": reused_count,
            "objective": objective,
        },
        "terminal": False,
    }


def _create_task_draft(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
    run_id: str | None,
    step_id: str | None,
) -> dict:
    requested_goal_ids = payload.get("goalIds") or []
    task_ids = payload.get("taskIds") or []
    task_titles = []
    for task_id in task_ids:
        task = store.get_task(task_id)
        task_goal = store.get_goal(task["goal_id"], user_id) if task else None
        if not task or not task_goal:
            raise ValueError("Task draft task was not found in the current user scope.")
        if goal_id and task["goal_id"] != goal_id:
            raise ValueError("Task draft task does not belong to the current goal.")
        requested_goal_ids.append(task["goal_id"])
        task_titles.append(task["title"])

    if not requested_goal_ids and goal_id:
        requested_goal_ids.append(goal_id)
    target_goal_ids = []
    for target_goal_id in requested_goal_ids:
        if target_goal_id in target_goal_ids:
            continue
        if goal_id and target_goal_id != goal_id:
            raise ValueError("Task draft goal does not belong to the current run.")
        if not store.get_goal(target_goal_id, user_id):
            raise ValueError("Task draft goal was not found in the current user scope.")
        target_goal_ids.append(target_goal_id)

    source_reason = (
        f"Generated from the Agent objective: {objective}"
        if objective
        else "Generated from the current learning goal because no open task plan exists."
    )
    if task_titles:
        source_reason = f"Generated as a follow-up for task(s): {', '.join(task_titles[:3])}."
    draft_payloads = [
        {
            "goalId": target_goal_id,
            "title": "Agent follow-up task",
            "detail": objective or "Complete the highest-priority learning follow-up.",
            "date": store.today_iso(),
            "priority": "medium",
            "sourceReason": source_reason,
        }
        for target_goal_id in target_goal_ids[:3]
    ]
    drafts, created_count, reused_count = _persist_drafts(
        "task",
        draft_payloads,
        user_id,
        goal_id,
        run_id,
        step_id,
        "create_task_draft",
    )
    return {
        "observation": _draft_observation("task", created_count, reused_count),
        "data": {
            "drafts": drafts,
            "createdCount": created_count,
            "reusedCount": reused_count,
        },
        "terminal": False,
    }


def _apply_confirmed_draft(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
    action_log_id: str | None,
) -> dict:
    resolved_action_log_id = action_log_id or payload.get("actionLogId")
    if not resolved_action_log_id:
        raise ValueError("Confirmed draft application requires an accepted ActionLog.")
    drafts, created_count, reused_count, applied_entity_ids = (
        agent_draft_service.apply_confirmed_drafts(
            draft_ids=payload["draftIds"],
            user_id=user_id,
            goal_id=goal_id,
            action_log_id=resolved_action_log_id,
        )
    )
    total = created_count + reused_count
    label = "formal record" if len(applied_entity_ids) == 1 else "formal records"
    verb = "Reused" if reused_count and not created_count else "Applied"
    return {
        "observation": f"{verb} {total} confirmed draft(s) to {len(applied_entity_ids)} {label}.",
        "data": {
            "drafts": drafts,
            "appliedCount": created_count,
            "reusedCount": reused_count,
            "appliedEntityIds": applied_entity_ids,
        },
        "terminal": False,
    }


def _persist_drafts(
    draft_type: str,
    payloads: list[dict],
    user_id: str | None,
    goal_id: str | None,
    run_id: str | None,
    step_id: str | None,
    tool_name: str,
) -> tuple[list[dict], int, int]:
    if not run_id or not step_id:
        raise ValueError("Draft creation requires a persisted AgentRun and AgentStep.")
    return agent_draft_service.create_or_reuse_drafts(
        draft_type=draft_type,
        payloads=payloads,
        user_id=user_id,
        goal_id=goal_id,
        run_id=run_id,
        step_id=step_id,
        tool_name=tool_name,
    )


def _draft_observation(draft_type: str, created_count: int, reused_count: int) -> str:
    total = created_count + reused_count
    label = f"{draft_type} draft" + ("" if total == 1 else "s")
    if reused_count and not created_count:
        return f"Reused {reused_count} {label}."
    if reused_count:
        return f"Persisted {created_count} {label}; reused {reused_count}."
    return f"Persisted {created_count} {label}."


def _suggest_material_gap(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
) -> dict:
    count = int(payload.get("insufficiencyCount") or 0)
    return {
        "observation": f"Prepared a source-gap suggestion from {count} insufficient answer(s).",
        "data": {
            "suggestion": "Add a source that directly covers the unsupported question, then rebuild chunks.",
            "objective": objective,
        },
        "terminal": False,
    }


def _answer_only(
    payload: dict,
    goal_id: str | None,
    user_id: str | None,
    objective: str,
) -> dict:
    return {
        "observation": "The Agent found no further executable action and completed the run.",
        "data": {"message": objective or "Continue the current learning plan."},
        "terminal": True,
    }
