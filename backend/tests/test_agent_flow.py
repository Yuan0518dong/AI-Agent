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
            "question": "How does RAG use retrieval?",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "mock"
    assert "资料片段" in data["answer"]
    assert "RAG notes" in data["basis"]
    assert "Agent goal" in data["suggestion"]
    assert data["isFromMaterial"] is True
    assert data["confidence"] == "high"
    assert len(data["references"]) == 1
    assert data["references"][0]["materialId"] == material["id"]
    assert data["references"][0]["materialTitle"] == "RAG notes"
    assert data["references"][0]["chunkIndex"] == 0
    assert data["references"][0]["score"] > 0


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
    create_material(
        goal["id"],
        "RAG notes",
        "RAG uses retrieval to find relevant chunks.",
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "question": "unrelated biology topic",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "mock"
    assert data["isFromMaterial"] is False
    assert data["confidence"] == "low"
    assert data["references"] == []
    assert "资料不足" in data["answer"]
    assert "没有检索到" in data["basis"]
    assert "RAG notes" not in data["suggestion"]


def test_agent_ask_validation_and_missing_goal():
    assert client.post("/api/agent/ask", json={"question": "   "}).status_code == 422
    assert client.post(
        "/api/agent/ask",
        json={
            "goalId": "goal_missing",
            "question": "RAG retrieval",
        },
    ).status_code == 404
