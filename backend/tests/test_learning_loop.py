from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from fsrs import Card

from backend.app.main import app
from backend.app.services import material_store, store
from backend.tests.auth_helpers import copy_session_cookie, register_session


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client.cookies.clear()
    store.set_db_path(tmp_path / "learning_loop.db")
    store.reset()
    register_session(client, email="loop-default@example.com", name="Learning Loop")
    yield
    client.cookies.clear()
    store.reset()


def create_goal() -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": "Learning loop goal",
            "subject": "Spaced repetition",
            "level": "basic",
            "deadline": "2026-12-31",
            "daily_minutes": 30,
            "notes": "FSRS review loop coverage",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_material(goal_id: str) -> dict:
    response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "title": "Review material",
            "type": "text",
            "content": "A review schedule uses a source-of-truth card and a due-date projection.",
            "url": "",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_flashcard(material_id: str) -> dict:
    response = client.post(
        f"/api/materials/{material_id}/flashcards/custom",
        json={"front": "What is the schedule source?", "back": "The FSRS card JSON."},
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.parametrize(
    ("rating", "expected_status"),
    [("again", "review"), ("hard", "review"), ("good", "known"), ("easy", "known")],
)
def test_fsrs_rating_keeps_atomic_schedule_projection(rating: str, expected_status: str):
    goal = create_goal()
    material = create_material(goal["id"])
    flashcard = create_flashcard(material["id"])

    initial_card = Card.from_json(flashcard["fsrsCard"])
    assert flashcard["dueAt"] == initial_card.due.isoformat()
    assert flashcard["reviewCount"] == 0
    assert flashcard["lastReviewedAt"] is None
    assert flashcard["lastRating"] is None

    response = client.post(
        f"/api/materials/{material['id']}/flashcards/{flashcard['id']}/reviews",
        json={"rating": rating},
    )
    assert response.status_code == 200
    reviewed = response.json()["data"]
    assert reviewed["flashcardId"] == flashcard["id"]
    assert reviewed["status"] == expected_status
    assert reviewed["reviewCount"] == 1
    assert reviewed["lastRating"] == rating
    assert reviewed["lastReviewedAt"]
    assert isinstance(reviewed["retrievability"], float)

    stored = client.get(f"/api/materials/{material['id']}/flashcards").json()["data"][0]
    assert stored["status"] == expected_status
    assert stored["reviewCount"] == 1
    assert stored["lastRating"] == rating
    assert stored["dueAt"] == Card.from_json(stored["fsrsCard"]).due.isoformat()
    assert Card.from_json(stored["fsrsCard"]).due.tzinfo is not None


def test_legacy_status_delegates_without_erasing_review_history():
    goal = create_goal()
    material = create_material(goal["id"])
    fresh = create_flashcard(material["id"])

    unchanged = client.patch(
        f"/api/materials/{material['id']}/flashcards/{fresh['id']}",
        json={"status": "new"},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["data"]["reviewCount"] == 0

    known = client.patch(
        f"/api/materials/{material['id']}/flashcards/{fresh['id']}",
        json={"status": "known"},
    )
    assert known.status_code == 200
    assert known.json()["data"]["status"] == "known"
    assert known.json()["data"]["lastRating"] == "good"
    assert known.json()["data"]["reviewCount"] == 1

    reset = client.patch(
        f"/api/materials/{material['id']}/flashcards/{fresh['id']}",
        json={"status": "new"},
    )
    assert reset.status_code == 409
    assert reset.json()["error"]["message"] == "flashcard_review_history_exists"


def test_bulk_generated_flashcards_start_with_complete_schedules():
    goal = create_goal()
    material = create_material(goal["id"])
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    generated = client.post(f"/api/materials/{material['id']}/flashcards")
    assert generated.status_code == 200
    assert generated.json()["data"]
    for card in generated.json()["data"]:
        assert card["status"] == "new"
        assert card["reviewCount"] == 0
        assert card["lastReviewedAt"] is None
        assert card["lastRating"] is None
        assert card["retrievability"] is None
        assert card["dueAt"] == Card.from_json(card["fsrsCard"]).due.isoformat()


def test_invalid_fsrs_json_is_rejected_without_resetting_state():
    goal = create_goal()
    material = create_material(goal["id"])
    flashcard = create_flashcard(material["id"])
    with store.db_connection() as conn:
        conn.execute(
            "UPDATE flashcards SET fsrs_card = ? WHERE id = ?",
            ("{not-json", flashcard["id"]),
        )

    response = client.post(
        f"/api/materials/{material['id']}/flashcards/{flashcard['id']}/reviews",
        json={"rating": "good"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["type"] == "flashcard_schedule_invalid"
    assert response.json()["error"]["message"] == "flashcard_schedule_invalid"
    with store.db_connection() as conn:
        persisted = conn.execute(
            "SELECT fsrs_card, review_count, status FROM flashcards WHERE id = ?",
            (flashcard["id"],),
        ).fetchone()
    assert persisted["fsrs_card"] == "{not-json"
    assert persisted["review_count"] == 0
    assert persisted["status"] == "new"


def test_sqlite_legacy_flashcard_initializes_due_now_without_fabricating_history():
    goal = create_goal()
    material = create_material(goal["id"])
    flashcard = create_flashcard(material["id"])
    with store.db_connection() as conn:
        conn.execute(
            """
            UPDATE flashcards
            SET status = 'known', fsrs_card = '', due_at = '', last_reviewed_at = ?,
                review_count = 12, last_rating = 'easy'
            WHERE id = ?
            """,
            (store.now_iso(), flashcard["id"]),
        )

    material_store.init_db()
    restored = material_store.get_flashcard(material["id"], flashcard["id"])
    restored_card = Card.from_json(restored["fsrsCard"])
    assert restored["status"] == "new"
    assert restored["reviewCount"] == 0
    assert restored["lastReviewedAt"] is None
    assert restored["lastRating"] is None
    assert restored["dueAt"] == restored_card.due.isoformat()
    assert restored_card.due <= datetime.now(timezone.utc)


def test_due_queue_is_goal_and_user_scoped_and_export_preserves_schedule():
    goal = create_goal()
    material = create_material(goal["id"])
    flashcard = create_flashcard(material["id"])

    queue = client.get("/api/review/queue", params={"goalId": goal["id"]})
    assert queue.status_code == 200
    queued = queue.json()["data"]
    assert [card["id"] for card in queued] == [flashcard["id"]]
    assert queued[0]["goalId"] == goal["id"]
    assert queued[0]["retrievability"] is None

    exported = client.get("/api/auth/export")
    assert exported.status_code == 200
    exported_card = exported.json()["data"]["flashcards"][0]
    assert exported_card["fsrs_card"]["due"] == flashcard["dueAt"]
    assert exported_card["review_count"] == 0

    other_client = TestClient(app)
    try:
        register_session(other_client, email="loop-other@example.com", name="Other User")
        forbidden = other_client.get("/api/review/queue", params={"goalId": goal["id"]})
        assert forbidden.status_code == 404
        all_other = other_client.get("/api/review/queue")
        assert all_other.status_code == 200
        assert all_other.json()["data"] == []
    finally:
        other_client.close()


def test_weak_points_are_derived_and_quiz_history_cannot_be_replaced():
    goal = create_goal()
    material = create_material(goal["id"])
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    question = {
        "id": store.make_id("quiz"),
        "materialId": material["id"],
        "question": "What must be preserved?",
        "type": "short-answer",
        "options": [],
        "answer": "Quiz attempts",
        "explanation": "Attempts are the weak-point source.",
        "createdAt": store.now_iso(),
        "updatedAt": store.now_iso(),
    }
    material_store.replace_quiz_questions_for_material(material["id"], [question])
    material_store.save_quiz_attempt(
        {
            "id": store.make_id("attempt"),
            "quizId": question["id"],
            "materialId": material["id"],
            "userAnswer": "Delete them",
            "isCorrect": False,
            "score": 40,
            "feedback": "This answer loses the history.",
            "suggestion": "Keep the attempt history.",
            "mode": "mock",
            "createdAt": store.now_iso(),
        }
    )

    weak_response = client.get("/api/review/weak-points", params={"goalId": goal["id"]})
    assert weak_response.status_code == 200
    weak_point = weak_response.json()["data"][0]
    assert weak_point["quizId"] == question["id"]
    assert weak_point["wrongCount"] == 1
    assert weak_point["resolved"] is False

    protected = client.post(f"/api/materials/{material['id']}/quiz")
    assert protected.status_code == 409
    assert protected.json()["error"]["message"] == "quiz_history_exists"
    assert [item["id"] for item in material_store.list_quiz_questions_for_material(material["id"])] == [
        question["id"]
    ]
    assert len(material_store.list_quiz_attempts_for_material(material["id"])) == 1

    material_store.save_quiz_attempt(
        {
            "id": store.make_id("attempt"),
            "quizId": question["id"],
            "materialId": material["id"],
            "userAnswer": "Quiz attempts",
            "isCorrect": True,
            "score": 70,
            "feedback": "Correct and sufficient.",
            "suggestion": "Continue reviewing.",
            "mode": "mock",
            "createdAt": store.now_iso(),
        }
    )
    resolved = client.get("/api/review/weak-points", params={"goalId": goal["id"]})
    assert resolved.status_code == 200
    assert resolved.json()["data"][0]["resolved"] is True

    context = client.get("/api/agent/context", params={"goalId": goal["id"]})
    assert context.status_code == 200
    assert context.json()["data"]["quiz"]["unresolvedWeakPointCount"] == 0


def test_demo_seed_uses_complete_fsrs_schedule():
    demo = client.post("/api/auth/demo")
    assert demo.status_code == 200
    materials = client.get("/api/materials")
    assert materials.status_code == 200
    material_id = materials.json()["data"][0]["id"]
    flashcards = client.get(f"/api/materials/{material_id}/flashcards")
    assert flashcards.status_code == 200
    for card in flashcards.json()["data"]:
        assert card["status"] == "new"
        assert card["dueAt"] == Card.from_json(card["fsrsCard"]).due.isoformat()
        assert card["reviewCount"] == 0
