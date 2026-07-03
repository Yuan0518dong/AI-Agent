from fastapi import APIRouter, HTTPException

from backend.app.schemas.agent import AgentAskRequest
from backend.app.services import agent_service, material_store, store
from backend.app.utils.responses import ok


router = APIRouter()


@router.post("/ask")
def ask_agent(payload: AgentAskRequest):
    goal_id = _normalize_goal_id(payload.goalId)
    material_id = _normalize_id(payload.materialId)
    material = material_store.get_material(material_id) if material_id else None
    if material_id and not material:
        raise HTTPException(status_code=404, detail="Material not found")

    if material and goal_id and material["goalId"] and material["goalId"] != goal_id:
        raise HTTPException(status_code=400, detail="Material does not belong to goal")

    goal_context_id = goal_id or (material["goalId"] if material else None)
    goal = store.get_goal(goal_context_id) if goal_context_id else None
    if goal_context_id and not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    answer = agent_service.answer_question(
        question=payload.question,
        goal=goal,
        material_id=material_id,
        limit=payload.limit,
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
