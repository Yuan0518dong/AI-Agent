from backend.app.services import agent_action_log_service, agent_context_service, store


def decide_next_action(
    goal_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    context = agent_context_service.build_agent_context(goal_id, user_id)
    summary = context["summary"]
    action_logs = agent_action_log_service.list_action_logs(goal_id, user_id, limit=20)
    feedback_memory = _feedback_memory(action_logs)
    problems = _collect_problems(context)
    primary_problem = problems[0] if problems else None
    proposed_actions = _apply_feedback_memory(
        _proposed_actions(context, problems),
        feedback_memory,
    )
    next_action = proposed_actions[0]["type"] if proposed_actions else "answer_only"

    return {
        "generatedAt": store.now_iso(),
        "mode": "rule-based",
        "scope": context["scope"],
        "stateSummary": _state_summary(summary),
        "problems": problems,
        "nextAction": next_action,
        "reason": _decision_reason(primary_problem, summary, feedback_memory),
        "requiresConfirmation": any(action["requiresConfirmation"] for action in proposed_actions),
        "proposedActions": proposed_actions,
        "feedbackMemory": feedback_memory,
    }


def _collect_problems(context: dict) -> list[dict]:
    problems = []
    summary = context["summary"]

    if summary["goalCount"] == 0:
        problems.append(
            _problem(
                "missing_goal",
                "high",
                "No learning goal exists yet.",
                "The Agent cannot plan without at least one goal.",
            )
        )
        return problems

    if summary["taskOverdue"]:
        overdue_groups = [group for group in context["tasks"] if group["overdue"]]
        problems.append(
            _problem(
                "overdue_tasks",
                "high",
                f"{summary['taskOverdue']} open task(s) are overdue.",
                _join_names(overdue_groups, "goalName"),
            )
        )

    if summary["materialsWithoutChunks"]:
        materials = [material for material in context["materials"] if material["chunkCount"] == 0]
        problems.append(
            _problem(
                "missing_chunks",
                "high",
                f"{summary['materialsWithoutChunks']} material(s) have no searchable chunks.",
                _join_names(materials, "title"),
            )
        )

    if summary["materialsWithoutSummary"]:
        materials = [material for material in context["materials"] if not material["hasSummary"]]
        problems.append(
            _problem(
                "missing_summary",
                "medium",
                f"{summary['materialsWithoutSummary']} material(s) have no AI summary.",
                _join_names(materials, "title"),
            )
        )

    if summary["qaInsufficiencyCount"]:
        problems.append(
            _problem(
                "material_insufficiency",
                "medium",
                f"{summary['qaInsufficiencyCount']} question(s) were marked as material-insufficient.",
                _join_names(context["qa"].get("insufficiencies", []), "materialTitle"),
            )
        )

    if summary["quizWeakAttemptCount"]:
        problems.append(
            _problem(
                "weak_quiz_attempts",
                "medium",
                f"{summary['quizWeakAttemptCount']} quiz attempt(s) show weak points.",
                _join_names(context["quiz"].get("weakAttempts", []), "title"),
            )
        )

    if context["review"].get("review") or context["review"].get("new"):
        review_total = context["review"].get("review", 0) + context["review"].get("new", 0)
        problems.append(
            _problem(
                "review_queue",
                "low",
                f"{review_total} flashcard(s) are waiting for review.",
                _join_names(context["review"].get("materialsNeedingReview", []), "title"),
            )
        )

    if summary["taskTotal"] == 0 and summary["goalCount"] > 0:
        problems.append(
            _problem(
                "missing_tasks",
                "medium",
                "Goals exist but no tasks have been generated.",
                _join_names(context["goals"], "name"),
            )
        )

    return problems


def _proposed_actions(context: dict, problems: list[dict]) -> list[dict]:
    actions = []
    problem_types = {problem["type"] for problem in problems}

    if "missing_goal" in problem_types:
        actions.append(
            _action(
                "create_followup_tasks",
                "Create the first learning goal",
                "Start by creating a goal so the Agent can build a learning path.",
                {},
                False,
            )
        )
        return actions

    if "overdue_tasks" in problem_types:
        overdue_task_ids = [
            task["id"]
            for group in context["tasks"]
            for task in group["overdueItems"]
        ]
        actions.append(
            _action(
                "reschedule_tasks",
                "Reschedule overdue tasks",
                "Review overdue work and regenerate a smaller, more realistic task sequence.",
                {"taskIds": overdue_task_ids},
                True,
            )
        )

    if "missing_chunks" in problem_types or "missing_summary" in problem_types:
        materials = [
            material
            for material in context["materials"]
            if material["chunkCount"] == 0 or not material["hasSummary"]
        ]
        actions.append(
            _action(
                "review_material",
                "Complete material processing",
                "Generate missing summaries or chunks before asking the Agent to reason over these materials.",
                {"materialIds": [material["id"] for material in materials]},
                False,
            )
        )

    if "weak_quiz_attempts" in problem_types:
        actions.append(
            _action(
                "create_flashcards",
                "Turn weak quiz points into review cards",
                "Use the weak quiz attempts as the basis for follow-up review drafts or flashcards.",
                {"weakAttemptCount": context["quiz"].get("weakAttemptCount", 0)},
                True,
            )
        )

    if "material_insufficiency" in problem_types:
        actions.append(
            _action(
                "ask_for_more_material",
                "Add missing source material",
                "The Agent found questions that current materials cannot support, so add or refine sources first.",
                {"insufficiencyCount": context["qa"].get("insufficiencyCount", 0)},
                False,
            )
        )

    if "review_queue" in problem_types:
        actions.append(
            _action(
                "review_material",
                "Run one flashcard review session",
                "Clear new and review flashcards before adding more content.",
                {
                    "new": context["review"].get("new", 0),
                    "review": context["review"].get("review", 0),
                },
                False,
            )
        )

    if "missing_tasks" in problem_types:
        actions.append(
            _action(
                "create_followup_tasks",
                "Generate learning tasks",
                "Create a short action plan so progress can be tracked.",
                {"goalIds": [goal["id"] for goal in context["goals"]]},
                True,
            )
        )

    if not actions:
        actions.append(
            _action(
                "answer_only",
                "Continue the current learning rhythm",
                "No immediate blocking issue was detected. Continue with today's task or ask a targeted question.",
                {},
                False,
            )
        )

    return actions[:4]


def _feedback_memory(action_logs: list[dict]) -> dict:
    latest_by_action = {}
    for action_log in action_logs:
        action_type = action_log["actionType"]
        if action_type not in latest_by_action:
            latest_by_action[action_type] = action_log

    pending_accepted = []
    recently_rejected = []
    deferred = []
    applied = []
    for action_log in latest_by_action.values():
        compact = _compact_action_log(action_log)
        if action_log["status"] == "accepted":
            pending_accepted.append(compact)
        elif action_log["status"] == "rejected":
            recently_rejected.append(compact)
        elif action_log["status"] == "later":
            deferred.append(compact)
        elif action_log["status"] == "applied":
            applied.append(compact)

    return {
        "recentActionCount": len(action_logs),
        "pendingAccepted": pending_accepted,
        "recentlyRejected": recently_rejected,
        "deferred": deferred,
        "applied": applied,
    }


def _compact_action_log(action_log: dict) -> dict:
    proposed_payload = action_log.get("proposedPayload") or {}
    return {
        "id": action_log["id"],
        "actionType": action_log["actionType"],
        "status": action_log["status"],
        "label": proposed_payload.get("label") or action_log["actionType"],
        "updatedAt": action_log["updatedAt"],
    }


def _apply_feedback_memory(actions: list[dict], feedback_memory: dict) -> list[dict]:
    pending_by_type = _index_memory_items(feedback_memory["pendingAccepted"])
    rejected_types = {item["actionType"] for item in feedback_memory["recentlyRejected"]}
    deferred_by_type = _index_memory_items(feedback_memory["deferred"])

    remembered_actions = []
    active_actions = []
    for action in actions:
        action_type = action["type"]
        if action_type in rejected_types:
            continue
        if action_type in pending_by_type:
            remembered_actions.append(
                _remembered_action(action, pending_by_type[action_type], "accepted")
            )
            continue
        if action_type in deferred_by_type:
            remembered_actions.append(
                _remembered_action(action, deferred_by_type[action_type], "later")
            )
            continue
        active_actions.append(action)

    next_actions = active_actions + remembered_actions
    if next_actions:
        return next_actions[:4]

    if feedback_memory["recentlyRejected"]:
        return [
            _action(
                "answer_only",
                "Wait for a new learning signal",
                "The matching Agent action was recently rejected, so this decision avoids repeating it unchanged.",
                {"rejectedActionTypes": [item["actionType"] for item in feedback_memory["recentlyRejected"]]},
                False,
            )
        ]

    if remembered_actions:
        return remembered_actions[:4]

    return actions[:4]


def _index_memory_items(items: list[dict]) -> dict:
    return {item["actionType"]: item for item in items}


def _remembered_action(action: dict, memory_item: dict, status: str) -> dict:
    if status == "accepted":
        label = f"Continue accepted action: {action['label']}"
        description = (
            "This action was already accepted. Finish it from the action log before creating another copy."
        )
    else:
        label = f"Resume deferred action: {action['label']}"
        description = (
            "This action was marked for later. It is kept as a remembered option, but new active blockers stay first."
        )

    return {
        **action,
        "label": label,
        "description": description,
        "payload": {
            **action.get("payload", {}),
            "actionLogId": memory_item["id"],
        },
        "status": status,
    }


def _state_summary(summary: dict) -> str:
    return (
        f"{summary['goalCount']} goal(s), {summary['taskOpen']} open task(s), "
        f"{summary['materialTotal']} material(s), {summary['flashcardTotal']} flashcard(s), "
        f"{summary['quizWeakAttemptCount']} weak quiz attempt(s)."
    )


def _decision_reason(primary_problem: dict | None, summary: dict, feedback_memory: dict) -> str:
    memory_note = _decision_memory_note(feedback_memory)
    if primary_problem:
        return f"Priority is {primary_problem['type']}: {primary_problem['message']}{memory_note}"
    if summary["goalCount"] == 0:
        return f"No goal exists yet, so the first step is to create a learning goal.{memory_note}"
    return f"The current learning state has no high-priority blocker.{memory_note}"


def _decision_memory_note(feedback_memory: dict) -> str:
    notes = []
    if feedback_memory["pendingAccepted"]:
        notes.append(f"{len(feedback_memory['pendingAccepted'])} accepted action(s) still need execution")
    if feedback_memory["recentlyRejected"]:
        notes.append(f"{len(feedback_memory['recentlyRejected'])} rejected action type(s) were avoided")
    if feedback_memory["deferred"]:
        notes.append(f"{len(feedback_memory['deferred'])} deferred action(s) were remembered")
    if not notes:
        return ""
    return " Feedback memory: " + "; ".join(notes) + "."


def _problem(problem_type: str, severity: str, message: str, evidence: str) -> dict:
    return {
        "type": problem_type,
        "severity": severity,
        "message": message,
        "evidence": evidence,
    }


def _action(
    action_type: str,
    label: str,
    description: str,
    payload: dict,
    requires_confirmation: bool,
) -> dict:
    return {
        "type": action_type,
        "label": label,
        "description": description,
        "payload": payload,
        "requiresConfirmation": requires_confirmation,
        "status": "proposed",
    }


def _join_names(items: list[dict], key: str) -> str:
    names = [str(item.get(key, "")).strip() for item in items if item.get(key)]
    if not names:
        return ""
    return ", ".join(names[:3])
