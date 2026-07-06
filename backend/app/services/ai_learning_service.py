import json
from datetime import date, timedelta
from typing import Any

from backend.app.services import llm_provider, material_ai_service, material_store, store


def generate_learning_plan(goal: dict, days: int, user_id: str | None = None) -> dict:
    materials = material_store.list_materials(goal_id=goal["id"], user_id=user_id)
    summaries = [
        summary
        for material in materials
        if (summary := material_store.get_material_summary(material["id"]))
    ]
    chunks = []
    for material in materials[:5]:
        chunks.extend(material_store.list_chunks_for_material(material["id"])[:3])

    fallback = _fallback_plan(goal, days, summaries, chunks)
    data = _generate_json(
        system=(
            "You are an AI study planner. Return only JSON. "
            "The JSON shape is {\"tasks\":[{\"day\":1,\"title\":\"...\","
            "\"detail\":\"...\",\"priority\":\"normal\"}],\"mode\":\"...\"}."
        ),
        user=json.dumps(
            {
                "goal": goal,
                "days": days,
                "materialSummaries": summaries[:5],
                "materialChunks": chunks[:10],
                "rules": [
                    "Create exactly the requested number of daily tasks.",
                    "Each task should be concrete and executable in the user's daily_minutes.",
                    "Prefer material-based review, practice, and self-test activities.",
                    "Use Chinese if the goal or material is Chinese.",
                ],
            },
            ensure_ascii=False,
        ),
    )
    tasks = _normalize_plan_tasks(data.get("tasks"), fallback["tasks"], days)
    return {"tasks": tasks, "mode": _result_mode(data, fallback)}


def generate_quiz_questions(material: dict, count: int = 5) -> dict:
    summary = material_store.get_material_summary(material["id"])
    if not summary:
        summary = {
            "materialId": material["id"],
            **material_ai_service.summarize_material(material),
            "createdAt": store.now_iso(),
            "updatedAt": store.now_iso(),
        }
    chunks = material_store.list_chunks_for_material(material["id"])
    if not chunks:
        source_text = material["content"] or material["url"] or material["title"]
        chunks = [
            {
                "content": chunk,
                "chunkIndex": index,
                "keywords": material_store.extract_keywords(chunk),
            }
            for index, chunk in enumerate(material_store.split_material_content(source_text)[:6])
        ]

    fallback = _fallback_quiz(summary, count)
    data = _generate_json(
        system=(
            "You are an AI quiz generator. Return only JSON. "
            "The JSON shape is {\"questions\":[{\"type\":\"short|choice|judge\","
            "\"question\":\"...\",\"options\":[],\"answer\":\"...\",\"explanation\":\"...\"}],"
            "\"mode\":\"...\"}."
        ),
        user=json.dumps(
            {
                "material": {
                    "title": material["title"],
                    "type": material["type"],
                    "contentPreview": (material["content"] or material["url"])[:1600],
                },
                "summary": summary,
                "chunks": chunks[:8],
                "count": count,
                "rules": [
                    "Questions must be answerable from the material.",
                    "Mix short answer, choice, and judge questions when possible.",
                    "Every choice question must include 3-4 options.",
                    "Use Chinese if the material is Chinese.",
                ],
            },
            ensure_ascii=False,
        ),
    )
    questions = _normalize_quiz_questions(data.get("questions"), fallback["questions"], count)
    return {"questions": questions, "mode": _result_mode(data, fallback)}


def grade_quiz_answer(question: dict, user_answer: str) -> dict:
    fallback = _fallback_grade(question, user_answer)
    data = _generate_json(
        system=(
            "You are an AI quiz grader. Return only JSON. "
            "The JSON shape is {\"isCorrect\":true,\"score\":0-100,"
            "\"feedback\":\"...\",\"suggestion\":\"...\"}."
        ),
        user=json.dumps(
            {
                "question": question["question"],
                "type": question["type"],
                "options": question.get("options", []),
                "referenceAnswer": question["answer"],
                "explanation": question["explanation"],
                "userAnswer": user_answer,
                "rules": [
                    "For short answers, allow paraphrases if the core meaning is correct.",
                    "Give concise feedback and one next action.",
                    "Use Chinese if the question or user answer is Chinese.",
                ],
            },
            ensure_ascii=False,
        ),
    )
    return {
        "isCorrect": _as_bool(data.get("isCorrect"), fallback["isCorrect"]),
        "score": _clamp_int(data.get("score"), fallback["score"], 0, 100),
        "feedback": _text(data.get("feedback"), fallback["feedback"]),
        "suggestion": _text(data.get("suggestion"), fallback["suggestion"]),
        "mode": _result_mode(data, fallback),
    }


def _generate_json(system: str, user: str) -> dict[str, Any]:
    provider = llm_provider.get_llm_provider()
    if not isinstance(provider, llm_provider.OpenAICompatibleLLMProvider):
        return {}

    try:
        result = provider._post_chat_completion(
            {
                "model": provider.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        )
        content = result["choices"][0]["message"]["content"]
        parsed = llm_provider._parse_model_json(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _fallback_plan(goal: dict, days: int, summaries: list[dict], chunks: list[dict]) -> dict:
    topics = []
    for summary in summaries:
        topics.extend(summary.get("keyPoints", []))
    topics.extend(chunk.get("content", "")[:48] for chunk in chunks)
    topics.extend([goal.get("subject", ""), goal.get("notes", "")])
    topics = [topic.strip()[:40] for topic in topics if topic and topic.strip()]
    if not topics:
        topics = ["core topic"]

    tasks = []
    for index in range(days):
        topic = topics[index % len(topics)]
        tasks.append(
            {
                "day": index + 1,
                "title": f"Day {index + 1}: Learn {topic}",
                "detail": (
                    f"Study {topic} for {goal['daily_minutes']} minutes, "
                    "then write a 3-sentence recap and complete one self-test."
                ),
                "priority": "normal",
            }
        )
    return {"tasks": tasks, "mode": "mock"}


def _fallback_quiz(summary: dict, count: int) -> dict:
    questions = material_ai_service.generate_quiz_questions(summary)
    if not questions:
        questions = [
            {
                "type": "short",
                "question": "What is the core idea of this material?",
                "options": [],
                "answer": "Summarize the main concept and support it with one detail from the material.",
                "explanation": "This checks whether the learner can restate the material.",
            }
        ]
    while len(questions) < count:
        questions.append(questions[len(questions) % len(questions)].copy())
    return {"questions": questions[:count], "mode": "mock"}


def _fallback_grade(question: dict, user_answer: str) -> dict:
    expected = str(question["answer"]).strip().lower()
    actual = user_answer.strip().lower()
    is_correct = bool(actual) and (actual in expected or expected in actual)
    score = 90 if is_correct else 40
    return {
        "isCorrect": is_correct,
        "score": score,
        "feedback": "回答与参考答案基本一致。" if is_correct else "回答还不完整，和参考答案相比缺少关键信息。",
        "suggestion": question.get("explanation") or "回到原资料复习后再尝试作答。",
        "mode": "mock",
    }


def _normalize_plan_tasks(raw_tasks: Any, fallback_tasks: list[dict], days: int) -> list[dict]:
    if not isinstance(raw_tasks, list):
        raw_tasks = []
    normalized = []
    for index, raw in enumerate(raw_tasks[:days]):
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"), "")
        detail = _text(raw.get("detail"), "")
        if not title or not detail:
            continue
        normalized.append(
            {
                "day": _clamp_int(raw.get("day"), index + 1, 1, days),
                "title": title[:120],
                "detail": detail[:500],
                "priority": _priority(raw.get("priority")),
            }
        )
    if len(normalized) < days:
        normalized.extend(fallback_tasks[len(normalized) : days])
    return normalized[:days]


def _normalize_quiz_questions(raw_questions: Any, fallback_questions: list[dict], count: int) -> list[dict]:
    if not isinstance(raw_questions, list):
        raw_questions = []
    normalized = []
    for raw in raw_questions[:count]:
        if not isinstance(raw, dict):
            continue
        question = _text(raw.get("question"), "")
        answer = _text(raw.get("answer"), "")
        explanation = _text(raw.get("explanation"), "")
        if not question or not answer:
            continue
        question_type = str(raw.get("type") or "short").lower()
        if question_type not in {"short", "choice", "judge"}:
            question_type = "short"
        options = raw.get("options") if isinstance(raw.get("options"), list) else []
        normalized.append(
            {
                "type": question_type,
                "question": question[:300],
                "options": [str(option)[:160] for option in options[:4]],
                "answer": answer[:500],
                "explanation": explanation[:500] or "Review the related material and compare with the reference answer.",
            }
        )
    if len(normalized) < count:
        normalized.extend(fallback_questions[len(normalized) : count])
    return normalized[:count]


def _current_mode() -> str:
    return getattr(llm_provider.get_llm_provider(), "mode", "mock")


def _result_mode(data: dict[str, Any], fallback: dict) -> str:
    if data:
        return str(data.get("mode") or data.get("provider") or _current_mode())
    return str(fallback.get("mode") or "mock")


def _priority(value: Any) -> str:
    return str(value).lower() if str(value).lower() in {"low", "normal", "high"} else "normal"


def _text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _as_bool(value: Any, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _clamp_int(value: Any, fallback: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(min_value, min(max_value, number))
