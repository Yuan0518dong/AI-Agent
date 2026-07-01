from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.tasks import TaskCheckInRequest
from backend.app.services import store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/today")
def list_today_tasks(date: str | None = Query(default=None)):
    target_date = date or store.today_iso()
    return ok(store.list_tasks_by_date(target_date))


@router.post("/{task_id}/checkin")
def checkin_task(task_id: str, payload: TaskCheckInRequest):
    task = store.set_task_checkin(task_id, payload.done)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return ok(task)

