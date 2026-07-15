import json

from backend.app.services import (
    agent_action_log_service,
    agent_context_service,
    agent_decision_service,
    sensitive_data_service,
    store,
)


VALID_TRIGGERS = {"manual", "after_write", "scheduled"}
VALID_STATUSES = {
    "created",
    "decided",
    "running",
    "waiting_confirmation",
    "feedback_recorded",
    "executed",
    "completed",
    "failed",
    "max_steps",
    "cancelled",
    "closed",
}
EXECUTABLE_STATUSES = {
    "created",
    "decided",
    "waiting_confirmation",
    "feedback_recorded",
    "executed",
}


def create_agent_run(
    goal_id: str | None = None,
    user_id: str | None = None,
    trigger: str = "manual",
    objective: str = "",
    decision_mode: str = "hybrid",
    max_steps: int = 4,
) -> dict:
    trigger_type = _normalize_trigger(trigger)
    context = agent_context_service.build_agent_context(goal_id, user_id)
    decision = agent_decision_service.decide_next_action(
        goal_id,
        user_id,
        decision_mode,
        objective,
    )
    feedback_summary = _feedback_summary(goal_id, user_id)
    now = store.now_iso()
    run = {
        "id": store.make_id("agentrun"),
        "userId": user_id,
        "goalId": goal_id,
        "trigger": trigger_type,
        "objective": sensitive_data_service.redact_text(objective, max_length=500),
        "decisionMode": decision_mode,
        "maxSteps": max_steps,
        "currentStep": 0,
        "status": "decided",
        "stopReason": "",
        "error": "",
        "contextSummary": _context_summary(context),
        "decisionSummary": _decision_summary(decision),
        "feedbackSummary": feedback_summary,
        "contextSnapshot": sensitive_data_service.redact(context),
        "decisionSnapshot": sensitive_data_service.redact(decision),
        "createdAt": now,
        "updatedAt": now,
    }

    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                id, user_id, goal_id, trigger, objective, decision_mode, max_steps,
                current_step, context_snapshot, decision_snapshot, feedback_summary,
                status, stop_reason, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["id"],
                run["userId"],
                run["goalId"],
                run["trigger"],
                run["objective"],
                run["decisionMode"],
                run["maxSteps"],
                run["currentStep"],
                json.dumps(run["contextSnapshot"], ensure_ascii=False),
                json.dumps(run["decisionSnapshot"], ensure_ascii=False),
                json.dumps(run["feedbackSummary"], ensure_ascii=False),
                run["status"],
                run["stopReason"],
                run["error"],
                run["createdAt"],
                run["updatedAt"],
            ),
        )
    return run


def list_agent_runs(
    goal_id: str | None = None,
    user_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    filters = []
    values = []
    if goal_id:
        filters.append("goal_id = ?")
        values.append(goal_id)
    if user_id:
        filters.append("user_id = ?")
        values.append(user_id)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    values.append(limit)

    with store.db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM agent_runs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [_agent_run_from_row(row, include_snapshots=False) for row in rows]


def get_agent_run(run_id: str, user_id: str | None = None) -> dict | None:
    with store.db_connection() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM agent_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM agent_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
    return _agent_run_from_row(row, include_snapshots=True) if row else None


def list_agent_run_steps(run_id: str) -> list[dict]:
    with store.db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_run_steps WHERE run_id = ? ORDER BY step_index ASC",
            (run_id,),
        ).fetchall()
    return [_agent_run_step_from_row(row) for row in rows]


def update_agent_run_status(
    run_id: str,
    status: str,
    user_id: str | None = None,
) -> dict | None:
    next_status = _normalize_status(status)
    existing = get_agent_run(run_id, user_id)
    if not existing:
        return None
    if existing["status"] == "cancelled":
        return existing
    if next_status == "cancelled":
        return cancel_agent_run(run_id, user_id)

    feedback_summary = _feedback_summary(existing["goalId"], user_id)
    now = store.now_iso()
    values = [
        next_status,
        json.dumps(feedback_summary, ensure_ascii=False),
        now,
        run_id,
    ]
    if user_id:
        values.append(user_id)

    with store.db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, feedback_summary = ?, updated_at = ?
            WHERE id = ?
            """
            + (" AND user_id = ?" if user_id else ""),
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_agent_run(run_id, user_id)


def claim_agent_run_execution(
    run_id: str,
    user_id: str | None = None,
) -> bool:
    """Atomically claim an executable Run without adding a lock column."""
    placeholders = ", ".join("?" for _ in EXECUTABLE_STATUSES)
    values: list[object] = ["running", "", "", store.now_iso(), run_id, *sorted(EXECUTABLE_STATUSES)]
    owner_filter = "user_id IS NULL" if user_id is None else "user_id = ?"
    if user_id is not None:
        values.append(user_id)
    with store.db_connection() as conn:
        cursor = conn.execute(
            f"""
            UPDATE agent_runs
            SET status = ?, stop_reason = ?, error = ?, updated_at = ?
            WHERE id = ? AND status IN ({placeholders}) AND {owner_filter}
            """,
            values,
        )
    return cursor.rowcount == 1


def cancel_agent_run(run_id: str, user_id: str | None = None) -> dict | None:
    """Cancel an active Run idempotently using its existing status field."""
    existing = get_agent_run(run_id, user_id)
    if not existing:
        return None
    if existing["status"] in {"completed", "failed", "max_steps", "cancelled", "closed"}:
        return existing

    owner_filter = "user_id IS NULL" if user_id is None else "user_id = ?"
    values: list[object] = ["cancelled", "cancelled", "", store.now_iso(), run_id]
    if user_id is not None:
        values.append(user_id)
    with store.db_connection() as conn:
        conn.execute(
            f"""
            UPDATE agent_runs
            SET status = ?, stop_reason = ?, error = ?, updated_at = ?
            WHERE id = ? AND {owner_filter}
              AND status NOT IN ('completed', 'failed', 'max_steps', 'cancelled', 'closed')
            """,
            values,
        )
    return get_agent_run(run_id, user_id)


def is_agent_run_cancelled(run_id: str, user_id: str | None = None) -> bool:
    run = get_agent_run(run_id, user_id)
    return bool(run and run["status"] == "cancelled")


def build_feedback_summary(goal_id: str | None, user_id: str | None) -> dict:
    return _feedback_summary(goal_id, user_id)


def _feedback_summary(goal_id: str | None, user_id: str | None) -> dict:
    logs = agent_action_log_service.list_action_logs(goal_id, user_id, limit=50)
    counts = {status: 0 for status in agent_action_log_service.VALID_STATUSES}
    for action_log in logs:
        counts[action_log["status"]] += 1
    return {
        "total": len(logs),
        "byStatus": counts,
        "latestActionType": logs[0]["actionType"] if logs else "",
        "latestStatus": logs[0]["status"] if logs else "",
    }


def _context_summary(context: dict) -> dict:
    summary = context.get("summary", {})
    return {
        "goalCount": summary.get("goalCount", 0),
        "taskOpen": summary.get("taskOpen", 0),
        "materialTotal": summary.get("materialTotal", 0),
        "flashcardTotal": summary.get("flashcardTotal", 0),
        "quizWeakAttemptCount": summary.get("quizWeakAttemptCount", 0),
        "observations": (summary.get("observations") or [])[:3],
    }


def _decision_summary(decision: dict) -> dict:
    return {
        "mode": decision.get("mode", ""),
        "nextAction": decision.get("nextAction", ""),
        "problemCount": len(decision.get("problems") or []),
        "actionCount": len(decision.get("proposedActions") or []),
        "reason": decision.get("reason", ""),
    }


def _normalize_trigger(trigger: str) -> str:
    if trigger not in VALID_TRIGGERS:
        raise ValueError("Invalid agent run trigger")
    return trigger


def _normalize_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ValueError("Invalid agent run status")
    return status


def _agent_run_from_row(row, include_snapshots: bool) -> dict:
    context_snapshot = json.loads(row["context_snapshot"])
    decision_snapshot = json.loads(row["decision_snapshot"])
    run = {
        "id": row["id"],
        "userId": row["user_id"],
        "goalId": row["goal_id"],
        "trigger": row["trigger"],
        "objective": row["objective"],
        "decisionMode": row["decision_mode"],
        "maxSteps": row["max_steps"],
        "currentStep": row["current_step"],
        "status": row["status"],
        "stopReason": row["stop_reason"],
        "error": row["error"],
        "contextSummary": _context_summary(context_snapshot),
        "decisionSummary": _decision_summary(decision_snapshot),
        "feedbackSummary": json.loads(row["feedback_summary"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_snapshots:
        run["contextSnapshot"] = context_snapshot
        run["decisionSnapshot"] = decision_snapshot
        run["steps"] = list_agent_run_steps(row["id"])
    return run


def _agent_run_step_from_row(row) -> dict:
    return {
        "id": row["id"],
        "runId": row["run_id"],
        "stepIndex": row["step_index"],
        "contextSnapshot": json.loads(row["context_snapshot"]),
        "decisionSnapshot": json.loads(row["decision_snapshot"]),
        "actionSnapshot": json.loads(row["action_snapshot"]),
        "toolName": row["tool_name"],
        "toolInput": json.loads(row["tool_input"]),
        "toolOutput": json.loads(row["tool_output"]),
        "actionLogId": row["action_log_id"],
        "status": row["status"],
        "error": row["error"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
