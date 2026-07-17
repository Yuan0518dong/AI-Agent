from backend.app.services import progress_service, store


def get_dashboard(target_date: str, user_id: str | None) -> dict:
    """Return the bounded data set needed to render the signed-in first view."""
    goals = store.list_goals(user_id)
    today_tasks = store.list_tasks_by_date(target_date, user_id)
    goal_by_id = {goal["id"]: goal for goal in goals}
    primary_goal = _primary_goal(goals, today_tasks)
    task_summary = _task_summary(user_id)
    flashcard_total = _flashcard_total(user_id)

    task_payload = [
        {
            **task,
            "goalName": goal_by_id.get(task["goal_id"], {}).get("name", ""),
            "dailyMinutes": goal_by_id.get(task["goal_id"], {}).get("daily_minutes", 0),
        }
        for task in today_tasks[:10]
    ]
    primary_payload = None
    if primary_goal:
        primary_progress = progress_service.get_goal_progress(primary_goal["id"], user_id)
        primary_payload = {
            **primary_goal,
            "progress": primary_progress,
        }

    total_tasks = task_summary["total"]
    completed_tasks = task_summary["completed"]
    return {
        "date": target_date,
        "summary": {
            "goalTotal": len(goals),
            "todayTaskTotal": len(today_tasks),
            "todayTaskCompleted": sum(1 for task in today_tasks if task["done"]),
            "taskTotal": total_tasks,
            "taskCompleted": completed_tasks,
            "completionRate": round((completed_tasks / total_tasks) * 100) if total_tasks else 0,
            "flashcardTotal": flashcard_total,
        },
        "primaryGoal": primary_payload,
        "todayTasks": task_payload,
    }


def _primary_goal(goals: list[dict], today_tasks: list[dict]) -> dict | None:
    goal_by_id = {goal["id"]: goal for goal in goals}
    first_pending = next((task for task in today_tasks if not task["done"]), None)
    if first_pending:
        return goal_by_id.get(first_pending["goal_id"])
    return goals[0] if goals else None


def _task_summary(user_id: str | None) -> dict:
    with store.db_connection() as conn:
        if user_id:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN tasks.done = 1 THEN 1 ELSE 0 END), 0) AS completed
                FROM tasks
                JOIN goals ON goals.id = tasks.goal_id
                WHERE goals.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END), 0) AS completed
                FROM tasks
                """
            ).fetchone()
    return {"total": int(row["total"] or 0), "completed": int(row["completed"] or 0)}


def _flashcard_total(user_id: str | None) -> int:
    with store.db_connection() as conn:
        if user_id:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM flashcards
                JOIN materials ON materials.id = flashcards.material_id
                WHERE materials.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS total FROM flashcards").fetchone()
    return int(row["total"] or 0)
