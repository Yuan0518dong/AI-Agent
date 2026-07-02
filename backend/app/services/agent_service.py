from backend.app.services import material_store


def answer_question(
    question: str,
    goal: dict | None = None,
    material_id: str | None = None,
    limit: int = 3,
) -> dict:
    matches = material_store.search_chunks(question, limit=20)
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

    if not references:
        suggestion = _build_fallback_suggestion(goal)
        return {
            "id": None,
            "materialId": material_id,
            "goalId": goal["id"] if goal else None,
            "question": question,
            "answer": "当前资料不足以直接回答这个问题。我不会把没有依据的内容当成资料结论。",
            "basis": "没有检索到与问题明显相关的资料片段。",
            "suggestion": suggestion,
            "sourceTitle": "",
            "references": [],
            "isFromMaterial": False,
            "confidence": "low",
            "createdAt": None,
            "mode": "mock",
        }

    context_preview = "；".join(reference["content"] for reference in references)
    basis = _build_basis(references)
    suggestion = _build_material_suggestion(goal)
    answer_material_id = material_id or references[0]["materialId"]
    return {
        "id": None,
        "materialId": answer_material_id,
        "goalId": goal["id"] if goal else None,
        "question": question,
        "answer": f"我先根据已检索到的资料片段回答：{context_preview}",
        "basis": basis,
        "suggestion": suggestion,
        "sourceTitle": references[0]["materialTitle"],
        "references": references,
        "isFromMaterial": True,
        "confidence": _estimate_confidence(references),
        "createdAt": None,
        "mode": "mock",
    }


def _build_basis(references: list[dict]) -> str:
    titles = []
    for reference in references:
        if reference["materialTitle"] not in titles:
            titles.append(reference["materialTitle"])
    return f"依据已检索到的 {len(references)} 个资料片段，来源资料：{'、'.join(titles)}。"


def _build_material_suggestion(goal: dict | None) -> str:
    if not goal:
        return "建议先复述命中的资料片段，再补充一个练习或测试题检查理解。"

    return (
        f"结合你的目标“{goal['name']}”（{goal['subject']}，当前水平：{goal['level']}），"
        f"建议今天用 {goal['daily_minutes']} 分钟先复述资料依据，再整理 1 个待复习问题。"
    )


def _build_fallback_suggestion(goal: dict | None) -> str:
    if not goal:
        return "建议补充更相关的资料，或先为已有资料生成 chunks 后再提问。"

    return (
        f"建议围绕目标“{goal['name']}”补充与问题直接相关的资料，"
        "再重新生成 chunks 后提问。以上只是通用学习建议，不是来自当前资料。"
    )


def _estimate_confidence(references: list[dict]) -> str:
    best_score = max(reference["score"] for reference in references)
    if best_score >= 3:
        return "high"
    return "medium"
