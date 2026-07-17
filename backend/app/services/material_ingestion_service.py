"""Persisted ingestion pipeline for extracted uploads.

Each phase updates the material record before and after work so the UI can show
completed, failed, and retryable stages without retaining the original file.
"""

from __future__ import annotations

from backend.app.services import (
    ai_learning_service,
    material_ai_service,
    material_processing_service,
    material_store,
    store,
)


PROCESSING_STAGES = ("extraction", "chunking", "embedding", "summary", "flashcards", "quiz")
RETRYABLE_STAGES = PROCESSING_STAGES[1:]


def initial_processing_status() -> dict:
    status = {stage: {"status": "pending", "error": ""} for stage in PROCESSING_STAGES}
    status["extraction"] = {"status": "completed", "error": ""}
    return status


def process_upload_pipeline(material_id: str, user_id: str | None) -> dict:
    material = material_store.get_material(material_id, user_id)
    if not material:
        raise LookupError("Material not found")
    for stage in RETRYABLE_STAGES:
        material = _run_stage(material, stage, user_id)
        if _stage_status(material, stage) == "failed":
            return material
    return material


def retry_processing_stage(material_id: str, stage: str, user_id: str | None) -> dict:
    if stage not in RETRYABLE_STAGES:
        raise ValueError("该处理阶段不能单独重试。")
    material = material_store.get_material(material_id, user_id)
    if not material:
        raise LookupError("Material not found")
    return _run_stage(material, stage, user_id)


def _run_stage(material: dict, stage: str, user_id: str | None) -> dict:
    material_store.update_processing_stage(material["id"], stage, "processing", store.now_iso())
    try:
        _execute_stage(material, stage, user_id)
    except Exception as exc:
        message = _safe_stage_error(exc)
        return material_store.update_processing_stage(
            material["id"], stage, "failed", store.now_iso(), message
        ) or material
    return material_store.update_processing_stage(material["id"], stage, "completed", store.now_iso()) or material


def _execute_stage(material: dict, stage: str, user_id: str | None) -> None:
    if stage == "chunking":
        chunks = material_processing_service.build_material_chunks(material)
        if not chunks:
            raise ValueError("未能从资料中生成可检索片段。")
        material_store.replace_chunks_for_material(material["id"], chunks)
        return
    if stage == "embedding":
        chunks = material_store.list_chunks_for_material(material["id"])
        if not chunks:
            raise ValueError("请先完成资料切分。")
        material_processing_service.embed_material_chunks(material, chunks, user_id, strict=True)
        return
    if stage == "summary":
        material_processing_service.summarize_material(material, user_id)
        return
    if stage == "flashcards":
        summary = material_store.get_material_summary(material["id"])
        if not summary:
            raise ValueError("请先完成资料总结。")
        now = store.now_iso()
        flashcards = [
            {
                "id": store.make_id("flashcard"),
                "materialId": material["id"],
                "front": card["front"],
                "back": card["back"],
                "status": "new",
                "createdAt": now,
                "updatedAt": now,
            }
            for card in material_ai_service.generate_flashcards(summary)
        ]
        material_store.replace_flashcards_for_material(material["id"], flashcards)
        return
    if stage == "quiz":
        summary = material_store.get_material_summary(material["id"])
        if not summary:
            raise ValueError("请先完成资料总结。")
        generated = ai_learning_service.generate_quiz_questions(
            material, max(1, len(summary["keyPoints"])), user_id
        )
        now = store.now_iso()
        questions = [
            {
                "id": store.make_id("quiz"),
                "materialId": material["id"],
                "question": question["question"],
                "type": question["type"],
                "options": question["options"],
                "answer": question["answer"],
                "explanation": question["explanation"],
                "createdAt": now,
                "updatedAt": now,
            }
            for question in generated["questions"]
        ]
        material_store.replace_quiz_questions_for_material(material["id"], questions)
        return
    raise ValueError("未知的处理阶段。")


def _stage_status(material: dict, stage: str) -> str:
    value = (material.get("processingStatus") or {}).get(stage, {})
    return str(value.get("status") or "pending")


def _safe_stage_error(exc: Exception) -> str:
    message = str(exc).strip() or "处理失败，请重试。"
    return message[:240]
