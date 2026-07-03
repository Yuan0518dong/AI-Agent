from fastapi import APIRouter, Depends, HTTPException

from backend.app.services import progress_service, store
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_progress(user_id: str | None = Depends(current_user_id)):
    return ok(progress_service.get_all_progress(user_id))


@router.get("/{goal_id}")
def get_goal_progress(goal_id: str, user_id: str | None = Depends(current_user_id)):
    if not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return ok(progress_service.get_goal_progress(goal_id, user_id))

