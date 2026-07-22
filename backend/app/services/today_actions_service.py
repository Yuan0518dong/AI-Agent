from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from backend.app.services import agent_draft_service, flashcard_review_service, material_store, store


CATEGORY_ORDER = (
    "overdue_task",
    "today_task",
    "due_flashcard",
    "weak_point",
    "pending_confirmation",
)
CATEGORY_LIMIT = 3
DRAFT_READ_LIMIT = 100


def get_today_actions(user_id: str | None, limit: int = 15) -> dict:
    """Return a small, read-only learning-action projection for the current day.

    This intentionally depends only on task, review, weak-point, and draft stores.
    Agent Context, decisions, runs, and providers are not part of the read path.
    """
    if not 1 <= limit <= 15:
        raise ValueError("Today actions limit must be between 1 and 15.")

    target_date = Date.today().isoformat()
    grouped_items = {
        "overdue_task": _task_items(user_id, target_date, overdue=True),
        "today_task": _task_items(user_id, target_date, overdue=False),
        "due_flashcard": _due_flashcard_items(user_id),
        "weak_point": _weak_point_items(user_id),
        "pending_confirmation": _pending_confirmation_items(user_id),
    }
    items = [item for kind in CATEGORY_ORDER for item in grouped_items[kind]][:limit]
    return {
        "date": target_date,
        "limit": limit,
        "items": items,
        "categoryCounts": {kind: len(grouped_items[kind]) for kind in CATEGORY_ORDER},
    }


def _task_items(user_id: str | None, target_date: str, *, overdue: bool) -> list[dict]:
    date_condition = "tasks.date < ?" if overdue else "tasks.date = ?"
    user_condition = "goals.user_id = ?" if user_id is not None else "goals.user_id IS NULL"
    parameters: list[str] = [target_date]
    if user_id is not None:
        parameters.append(user_id)
    with store.db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT tasks.id, tasks.goal_id, tasks.title, tasks.detail, tasks.date, tasks.priority,
                   goals.name AS goal_name
            FROM tasks
            JOIN goals ON goals.id = tasks.goal_id
            WHERE tasks.done = 0 AND {date_condition} AND {user_condition}
            ORDER BY
                tasks.date ASC,
                CASE LOWER(tasks.priority)
                    WHEN 'high' THEN 0
                    WHEN 'normal' THEN 1
                    WHEN 'low' THEN 2
                    ELSE 3
                END ASC,
                tasks.id ASC
            LIMIT ?
            """,
            [*parameters, CATEGORY_LIMIT],
        ).fetchall()
    kind = "overdue_task" if overdue else "today_task"
    label = "逾期任务" if overdue else "今日任务"
    return [
        {
            "id": row["id"],
            "kind": kind,
            "label": label,
            "title": row["title"],
            "detail": _task_detail(row["goal_name"], row["date"], row["priority"]),
            "goalId": row["goal_id"],
            "target": {"view": "goals", "taskId": row["id"]},
        }
        for row in rows
    ]


def _due_flashcard_items(user_id: str | None) -> list[dict]:
    return [
        {
            "id": flashcard["id"],
            "kind": "due_flashcard",
            "label": "到期闪卡",
            "title": f"复习：{flashcard['front']}",
            "detail": f"{flashcard['materialTitle']} · 到期 {flashcard['dueAt']}",
            "goalId": flashcard["goalId"],
            "target": {
                "view": "memory",
                "materialId": flashcard["materialId"],
                "flashcardId": flashcard["id"],
            },
        }
        for flashcard in flashcard_review_service.list_due_flashcards(None, user_id, CATEGORY_LIMIT)
    ]


def _weak_point_items(user_id: str | None) -> list[dict]:
    unresolved = [
        point
        for point in material_store.list_weak_points_for_scope(None, user_id)
        if not point["resolved"]
    ]
    ordered = sorted(
        unresolved,
        key=lambda point: (*_descending_timestamp_key(point["latestAttemptAt"]), point["quizId"]),
    )[:CATEGORY_LIMIT]
    return [
        {
            "id": point["quizId"],
            "kind": "weak_point",
            "label": "待巩固薄弱点",
            "title": f"巩固：{point['question']}",
            "detail": _weak_point_detail(point),
            "goalId": point["goalId"],
            "target": {
                "view": "memory",
                "materialId": point["materialId"],
                "quizId": point["quizId"],
            },
        }
        for point in ordered
    ]


def _pending_confirmation_items(user_id: str | None) -> list[dict]:
    drafts = agent_draft_service.list_agent_drafts(
        user_id=user_id,
        status="proposed",
        limit=DRAFT_READ_LIMIT,
        ascending=True,
        require_goal_id=True,
    )
    ordered = sorted(
        drafts,
        key=lambda draft: (*_ascending_timestamp_key(draft["createdAt"]), draft["id"]),
    )[:CATEGORY_LIMIT]
    return [
        {
            "id": draft["id"],
            "kind": "pending_confirmation",
            "label": "待处理助手确认",
            "title": _draft_title(draft["draftType"]),
            "detail": f"创建于 {draft['createdAt']}",
            "goalId": draft["goalId"],
            "target": {
                "view": "agent",
                "runId": draft["runId"],
                "draftId": draft["id"],
            },
        }
        for draft in ordered
    ]


def _task_detail(goal_name: str, target_date: str, priority: str) -> str:
    priority_labels = {"high": "高优先级", "normal": "普通优先级", "low": "低优先级"}
    return f"{goal_name} · {target_date} · {priority_labels.get((priority or '').lower(), '未标注优先级')}"


def _weak_point_detail(point: dict) -> str:
    score = point["latestScore"]
    score_text = f"上次得分 {score}" if score is not None else "有待巩固"
    return f"{point['materialTitle']} · {score_text}"


def _draft_title(draft_type: str) -> str:
    return "确认复习草稿" if draft_type == "review" else "确认学习任务草稿"


def _descending_timestamp_key(value: str) -> tuple[int, float]:
    """Place absent/invalid times last while keeping valid times newest first."""
    try:
        normalized = str(value or "").replace("Z", "+00:00")
        timestamp = DateTime.fromisoformat(normalized).timestamp()
    except (TypeError, ValueError):
        return (1, 0.0)
    return (0, -timestamp)


def _ascending_timestamp_key(value: str) -> tuple[int, float]:
    try:
        normalized = str(value or "").replace("Z", "+00:00")
        timestamp = DateTime.fromisoformat(normalized).timestamp()
    except (TypeError, ValueError):
        return (1, 0.0)
    return (0, timestamp)
