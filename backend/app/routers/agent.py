from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.schemas.agent import AgentActionLogCreate, AgentActionLogUpdate, AgentAskRequest
from backend.app.services import (
    agent_action_log_service,
    agent_context_service,
    agent_decision_service,
    agent_service,
    material_store,
    store,
)
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("/context")
def get_agent_context(
    goalId: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(agent_context_service.build_agent_context(goal_id, user_id))


@router.post("/decide")
def decide_agent_next_action(
    goalId: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(agent_decision_service.decide_next_action(goal_id, user_id))


@router.get("/action-logs")
def list_agent_action_logs(
    goalId: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(agent_action_log_service.list_action_logs(goal_id, user_id, limit))


@router.post("/action-logs")
def create_agent_action_log(
    payload: AgentActionLogCreate,
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(payload.goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    action_log = agent_action_log_service.create_action_log(
        {
            **payload.model_dump(),
            "goalId": goal_id,
        },
        user_id,
    )
    return ok(action_log)


@router.patch("/action-logs/{log_id}")
def update_agent_action_log(
    log_id: str,
    payload: AgentActionLogUpdate,
    user_id: str | None = Depends(current_user_id),
):
    action_log = agent_action_log_service.update_action_log_status(
        log_id,
        payload.status,
        user_id,
    )
    if not action_log:
        raise HTTPException(status_code=404, detail="Action log not found")

    return ok(action_log)


@router.post("/ask")
def ask_agent(payload: AgentAskRequest, user_id: str | None = Depends(current_user_id)):
    goal_id = _normalize_goal_id(payload.goalId)
    material_id = _normalize_id(payload.materialId)
    material = material_store.get_material(material_id, user_id) if material_id else None
    if material_id and not material:
        raise HTTPException(status_code=404, detail="Material not found")

    if material and goal_id and material["goalId"] and material["goalId"] != goal_id:
        raise HTTPException(status_code=400, detail="Material does not belong to goal")

    goal_context_id = goal_id or (material["goalId"] if material else None)
    goal = store.get_goal(goal_context_id, user_id) if goal_context_id else None
    if goal_context_id and not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    answer = agent_service.answer_question(
        question=payload.question,
        goal=goal,
        material_id=material_id,
        limit=payload.limit,
        user_id=user_id,
    )
    if answer["materialId"]:
        now = store.now_iso()
        material_qa_record = {
            "id": store.make_id("qa"),
            "materialId": answer["materialId"],
            "goalId": answer["goalId"],
            "question": answer["question"],
            "answer": answer["answer"],
            "basis": answer["basis"],
            "suggestion": answer["suggestion"],
            "sourceTitle": answer["sourceTitle"],
            "isFromMaterial": answer["isFromMaterial"],
            "confidence": answer["confidence"],
            "mode": answer["mode"],
            "nextAction": answer["nextAction"],
            "requiresConfirmation": answer["requiresConfirmation"],
            "insufficiencyReason": answer["insufficiencyReason"],
            "reviewDrafts": answer["reviewDrafts"],
            "createdAt": now,
        }
        material_store.save_qa_record(material_qa_record)
        answer["id"] = material_qa_record["id"]
        answer["createdAt"] = now

    return ok(answer)


def _normalize_goal_id(goal_id: str | None) -> str | None:
    return _normalize_id(goal_id)


def _normalize_id(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
