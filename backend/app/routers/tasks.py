from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.tasks import TaskCheckInRequest
from backend.app.services import store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/today")
def list_today_tasks(date: str | None = Query(default=None)):
    target_date = date or store.today_iso()
    tasks = [task for task in store.tasks.values() if task["date"] == target_date]
    return ok(tasks)


@router.post("/{task_id}/checkin")
def checkin_task(task_id: str, payload: TaskCheckInRequest):
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    now = store.now_iso()
    task["done"] = payload.done
    task["completed_at"] = now if payload.done else None
    task["updated_at"] = now

    store.checkins.append(
        {
            "id": store.make_id("checkin"),
            "goal_id": task["goal_id"],
            "task_id": task_id,
            "date": store.today_iso(),
            "status": "completed" if payload.done else "canceled",
            "checked_at": now,
        }
    )
    return ok(task)

