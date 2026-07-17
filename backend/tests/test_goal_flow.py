from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import ai_learning_service, store
from backend.tests.auth_helpers import copy_session_cookie, register_session


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    client.cookies.clear()
    store.set_db_path(tmp_path / "test_ai_agent.db")
    store.reset()
    register_session(client, email="goal-default@example.com", name="Goal Default")
    yield
    client.cookies.clear()
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


def test_root_serves_frontend_entrypoint_for_one_command_startup():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "智能学习助手" in response.text
    assert 'id="agent-goal-select"' in response.text


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


def test_dashboard_returns_only_first_view_summary_for_the_signed_in_user():
    goal = create_goal()
    tasks = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 2, "regenerate": True},
    ).json()["data"]
    assert client.post(f"/api/tasks/{tasks[0]['id']}/checkin", json={"done": True}).status_code == 200

    response = client.get("/api/dashboard", params={"date": store.today_iso()})

    assert response.status_code == 200
    dashboard = response.json()["data"]
    assert dashboard["date"] == store.today_iso()
    assert dashboard["summary"] == {
        "goalTotal": 1,
        "todayTaskTotal": 1,
        "todayTaskCompleted": 1,
        "taskTotal": 2,
        "taskCompleted": 1,
        "completionRate": 50,
        "flashcardTotal": 0,
    }
    assert dashboard["primaryGoal"]["id"] == goal["id"]
    assert len(dashboard["todayTasks"]) == 1
    assert dashboard["todayTasks"][0]["goalName"] == goal["name"]
    assert "materials" not in dashboard
    assert "agentRuns" not in dashboard


def test_generate_plan_ignores_unrelated_material_even_if_linked_to_goal():
    goal = create_goal(
        {
            "name": "学习高数第一章内容极限",
            "subject": "数学",
            "notes": "提升自己求极限的能力，提高自己对极限定理的理解",
        }
    )
    goal_id = goal["id"]

    material_response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "title": "春江花月夜",
            "type": "text",
            "content": "春江潮水连海平，海上明月共潮生。诗歌描写月夜江景和离愁。",
        },
    )
    assert material_response.status_code == 200
    material_id = material_response.json()["data"]["id"]
    assert client.post(f"/api/materials/{material_id}/summarize").status_code == 200

    plan_response = client.post(
        f"/api/goals/{goal_id}/plans",
        json={"days": 3, "regenerate": True},
    )
    assert plan_response.status_code == 200
    tasks = plan_response.json()["data"]
    task_text = " ".join(f"{task['title']} {task['detail']}" for task in tasks)

    assert "春江花月夜" not in task_text
    assert "诗" not in task_text
    assert "极限" in task_text or "数学" in task_text


def test_fallback_plan_uses_chinese_task_template_and_ignores_goal_level():
    goal = create_goal(
        {
            "name": "学习高数第一章内容极限",
            "subject": "数学",
            "level": "刚开始",
            "notes": "提升自己求极限的能力，提高自己对极限定义的理解",
        }
    )

    plan_response = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 5, "regenerate": True},
    )
    assert plan_response.status_code == 200
    tasks = plan_response.json()["data"]
    task_text = " ".join(f"{task['title']} {task['detail']}" for task in tasks)

    assert "Day" not in task_text
    assert "Learn" not in task_text
    assert "Study" not in task_text
    assert "3-sentence" not in task_text
    assert "刚开始" not in task_text
    assert "梳理数学" not in task_text
    assert "提升自己" not in task_text
    assert "第 1 天" in task_text
    assert "分钟" in task_text
    assert len({task["detail"] for task in tasks}) > 1
    assert any("定义" in task["detail"] for task in tasks)
    assert any("例题" in task["detail"] for task in tasks)


def test_plan_normalizes_english_llm_template_before_saving(monkeypatch):
    goal = create_goal(
        {
            "name": "学习高数第一章内容极限",
            "subject": "数学",
            "level": "刚开始",
            "notes": "提升自己求极限的能力，提高自己对极限定义的理解",
        }
    )

    def fake_generate_json(system: str, user: str) -> dict:
        return {
            "mode": "fake-llm",
            "tasks": [
                {
                    "day": 1,
                    "title": "Day 1: Learn 刚开始",
                    "detail": "Study 刚开始 for 60 minutes, then write a 3-sentence recap and complete one self-test.",
                    "priority": "normal",
                }
            ],
        }

    monkeypatch.setattr(ai_learning_service, "_generate_json", fake_generate_json)

    plan_response = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 1, "regenerate": True},
    )
    assert plan_response.status_code == 200
    task = plan_response.json()["data"][0]
    task_text = f"{task['title']} {task['detail']}"

    assert "Day" not in task_text
    assert "Learn" not in task_text
    assert "Study" not in task_text
    assert "3-sentence" not in task_text
    assert "刚开始" not in task_text
    assert "提升自己" not in task_text
    assert task["title"].startswith("第 1 天")
    assert "分钟" in task["detail"]


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


def test_sqlite_data_persists_with_same_database_file():
    goal = create_goal({"name": "Persisted goal"})

    with TestClient(app) as second_client:
        copy_session_cookie(client, second_client)
        response = second_client.get(f"/api/goals/{goal['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Persisted goal"
