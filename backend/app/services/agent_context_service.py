from collections import Counter

from backend.app.services import (
    agent_draft_service,
    flashcard_review_service,
    material_store,
    progress_service,
    store,
)


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

    due_flashcards = flashcard_review_service.list_due_flashcards(goal_id, user_id)
    review_context = _review_context(material_contexts, due_flashcards)
    quiz_context = _quiz_context(material_contexts)
    qa_context = _qa_context(material_contexts)
    draft_context = _draft_context(goal_id, user_id)

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
            draft_context,
        ),
        "goals": goal_contexts,
        "tasks": task_contexts,
        "materials": material_contexts,
        "qa": qa_context,
        "review": review_context,
        "quiz": quiz_context,
        "drafts": draft_context,
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
    weak_points = material_store.list_weak_points_for_material(material_id, material["title"])

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
        "quizStats": _material_quiz_stats(quiz_questions, quiz_attempts, weak_points),
        "updatedAt": material["updatedAt"],
    }


def _review_context(material_contexts: list[dict], due_flashcards: list[dict]) -> dict:
    totals = Counter()
    for material in material_contexts:
        totals.update(material["flashcardStats"]["byStatus"])

    total = sum(totals.values())
    return {
        "flashcardTotal": total,
        "new": totals.get("new", 0),
        "known": totals.get("known", 0),
        "review": totals.get("review", 0),
        "dueCount": len(due_flashcards),
        "dueFlashcards": [
            {
                "flashcardId": card["id"],
                "materialId": card["materialId"],
                "materialTitle": card["materialTitle"],
                "dueAt": card["dueAt"],
                "reviewCount": card["reviewCount"],
                "retrievability": card["retrievability"],
            }
            for card in due_flashcards[:10]
        ],
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
    weak_points = [
        {
            "materialId": material["id"],
            "title": material["title"],
            **point,
        }
        for material in material_contexts
        for point in material["quizStats"]["weakPoints"]
    ]
    unresolved_weak_points = [point for point in weak_points if not point["resolved"]]
    weak_attempts = [
        {
            "materialId": point["materialId"],
            "title": point["title"],
            "quizId": point["quizId"],
            "score": point["latestScore"],
            "feedback": point["latestFeedback"],
            "suggestion": "",
            "createdAt": point["latestAttemptAt"],
        }
        for point in unresolved_weak_points
    ]

    return {
        "questionTotal": question_total,
        "attemptTotal": attempt_total,
        "weakAttemptCount": len(weak_attempts),
        "weakAttempts": weak_attempts[:5],
        "weakPointCount": len(weak_points),
        "unresolvedWeakPointCount": len(unresolved_weak_points),
        "unresolvedWeakPoints": unresolved_weak_points[:5],
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


def _draft_context(goal_id: str | None, user_id: str | None) -> dict:
    drafts = agent_draft_service.list_agent_drafts(
        user_id=user_id,
        goal_id=goal_id,
        limit=50,
    )
    by_status = Counter(draft["status"] for draft in drafts)
    proposed = [draft for draft in drafts if draft["status"] == "proposed"]
    return {
        "proposedCount": by_status.get("proposed", 0),
        "confirmedCount": by_status.get("confirmed", 0),
        "appliedCount": by_status.get("applied", 0),
        "rejectedCount": by_status.get("rejected", 0),
        "proposed": [
            {
                "id": draft["id"],
                "draftType": draft["draftType"],
                "goalId": draft["goalId"],
                "sourceReason": draft["payload"].get("sourceReason", ""),
                "createdAt": draft["createdAt"],
            }
            for draft in proposed[:20]
        ],
    }


def _summary(
    goal_contexts: list[dict],
    task_contexts: list[dict],
    material_contexts: list[dict],
    review_context: dict,
    quiz_context: dict,
    qa_context: dict,
    draft_context: dict,
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
    if draft_context["proposedCount"]:
        observations.append(f"{draft_context['proposedCount']} draft(s) await confirmation.")
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
        "draftProposedCount": draft_context["proposedCount"],
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


def _material_quiz_stats(questions: list[dict], attempts: list[dict], weak_points: list[dict]) -> dict:
    latest_score = attempts[0]["score"] if attempts else None
    return {
        "questionCount": len(questions),
        "attemptCount": len(attempts),
        "latestScore": latest_score,
        "weakPoints": weak_points,
        "weakAttempts": [
            {
                "quizId": point["quizId"],
                "score": point["latestScore"],
                "feedback": _preview(point["latestFeedback"], 120),
                "suggestion": "",
                "createdAt": point["latestAttemptAt"],
            }
            for point in weak_points
            if not point["resolved"]
        ][:3],
    }


def _preview(text: str, max_chars: int = 120) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3]}..."
