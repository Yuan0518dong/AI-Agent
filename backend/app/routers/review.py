from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.services import flashcard_review_service, material_store, store
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/queue")
def list_review_queue(
    goalId: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _scoped_goal_id(goalId, user_id)
    return ok(flashcard_review_service.list_due_flashcards(goal_id, user_id, limit))


@router.get("/weak-points")
def list_review_weak_points(
    goalId: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _scoped_goal_id(goalId, user_id)
    return ok(material_store.list_weak_points_for_scope(goal_id, user_id))


def _scoped_goal_id(goal_id: str | None, user_id: str | None) -> str | None:
    normalized_goal_id = goal_id.strip() if goal_id else None
    if normalized_goal_id and not store.get_goal(normalized_goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return normalized_goal_id
