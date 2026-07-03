from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import store


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    store.set_db_path(tmp_path / "test_ai_agent.db")
    store.reset()
    yield
    store.reset()


def register_user(email: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "name": email.split("@", 1)[0],
            "email": email,
            "password": "secret123",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_goal(user_id: str, name: str) -> dict:
    response = client.post(
        "/api/goals",
        headers={"X-User-Id": user_id},
        json={
            "name": name,
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_material(user_id: str, goal_id: str, title: str, content: str) -> dict:
    response = client.post(
        "/api/materials",
        headers={"X-User-Id": user_id},
        json={
            "goalId": goal_id,
            "type": "text",
            "title": title,
            "content": content,
            "url": "",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_goals_and_materials_are_isolated_by_user_header():
    chen = register_user("chen@example.com")
    zhao = register_user("zhao@example.com")

    chen_goal = create_goal(chen["id"], "Chen private goal")
    zhao_goal = create_goal(zhao["id"], "Zhao private goal")

    chen_material = create_material(
        chen["id"],
        chen_goal["id"],
        "Chen RAG notes",
        "RAG retrieval belongs to Chen only.",
    )
    zhao_material = create_material(
        zhao["id"],
        zhao_goal["id"],
        "Zhao SQL notes",
        "SQLite persistence belongs to Zhao only.",
    )

    chen_goals = client.get("/api/goals", headers={"X-User-Id": chen["id"]}).json()["data"]
    zhao_goals = client.get("/api/goals", headers={"X-User-Id": zhao["id"]}).json()["data"]
    assert [goal["id"] for goal in chen_goals] == [chen_goal["id"]]
    assert [goal["id"] for goal in zhao_goals] == [zhao_goal["id"]]

    chen_materials = client.get("/api/materials", headers={"X-User-Id": chen["id"]}).json()["data"]
    zhao_materials = client.get("/api/materials", headers={"X-User-Id": zhao["id"]}).json()["data"]
    assert [material["id"] for material in chen_materials] == [chen_material["id"]]
    assert [material["id"] for material in zhao_materials] == [zhao_material["id"]]

    assert client.get(
        f"/api/materials/{zhao_material['id']}",
        headers={"X-User-Id": chen["id"]},
    ).status_code == 404


def test_chunk_search_is_isolated_by_user_header():
    chen = register_user("chen@example.com")
    zhao = register_user("zhao@example.com")
    chen_goal = create_goal(chen["id"], "Chen private goal")
    zhao_goal = create_goal(zhao["id"], "Zhao private goal")
    chen_material = create_material(
        chen["id"],
        chen_goal["id"],
        "Chen RAG notes",
        "RAG retrieval belongs to Chen only.",
    )
    zhao_material = create_material(
        zhao["id"],
        zhao_goal["id"],
        "Zhao RAG notes",
        "RAG retrieval belongs to Zhao only.",
    )

    assert client.post(
        f"/api/materials/{chen_material['id']}/chunks",
        headers={"X-User-Id": chen["id"]},
    ).status_code == 200
    assert client.post(
        f"/api/materials/{zhao_material['id']}/chunks",
        headers={"X-User-Id": zhao["id"]},
    ).status_code == 200

    chen_search = client.get(
        "/api/materials/search",
        headers={"X-User-Id": chen["id"]},
        params={"query": "RAG", "limit": 10},
    ).json()["data"]
    zhao_search = client.get(
        "/api/materials/search",
        headers={"X-User-Id": zhao["id"]},
        params={"query": "RAG", "limit": 10},
    ).json()["data"]

    assert {item["materialId"] for item in chen_search} == {chen_material["id"]}
    assert {item["materialId"] for item in zhao_search} == {zhao_material["id"]}
