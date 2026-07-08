import json

from backend.app.services import (
    agent_action_log_service,
    agent_context_service,
    agent_decision_service,
    store,
)


VALID_TRIGGERS = {"manual", "after_write", "scheduled"}
VALID_STATUSES = {"created", "decided", "feedback_recorded", "executed", "closed"}


def create_agent_run(
    goal_id: str | None = None,
    user_id: str | None = None,
    trigger: str = "manual",
) -> dict:
    trigger_type = _normalize_trigger(trigger)
    context = agent_context_service.build_agent_context(goal_id, user_id)
    decision = agent_decision_service.decide_next_action(goal_id, user_id)
    feedback_summary = _feedback_summary(goal_id, user_id)
    now = store.now_iso()
    run = {
        "id": store.make_id("agentrun"),
        "userId": user_id,
        "goalId": goal_id,
        "trigger": trigger_type,
        "status": "decided",
        "contextSummary": _context_summary(context),
        "decisionSummary": _decision_summary(decision),
        "feedbackSummary": feedback_summary,
        "contextSnapshot": context,
        "decisionSnapshot": decision,
        "createdAt": now,
        "updatedAt": now,
    }

    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                id, user_id, goal_id, trigger, context_snapshot, decision_snapshot,
                feedback_summary, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["id"],
                run["userId"],
                run["goalId"],
                run["trigger"],
                json.dumps(run["contextSnapshot"], ensure_ascii=False),
                json.dumps(run["decisionSnapshot"], ensure_ascii=False),
                json.dumps(run["feedbackSummary"], ensure_ascii=False),
                run["status"],
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


def update_agent_run_status(
    run_id: str,
    status: str,
    user_id: str | None = None,
) -> dict | None:
    next_status = _normalize_status(status)
    existing = get_agent_run(run_id, user_id)
    if not existing:
        return None

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
        "status": row["status"],
        "contextSummary": _context_summary(context_snapshot),
        "decisionSummary": _decision_summary(decision_snapshot),
        "feedbackSummary": json.loads(row["feedback_summary"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_snapshots:
        run["contextSnapshot"] = context_snapshot
        run["decisionSnapshot"] = decision_snapshot
    return run
