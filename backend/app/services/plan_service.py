from datetime import date, timedelta

from backend.app.services import ai_learning_service, store


def delete_tasks_for_goal(goal_id: str) -> None:
    store.delete_tasks_for_goal(goal_id)


def generate_plan_for_goal(
    goal: dict,
    days: int,
    regenerate: bool = True,
    user_id: str | None = None,
) -> list[dict]:
    if regenerate:
        delete_tasks_for_goal(goal["id"])

    plan = ai_learning_service.generate_learning_plan(goal, days, user_id)
    today = date.today()
    created_tasks = []

    for index, plan_task in enumerate(plan["tasks"]):
        now = store.now_iso()
        task = {
            "id": store.make_id("task"),
            "goal_id": goal["id"],
            "title": plan_task["title"],
            "detail": plan_task["detail"],
            "date": (today + timedelta(days=index)).isoformat(),
            "priority": plan_task["priority"],
            "done": False,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        created_tasks.append(store.create_task(task))

    return created_tasks


def _collect_topics(goal: dict) -> list[str]:
    parts = [goal.get("subject", ""), goal.get("notes", "")]
    topics = []

    for part in parts:
        for chunk in part.replace("，", ",").replace("。", ",").split(","):
            text = chunk.strip()
            if text:
                topics.append(text[:24])

    return topics or ["core topic"]

