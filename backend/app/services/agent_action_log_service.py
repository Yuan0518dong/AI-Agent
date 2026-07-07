import json

from backend.app.services import store


VALID_STATUSES = {"proposed", "accepted", "rejected", "later", "applied"}


def create_action_log(payload: dict, user_id: str | None = None) -> dict:
    now = store.now_iso()
    log = {
        "id": store.make_id("actionlog"),
        "userId": user_id,
        "goalId": payload.get("goalId"),
        "actionType": payload["actionType"],
        "observation": payload.get("observation", ""),
        "decision": payload.get("decision", {}),
        "proposedPayload": payload.get("proposedPayload", {}),
        "status": _normalize_status(payload.get("status", "proposed")),
        "createdAt": now,
        "updatedAt": now,
    }

    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_action_logs (
                id, user_id, goal_id, action_type, observation, decision,
                proposed_payload, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log["id"],
                log["userId"],
                log["goalId"],
                log["actionType"],
                log["observation"],
                json.dumps(log["decision"], ensure_ascii=False),
                json.dumps(log["proposedPayload"], ensure_ascii=False),
                log["status"],
                log["createdAt"],
                log["updatedAt"],
            ),
        )
    return log


def list_action_logs(
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
            SELECT * FROM agent_action_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [_action_log_from_row(row) for row in rows]


def update_action_log_status(
    log_id: str,
    status: str,
    user_id: str | None = None,
) -> dict | None:
    next_status = _normalize_status(status)
    now = store.now_iso()
    values = [next_status, now, log_id]
    if user_id:
        values.append(user_id)

    with store.db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE agent_action_logs
            SET status = ?, updated_at = ?
            WHERE id = ?
            """
            + (" AND user_id = ?" if user_id else ""),
            values,
        )
        if cursor.rowcount == 0:
            return None

    return get_action_log(log_id, user_id)


def get_action_log(log_id: str, user_id: str | None = None) -> dict | None:
    with store.db_connection() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM agent_action_logs WHERE id = ? AND user_id = ?",
                (log_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM agent_action_logs WHERE id = ?",
                (log_id,),
            ).fetchone()
    return _action_log_from_row(row) if row else None


def _normalize_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ValueError("Invalid action log status")
    return status


def _action_log_from_row(row) -> dict:
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "goalId": row["goal_id"],
        "actionType": row["action_type"],
        "observation": row["observation"],
        "decision": json.loads(row["decision"]),
        "proposedPayload": json.loads(row["proposed_payload"]),
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
