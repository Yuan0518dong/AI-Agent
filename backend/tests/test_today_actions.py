from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import (
    agent_context_service,
    agent_draft_service,
    agent_loop_service,
    flashcard_review_service,
    material_store,
    store,
)
from backend.tests.auth_helpers import register_session


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client.cookies.clear()
    store.set_db_path(tmp_path / "today_actions.db")
    store.reset()
    user = register_session(client, email="today-owner@example.com", name="Today Owner")
    yield user
    client.cookies.clear()
    store.reset()


def create_goal(name: str = "Today Actions Goal") -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": name,
            "subject": "可靠学习流程",
            "level": "basic",
            "deadline": "2026-12-31",
            "daily_minutes": 30,
            "notes": "Today Actions fixture",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def create_material(goal_id: str, title: str = "Today Actions Material") -> dict:
    response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "title": title,
            "type": "text",
            "content": "Today Actions uses a bounded, deterministic read model.",
            "url": "",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def create_task(goal_id: str, task_id: str, target_date: str, priority: str) -> None:
    timestamp = store.now_iso()
    store.create_task(
        {
            "id": task_id,
            "goal_id": goal_id,
            "title": f"{task_id} title",
            "detail": f"{task_id} detail",
            "date": target_date,
            "priority": priority,
            "done": False,
            "completed_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )


def create_due_flashcards(material_id: str, *flashcard_ids: str) -> None:
    scheduled_at = store.now_iso()
    for flashcard_id in flashcard_ids:
        flashcard_review_service.create_flashcard_for_material(
            flashcard_review_service.new_scheduled_flashcard(
                material_id=material_id,
                front=f"Question {flashcard_id}",
                back="Answer",
                flashcard_id=flashcard_id,
                now=scheduled_at,
            )
        )


def create_unresolved_weak_points(material: dict, *quiz_ids: str) -> None:
    now = store.now_iso()
    questions = [
        {
            "id": quiz_id,
            "materialId": material["id"],
            "question": f"Question {quiz_id}",
            "type": "short-answer",
            "options": [],
            "answer": "Expected answer",
            "explanation": "Weak-point fixture.",
            "createdAt": now,
            "updatedAt": now,
        }
        for quiz_id in quiz_ids
    ]
    material_store.replace_quiz_questions_for_material(material["id"], questions)
    for quiz_id in quiz_ids:
        material_store.save_quiz_attempt(
            {
                "id": f"attempt-{quiz_id}",
                "quizId": quiz_id,
                "materialId": material["id"],
                "userAnswer": "Incorrect answer",
                "isCorrect": False,
                "score": 40,
                "feedback": "Review this point.",
                "suggestion": "Return to the material.",
                "mode": "mock",
                "createdAt": "2026-01-02T00:00:00+00:00",
            }
        )


def create_proposed_drafts(user: dict, goal_id: str, material_id: str, *draft_ids: str) -> None:
    run_id = "today-actions-run"
    now = store.now_iso()
    user_id = store.get_user_by_email(user["email"])["id"]
    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                id, user_id, goal_id, trigger, objective, decision_mode, max_steps,
                current_step, context_snapshot, decision_snapshot, feedback_summary,
                status, stop_reason, error, created_at, updated_at
            ) VALUES (?, ?, ?, 'manual', 'Today Actions fixture', 'rule-based', 4,
                      1, '{}', '{}', '{}', 'waiting_confirmation', '', '', ?, ?)
            """,
            (run_id, user_id, goal_id, now, now),
        )
    step_id = agent_loop_service._insert_step(
        {"id": run_id},
        1,
        {},
        {},
        {"toolName": "create_review_draft", "payload": {"materialIds": [material_id]}},
        {},
        "waiting_confirmation",
        step_id="today-actions-step",
    )
    for draft_id in draft_ids:
        drafts, _, _ = agent_draft_service.create_or_reuse_drafts(
            draft_type="review",
            payloads=[{"materialId": material_id, "front": draft_id, "back": "Answer"}],
            user_id=user_id,
            goal_id=goal_id,
            run_id=run_id,
            step_id=step_id,
            tool_name="create_review_draft",
        )
        with store.db_connection() as conn:
            conn.execute("UPDATE agent_drafts SET id = ? WHERE id = ?", (draft_id, drafts[0]["id"]))


def test_today_actions_has_five_stable_categories_and_lightweight_fields(clean_store):
    user = clean_store
    goal = create_goal()
    material = create_material(goal["id"])
    today = date.today()
    create_task(goal["id"], "overdue-b", (today - timedelta(days=2)).isoformat(), "normal")
    create_task(goal["id"], "overdue-a", (today - timedelta(days=2)).isoformat(), "high")
    create_task(goal["id"], "today-b", today.isoformat(), "high")
    create_task(goal["id"], "today-a", today.isoformat(), "high")
    create_due_flashcards(material["id"], "flashcard-b", "flashcard-a")
    create_unresolved_weak_points(material, "quiz-b", "quiz-a")
    create_proposed_drafts(user, goal["id"], material["id"], "draft-b", "draft-a")
    with store.db_connection() as conn:
        conn.execute("UPDATE agent_drafts SET created_at = ? WHERE id = ?", ("2026-01-02T00:00:00+00:00", "draft-b"))
        conn.execute("UPDATE agent_drafts SET created_at = ? WHERE id = ?", ("2026-01-01T00:00:00+00:00", "draft-a"))

    response = client.get("/api/today/actions")
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["date"] == today.isoformat()
    assert [item["kind"] for item in payload["items"]] == [
        "overdue_task",
        "overdue_task",
        "today_task",
        "today_task",
        "due_flashcard",
        "due_flashcard",
        "weak_point",
        "weak_point",
        "pending_confirmation",
        "pending_confirmation",
    ]
    assert [item["id"] for item in payload["items"] if item["kind"] == "overdue_task"] == ["overdue-a", "overdue-b"]
    assert [item["id"] for item in payload["items"] if item["kind"] == "today_task"] == ["today-a", "today-b"]
    assert [item["id"] for item in payload["items"] if item["kind"] == "due_flashcard"] == ["flashcard-a", "flashcard-b"]
    assert [item["id"] for item in payload["items"] if item["kind"] == "weak_point"] == ["quiz-a", "quiz-b"]
    assert [item["id"] for item in payload["items"] if item["kind"] == "pending_confirmation"] == ["draft-a", "draft-b"]
    assert payload["categoryCounts"] == {
        "overdue_task": 2,
        "today_task": 2,
        "due_flashcard": 2,
        "weak_point": 2,
        "pending_confirmation": 2,
    }
    assert all("payload" not in item and "front" not in item and "back" not in item for item in payload["items"])
    assert all("fsrsCard" not in item and "content" not in item for item in payload["items"])
    assert payload["items"][0]["target"] == {"view": "goals", "taskId": "overdue-a"}
    assert payload["items"][4]["target"] == {
        "view": "memory",
        "materialId": material["id"],
        "flashcardId": "flashcard-a",
    }
    assert payload["items"][6]["target"] == {
        "view": "memory",
        "materialId": material["id"],
        "quizId": "quiz-a",
    }
    assert payload["items"][8]["target"]["runId"] == "today-actions-run"


def test_today_actions_limits_each_category_and_then_applies_global_limit(clean_store):
    goal = create_goal()
    today = date.today()
    for index in range(4):
        create_task(goal["id"], f"overdue-{index}", (today - timedelta(days=1)).isoformat(), "normal")
        create_task(goal["id"], f"today-{index}", today.isoformat(), "normal")

    response = client.get("/api/today/actions", params={"limit": 4})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["categoryCounts"]["overdue_task"] == 3
    assert payload["categoryCounts"]["today_task"] == 3
    assert [item["kind"] for item in payload["items"]] == [
        "overdue_task",
        "overdue_task",
        "overdue_task",
        "today_task",
    ]
    assert client.get("/api/today/actions", params={"limit": 0}).status_code == 422
    assert client.get("/api/today/actions", params={"limit": 16}).status_code == 422


def test_today_actions_caps_review_weak_point_and_confirmation_categories(clean_store):
    user = clean_store
    goal = create_goal()
    material = create_material(goal["id"])
    create_due_flashcards(material["id"], "flashcard-4", "flashcard-3", "flashcard-2", "flashcard-1")
    create_unresolved_weak_points(material, "quiz-4", "quiz-3", "quiz-2", "quiz-1")
    create_proposed_drafts(user, goal["id"], material["id"], "draft-4", "draft-3", "draft-2", "draft-1")
    with store.db_connection() as conn:
        for index, draft_id in enumerate(("draft-3", "draft-2", "draft-1"), start=1):
            conn.execute(
                "UPDATE agent_drafts SET created_at = ? WHERE id = ?",
                (f"2026-01-0{index}T00:00:00+00:00", draft_id),
            )
        conn.execute("UPDATE agent_drafts SET created_at = ? WHERE id = ?", ("not-a-time", "draft-4"))

    response = client.get("/api/today/actions", params={"limit": 15})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["categoryCounts"] == {
        "overdue_task": 0,
        "today_task": 0,
        "due_flashcard": 3,
        "weak_point": 3,
        "pending_confirmation": 3,
    }
    assert [item["id"] for item in payload["items"] if item["kind"] == "due_flashcard"] == [
        "flashcard-1",
        "flashcard-2",
        "flashcard-3",
    ]
    assert [item["id"] for item in payload["items"] if item["kind"] == "weak_point"] == [
        "quiz-1",
        "quiz-2",
        "quiz-3",
    ]
    assert [item["id"] for item in payload["items"] if item["kind"] == "pending_confirmation"] == [
        "draft-3",
        "draft-2",
        "draft-1",
    ]


def test_today_actions_is_user_scoped_and_never_builds_agent_context(clean_store, monkeypatch):
    goal = create_goal()
    create_task(goal["id"], "owner-today", date.today().isoformat(), "high")

    def context_must_not_run(*_args, **_kwargs):
        raise AssertionError("Today Actions must not build Agent Context")

    monkeypatch.setattr(agent_context_service, "build_agent_context", context_must_not_run)
    owner = client.get("/api/today/actions")
    assert owner.status_code == 200
    assert [item["id"] for item in owner.json()["data"]["items"]] == ["owner-today"]

    other_client = TestClient(app)
    try:
        register_session(other_client, email="today-other@example.com", name="Today Other")
        other = other_client.get("/api/today/actions")
        assert other.status_code == 200
        assert other.json()["data"]["items"] == []
    finally:
        other_client.close()
