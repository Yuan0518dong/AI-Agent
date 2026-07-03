from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import store


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    test_db_path = tmp_path / "test_ai_agent.db"
    store.set_db_path(test_db_path)
    store.reset()
    yield
    store.reset()


def create_goal(name: str = "Agent goal") -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": name,
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "RAG, chunks, retrieval",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_material(goal_id: str, title: str, content: str) -> dict:
    response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "type": "text",
            "title": title,
            "content": content,
            "url": "",
        },
    )
    assert response.status_code == 200
    material = response.json()["data"]

    chunks_response = client.post(f"/api/materials/{material['id']}/chunks")
    assert chunks_response.status_code == 200
    assert len(chunks_response.json()["data"]) >= 1
    return material


def test_agent_ask_returns_mock_answer_with_references():
    goal = create_goal()
    material = create_material(
        goal["id"],
        "RAG notes",
        "RAG uses retrieval to find relevant chunks before generating an answer.",
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "materialId": material["id"],
            "question": "How does RAG use retrieval?",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "mock"
    assert data["id"].startswith("qa_")
    assert data["materialId"] == material["id"]
    assert data["goalId"] == goal["id"]
    assert data["question"] == "How does RAG use retrieval?"
    assert "资料片段" in data["answer"]
    assert "RAG notes" in data["basis"]
    assert "Agent goal" in data["suggestion"]
    assert data["sourceTitle"] == "RAG notes"
    assert data["isFromMaterial"] is True
    assert data["confidence"] == "high"
    assert data["createdAt"]
    assert len(data["references"]) == 1
    assert data["references"][0]["materialId"] == material["id"]
    assert data["references"][0]["materialTitle"] == "RAG notes"
    assert data["references"][0]["chunkIndex"] == 0
    assert data["references"][0]["score"] > 0

    history_response = client.get(f"/api/materials/{material['id']}/qa")
    assert history_response.status_code == 200
    history = history_response.json()["data"]
    assert len(history) == 1
    assert history[0]["id"] == data["id"]
    assert history[0]["materialId"] == material["id"]
    assert history[0]["goalId"] == goal["id"]
    assert history[0]["question"] == data["question"]
    assert history[0]["answer"] == data["answer"]
    assert history[0]["basis"] == data["basis"]
    assert history[0]["suggestion"] == data["suggestion"]
    assert history[0]["sourceTitle"] == data["sourceTitle"]
    assert history[0]["isFromMaterial"] is True
    assert history[0]["confidence"] == data["confidence"]


def test_agent_ask_filters_references_by_goal():
    target_goal = create_goal("Target goal")
    other_goal = create_goal("Other goal")
    target_material = create_material(
        target_goal["id"],
        "Target RAG notes",
        "RAG retrieval can answer questions with target goal context.",
    )
    create_material(
        other_goal["id"],
        "Other RAG notes",
        "RAG retrieval can answer questions with other goal context.",
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": target_goal["id"],
            "materialId": target_material["id"],
            "question": "RAG retrieval context",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "Target goal" in data["suggestion"]
    references = data["references"]
    assert len(references) == 1
    assert references[0]["materialId"] == target_material["id"]


def test_agent_ask_returns_fallback_when_no_chunks_match():
    goal = create_goal()
    material = create_material(
        goal["id"],
        "RAG notes",
        "RAG uses retrieval to find relevant chunks.",
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "materialId": material["id"],
            "question": "unrelated biology topic",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "mock"
    assert data["id"].startswith("qa_")
    assert data["materialId"] == material["id"]
    assert data["isFromMaterial"] is False
    assert data["confidence"] == "low"
    assert data["references"] == []
    assert "资料不足" in data["answer"]
    assert "没有检索到" in data["basis"]
    assert "RAG notes" not in data["suggestion"]

    history = client.get(f"/api/materials/{material['id']}/qa").json()["data"]
    assert len(history) == 1
    assert history[0]["id"] == data["id"]
    assert history[0]["isFromMaterial"] is False
    assert history[0]["confidence"] == "low"


def test_agent_ask_validation_and_missing_goal():
    assert client.post("/api/agent/ask", json={"question": "   "}).status_code == 422
    assert client.post(
        "/api/agent/ask",
        json={
            "goalId": "goal_missing",
            "question": "RAG retrieval",
        },
    ).status_code == 404
    assert client.post(
        "/api/agent/ask",
        json={
            "materialId": "material_missing",
            "question": "RAG retrieval",
        },
    ).status_code == 404


def test_agent_ask_qa_records_persist_and_cascade_with_material():
    goal = create_goal()
    material = create_material(
        goal["id"],
        "Persisted RAG notes",
        "RAG persistence stores question answer records for review.",
    )

    first_response = client.post(
        "/api/agent/ask",
        json={
            "materialId": material["id"],
            "question": "What does RAG persistence store?",
        },
    )
    second_response = client.post(
        "/api/agent/ask",
        json={
            "materialId": material["id"],
            "question": "How can records help review?",
        },
    )
    assert first_response.status_code == 200
    assert second_response.status_code == 200

    with TestClient(app) as second_client:
        history_response = second_client.get(f"/api/materials/{material['id']}/qa")

    assert history_response.status_code == 200
    history = history_response.json()["data"]
    assert [item["id"] for item in history] == [
        first_response.json()["data"]["id"],
        second_response.json()["data"]["id"],
    ]

    delete_response = client.delete(f"/api/materials/{material['id']}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/materials/{material['id']}/qa").status_code == 404
