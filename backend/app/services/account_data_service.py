import json

from backend.app.services import rate_limit_service, store


def export_account_data(user: dict) -> dict:
    """Build a portable account export without credentials or session secrets."""
    user_id = user["id"]
    return {
        "exportedAt": store.now_iso(),
        "formatVersion": 2,
        "account": {
            "name": user["name"],
            "email": user["email"],
            "accountType": user["account_type"],
            "expiresAt": user["expires_at"],
            "createdAt": user["created_at"],
        },
        "goals": _rows("SELECT * FROM goals WHERE user_id = ? ORDER BY created_at ASC", (user_id,)),
        "tasks": _rows(
            """
            SELECT tasks.* FROM tasks
            JOIN goals ON goals.id = tasks.goal_id
            WHERE goals.user_id = ? ORDER BY tasks.created_at ASC
            """,
            (user_id,),
        ),
        "checkins": _rows(
            """
            SELECT checkins.* FROM checkins
            JOIN goals ON goals.id = checkins.goal_id
            WHERE goals.user_id = ? ORDER BY checkins.checked_at ASC
            """,
            (user_id,),
        ),
        "materials": _rows("SELECT * FROM materials WHERE user_id = ? ORDER BY created_at ASC", (user_id,)),
        "materialSummaries": _rows(
            """
            SELECT material_summaries.* FROM material_summaries
            JOIN materials ON materials.id = material_summaries.material_id
            WHERE materials.user_id = ?
            """,
            (user_id,),
        ),
        "materialChunks": _rows(
            """
            SELECT material_chunks.* FROM material_chunks
            JOIN materials ON materials.id = material_chunks.material_id
            WHERE materials.user_id = ? ORDER BY material_chunks.material_id, material_chunks.chunk_index
            """,
            (user_id,),
        ),
        "materialQaRecords": _rows(
            """
            SELECT material_qa_records.* FROM material_qa_records
            JOIN materials ON materials.id = material_qa_records.material_id
            WHERE materials.user_id = ? ORDER BY material_qa_records.created_at ASC
            """,
            (user_id,),
        ),
        "flashcards": _rows(
            """
            SELECT flashcards.* FROM flashcards
            JOIN materials ON materials.id = flashcards.material_id
            WHERE materials.user_id = ? ORDER BY flashcards.created_at ASC
            """,
            (user_id,),
        ),
        "quizQuestions": _rows(
            """
            SELECT quiz_questions.* FROM quiz_questions
            JOIN materials ON materials.id = quiz_questions.material_id
            WHERE materials.user_id = ? ORDER BY quiz_questions.created_at ASC
            """,
            (user_id,),
        ),
        "quizAttempts": _rows(
            """
            SELECT quiz_attempts.* FROM quiz_attempts
            JOIN materials ON materials.id = quiz_attempts.material_id
            WHERE materials.user_id = ? ORDER BY quiz_attempts.created_at ASC
            """,
            (user_id,),
        ),
        "agentActionLogs": _rows(
            "SELECT * FROM agent_action_logs WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ),
        "agentRuns": _rows(
            "SELECT * FROM agent_runs WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ),
        "agentRunSteps": _rows(
            """
            SELECT agent_run_steps.* FROM agent_run_steps
            JOIN agent_runs ON agent_runs.id = agent_run_steps.run_id
            WHERE agent_runs.user_id = ? ORDER BY agent_run_steps.created_at ASC
            """,
            (user_id,),
        ),
        "agentDrafts": _rows(
            "SELECT * FROM agent_drafts WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ),
    }


def delete_account_data(user_id: str) -> bool:
    """Delete the account and all rows that are owned by it in one transaction."""
    with store.db_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM agent_action_logs WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM agent_drafts WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM agent_runs WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM materials WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM goals WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.execute(
            "DELETE FROM model_usage_counters WHERE owner_hash = ?",
            (rate_limit_service._hash_identifier(user_id),),
        )
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount == 1


def _rows(statement: str, parameters: tuple[str, ...]) -> list[dict]:
    with store.db_connection() as conn:
        rows = conn.execute(statement, parameters).fetchall()
    return [_serialize_row(row) for row in rows]


def _serialize_row(row) -> dict:
    result = dict(row)
    for key in {
        "action_items",
        "action_snapshot",
        "applied_entity_ids",
        "context_snapshot",
        "decision",
        "decision_snapshot",
        "embedding",
        "feedback_summary",
        "fsrs_card",
        "key_points",
        "keywords",
        "options",
        "proposed_payload",
        "review_drafts",
        "study_order",
        "tool_input",
        "tool_output",
    }:
        if isinstance(result.get(key), str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                pass
    return result
