from fastapi import APIRouter, HTTPException

from backend.app.schemas.goals import GoalCreate, GoalUpdate
from backend.app.schemas.tasks import PlanGenerateRequest
from backend.app.services import plan_service, store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_goals():
    return ok(store.list_goals())


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
    return ok(store.create_goal(goal))


@router.get("/{goal_id}")
def get_goal(goal_id: str):
    goal = store.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return ok(goal)


@router.put("/{goal_id}")
def update_goal(goal_id: str, payload: GoalUpdate):
    goal = store.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return ok(goal)

    if "deadline" in changes:
        changes["deadline"] = changes["deadline"].isoformat()
    changes["updated_at"] = store.now_iso()
    updated_goal = store.update_goal(goal_id, changes)
    return ok(updated_goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: str):
    if not store.delete_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok({"deleted": True, "goal_id": goal_id})


@router.post("/{goal_id}/plans")
def generate_plan(goal_id: str, payload: PlanGenerateRequest):
    goal = store.get_goal(goal_id)
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
    if not store.get_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(store.list_tasks_for_goal(goal_id))
