from fastapi import APIRouter, HTTPException

from backend.app.schemas.goals import GoalCreate, GoalUpdate
from backend.app.schemas.tasks import PlanGenerateRequest
from backend.app.services import plan_service, store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_goals():
    return ok(list(store.goals.values()))


@router.post("")
def create_goal(payload: GoalCreate):
    now = store.now_iso()
    goal = {
        "id": store.make_id("goal"),
        "name": payload.name,
        "subject": payload.subject,
        "level": payload.level,
        "deadline": payload.deadline.isoformat(),
        "daily_minutes": payload.daily_minutes,
        "notes": payload.notes or "",
        "created_at": now,
        "updated_at": now,
    }
    store.goals[goal["id"]] = goal
    return ok(goal)


@router.get("/{goal_id}")
def get_goal(goal_id: str):
    goal = store.goals.get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return ok(goal)


@router.put("/{goal_id}")
def update_goal(goal_id: str, payload: GoalUpdate):
    goal = store.goals.get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    changes = payload.model_dump(exclude_unset=True)
    if "deadline" in changes:
        changes["deadline"] = changes["deadline"].isoformat()
    goal.update(changes)
    goal["updated_at"] = store.now_iso()
    return ok(goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: str):
    if goal_id not in store.goals:
        raise HTTPException(status_code=404, detail="Goal not found")

    del store.goals[goal_id]
    plan_service.delete_tasks_for_goal(goal_id)
    store.checkins[:] = [item for item in store.checkins if item["goal_id"] != goal_id]
    return ok({"deleted": True, "goal_id": goal_id})


@router.post("/{goal_id}/plans")
def generate_plan(goal_id: str, payload: PlanGenerateRequest):
    goal = store.goals.get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    tasks = plan_service.generate_plan_for_goal(
        goal=goal,
        days=payload.days,
        regenerate=payload.regenerate,
    )
    return ok(tasks)


@router.get("/{goal_id}/tasks")
def list_goal_tasks(goal_id: str):
    if goal_id not in store.goals:
        raise HTTPException(status_code=404, detail="Goal not found")

    tasks = [task for task in store.tasks.values() if task["goal_id"] == goal_id]
    return ok(tasks)

