from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from backend.app.services import dashboard_service, store
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def get_dashboard(
    target_date: Date | None = Query(default=None, alias="date"),
    user_id: str | None = Depends(current_user_id),
):
    return ok(dashboard_service.get_dashboard((target_date or Date.today()).isoformat(), user_id))
