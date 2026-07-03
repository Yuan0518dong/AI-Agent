from backend.app.services import llm_provider, material_store


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
    if goal:
        matches = [chunk for chunk in matches if chunk["goalId"] == goal["id"]]

    references = [
        {
            "materialId": chunk["materialId"],
            "materialTitle": chunk["materialTitle"],
            "chunkIndex": chunk["chunkIndex"],
            "content": chunk["content"],
            "score": chunk["score"],
        }
        for chunk in matches[:limit]
    ]

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
    }
