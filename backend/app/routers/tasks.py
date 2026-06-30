from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.tasks import TaskCheckInRequest
from backend.app.services import store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/today")
def list_today_tasks(date: str | None = Query(default=None)):
    target_date = date or store.today_iso()
    return ok(store.list_tasks_for_date(target_date))


@router.post("/{task_id}/checkin")
def checkin_task(task_id: str, payload: TaskCheckInRequest):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    now = store.now_iso()
    completed_at = now if payload.done else None
    task = store.update_task_checkin(task_id, payload.done, completed_at)

    store.create_checkin(
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

