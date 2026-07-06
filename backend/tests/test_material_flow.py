from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import material_store, store


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    test_db_path = tmp_path / "test_ai_agent.db"
    store.set_db_path(test_db_path)
    store.reset()
    yield
    store.reset()


def create_goal() -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": "Material goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 20,
            "notes": "materials, flashcards, quiz",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_material(goal_id: str | None = None, payload: dict | None = None) -> dict:
    material_payload = {
        "goalId": goal_id,
        "type": "text",
        "title": "Learning material",
        "content": "This material explains how goals, plans, and review tasks work.",
        "url": "",
    }
    if payload:
        material_payload.update(payload)

    response = client.post("/api/materials", json=material_payload)
    assert response.status_code == 200
    return response.json()["data"]


def test_material_crud_summary_flashcards_and_quiz_flow():
    goal = create_goal()
    material = create_material(goal["id"])
    material_id = material["id"]

    list_response = client.get("/api/materials", params={"goalId": goal["id"]})
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    detail_response = client.get(f"/api/materials/{material_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["title"] == "Learning material"

    update_response = client.put(
        f"/api/materials/{material_id}",
        json={"title": "Updated material"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["title"] == "Updated material"
    assert update_response.json()["data"]["content"] == material["content"]

    empty_summary_response = client.get(f"/api/materials/{material_id}/summary")
    assert empty_summary_response.status_code == 200
    assert empty_summary_response.json()["data"] is None

    flashcards_without_summary = client.post(f"/api/materials/{material_id}/flashcards")
    assert flashcards_without_summary.status_code == 409

    quiz_without_summary = client.post(f"/api/materials/{material_id}/quiz")
    assert quiz_without_summary.status_code == 409

    summary_response = client.post(f"/api/materials/{material_id}/summarize")
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["materialId"] == material_id
    assert summary["aiMode"] == "mock"
    assert len(summary["keyPoints"]) >= 1

    summary_read_response = client.get(f"/api/materials/{material_id}/summary")
    assert summary_read_response.status_code == 200
    assert summary_read_response.json()["data"]["materialId"] == material_id

    empty_chunks_response = client.get(f"/api/materials/{material_id}/chunks")
    assert empty_chunks_response.status_code == 200
    assert empty_chunks_response.json()["data"] == []

    chunks_response = client.post(f"/api/materials/{material_id}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()["data"]
    assert len(chunks) >= 1
    assert chunks[0]["materialId"] == material_id
    assert chunks[0]["chunkIndex"] == 0
    assert "review" in chunks[0]["content"]
    assert len(chunks[0]["keywords"]) >= 1

    chunks_read_response = client.get(f"/api/materials/{material_id}/chunks")
    assert chunks_read_response.status_code == 200
    assert chunks_read_response.json()["data"] == chunks

    empty_qa_response = client.get(f"/api/materials/{material_id}/qa")
    assert empty_qa_response.status_code == 200
    assert empty_qa_response.json()["data"] == []

    search_response = client.get("/api/materials/search", params={"query": "review tasks"})
    assert search_response.status_code == 200
    search_results = search_response.json()["data"]
    assert len(search_results) >= 1
    assert search_results[0]["materialId"] == material_id
    assert search_results[0]["materialTitle"] == "Updated material"
    assert search_results[0]["score"] > 0

    empty_search_response = client.get("/api/materials/search", params={"query": "unrelated biology topic"})
    assert empty_search_response.status_code == 200
    assert empty_search_response.json()["data"] == []

    flashcards_response = client.post(f"/api/materials/{material_id}/flashcards")
    assert flashcards_response.status_code == 200
    flashcards = flashcards_response.json()["data"]
    assert len(flashcards) == len(summary["keyPoints"])

    flashcards_read_response = client.get(f"/api/materials/{material_id}/flashcards")
    assert flashcards_read_response.status_code == 200
    assert len(flashcards_read_response.json()["data"]) == len(flashcards)

    custom_flashcard_response = client.post(
        f"/api/materials/{material_id}/flashcards/custom",
        json={
            "front": "What should be reviewed?",
            "back": "Review tasks should be connected to saved materials.",
        },
    )
    assert custom_flashcard_response.status_code == 200
    custom_flashcard = custom_flashcard_response.json()["data"]
    assert custom_flashcard["materialId"] == material_id
    assert custom_flashcard["status"] == "new"

    update_flashcard_response = client.patch(
        f"/api/materials/{material_id}/flashcards/{custom_flashcard['id']}",
        json={"status": "known"},
    )
    assert update_flashcard_response.status_code == 200
    assert update_flashcard_response.json()["data"]["status"] == "known"

    flashcards_after_custom = client.get(f"/api/materials/{material_id}/flashcards").json()["data"]
    assert len(flashcards_after_custom) == len(flashcards) + 1

    quiz_response = client.post(f"/api/materials/{material_id}/quiz")
    assert quiz_response.status_code == 200
    quiz_questions = quiz_response.json()["data"]
    assert len(quiz_questions) == len(summary["keyPoints"])

    quiz_read_response = client.get(f"/api/materials/{material_id}/quiz")
    assert quiz_read_response.status_code == 200
    assert len(quiz_read_response.json()["data"]) == len(quiz_questions)

    answer_response = client.post(
        f"/api/materials/{material_id}/quiz/{quiz_questions[0]['id']}/answer",
        json={"answer": quiz_questions[0]["answer"]},
    )
    assert answer_response.status_code == 200
    attempt = answer_response.json()["data"]
    assert attempt["quizId"] == quiz_questions[0]["id"]
    assert attempt["materialId"] == material_id
    assert 0 <= attempt["score"] <= 100
    assert attempt["feedback"]

    attempts_response = client.get(f"/api/materials/{material_id}/quiz/attempts")
    assert attempts_response.status_code == 200
    assert attempts_response.json()["data"][0]["id"] == attempt["id"]

    delete_response = client.delete(f"/api/materials/{material_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True

    assert client.get(f"/api/materials/{material_id}").status_code == 404
    assert client.get(f"/api/materials/{material_id}/summary").status_code == 404
    assert client.get(f"/api/materials/{material_id}/chunks").status_code == 404
    assert client.get(f"/api/materials/{material_id}/qa").status_code == 404
    assert client.get(f"/api/materials/{material_id}/flashcards").status_code == 404
    assert client.get(f"/api/materials/{material_id}/quiz").status_code == 404


def test_material_validation_and_missing_resources():
    assert client.post(
        "/api/materials",
        json={
            "goalId": "goal_missing",
            "type": "text",
            "title": "Missing goal material",
            "content": "content",
            "url": "",
        },
    ).status_code == 404

    assert client.post(
        "/api/materials",
        json={
            "type": "text",
            "title": "Empty text material",
            "content": "",
            "url": "",
        },
    ).status_code == 422

    assert client.post(
        "/api/materials",
        json={
            "type": "link",
            "title": "Empty link material",
            "content": "",
            "url": "",
        },
    ).status_code == 422

    assert client.get("/api/materials/material_missing").status_code == 404
    assert client.put("/api/materials/material_missing", json={"title": "new"}).status_code == 404
    assert client.delete("/api/materials/material_missing").status_code == 404
    assert client.get("/api/materials/material_missing/chunks").status_code == 404
    assert client.post("/api/materials/material_missing/chunks").status_code == 404
    assert client.get("/api/materials/material_missing/qa").status_code == 404
    assert client.post("/api/materials/material_missing/summarize").status_code == 404


def test_material_store_uses_same_temporary_database_as_goal_store(tmp_path):
    test_db_path = tmp_path / "shared_test_ai_agent.db"
    store.set_db_path(test_db_path)
    store.reset()

    assert material_store.DB_PATH == test_db_path

    goal = create_goal()
    material = create_material(goal["id"], {"title": "Persisted material"})
    summary = client.post(f"/api/materials/{material['id']}/summarize").json()["data"]
    flashcards = client.post(f"/api/materials/{material['id']}/flashcards").json()["data"]
    quiz_questions = client.post(f"/api/materials/{material['id']}/quiz").json()["data"]

    with TestClient(app) as second_client:
        material_response = second_client.get(f"/api/materials/{material['id']}")
        summary_response = second_client.get(f"/api/materials/{material['id']}/summary")
        flashcards_response = second_client.get(f"/api/materials/{material['id']}/flashcards")
        quiz_response = second_client.get(f"/api/materials/{material['id']}/quiz")

    assert material_response.status_code == 200
    assert material_response.json()["data"]["title"] == "Persisted material"
    assert summary_response.json()["data"]["materialId"] == summary["materialId"]
    assert len(flashcards_response.json()["data"]) == len(flashcards)
    assert len(quiz_response.json()["data"]) == len(quiz_questions)
