from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import store


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    store.reset()
    yield
    store.reset()


def create_goal(payload: dict | None = None) -> dict:
    goal_payload = {
        "name": "Math improvement",
        "subject": "Math",
        "level": "basic",
        "deadline": "2026-07-15",
        "daily_minutes": 30,
        "notes": "algebra, geometry",
    }
    if payload:
        goal_payload.update(payload)

    response = client.post("/api/goals", json=goal_payload)
    assert response.status_code == 200
    return response.json()["data"]


def test_health_check():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_goal_crud_and_partial_update_keeps_existing_fields():
    goal = create_goal()
    goal_id = goal["id"]

    list_response = client.get("/api/goals")
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    detail_response = client.get(f"/api/goals/{goal_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["name"] == "Math improvement"

    update_response = client.put(
        f"/api/goals/{goal_id}",
        json={"daily_minutes": 60},
    )
    assert update_response.status_code == 200

    updated_goal = update_response.json()["data"]
    assert updated_goal["daily_minutes"] == 60
    assert updated_goal["name"] == "Math improvement"
    assert updated_goal["subject"] == "Math"
    assert updated_goal["level"] == "basic"
    assert updated_goal["deadline"] == "2026-07-15"
    assert updated_goal["notes"] == "algebra, geometry"


def test_generate_plan_list_tasks_checkin_and_progress():
    goal = create_goal()
    goal_id = goal["id"]

    plan_response = client.post(
        f"/api/goals/{goal_id}/plans",
        json={"days": 3, "regenerate": True},
    )
    assert plan_response.status_code == 200
    tasks = plan_response.json()["data"]
    assert len(tasks) == 3

    task_id = tasks[0]["id"]

    goal_tasks_response = client.get(f"/api/goals/{goal_id}/tasks")
    assert goal_tasks_response.status_code == 200
    assert len(goal_tasks_response.json()["data"]) == 3

    today_tasks_response = client.get("/api/tasks/today")
    assert today_tasks_response.status_code == 200
    assert len(today_tasks_response.json()["data"]) >= 1

    checkin_response = client.post(
        f"/api/tasks/{task_id}/checkin",
        json={"done": True},
    )
    assert checkin_response.status_code == 200
    assert checkin_response.json()["data"]["done"] is True
    assert checkin_response.json()["data"]["completed_at"] is not None

    progress_response = client.get(f"/api/progress/{goal_id}")
    assert progress_response.status_code == 200
    progress = progress_response.json()["data"]
    assert progress["total_tasks"] == 3
    assert progress["completed_tasks"] == 1
    assert progress["completion_rate"] == 33

    cancel_response = client.post(
        f"/api/tasks/{task_id}/checkin",
        json={"done": False},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["data"]["done"] is False
    assert cancel_response.json()["data"]["completed_at"] is None


def test_delete_goal_removes_related_tasks_and_progress():
    goal = create_goal()
    goal_id = goal["id"]
    plan_response = client.post(
        f"/api/goals/{goal_id}/plans",
        json={"days": 2, "regenerate": True},
    )
    assert plan_response.status_code == 200
    task_id = plan_response.json()["data"][0]["id"]

    delete_response = client.delete(f"/api/goals/{goal_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True

    assert client.get(f"/api/goals/{goal_id}").status_code == 404
    assert client.get(f"/api/progress/{goal_id}").status_code == 404
    assert client.post(f"/api/tasks/{task_id}/checkin", json={"done": True}).status_code == 404


def test_missing_goal_and_task_return_404():
    assert client.get("/api/goals/missing").status_code == 404
    assert client.put("/api/goals/missing", json={"daily_minutes": 10}).status_code == 404
    assert client.delete("/api/goals/missing").status_code == 404
    assert client.post("/api/goals/missing/plans", json={"days": 3}).status_code == 404
    assert client.get("/api/goals/missing/tasks").status_code == 404
    assert client.get("/api/progress/missing").status_code == 404
    assert client.post("/api/tasks/missing/checkin", json={"done": True}).status_code == 404


def test_goal_validation_rejects_invalid_payload():
    response = client.post(
        "/api/goals",
        json={
            "name": "",
            "subject": "Math",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 0,
        },
    )

    assert response.status_code == 422
