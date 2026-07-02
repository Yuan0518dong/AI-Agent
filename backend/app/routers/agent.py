from fastapi import APIRouter, HTTPException

from backend.app.schemas.agent import AgentAskRequest
from backend.app.services import agent_service, store
from backend.app.utils.responses import ok


router = APIRouter()


@router.post("/ask")
def ask_agent(payload: AgentAskRequest):
    goal_id = _normalize_goal_id(payload.goalId)
    goal = store.get_goal(goal_id) if goal_id else None
    if goal_id and not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(
        agent_service.answer_question(
            question=payload.question,
            goal=goal,
            limit=payload.limit,
        )
    )


def _normalize_goal_id(goal_id: str | None) -> str | None:
    if goal_id is None:
        return None
    return goal_id.strip() or None
