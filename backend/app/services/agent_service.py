import re

from backend.app.services import llm_provider, material_store, model_usage_service, store


def answer_question(
    question: str,
    goal: dict | None = None,
    material_id: str | None = None,
    limit: int = 3,
    user_id: str | None = None,
) -> dict:
    matches = material_store.search_chunks(question, limit=20, user_id=user_id)
    if material_id:
        matches = [chunk for chunk in matches if chunk["materialId"] == material_id]
        if not matches:
            matches = _fallback_chunks_for_material(question, material_id, user_id)
    if goal:
        matches = [chunk for chunk in matches if chunk["goalId"] == goal["id"]]

    references = [
        {
            "materialId": chunk["materialId"],
            "materialTitle": chunk["materialTitle"],
            "chunkIndex": chunk["chunkIndex"],
            "content": chunk["content"],
            "score": chunk["score"],
            "searchMode": chunk.get("searchMode", "keyword"),
            "retrievalModes": chunk.get("retrievalModes", [chunk.get("searchMode", "keyword")]),
            "pageNumber": chunk.get("pageNumber"),
            "headingPath": chunk.get("headingPath", ""),
            "paragraphIndex": chunk.get("paragraphIndex"),
        }
        for chunk in matches[:limit]
    ]

    if not references:
        return _insufficient_answer(question, goal, material_id)

    with model_usage_service.user_usage_scope(user_id):
        provider = llm_provider.get_llm_provider()
        generated = provider.generate_answer(
            llm_provider.LLMAnswerContext(
                question=question,
                goal=goal,
                material_id=material_id,
                references=references,
            )
        )
    answer_material_id = material_id or (references[0]["materialId"] if references else None)
    return {
        "id": None,
        "materialId": answer_material_id,
        "goalId": goal["id"] if goal else None,
        "question": question,
        "answer": generated.answer,
        "basis": generated.basis,
        "suggestion": generated.suggestion,
        "sourceTitle": generated.source_title,
        "references": references,
        "isFromMaterial": generated.is_from_material,
        "confidence": generated.confidence,
        "createdAt": None,
        "mode": generated.mode,
        "nextAction": generated.next_action,
        "requiresConfirmation": generated.requires_confirmation,
        "insufficiencyReason": generated.insufficiency_reason,
        "reviewDrafts": generated.review_drafts,
    }


def _insufficient_answer(question: str, goal: dict | None, material_id: str | None) -> dict:
    reason = "没有检索到能够支撑该问题的资料引用。"
    return {
        "id": None,
        "materialId": material_id,
        "goalId": goal["id"] if goal else None,
        "question": question,
        "answer": "当前资料不足以直接回答这个问题。我不会把没有引用的常识当成资料依据。",
        "basis": reason,
        "suggestion": "请补充直接讨论该问题的资料后再提问。",
        "sourceTitle": "",
        "references": [],
        "isFromMaterial": False,
        "confidence": "low",
        "createdAt": None,
        "mode": "grounded-refusal",
        "nextAction": "ask_for_more_material",
        "requiresConfirmation": False,
        "insufficiencyReason": reason,
        "reviewDrafts": [],
    }


def answer_and_record(
    question: str,
    goal: dict | None = None,
    material_id: str | None = None,
    limit: int = 3,
    user_id: str | None = None,
) -> dict:
    answer = answer_question(question, goal, material_id, limit, user_id)
    if not answer["materialId"]:
        return answer

    now = store.now_iso()
    record = {
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
    material_store.save_qa_record(record)
    return {**answer, "id": record["id"], "createdAt": now}


def _fallback_chunks_for_material(
    question: str,
    material_id: str,
    user_id: str | None = None,
) -> list[dict]:
    material = material_store.get_material(material_id, user_id)
    if not material or not _should_use_current_material(question, material):
        return []

    chunks = material_store.list_chunks_for_material(material_id)
    fallback_matches = []
    for chunk in chunks:
        fallback_matches.append(
            {
                **chunk,
                "materialTitle": material["title"],
                "goalId": material["goalId"],
                "score": 1,
                "searchMode": "keyword",
            }
        )
    return fallback_matches


def _should_use_current_material(question: str, material: dict) -> bool:
    normalized_question = _normalize_text(question)
    normalized_title = _normalize_text(material["title"])
    if normalized_title and normalized_title in normalized_question:
        return True

    material_intent_markers = [
        "这份资料",
        "当前资料",
        "本文",
        "这篇",
        "这首",
        "核心内容",
        "主要内容",
        "总结",
        "概括",
        "解释这份",
        "基于资料",
        "复习建议",
        "下一步",
    ]
    return any(_normalize_text(marker) in normalized_question for marker in material_intent_markers)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()
