from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.schemas.materials import MaterialCreate, MaterialUpdate
from backend.app.services import material_ai_service, material_store, store
from backend.app.utils.auth import current_user_id
from backend.app.utils.responses import ok


router = APIRouter()


@router.get("")
def list_materials(
    goalId: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
):
    goal_id = _normalize_goal_id(goalId)
    return ok(material_store.list_materials(goal_id, user_id))


@router.post("")
def create_material(payload: MaterialCreate, user_id: str | None = Depends(current_user_id)):
    goal_id = _normalize_goal_id(payload.goalId)
    if goal_id and not store.goal_exists(goal_id, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    now = store.now_iso()
    material = {
        "id": store.make_id("material"),
        "userId": user_id,
        "goalId": goal_id,
        "title": payload.title,
        "type": payload.type,
        "content": payload.content,
        "url": payload.url,
        "createdAt": now,
        "updatedAt": now,
    }
    return ok(material_store.save_material(material))


@router.get("/search")
def search_material_chunks(
    query: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    user_id: str | None = Depends(current_user_id),
):
    return ok(material_store.search_chunks(query, limit, user_id))


@router.get("/{material_id}")
def get_material(material_id: str, user_id: str | None = Depends(current_user_id)):
    material = material_store.get_material(material_id, user_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return ok(material)


@router.put("/{material_id}")
def update_material(
    material_id: str,
    payload: MaterialUpdate,
    user_id: str | None = Depends(current_user_id),
):
    material = material_store.get_material(material_id, user_id)
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
        goal_id = _normalize_goal_id(changes["goalId"])
        if goal_id and not store.goal_exists(goal_id, user_id):
            raise HTTPException(status_code=404, detail="Goal not found")
        changes["goalId"] = goal_id

    if not changes:
        return ok(material)

    next_material = {**material, **changes}
    _validate_material_body(next_material)
    next_material["updatedAt"] = store.now_iso()
    return ok(material_store.save_material(next_material))


@router.delete("/{material_id}")
def delete_material(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.delete_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")
    return ok({"deleted": True, "material_id": material_id})


@router.post("/{material_id}/chunks")
def generate_material_chunks(material_id: str, user_id: str | None = Depends(current_user_id)):
    material = material_store.get_material(material_id, user_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    source_text = material["content"] or material["url"]
    chunk_texts = material_store.split_material_content(source_text)
    now = store.now_iso()
    chunks = [
        {
            "id": store.make_id("chunk"),
            "materialId": material_id,
            "chunkIndex": index,
            "content": chunk,
            "keywords": material_store.extract_keywords(f"{material['title']} {chunk}"),
            "createdAt": now,
            "updatedAt": now,
        }
        for index, chunk in enumerate(chunk_texts)
    ]
    return ok(material_store.replace_chunks_for_material(material_id, chunks))


@router.get("/{material_id}/chunks")
def list_material_chunks(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok(material_store.list_chunks_for_material(material_id))


@router.get("/{material_id}/qa")
def list_material_qa_records(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok(material_store.list_qa_records_for_material(material_id))


@router.post("/{material_id}/summarize")
def summarize_material(material_id: str, user_id: str | None = Depends(current_user_id)):
    material = material_store.get_material(material_id, user_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    now = store.now_iso()
    existing_summary = material_store.get_material_summary(material_id)
    summary = {
        "materialId": material_id,
        **material_ai_service.summarize_material(material),
        "createdAt": existing_summary["createdAt"] if existing_summary else now,
        "updatedAt": now,
    }
    return ok(material_store.save_material_summary(material_id, summary))


@router.get("/{material_id}/summary")
def get_material_summary(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok(material_store.get_material_summary(material_id))


@router.get("/{material_id}/flashcards")
def list_material_flashcards(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok(material_store.list_flashcards_for_material(material_id))


@router.post("/{material_id}/flashcards")
def generate_material_flashcards(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    summary = material_store.get_material_summary(material_id)
    if not summary:
        raise HTTPException(status_code=409, detail="Material summary required")

    now = store.now_iso()
    flashcards = [
        {
            "id": store.make_id("flashcard"),
            "materialId": material_id,
            "front": card["front"],
            "back": card["back"],
            "status": "new",
            "createdAt": now,
            "updatedAt": now,
        }
        for card in material_ai_service.generate_flashcards(summary)
    ]
    return ok(material_store.replace_flashcards_for_material(material_id, flashcards))


@router.get("/{material_id}/quiz")
def list_material_quiz(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    return ok(material_store.list_quiz_questions_for_material(material_id))


@router.post("/{material_id}/quiz")
def generate_material_quiz(material_id: str, user_id: str | None = Depends(current_user_id)):
    if not material_store.get_material(material_id, user_id):
        raise HTTPException(status_code=404, detail="Material not found")

    summary = material_store.get_material_summary(material_id)
    if not summary:
        raise HTTPException(status_code=409, detail="Material summary required")

    now = store.now_iso()
    questions = [
        {
            "id": store.make_id("quiz"),
            "materialId": material_id,
            "question": question["question"],
            "type": question["type"],
            "options": question["options"],
            "answer": question["answer"],
            "explanation": question["explanation"],
            "createdAt": now,
            "updatedAt": now,
        }
        for question in material_ai_service.generate_quiz_questions(summary)
    ]
    return ok(material_store.replace_quiz_questions_for_material(material_id, questions))


def _normalize_goal_id(goal_id: str | None) -> str | None:
    if goal_id is None:
        return None
    return goal_id.strip() or None


def _validate_material_body(material: dict) -> None:
    if material["type"] == "text" and not material["content"].strip():
        raise HTTPException(status_code=422, detail="Text materials require content")
    if material["type"] == "link" and not material["url"].strip():
        raise HTTPException(status_code=422, detail="Link materials require url")
