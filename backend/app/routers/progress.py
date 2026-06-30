from fastapi import APIRouter, HTTPException

from backend.app.services import progress_service, store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_progress():
    return ok(progress_service.get_all_progress())


@router.get("/{goal_id}")
def get_goal_progress(goal_id: str):
    if goal_id not in store.goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    return ok(progress_service.get_goal_progress(goal_id))

