from datetime import date, timedelta

from backend.app.services import store


def delete_tasks_for_goal(goal_id: str) -> None:
    store.delete_tasks_for_goal(goal_id)


def generate_plan_for_goal(goal: dict, days: int, regenerate: bool = True) -> list[dict]:
    if regenerate:
        delete_tasks_for_goal(goal["id"])

    topics = _collect_topics(goal)
    today = date.today()
    created_tasks = []

    for index in range(days):
        topic = topics[index % len(topics)]
        now = store.now_iso()
        task = {
            "id": store.make_id("task"),
            "goal_id": goal["id"],
            "title": f"Day {index + 1}: Learn {topic}",
            "detail": f"Study for {goal['daily_minutes']} minutes and complete one review.",
            "date": (today + timedelta(days=index)).isoformat(),
            "priority": "normal",
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

