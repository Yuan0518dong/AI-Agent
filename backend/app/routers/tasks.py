from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.schemas.tasks import TaskCheckInRequest
from backend.app.services import store
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/today")
def list_today_tasks(
    date: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
):
    target_date = date or store.today_iso()
    return ok(store.list_tasks_by_date(target_date, user_id))


@router.post("/{task_id}/checkin")
def checkin_task(
    task_id: str,
    payload: TaskCheckInRequest,
    user_id: str | None = Depends(current_user_id),
):
    if user_id:
        task = store.get_task(task_id)
        if not task or not store.get_goal(task["goal_id"], user_id):
            raise HTTPException(status_code=404, detail="Task not found")

    task = store.set_task_checkin(task_id, payload.done)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return ok(task)

