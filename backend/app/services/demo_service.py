import json
import secrets
from datetime import datetime, timedelta, timezone

from backend.app.services import auth_service, store


def create_demo_session() -> tuple[dict, str]:
    """Create an isolated, deterministic demo workspace without invoking any model provider."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_at = (now + timedelta(hours=24)).isoformat()
    user_id = store.make_id("demo")
    goal_id = store.make_id("goal")
    material_id = store.make_id("material")
    action_log_id = store.make_id("action")
    run_id = store.make_id("run")
    step_id = store.make_id("step")
    token = secrets.token_urlsafe(auth_service.SESSION_TOKEN_BYTES)

    user = {
        "id": user_id,
        "name": "体验用户",
        "email": f"demo-{secrets.token_hex(8)}@example.invalid",
        "password_hash": "",
        "password_salt": "",
        "account_type": "demo",
        "password_algorithm": "none",
        "expires_at": expires_at,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    context_snapshot = {
        "summary": {"goalCount": 1, "taskOpen": 3, "materialTotal": 1, "flashcardTotal": 2},
        "goals": [{"id": goal_id, "name": "完成一周 AI Agent 学习计划"}],
    }
    decision_snapshot = {
        "nextAction": "create_followup_tasks",
        "requiresConfirmation": True,
        "reason": "演示任务需要用户确认后写入正式计划。",
    }

    store.init_db()
    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, name, email, password_hash, password_salt, account_type,
                password_algorithm, expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user["name"],
                user["email"],
                "",
                "",
                "demo",
                "none",
                expires_at,
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, revoked_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (store.make_id("session"), user_id, auth_service.hash_session_token(token), expires_at, now_iso),
        )
        conn.execute(
            """
            INSERT INTO goals (
                id, user_id, name, subject, level, deadline, daily_minutes, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                goal_id,
                user_id,
                "完成一周 AI Agent 学习计划",
                "AI Agent 后端",
                "有基础",
                "2026-12-31",
                60,
                "掌握可控 Agent Runtime、检索和部署基础。",
                now_iso,
                now_iso,
            ),
        )
        for index, task in enumerate(("阅读 Agent Runtime 设计", "完成检索练习", "复盘工具调用边界"), start=1):
            conn.execute(
                """
                INSERT INTO tasks (
                    id, goal_id, title, detail, date, priority, done, completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    store.make_id("task"),
                    goal_id,
                    task,
                    "这是一键试用创建的确定性演示任务。",
                    f"2026-07-{16 + index:02d}",
                    "high" if index == 1 else "medium",
                    now_iso,
                    now_iso,
                ),
            )
        conn.execute(
            """
            INSERT INTO materials (
                id, user_id, goal_id, title, type, content, url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'text', ?, '', ?, ?)
            """,
            (
                material_id,
                user_id,
                goal_id,
                "Agent Runtime 演示资料",
                "Agent Runtime 通过观察、决策、工具执行与回读形成受控学习闭环。高风险写入必须等待用户确认。",
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO material_summaries (
                material_id, overview, key_points, difficulties, study_order, action_items, ai_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'demo-seed', ?, ?)
            """,
            (
                material_id,
                "用于演示受控 Agent 学习闭环的已处理资料。",
                json.dumps(["观察与决策", "高风险确认"], ensure_ascii=False),
                json.dumps(["区分建议与正式写入"], ensure_ascii=False),
                json.dumps(["先阅读概念", "再执行演示任务"], ensure_ascii=False),
                json.dumps(["确认后继续运行"], ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO material_chunks (
                id, material_id, chunk_index, content, keywords, embedding, created_at, updated_at
            ) VALUES (?, ?, 0, ?, ?, '[]', ?, ?)
            """,
            (
                store.make_id("chunk"),
                material_id,
                "Agent Runtime 通过观察、决策、工具执行与回读形成受控学习闭环。高风险写入必须等待用户确认。",
                json.dumps(["Agent", "Runtime", "确认"], ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )
        for front, back in (
            ("Agent Runtime 的受控闭环是什么？", "观察、决策、工具执行、回读，并对高风险写入要求确认。"),
            ("为什么高风险写入需要确认？", "避免智能体直接修改正式学习记录。"),
        ):
            conn.execute(
                """
                INSERT INTO flashcards (id, material_id, front, back, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'new', ?, ?)
                """,
                (store.make_id("flashcard"), material_id, front, back, now_iso, now_iso),
            )
        conn.execute(
            """
            INSERT INTO quiz_questions (
                id, material_id, question, type, options, answer, explanation, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store.make_id("quiz"),
                material_id,
                "高风险写入之前需要什么？",
                "理解题",
                "[]",
                "需要用户确认。",
                "演示资料明确要求高风险写入等待确认。",
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_action_logs (
                id, user_id, goal_id, action_type, observation, decision, proposed_payload, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'create_followup_tasks', ?, ?, ?, 'proposed', ?, ?)
            """,
            (
                action_log_id,
                user_id,
                goal_id,
                "演示任务需要确认。",
                json.dumps(decision_snapshot, ensure_ascii=False),
                json.dumps({"label": "确认创建后续任务"}, ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_runs (
                id, user_id, goal_id, trigger, objective, decision_mode, max_steps, current_step,
                context_snapshot, decision_snapshot, feedback_summary, status, stop_reason, error, created_at, updated_at
            ) VALUES (?, ?, ?, 'demo', ?, 'rule-based', 3, 1, ?, ?, '{}', 'waiting_confirmation', '', '', ?, ?)
            """,
            (
                run_id,
                user_id,
                goal_id,
                "整理本周学习计划并等待确认。",
                json.dumps(context_snapshot, ensure_ascii=False),
                json.dumps(decision_snapshot, ensure_ascii=False),
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_run_steps (
                id, run_id, step_index, context_snapshot, decision_snapshot, action_snapshot,
                tool_name, tool_input, tool_output, action_log_id, status, error, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, 'create_task_draft', '{}', '{}', ?, 'waiting_confirmation', '', ?, ?)
            """,
            (
                step_id,
                run_id,
                json.dumps(context_snapshot, ensure_ascii=False),
                json.dumps(decision_snapshot, ensure_ascii=False),
                json.dumps({"type": "create_followup_tasks"}, ensure_ascii=False),
                action_log_id,
                now_iso,
                now_iso,
            ),
        )
    return auth_service.public_user(user), token
