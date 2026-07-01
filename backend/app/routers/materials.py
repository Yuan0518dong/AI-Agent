from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.materials import MaterialCreate, MaterialUpdate
from backend.app.services import store
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_materials(goalId: str | None = Query(default=None)):
    return ok(store.list_materials(_normalize_goal_id(goalId)))


@router.post("")
def create_material(payload: MaterialCreate):
    goal_id = _normalize_goal_id(payload.goalId)
    if goal_id and not store.get_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    now = store.now_iso()
    material = {
        "id": store.make_id("material"),
        "goal_id": goal_id,
        "title": payload.title,
        "type": payload.type,
        "content": payload.content,
        "url": payload.url,
        "created_at": now,
        "updated_at": now,
    }
    return ok(store.create_material(material))


@router.get("/{material_id}")
def get_material(material_id: str):
    material = store.get_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return ok(material)


@router.put("/{material_id}")
def update_material(material_id: str, payload: MaterialUpdate):
    material = store.get_material(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "type"):
        if changes.get(field) is None:
            changes.pop(field, None)
    for field in ("content", "url"):
        if field in changes and changes[field] is None:
            changes[field] = ""

    if "goalId" in changes:
        goal_id = _normalize_goal_id(changes.pop("goalId"))
        if goal_id and not store.get_goal(goal_id):
            raise HTTPException(status_code=404, detail="Goal not found")
        changes["goal_id"] = goal_id

    if not changes:
        return ok(material)

    _validate_material_body({**material, **_to_response_keys(changes)})
    changes["updated_at"] = store.now_iso()
    updated_material = store.update_material(material_id, changes)
    return ok(updated_material)


@router.delete("/{material_id}")
def delete_material(material_id: str):
    if not store.delete_material(material_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok({"deleted": True, "material_id": material_id})


def _normalize_goal_id(goal_id: str | None) -> str | None:
    if goal_id is None:
        return None

    stripped_goal_id = goal_id.strip()
    return stripped_goal_id or None


def _validate_material_body(material: dict) -> None:
    if material["type"] == "text" and not material["content"].strip():
        raise HTTPException(status_code=422, detail="Text materials require content")
    if material["type"] == "link" and not material["url"].strip():
        raise HTTPException(status_code=422, detail="Link materials require url")


def _to_response_keys(changes: dict) -> dict:
    response_changes = dict(changes)
    if "goal_id" in response_changes:
        response_changes["goalId"] = response_changes.pop("goal_id")
    return response_changes
