import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app
from backend.app.services import store


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        store.set_db_path(Path(temp_dir) / "smoke.db")
        store.reset()

        with TestClient(app) as client:
            health = client.get("/api/health")
            health.raise_for_status()

            goal_response = client.post(
                "/api/goals",
                json={
                    "name": "API smoke test goal",
                    "subject": "AI Agent",
                    "level": "beginner",
                    "deadline": "2026-07-15",
                    "daily_minutes": 45,
                    "notes": "goal, material, plan, check-in, progress",
                },
            )
            goal_response.raise_for_status()
            goal_id = goal_response.json()["data"]["id"]

            material_response = client.post(
                "/api/materials",
                json={
                    "goalId": goal_id,
                    "type": "text",
                    "title": "Smoke test material",
                    "content": "Use this material to verify material CRUD APIs.",
                    "url": "",
                },
            )
            material_response.raise_for_status()
            material = material_response.json()["data"]
            material_id = material["id"]

            pending_material_response = client.post(
                "/api/materials",
                json={
                    "goalId": goal_id,
                    "type": "text",
                    "title": "Pending summary material",
                    "content": "This material has no summary yet.",
                    "url": "",
                },
            )
            pending_material_response.raise_for_status()
            pending_material_id = pending_material_response.json()["data"]["id"]

            empty_summary_response = client.get(f"/api/materials/{pending_material_id}/summary")
            empty_summary_response.raise_for_status()

            missing_summary_response = client.get("/api/materials/material_missing/summary")

            empty_flashcards_response = client.get(f"/api/materials/{pending_material_id}/flashcards")
            empty_flashcards_response.raise_for_status()

            flashcards_without_summary_response = client.post(
                f"/api/materials/{pending_material_id}/flashcards"
            )

            empty_quiz_response = client.get(f"/api/materials/{pending_material_id}/quiz")
            empty_quiz_response.raise_for_status()

            quiz_without_summary_response = client.post(
                f"/api/materials/{pending_material_id}/quiz"
            )

            materials_response = client.get("/api/materials", params={"goalId": goal_id})
            materials_response.raise_for_status()

            material_detail_response = client.get(f"/api/materials/{material_id}")
            material_detail_response.raise_for_status()

            material_update_response = client.put(
                f"/api/materials/{material_id}",
                json={"title": "Updated smoke test material"},
            )
            material_update_response.raise_for_status()

            material_summary_response = client.post(f"/api/materials/{material_id}/summarize")
            material_summary_response.raise_for_status()
            material_summary = material_summary_response.json()["data"]

            material_summary_get_response = client.get(f"/api/materials/{material_id}/summary")
            material_summary_get_response.raise_for_status()
            material_summary_get = material_summary_get_response.json()["data"]

            flashcards_response = client.post(f"/api/materials/{material_id}/flashcards")
            flashcards_response.raise_for_status()
            flashcards = flashcards_response.json()["data"]

            flashcards_get_response = client.get(f"/api/materials/{material_id}/flashcards")
            flashcards_get_response.raise_for_status()
            flashcards_get = flashcards_get_response.json()["data"]

            quiz_response = client.post(f"/api/materials/{material_id}/quiz")
            quiz_response.raise_for_status()
            quiz_questions = quiz_response.json()["data"]

            quiz_get_response = client.get(f"/api/materials/{material_id}/quiz")
            quiz_get_response.raise_for_status()
            quiz_questions_get = quiz_get_response.json()["data"]

            plan_response = client.post(
                f"/api/goals/{goal_id}/plans",
                json={"days": 3, "regenerate": True},
            )
            plan_response.raise_for_status()
            tasks = plan_response.json()["data"]
            task_id = tasks[0]["id"]

            today_response = client.get("/api/tasks/today")
            today_response.raise_for_status()

            checkin_response = client.post(
                f"/api/tasks/{task_id}/checkin",
                json={"done": True},
            )
            checkin_response.raise_for_status()

            progress_response = client.get(f"/api/progress/{goal_id}")
            progress_response.raise_for_status()

            material_delete_response = client.delete(f"/api/materials/{material_id}")
            material_delete_response.raise_for_status()
            pending_material_delete_response = client.delete(f"/api/materials/{pending_material_id}")
            pending_material_delete_response.raise_for_status()

            result = {
                "health_code": health.json()["code"],
                "goal_code": goal_response.json()["code"],
                "material_code": material_response.json()["code"],
                "material_count": len(materials_response.json()["data"]),
                "material_title": material_update_response.json()["data"]["title"],
                "empty_summary": empty_summary_response.json()["data"],
                "missing_summary_status": missing_summary_response.status_code,
                "empty_flashcards_count": len(empty_flashcards_response.json()["data"]),
                "flashcards_without_summary_status": flashcards_without_summary_response.status_code,
                "empty_quiz_count": len(empty_quiz_response.json()["data"]),
                "quiz_without_summary_status": quiz_without_summary_response.status_code,
                "material_summary_mode": material_summary["aiMode"],
                "material_summary_readback": material_summary_get["materialId"] == material_id,
                "material_summary_points": len(material_summary["keyPoints"]),
                "flashcard_count": len(flashcards),
                "flashcard_readback": len(flashcards_get) == len(flashcards),
                "quiz_count": len(quiz_questions),
                "quiz_readback": len(quiz_questions_get) == len(quiz_questions),
                "plan_count": len(tasks),
                "today_status": today_response.status_code,
                "checkin_done": checkin_response.json()["data"]["done"],
                "completion_rate": progress_response.json()["data"]["completion_rate"],
                "material_deleted": material_delete_response.json()["data"]["deleted"],
            }
            print(result)


if __name__ == "__main__":
    main()
