from collections import Counter

from backend.app.services import material_store, progress_service, store


def build_agent_context(
    goal_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    goals = _select_goals(goal_id, user_id)
    goal_ids = {goal["id"] for goal in goals}
    materials = [
        material
        for material in material_store.list_materials(user_id=user_id)
        if not goal_ids or material["goalId"] in goal_ids
    ]

    goal_contexts = [_goal_context(goal, materials) for goal in goals]
    material_contexts = [_material_context(material) for material in materials]
    task_contexts = [_task_context(goal) for goal in goals]
    progress_contexts = [
        progress_service.get_goal_progress(goal["id"], user_id) for goal in goals
    ]

    review_context = _review_context(material_contexts)
    quiz_context = _quiz_context(material_contexts)
    qa_context = _qa_context(material_contexts)

    return {
        "generatedAt": store.now_iso(),
        "scope": {
            "goalId": goal_id,
            "goalCount": len(goals),
            "materialCount": len(materials),
        },
        "summary": _summary(
            goal_contexts,
            task_contexts,
            material_contexts,
            review_context,
            quiz_context,
            qa_context,
        ),
        "goals": goal_contexts,
        "tasks": task_contexts,
        "materials": material_contexts,
        "qa": qa_context,
        "review": review_context,
        "quiz": quiz_context,
        "progress": progress_contexts,
    }


def _select_goals(goal_id: str | None, user_id: str | None) -> list[dict]:
    if goal_id:
        goal = store.get_goal(goal_id, user_id)
        return [goal] if goal else []
    return store.list_goals(user_id)


def _goal_context(goal: dict, materials: list[dict]) -> dict:
    goal_materials = [material for material in materials if material["goalId"] == goal["id"]]
    return {
        "id": goal["id"],
        "name": goal["name"],
        "subject": goal["subject"],
        "level": goal["level"],
        "deadline": goal["deadline"],
        "dailyMinutes": goal["daily_minutes"],
        "notes": goal["notes"],
        "materialCount": len(goal_materials),
    }


def _task_context(goal: dict) -> dict:
    tasks = store.list_goal_tasks(goal["id"])
    today = store.today_iso()
    open_tasks = [task for task in tasks if not task["done"]]
    overdue_tasks = [task for task in open_tasks if task["date"] < today]
    today_tasks = [task for task in tasks if task["date"] == today]
    completed_tasks = [task for task in tasks if task["done"]]

    return {
        "goalId": goal["id"],
        "goalName": goal["name"],
        "total": len(tasks),
        "completed": len(completed_tasks),
        "open": len(open_tasks),
        "todayTotal": len(today_tasks),
        "todayCompleted": len([task for task in today_tasks if task["done"]]),
        "overdue": len(overdue_tasks),
        "today": [_task_item(task) for task in today_tasks],
        "overdueItems": [_task_item(task) for task in overdue_tasks[:5]],
        "nextOpen": [_task_item(task) for task in open_tasks[:5]],
    }


def _material_context(material: dict) -> dict:
    material_id = material["id"]
    summary = material_store.get_material_summary(material_id)
    chunks = material_store.list_chunks_for_material(material_id)
    qa_records = material_store.list_qa_records_for_material(material_id)
    flashcards = material_store.list_flashcards_for_material(material_id)
    quiz_questions = material_store.list_quiz_questions_for_material(material_id)
    quiz_attempts = material_store.list_quiz_attempts_for_material(material_id)

    return {
        "id": material_id,
        "goalId": material["goalId"],
        "title": material["title"],
        "type": material["type"],
        "contentPreview": _preview(material["content"] or material["url"]),
        "hasSummary": summary is not None,
        "summary": _summary_item(summary),
        "chunkCount": len(chunks),
        "qaCount": len(qa_records),
        "recentQa": [_qa_item(record) for record in qa_records[-3:]],
        "flashcardStats": _flashcard_stats(flashcards),
        "quizStats": _material_quiz_stats(quiz_questions, quiz_attempts),
        "updatedAt": material["updatedAt"],
    }


def _review_context(material_contexts: list[dict]) -> dict:
    totals = Counter()
    for material in material_contexts:
        totals.update(material["flashcardStats"]["byStatus"])

    total = sum(totals.values())
    return {
        "flashcardTotal": total,
        "new": totals.get("new", 0),
        "known": totals.get("known", 0),
        "review": totals.get("review", 0),
        "materialsNeedingReview": [
            {
                "materialId": material["id"],
                "title": material["title"],
                "reviewCount": material["flashcardStats"]["byStatus"].get("review", 0),
                "newCount": material["flashcardStats"]["byStatus"].get("new", 0),
            }
            for material in material_contexts
            if material["flashcardStats"]["byStatus"].get("review", 0)
            or material["flashcardStats"]["byStatus"].get("new", 0)
        ],
    }


def _quiz_context(material_contexts: list[dict]) -> dict:
    question_total = sum(material["quizStats"]["questionCount"] for material in material_contexts)
    attempt_total = sum(material["quizStats"]["attemptCount"] for material in material_contexts)
    weak_attempts = [
        {
            "materialId": material["id"],
            "title": material["title"],
            **attempt,
        }
        for material in material_contexts
        for attempt in material["quizStats"]["weakAttempts"]
    ]

    return {
        "questionTotal": question_total,
        "attemptTotal": attempt_total,
        "weakAttemptCount": len(weak_attempts),
        "weakAttempts": weak_attempts[:5],
    }


def _qa_context(material_contexts: list[dict]) -> dict:
    qa_records = [
        {
            "materialId": material["id"],
            "materialTitle": material["title"],
            **record,
        }
        for material in material_contexts
        for record in material["recentQa"]
    ]
    insufficiencies = [
        record
        for record in qa_records
        if record["nextAction"] == "ask_for_more_material" or record["insufficiencyReason"]
    ]

    return {
        "recentCount": len(qa_records),
        "recent": qa_records[-10:],
        "insufficiencyCount": len(insufficiencies),
        "insufficiencies": insufficiencies[-5:],
    }


def _summary(
    goal_contexts: list[dict],
    task_contexts: list[dict],
    material_contexts: list[dict],
    review_context: dict,
    quiz_context: dict,
    qa_context: dict,
) -> dict:
    total_tasks = sum(item["total"] for item in task_contexts)
    completed_tasks = sum(item["completed"] for item in task_contexts)
    overdue_tasks = sum(item["overdue"] for item in task_contexts)
    materials_without_chunks = [
        material["id"] for material in material_contexts if material["chunkCount"] == 0
    ]
    materials_without_summary = [
        material["id"] for material in material_contexts if not material["hasSummary"]
    ]

    observations = []
    if overdue_tasks:
        observations.append(f"{overdue_tasks} open task(s) are overdue.")
    if materials_without_chunks:
        observations.append(f"{len(materials_without_chunks)} material(s) have no chunks yet.")
    if materials_without_summary:
        observations.append(f"{len(materials_without_summary)} material(s) have no summary yet.")
    if review_context["review"] or review_context["new"]:
        observations.append("Flashcards are waiting for review.")
    if quiz_context["weakAttemptCount"]:
        observations.append("Recent quiz attempts show weak points.")
    if qa_context["insufficiencyCount"]:
        observations.append("Some questions were marked as material-insufficient.")
    if not observations:
        observations.append("Learning context is ready for the next Agent decision.")

    return {
        "goalCount": len(goal_contexts),
        "taskTotal": total_tasks,
        "taskCompleted": completed_tasks,
        "taskOpen": total_tasks - completed_tasks,
        "taskOverdue": overdue_tasks,
        "materialTotal": len(material_contexts),
        "materialsWithoutChunks": len(materials_without_chunks),
        "materialsWithoutSummary": len(materials_without_summary),
        "flashcardTotal": review_context["flashcardTotal"],
        "quizQuestionTotal": quiz_context["questionTotal"],
        "quizWeakAttemptCount": quiz_context["weakAttemptCount"],
        "qaInsufficiencyCount": qa_context["insufficiencyCount"],
        "observations": observations,
    }


def _task_item(task: dict) -> dict:
    return {
        "id": task["id"],
        "goalId": task["goal_id"],
        "title": task["title"],
        "detail": task["detail"],
        "date": task["date"],
        "priority": task["priority"],
        "done": task["done"],
        "completedAt": task["completed_at"],
    }


def _summary_item(summary: dict | None) -> dict | None:
    if not summary:
        return None
    return {
        "overview": summary["overview"],
        "keyPoints": summary["keyPoints"][:5],
        "difficulties": summary["difficulties"][:5],
        "studyOrder": summary["studyOrder"][:5],
        "actionItems": summary["actionItems"][:5],
        "aiMode": summary["aiMode"],
        "updatedAt": summary["updatedAt"],
    }


def _qa_item(record: dict) -> dict:
    return {
        "id": record["id"],
        "question": record["question"],
        "answer": _preview(record["answer"], 160),
        "confidence": record["confidence"],
        "mode": record["mode"],
        "nextAction": record["nextAction"],
        "requiresConfirmation": record["requiresConfirmation"],
        "insufficiencyReason": record["insufficiencyReason"],
        "reviewDraftCount": len(record["reviewDrafts"]),
        "createdAt": record["createdAt"],
    }


def _flashcard_stats(flashcards: list[dict]) -> dict:
    by_status = Counter(card["status"] for card in flashcards)
    return {
        "total": len(flashcards),
        "byStatus": {
            "new": by_status.get("new", 0),
            "known": by_status.get("known", 0),
            "review": by_status.get("review", 0),
        },
    }


def _material_quiz_stats(questions: list[dict], attempts: list[dict]) -> dict:
    weak_attempts = [
        {
            "quizId": attempt["quizId"],
            "score": attempt["score"],
            "feedback": _preview(attempt["feedback"], 120),
            "suggestion": _preview(attempt["suggestion"], 120),
            "createdAt": attempt["createdAt"],
        }
        for attempt in attempts
        if attempt["score"] < 60 or not attempt["isCorrect"]
    ]
    latest_score = attempts[0]["score"] if attempts else None
    return {
        "questionCount": len(questions),
        "attemptCount": len(attempts),
        "latestScore": latest_score,
        "weakAttempts": weak_attempts[:3],
    }


def _preview(text: str, max_chars: int = 120) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3]}..."
