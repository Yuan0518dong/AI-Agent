import hashlib
import json
from typing import Any

from backend.app.services import flashcard_review_service, store


VALID_DRAFT_TYPES = {"review", "task"}
VALID_DRAFT_STATUSES = {"proposed", "confirmed", "applied", "rejected"}
DRAFT_STATUS_TRANSITIONS = {
    "proposed": {"confirmed", "rejected"},
    "confirmed": {"applied", "rejected"},
    "applied": set(),
    "rejected": set(),
}


def create_or_reuse_drafts(
    *,
    draft_type: str,
    payloads: list[dict],
    user_id: str | None,
    goal_id: str | None,
    run_id: str,
    step_id: str,
    tool_name: str,
) -> tuple[list[dict], int, int]:
    """Persist proposed drafts and reuse an existing record for the same Step payload."""
    normalized_type = _normalize_draft_type(draft_type)
    _validate_origin(run_id, step_id, user_id, goal_id)

    drafts = []
    created_count = 0
    reused_count = 0
    now = store.now_iso()
    with store.db_connection() as conn:
        for payload in payloads:
            normalized_payload = _normalize_payload(payload)
            idempotency_key = make_idempotency_key(
                user_id,
                run_id,
                step_id,
                tool_name,
                normalized_payload,
            )
            existing = conn.execute(
                "SELECT * FROM agent_drafts WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                drafts.append(_draft_from_row(existing))
                reused_count += 1
                continue

            draft = {
                "id": store.make_id("agentdraft"),
                "userId": user_id,
                "goalId": goal_id,
                "runId": run_id,
                "stepId": step_id,
                "draftType": normalized_type,
                "payload": normalized_payload,
                "status": "proposed",
                "idempotencyKey": idempotency_key,
                "appliedEntityIds": [],
                "createdAt": now,
                "updatedAt": now,
                "appliedAt": None,
            }
            conn.execute(
                """
                INSERT INTO agent_drafts (
                    id, user_id, goal_id, run_id, step_id, draft_type, payload,
                    status, idempotency_key, applied_entity_ids, created_at, updated_at, applied_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft["id"],
                    draft["userId"],
                    draft["goalId"],
                    draft["runId"],
                    draft["stepId"],
                    draft["draftType"],
                    _canonical_json(draft["payload"]),
                    draft["status"],
                    draft["idempotencyKey"],
                    "[]",
                    draft["createdAt"],
                    draft["updatedAt"],
                    draft["appliedAt"],
                ),
            )
            drafts.append(draft)
            created_count += 1
    return drafts, created_count, reused_count


def list_agent_drafts(
    *,
    user_id: str | None,
    goal_id: str | None = None,
    draft_type: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    filters = ["user_id = ?" if user_id is not None else "user_id IS NULL"]
    values: list[Any] = [user_id] if user_id is not None else []
    if goal_id:
        filters.append("goal_id = ?")
        values.append(goal_id)
    if draft_type:
        filters.append("draft_type = ?")
        values.append(_normalize_draft_type(draft_type))
    if status:
        filters.append("status = ?")
        values.append(_normalize_draft_status(status))
    values.append(limit)

    with store.db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM agent_drafts
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [_draft_from_row(row) for row in rows]


def get_agent_draft(draft_id: str, user_id: str | None) -> dict | None:
    with store.db_connection() as conn:
        if user_id is None:
            row = conn.execute(
                "SELECT * FROM agent_drafts WHERE id = ? AND user_id IS NULL",
                (draft_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM agent_drafts WHERE id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
    return _draft_from_row(row) if row else None


def make_idempotency_key(
    user_id: str | None,
    run_id: str,
    step_id: str,
    tool_name: str,
    payload: dict,
) -> str:
    user_scope = user_id or "anonymous"
    canonical_payload = _canonical_json(_normalize_payload(payload))
    source = "|".join([user_scope, run_id, step_id, tool_name, canonical_payload])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def is_valid_status_transition(current_status: str, next_status: str) -> bool:
    return next_status in DRAFT_STATUS_TRANSITIONS.get(current_status, set())


def transition_drafts_for_action_log(
    conn,
    draft_ids: list[str],
    user_id: str | None,
    goal_id: str | None,
    next_status: str,
) -> list[dict]:
    """Move a confirmation batch together with its ActionLog transaction."""
    if next_status not in {"confirmed", "rejected"}:
        raise ValueError("Action log can only confirm or reject drafts.")

    rows = _get_scoped_draft_rows(conn, draft_ids, user_id, goal_id)
    current_statuses = {row["status"] for row in rows}
    if next_status == "confirmed":
        if current_statuses == {"confirmed"}:
            return [_draft_from_row(row) for row in rows]
        if current_statuses != {"proposed"}:
            raise ValueError("Only proposed drafts can be confirmed.")
    else:
        if current_statuses == {"rejected"}:
            return [_draft_from_row(row) for row in rows]
        if not current_statuses <= {"proposed", "confirmed"}:
            raise ValueError("Applied drafts cannot be rejected.")

    now = store.now_iso()
    placeholders = ", ".join("?" for _ in draft_ids)
    conn.execute(
        f"""
        UPDATE agent_drafts
        SET status = ?, updated_at = ?
        WHERE id IN ({placeholders})
        """,
        [next_status, now, *draft_ids],
    )
    return [
        {**_draft_from_row(row), "status": next_status, "updatedAt": now}
        for row in rows
    ]


def apply_confirmed_drafts(
    *,
    draft_ids: list[str],
    user_id: str | None,
    goal_id: str | None,
    action_log_id: str,
) -> tuple[list[dict], int, int, list[str]]:
    """Apply a confirmed batch once, including formal records and ActionLog state."""
    normalized_ids = _normalize_draft_ids(draft_ids)
    with store.db_connection() as conn:
        action_log = _get_scoped_action_log(conn, action_log_id, user_id)
        if action_log["action_type"] != "apply_confirmed_draft":
            raise ValueError("Action log does not authorize confirmed draft application.")
        if action_log["goal_id"] != goal_id:
            raise ValueError("Action log goal does not match the current run.")

        proposed_payload = json.loads(action_log["proposed_payload"])
        if proposed_payload.get("draftIds") != normalized_ids:
            raise ValueError("Action log draft IDs do not match the apply request.")

        rows = _get_scoped_draft_rows(conn, normalized_ids, user_id, goal_id)
        statuses = {row["status"] for row in rows}
        if statuses == {"applied"}:
            if action_log["status"] not in {"accepted", "applied"}:
                raise ValueError("Applied drafts require an accepted ActionLog.")
            if action_log["status"] == "accepted":
                conn.execute(
                    "UPDATE agent_action_logs SET status = ?, updated_at = ? WHERE id = ?",
                    ("applied", store.now_iso(), action_log_id),
                )
            drafts = [_draft_from_row(row) for row in rows]
            return drafts, 0, len(drafts), _flatten_applied_entity_ids(drafts)

        if statuses != {"confirmed"}:
            raise ValueError("All drafts must be confirmed before formal application.")
        if action_log["status"] != "accepted":
            raise ValueError("Confirmed draft application requires an accepted ActionLog.")

        now = store.now_iso()
        applied_drafts = []
        applied_entity_ids = []
        for row in rows:
            draft = _draft_from_row(row)
            entity_id = _apply_formal_entity(conn, draft, user_id, goal_id, now)
            applied_entity_ids.append(entity_id)
            applied_drafts.append(
                {
                    **draft,
                    "status": "applied",
                    "appliedEntityIds": [entity_id],
                    "updatedAt": now,
                    "appliedAt": now,
                }
            )
            conn.execute(
                """
                UPDATE agent_drafts
                SET status = ?, applied_entity_ids = ?, updated_at = ?, applied_at = ?
                WHERE id = ? AND status = ?
                """,
                ("applied", json.dumps([entity_id]), now, now, draft["id"], "confirmed"),
            )

        action_cursor = conn.execute(
            """
            UPDATE agent_action_logs
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            ("applied", now, action_log_id, "accepted"),
        )
        if action_cursor.rowcount != 1:
            raise ValueError("Action log is no longer accepted for formal application.")

    return applied_drafts, len(applied_drafts), 0, applied_entity_ids


def _validate_origin(
    run_id: str,
    step_id: str,
    user_id: str | None,
    goal_id: str | None,
) -> None:
    with store.db_connection() as conn:
        if user_id is None:
            run = conn.execute(
                "SELECT id, goal_id FROM agent_runs WHERE id = ? AND user_id IS NULL",
                (run_id,),
            ).fetchone()
        else:
            run = conn.execute(
                "SELECT id, goal_id FROM agent_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
        if not run:
            raise ValueError("Draft source run was not found in the current user scope.")
        if run["goal_id"] != goal_id:
            raise ValueError("Draft goal does not match the source run.")

        step = conn.execute(
            "SELECT id FROM agent_run_steps WHERE id = ? AND run_id = ?",
            (step_id, run_id),
        ).fetchone()
        if not step:
            raise ValueError("Draft source step does not belong to the source run.")


def _normalize_draft_type(draft_type: str) -> str:
    if draft_type not in VALID_DRAFT_TYPES:
        raise ValueError("Invalid draft type")
    return draft_type


def _normalize_draft_status(status: str) -> str:
    if status not in VALID_DRAFT_STATUSES:
        raise ValueError("Invalid draft status")
    return status


def _normalize_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Draft payload must be an object")
    return json.loads(_canonical_json(payload))


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_draft_ids(draft_ids: list[str]) -> list[str]:
    if not isinstance(draft_ids, list) or not draft_ids:
        raise ValueError("At least one draft ID is required.")
    if not all(isinstance(draft_id, str) and draft_id.strip() for draft_id in draft_ids):
        raise ValueError("Draft IDs must be non-empty strings.")
    normalized_ids = [draft_id.strip() for draft_id in draft_ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("Draft IDs must be unique within one apply request.")
    return normalized_ids


def _get_scoped_draft_rows(
    conn,
    draft_ids: list[str],
    user_id: str | None,
    goal_id: str | None,
):
    normalized_ids = _normalize_draft_ids(draft_ids)
    placeholders = ", ".join("?" for _ in normalized_ids)
    owner_clause = "user_id IS NULL" if user_id is None else "user_id = ?"
    goal_clause = "goal_id IS NULL" if goal_id is None else "goal_id = ?"
    values: list[Any] = [*normalized_ids]
    if user_id is not None:
        values.append(user_id)
    if goal_id is not None:
        values.append(goal_id)
    rows = conn.execute(
        f"""
        SELECT * FROM agent_drafts
        WHERE id IN ({placeholders}) AND {owner_clause} AND {goal_clause}
        """,
        values,
    ).fetchall()
    rows_by_id = {row["id"]: row for row in rows}
    if len(rows_by_id) != len(normalized_ids):
        raise ValueError("One or more drafts were not found in the current user and goal scope.")
    return [rows_by_id[draft_id] for draft_id in normalized_ids]


def _get_scoped_action_log(conn, action_log_id: str, user_id: str | None):
    if user_id is None:
        row = conn.execute(
            "SELECT * FROM agent_action_logs WHERE id = ? AND user_id IS NULL",
            (action_log_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM agent_action_logs WHERE id = ? AND user_id = ?",
            (action_log_id, user_id),
        ).fetchone()
    if not row:
        raise ValueError("Action log was not found in the current user scope.")
    return row


def _apply_formal_entity(
    conn,
    draft: dict,
    user_id: str | None,
    goal_id: str | None,
    now: str,
) -> str:
    payload = draft["payload"]
    if draft["draftType"] == "review":
        material_id = _required_text(payload, "materialId")
        _validate_material_scope(conn, material_id, user_id, goal_id)
        front = _required_text(payload, "front")
        back = _required_text(payload, "back")
        entity_id = store.make_id("flashcard")
        flashcard_review_service.insert_scheduled_flashcard(
            conn,
            flashcard_review_service.new_scheduled_flashcard(
                material_id=material_id,
                front=front,
                back=back,
                flashcard_id=entity_id,
                now=now,
            ),
        )
        return entity_id

    if draft["draftType"] == "task":
        payload_goal_id = _required_text(payload, "goalId")
        if payload_goal_id != draft["goalId"] or payload_goal_id != goal_id:
            raise ValueError("Task draft payload goal does not match the current goal scope.")
        _validate_goal_scope(conn, payload_goal_id, user_id)
        title = _required_text(payload, "title")
        detail = _required_text(payload, "detail")
        target_date = _required_text(payload, "date")
        priority = _required_text(payload, "priority")
        entity_id = store.make_id("task")
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal_id, title, detail, date, priority, done, completed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (entity_id, payload_goal_id, title, detail, target_date, priority, 0, None, now, now),
        )
        return entity_id

    raise ValueError("Draft type cannot be mapped to a formal entity.")


def _validate_material_scope(conn, material_id: str, user_id: str | None, goal_id: str | None) -> None:
    row = conn.execute(
        "SELECT id, goal_id FROM materials WHERE id = ?",
        (material_id,),
    ).fetchone()
    if not row or row["goal_id"] != goal_id:
        raise ValueError("Review draft material does not belong to the current goal scope.")
    if goal_id is None:
        raise ValueError("Review draft material requires a scoped learning goal.")
    _validate_goal_scope(conn, goal_id, user_id)


def _validate_goal_scope(conn, goal_id: str, user_id: str | None) -> None:
    if user_id is None:
        row = conn.execute(
            "SELECT id FROM goals WHERE id = ? AND user_id IS NULL",
            (goal_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM goals WHERE id = ? AND user_id = ?",
            (goal_id, user_id),
        ).fetchone()
    if not row:
        raise ValueError("Draft goal was not found in the current user scope.")


def _required_text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Draft payload field {field} must be a non-empty string.")
    return value.strip()


def _flatten_applied_entity_ids(drafts: list[dict]) -> list[str]:
    return [
        entity_id
        for draft in drafts
        for entity_id in draft.get("appliedEntityIds") or []
    ]


def _draft_from_row(row) -> dict:
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "goalId": row["goal_id"],
        "runId": row["run_id"],
        "stepId": row["step_id"],
        "draftType": row["draft_type"],
        "payload": json.loads(row["payload"]),
        "status": row["status"],
        "idempotencyKey": row["idempotency_key"],
        "appliedEntityIds": json.loads(row["applied_entity_ids"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "appliedAt": row["applied_at"],
    }
