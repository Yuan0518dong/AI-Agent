from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import store
from backend.tests.auth_helpers import register_session


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    client.cookies.clear()
    store.set_db_path(tmp_path / "test_ai_agent.db")
    store.reset()
    register_session(client, email="isolation-default@example.com", name="Isolation Default")
    yield
    client.cookies.clear()
    store.reset()


def create_goal(session_client: TestClient, name: str) -> dict:
    response = session_client.post(
        "/api/goals",
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


def create_material(
    session_client: TestClient,
    goal_id: str,
    title: str,
    content: str,
) -> dict:
    response = session_client.post(
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
    return response.json()["data"]


def test_goals_and_materials_are_isolated_by_cookie_session():
    with TestClient(app) as chen_client, TestClient(app) as zhao_client:
        register_session(chen_client, email="chen@example.com", name="Chen")
        register_session(zhao_client, email="zhao@example.com", name="Zhao")
        chen_goal = create_goal(chen_client, "Chen private goal")
        zhao_goal = create_goal(zhao_client, "Zhao private goal")
        chen_material = create_material(
            chen_client,
            chen_goal["id"],
            "Chen RAG notes",
            "RAG retrieval belongs to Chen only.",
        )
        zhao_material = create_material(
            zhao_client,
            zhao_goal["id"],
            "Zhao SQL notes",
            "SQLite persistence belongs to Zhao only.",
        )

        chen_goals = chen_client.get("/api/goals").json()["data"]
        zhao_goals = zhao_client.get("/api/goals").json()["data"]
        assert [goal["id"] for goal in chen_goals] == [chen_goal["id"]]
        assert [goal["id"] for goal in zhao_goals] == [zhao_goal["id"]]

        chen_materials = chen_client.get("/api/materials").json()["data"]
        zhao_materials = zhao_client.get("/api/materials").json()["data"]
        assert [material["id"] for material in chen_materials] == [chen_material["id"]]
        assert [material["id"] for material in zhao_materials] == [zhao_material["id"]]
        assert chen_client.get(f"/api/materials/{zhao_material['id']}").status_code == 404

        zhao_id = store.get_user_by_email("zhao@example.com")["id"]
        forged = chen_client.get("/api/goals", headers={"X-User-Id": zhao_id})
        assert forged.status_code == 200
        assert [goal["id"] for goal in forged.json()["data"]] == [chen_goal["id"]]


def test_chunk_search_is_isolated_by_cookie_session():
    with TestClient(app) as chen_client, TestClient(app) as zhao_client:
        register_session(chen_client, email="chen@example.com", name="Chen")
        register_session(zhao_client, email="zhao@example.com", name="Zhao")
        chen_goal = create_goal(chen_client, "Chen private goal")
        zhao_goal = create_goal(zhao_client, "Zhao private goal")
        chen_material = create_material(
            chen_client,
            chen_goal["id"],
            "Chen RAG notes",
            "RAG retrieval belongs to Chen only.",
        )
        zhao_material = create_material(
            zhao_client,
            zhao_goal["id"],
            "Zhao RAG notes",
            "RAG retrieval belongs to Zhao only.",
        )

        assert chen_client.post(f"/api/materials/{chen_material['id']}/chunks").status_code == 200
        assert zhao_client.post(f"/api/materials/{zhao_material['id']}/chunks").status_code == 200

        chen_search = chen_client.get(
            "/api/materials/search",
            params={"query": "RAG", "limit": 10},
        ).json()["data"]
        zhao_search = zhao_client.get(
            "/api/materials/search",
            params={"query": "RAG", "limit": 10},
        ).json()["data"]

        assert {item["materialId"] for item in chen_search} == {chen_material["id"]}
        assert {item["materialId"] for item in zhao_search} == {zhao_material["id"]}
