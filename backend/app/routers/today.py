from fastapi import APIRouter, Depends, Query

from backend.app.services import today_actions_service
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/actions")
def get_today_actions(
    limit: int = Query(default=15, ge=1, le=15),
    user_id: str | None = Depends(current_user_id),
):
    return ok(today_actions_service.get_today_actions(user_id, limit))
