from backend.app.services import store


def get_all_progress() -> list[dict]:
    return [get_goal_progress(goal["id"]) for goal in store.list_goals()]


def get_goal_progress(goal_id: str) -> dict:
    goal = store.get_goal(goal_id)
    goal_tasks = store.list_tasks_for_goal(goal_id)
    completed = [task for task in goal_tasks if task["done"]]
    today = store.today_iso()
    today_tasks = [task for task in goal_tasks if task["date"] == today]
    today_completed = [task for task in today_tasks if task["done"]]
    completion_rate = round((len(completed) / len(goal_tasks)) * 100) if goal_tasks else 0

    return {
        "goal_id": goal_id,
        "goal_name": goal["name"],
        "total_tasks": len(goal_tasks),
        "completed_tasks": len(completed),
        "completion_rate": completion_rate,
        "today_total": len(today_tasks),
        "today_completed": len(today_completed),
    }

