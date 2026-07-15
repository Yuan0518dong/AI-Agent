from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.schemas.agent import (
    AgentActionLogCreate,
    AgentActionLogUpdate,
    AgentAskRequest,
    AgentRunCreate,
    AgentRunExecute,
    AgentRunUpdate,
)
from backend.app.services import (
    agent_action_log_service,
    agent_context_service,
    agent_decision_service,
    agent_draft_service,
    agent_run_service,
    agent_loop_service,
    agent_service,
    agent_tool_registry_service,
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
    decisionMode: str = Query(default="hybrid", pattern="^(rule-based|llm-json|hybrid)$"),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(agent_decision_service.decide_next_action(goal_id, user_id, decisionMode))


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
    try:
        action_log = agent_action_log_service.update_action_log_status(
            log_id,
            payload.status,
            user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not action_log:
        raise HTTPException(status_code=404, detail="Action log not found")

    return ok(action_log)


@router.get("/drafts")
def list_agent_drafts(
    goalId: str | None = Query(default=None),
    draftType: str | None = Query(default=None, pattern="^(review|task)$"),
    status: str | None = Query(default=None, pattern="^(proposed|confirmed|applied|rejected)$"),
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(
        agent_draft_service.list_agent_drafts(
            user_id=user_id,
            goal_id=goal_id,
            draft_type=draftType,
            status=status,
            limit=limit,
        )
    )


@router.get("/drafts/{draft_id}")
def get_agent_draft(
    draft_id: str,
    user_id: str | None = Depends(current_user_id),
):
    draft = agent_draft_service.get_agent_draft(draft_id, user_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Agent draft not found")

    return ok(draft)


@router.get("/tools")
def list_agent_tools():
    return ok(agent_tool_registry_service.list_tools())


@router.post("/runs")
def create_agent_run(
    payload: AgentRunCreate,
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(payload.goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(
        agent_run_service.create_agent_run(
            goal_id,
            user_id,
            payload.trigger,
            payload.objective,
            payload.decisionMode,
            payload.maxSteps,
        )
    )


@router.get("/runs")
def list_agent_runs(
    goalId: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    if goal_id and not store.get_goal(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    return ok(agent_run_service.list_agent_runs(goal_id, user_id, limit))


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    user_id: str | None = Depends(current_user_id),
):
    agent_run = agent_run_service.get_agent_run(run_id, user_id)
    if not agent_run:
        raise HTTPException(status_code=404, detail="Agent run not found")

    return ok(agent_run)


@router.patch("/runs/{run_id}")
def update_agent_run(
    run_id: str,
    payload: AgentRunUpdate,
    user_id: str | None = Depends(current_user_id),
):
    agent_run = agent_run_service.update_agent_run_status(run_id, payload.status, user_id)
    if not agent_run:
        raise HTTPException(status_code=404, detail="Agent run not found")

    return ok(agent_run)


@router.post("/runs/{run_id}/cancel")
def cancel_agent_run(
    run_id: str,
    user_id: str | None = Depends(current_user_id),
):
    agent_run = agent_run_service.cancel_agent_run(run_id, user_id)
    if not agent_run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return ok(agent_run)


@router.post("/runs/{run_id}/execute")
def execute_agent_run(
    run_id: str,
    payload: AgentRunExecute,
    user_id: str | None = Depends(current_user_id),
):
    agent_run = agent_loop_service.execute_agent_run(run_id, user_id, payload.maxSteps)
    if not agent_run:
        raise HTTPException(status_code=404, detail="Agent run not found")

    return ok(agent_run)


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

    answer = agent_service.answer_and_record(
        question=payload.question,
        goal=goal,
        material_id=material_id,
        limit=payload.limit,
        user_id=user_id,
    )
    return ok(answer)


def _normalize_goal_id(goal_id: str | None) -> str | None:
    return _normalize_id(goal_id)


def _normalize_id(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
