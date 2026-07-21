from __future__ import annotations

from backend.app.services import agent_tool_registry_service


EVIDENCE_TERMS = {
    "evidence",
    "grounded",
    "retrieve",
    "retrieval",
    "search",
    "source",
    "citation",
    "证据",
    "引用",
    "检索",
    "搜索",
    "查找",
    "来源",
}
REVIEW_TERMS = {
    "review",
    "flashcard",
    "quiz",
    "weak",
    "复习",
    "闪卡",
    "测验",
    "错题",
    "薄弱",
    "回顾",
}
TASK_TERMS = {
    "task",
    "plan",
    "schedule",
    "reschedule",
    "任务",
    "计划",
    "安排",
    "日程",
}
MATERIAL_PROCESSING_TERMS = {
    "prepare the material",
    "process the material",
    "organize the material",
    "处理资料",
    "整理资料",
    "准备资料",
}
NO_PROGRESS_TERMS = {
    "already attempted",
    "no progress",
    "stop when",
    "已经尝试",
    "没有进展",
    "停止条件",
}
ROLLBACK_TERMS = {
    "roll back",
    "rollback",
    "invalid draft",
    "回滚",
    "无效草稿",
}
AVOID_TERMS = {"avoid", "rejected", "do not repeat", "避开", "拒绝", "不要重复"}


def allowed_action_types(context: dict, fallback_decision: dict) -> set[str]:
    """Return the action types the model may choose for the current Run state."""

    drafts = context.get("drafts") or {}
    if drafts.get("proposedCount", 0) or drafts.get("proposed"):
        return {"apply_confirmed_draft"}

    objective = str((context.get("agentRun") or {}).get("objective") or "").strip().lower()
    feedback_memory = fallback_decision.get("feedbackMemory") or {}
    rejected_actions = _expanded_memory_actions(feedback_memory.get("recentlyRejected") or [])
    accepted_actions = _expanded_memory_actions(feedback_memory.get("pendingAccepted") or [])

    if _contains_any(objective, ROLLBACK_TERMS):
        return {"apply_confirmed_draft"}
    if accepted_actions:
        return accepted_actions | {"apply_confirmed_draft"}
    if rejected_actions and _contains_any(objective, AVOID_TERMS):
        return {"answer_only"}

    summary = context.get("summary") or {}
    if summary.get("materialsWithoutChunks", 0):
        return {"review_material", "ask_for_more_material", "answer_only"}
    if _contains_any(objective, NO_PROGRESS_TERMS):
        return {"search_materials"}
    if _contains_any(objective, EVIDENCE_TERMS):
        if _completed_tool_names(context) & {"search_materials"}:
            return {"answer_with_sources", "ask_for_more_material", "answer_only"}
        return {"search_materials"}
    if _contains_any(objective, MATERIAL_PROCESSING_TERMS):
        return {"review_material", "answer_only"}
    if _contains_any(objective, REVIEW_TERMS):
        return {"create_flashcards", "create_quiz", "answer_only"} - rejected_actions
    if _contains_any(objective, TASK_TERMS):
        return {"create_followup_tasks", "reschedule_tasks", "answer_only"} - rejected_actions

    if summary.get("qaInsufficiencyCount", 0):
        return {"search_materials", "ask_for_more_material", "answer_only"}
    if summary.get("quizWeakAttemptCount", 0) or (context.get("review") or {}).get("review", 0):
        return {"create_flashcards", "create_quiz", "review_material", "answer_only"} - rejected_actions
    if summary.get("taskTotal", 0) == 0 and summary.get("goalCount", 0) > 0:
        return {"create_followup_tasks", "answer_only"} - rejected_actions

    allowed = {"answer_only"}
    if summary.get("materialTotal", 0):
        allowed.update({"search_materials", "answer_with_sources"})
    return allowed - rejected_actions or {"answer_only"}


def _expanded_memory_actions(items: list[dict]) -> set[str]:
    expanded: set[str] = set()
    for item in items:
        action_or_tool = str(item.get("actionType") or "")
        if action_or_tool in agent_tool_registry_service.ACTION_TOOL_MAP:
            expanded.add(action_or_tool)
        if action_or_tool in agent_tool_registry_service.TOOLS:
            expanded.update(
                action_type
                for action_type, tool_name in agent_tool_registry_service.ACTION_TOOL_MAP.items()
                if tool_name == action_or_tool
            )
    return expanded


def _completed_tool_names(context: dict) -> set[str]:
    return {
        str(step.get("toolName") or "")
        for step in (context.get("agentRun") or {}).get("stepHistory", [])
        if step.get("status") == "completed"
    }


def _contains_any(value: str, terms: set[str]) -> bool:
    return any(term in value for term in terms)
