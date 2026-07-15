import sys
import os
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
        os.environ["LLM_PROVIDER"] = "mock"
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["LLM_ENV_FILE"] = str(Path(temp_dir) / "missing.env")
        os.environ["EMBEDDING_ENV_FILE"] = str(Path(temp_dir) / "missing.env")
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

            chunks_response = client.post(f"/api/materials/{material_id}/chunks")
            chunks_response.raise_for_status()
            chunks = chunks_response.json()["data"]

            chunks_get_response = client.get(f"/api/materials/{material_id}/chunks")
            chunks_get_response.raise_for_status()
            chunks_get = chunks_get_response.json()["data"]

            chunks_search_response = client.get(
                "/api/materials/search",
                params={"query": "material CRUD"},
            )
            chunks_search_response.raise_for_status()
            chunks_search = chunks_search_response.json()["data"]

            agent_ask_response = client.post(
                "/api/agent/ask",
                json={
                    "goalId": goal_id,
                    "materialId": material_id,
                    "question": "How does material CRUD work?",
                },
            )
            agent_ask_response.raise_for_status()
            agent_answer = agent_ask_response.json()["data"]

            material_qa_response = client.get(f"/api/materials/{material_id}/qa")
            material_qa_response.raise_for_status()
            material_qa_records = material_qa_response.json()["data"]

            flashcards_response = client.post(f"/api/materials/{material_id}/flashcards")
            flashcards_response.raise_for_status()
            flashcards = flashcards_response.json()["data"]

            flashcards_get_response = client.get(f"/api/materials/{material_id}/flashcards")
            flashcards_get_response.raise_for_status()
            flashcards_get = flashcards_get_response.json()["data"]

            agent_context_before_custom_flashcard_response = client.get(
                "/api/agent/context",
                params={"goalId": goal_id},
            )
            agent_context_before_custom_flashcard_response.raise_for_status()
            agent_context_before_custom_flashcard = (
                agent_context_before_custom_flashcard_response.json()["data"]
            )

            custom_flashcard_response = client.post(
                f"/api/materials/{material_id}/flashcards/custom",
                json={
                    "front": "What does context read-back prove?",
                    "back": "Confirmed writes become visible to the next AgentContext.",
                },
            )
            custom_flashcard_response.raise_for_status()

            agent_context_after_custom_flashcard_response = client.get(
                "/api/agent/context",
                params={"goalId": goal_id},
            )
            agent_context_after_custom_flashcard_response.raise_for_status()
            agent_context_after_custom_flashcard = (
                agent_context_after_custom_flashcard_response.json()["data"]
            )

            agent_decision_after_custom_flashcard_response = client.post(
                "/api/agent/decide",
                params={"goalId": goal_id},
            )
            agent_decision_after_custom_flashcard_response.raise_for_status()
            agent_decision_after_custom_flashcard = (
                agent_decision_after_custom_flashcard_response.json()["data"]
            )

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

            agent_context_response = client.get(
                "/api/agent/context",
                params={"goalId": goal_id},
            )
            agent_context_response.raise_for_status()
            agent_context = agent_context_response.json()["data"]

            agent_decision_response = client.post(
                "/api/agent/decide",
                params={"goalId": goal_id},
            )
            agent_decision_response.raise_for_status()
            agent_decision = agent_decision_response.json()["data"]

            agent_hybrid_decision_response = client.post(
                "/api/agent/decide",
                params={"goalId": goal_id, "decisionMode": "hybrid"},
            )
            agent_hybrid_decision_response.raise_for_status()
            agent_hybrid_decision = agent_hybrid_decision_response.json()["data"]
            hybrid_metadata = agent_hybrid_decision.get("providerMetadata") or {}
            if hybrid_metadata.get("provider") != "mock":
                raise RuntimeError("Agent hybrid smoke did not keep Mock as the CI fallback provider")
            if hybrid_metadata.get("promptVersion") != "batch-c-v1":
                raise RuntimeError("Agent hybrid smoke did not record the Batch C prompt version")

            agent_tools_response = client.get("/api/agent/tools")
            agent_tools_response.raise_for_status()
            agent_tools = agent_tools_response.json()["data"]

            first_action = agent_decision["proposedActions"][0]
            action_log_create_response = client.post(
                "/api/agent/action-logs",
                json={
                    "goalId": goal_id,
                    "actionType": first_action["type"],
                    "observation": agent_decision["stateSummary"],
                    "decision": agent_decision,
                    "proposedPayload": first_action,
                    "status": "accepted",
                },
            )
            action_log_create_response.raise_for_status()
            action_log = action_log_create_response.json()["data"]

            action_log_list_response = client.get(
                "/api/agent/action-logs",
                params={"goalId": goal_id},
            )
            action_log_list_response.raise_for_status()
            action_logs = action_log_list_response.json()["data"]

            action_log_update_response = client.patch(
                f"/api/agent/action-logs/{action_log['id']}",
                json={"status": "later"},
            )
            action_log_update_response.raise_for_status()
            updated_action_log = action_log_update_response.json()["data"]

            action_log_apply_response = client.patch(
                f"/api/agent/action-logs/{action_log['id']}",
                json={"status": "applied"},
            )
            action_log_apply_response.raise_for_status()
            applied_action_log = action_log_apply_response.json()["data"]

            agent_run_create_response = client.post(
                "/api/agent/runs",
                json={"goalId": goal_id, "trigger": "manual"},
            )
            agent_run_create_response.raise_for_status()
            agent_run = agent_run_create_response.json()["data"]

            agent_run_list_response = client.get(
                "/api/agent/runs",
                params={"goalId": goal_id},
            )
            agent_run_list_response.raise_for_status()
            agent_runs = agent_run_list_response.json()["data"]

            agent_run_update_response = client.patch(
                f"/api/agent/runs/{agent_run['id']}",
                json={"status": "feedback_recorded"},
            )
            agent_run_update_response.raise_for_status()
            updated_agent_run = agent_run_update_response.json()["data"]

            loop_run_create_response = client.post(
                "/api/agent/runs",
                json={
                    "goalId": goal_id,
                    "trigger": "manual",
                    "objective": "Inspect the learning state and choose the next safe action.",
                    "decisionMode": "rule-based",
                    "maxSteps": 3,
                },
            )
            loop_run_create_response.raise_for_status()
            loop_run = loop_run_create_response.json()["data"]
            loop_execute_response = client.post(
                f"/api/agent/runs/{loop_run['id']}/execute",
                json={},
            )
            loop_execute_response.raise_for_status()
            executed_loop_run = loop_execute_response.json()["data"]
            if executed_loop_run["status"] == "failed":
                raise RuntimeError(f"Agent loop smoke failed: {executed_loop_run['error']}")
            if not executed_loop_run["decisionSnapshot"].get("reflection"):
                raise RuntimeError("Agent loop smoke did not persist terminal reflection")

            draft_goal_response = client.post(
                "/api/goals",
                json={
                    "name": "Draft persistence smoke goal",
                    "subject": "AI Agent",
                    "level": "beginner",
                    "deadline": "2026-07-15",
                    "daily_minutes": 30,
                    "notes": "persist, confirm, and apply exactly one task draft",
                },
            )
            draft_goal_response.raise_for_status()
            draft_goal_id = draft_goal_response.json()["data"]["id"]
            draft_run_response = client.post(
                "/api/agent/runs",
                json={"goalId": draft_goal_id, "maxSteps": 2},
            )
            draft_run_response.raise_for_status()
            draft_run = draft_run_response.json()["data"]
            draft_execute_response = client.post(
                f"/api/agent/runs/{draft_run['id']}/execute",
                json={},
            )
            draft_execute_response.raise_for_status()
            executed_draft_run = draft_execute_response.json()["data"]
            if executed_draft_run["status"] == "failed":
                raise RuntimeError(f"Agent draft smoke failed: {executed_draft_run['error']}")
            draft_step = executed_draft_run["steps"][0]
            persisted_draft = draft_step["toolOutput"]["data"]["drafts"][0]
            draft_list_response = client.get(
                "/api/agent/drafts",
                params={"goalId": draft_goal_id, "draftType": "task", "status": "proposed"},
            )
            draft_list_response.raise_for_status()
            persisted_drafts = draft_list_response.json()["data"]
            draft_readback_response = client.get(f"/api/agent/drafts/{persisted_draft['id']}")
            draft_readback_response.raise_for_status()
            if persisted_draft["id"] != draft_readback_response.json()["data"]["id"]:
                raise RuntimeError("Agent draft smoke did not return the persisted draft record")
            if store.list_goal_tasks(draft_goal_id):
                raise RuntimeError("Agent draft smoke unexpectedly wrote formal tasks")
            apply_step = executed_draft_run["steps"][1]
            if apply_step["toolName"] != "apply_confirmed_draft":
                raise RuntimeError("Agent draft smoke did not request confirmed application")
            accepted_response = client.patch(
                f"/api/agent/action-logs/{apply_step['actionLogId']}",
                json={"status": "accepted"},
            )
            accepted_response.raise_for_status()
            confirmed_draft = client.get(f"/api/agent/drafts/{persisted_draft['id']}")
            confirmed_draft.raise_for_status()
            if confirmed_draft.json()["data"]["status"] != "confirmed":
                raise RuntimeError("Agent draft smoke did not confirm the selected draft")
            resume_draft_response = client.post(
                f"/api/agent/runs/{draft_run['id']}/execute",
                json={},
            )
            resume_draft_response.raise_for_status()
            applied_draft_run = resume_draft_response.json()["data"]
            if applied_draft_run["status"] == "failed":
                raise RuntimeError(f"Agent apply smoke failed: {applied_draft_run['error']}")
            applied_draft_step = applied_draft_run["steps"][1]
            applied_draft = client.get(f"/api/agent/drafts/{persisted_draft['id']}")
            applied_draft.raise_for_status()
            if applied_draft.json()["data"]["status"] != "applied":
                raise RuntimeError("Agent draft smoke did not mark the draft applied")
            if len(store.list_goal_tasks(draft_goal_id)) != 1:
                raise RuntimeError("Agent draft smoke did not write exactly one formal task")
            if applied_draft_run["status"] != "max_steps":
                raise RuntimeError("Agent draft smoke did not stop at the exhausted step budget")
            if applied_draft_run["contextSnapshot"]["summary"]["taskTotal"] != 1:
                raise RuntimeError("Agent draft smoke did not persist the formal task readback")
            if applied_draft_run["contextSnapshot"]["drafts"]["proposedCount"] != 0:
                raise RuntimeError("Agent draft smoke kept the applied draft as proposed")
            if any(
                action["type"] == "apply_confirmed_draft"
                for action in applied_draft_run["decisionSnapshot"]["proposedActions"]
            ):
                raise RuntimeError("Agent draft smoke repeated the applied draft decision")
            draft_run_readback = client.get(f"/api/agent/runs/{draft_run['id']}")
            draft_run_readback.raise_for_status()
            persisted_draft_run = draft_run_readback.json()["data"]
            if (
                persisted_draft_run["contextSnapshot"] != applied_draft_run["contextSnapshot"]
                or persisted_draft_run["decisionSnapshot"] != applied_draft_run["decisionSnapshot"]
            ):
                raise RuntimeError("Agent draft smoke Run readback did not match execute snapshots")
            duplicate_draft_run = client.post(
                f"/api/agent/runs/{draft_run['id']}/execute",
                json={},
            )
            duplicate_draft_run.raise_for_status()
            if len(store.list_goal_tasks(draft_goal_id)) != 1:
                raise RuntimeError("Agent draft smoke duplicated the formal task on resume")

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
                "chunk_count": len(chunks),
                "chunk_readback": len(chunks_get) == len(chunks),
                "chunk_search_count": len(chunks_search),
                "agent_mode": agent_answer["mode"],
                "agent_reference_count": len(agent_answer["references"]),
                "agent_from_material": agent_answer["isFromMaterial"],
                "agent_confidence": agent_answer["confidence"],
                "agent_next_action": agent_answer["nextAction"],
                "agent_requires_confirmation": agent_answer["requiresConfirmation"],
                "agent_context_goal_count": agent_context["summary"]["goalCount"],
                "agent_context_material_count": agent_context["summary"]["materialTotal"],
                "agent_context_task_total": agent_context["summary"]["taskTotal"],
                "agent_context_flashcard_total": agent_context["summary"]["flashcardTotal"],
                "agent_decision_mode": agent_decision["mode"],
                "agent_decision_next_action": agent_decision["nextAction"],
                "agent_decision_problem_count": len(agent_decision["problems"]),
                "agent_decision_action_count": len(agent_decision["proposedActions"]),
                "agent_hybrid_decision_mode": agent_hybrid_decision["mode"],
                "agent_hybrid_requested_mode": agent_hybrid_decision["requestedMode"],
                "agent_hybrid_fallback": bool(agent_hybrid_decision["fallbackReason"]),
                "agent_hybrid_guard_status": agent_hybrid_decision.get("decisionGuard", {}).get("status"),
                "agent_hybrid_provider": hybrid_metadata.get("provider"),
                "agent_hybrid_prompt_version": hybrid_metadata.get("promptVersion"),
                "agent_tool_count": len(agent_tools),
                "agent_decision_first_tool": first_action["toolName"],
                "agent_decision_first_risk": first_action["riskLevel"],
                "agent_decision_first_draft_only": first_action["draftOnly"],
                "agent_action_log_count": len(action_logs),
                "agent_action_log_status": updated_action_log["status"],
                "agent_action_log_applied_status": applied_action_log["status"],
                "agent_run_count": len(agent_runs),
                "agent_run_status": updated_agent_run["status"],
                "agent_run_feedback_total": updated_agent_run["feedbackSummary"]["total"],
                "agent_run_latest_feedback_status": (
                    updated_agent_run["feedbackSummary"]["latestStatus"]
                ),
                "agent_loop_status": executed_loop_run["status"],
                "agent_loop_stop_reason": executed_loop_run["stopReason"],
                "agent_loop_step_count": len(executed_loop_run["steps"]),
                "agent_loop_error": executed_loop_run["error"],
                "agent_loop_reflection": bool(
                    executed_loop_run["decisionSnapshot"].get("reflection")
                ),
                "agent_loop_step_errors": [
                    step["error"] for step in executed_loop_run["steps"] if step["error"]
                ],
                "agent_draft_waiting_status": executed_draft_run["status"],
                "agent_draft_run_status": applied_draft_run["status"],
                "agent_draft_step_tool": draft_step["toolName"],
                "agent_draft_created_count": draft_step["toolOutput"]["data"]["createdCount"],
                "agent_draft_reused_count": draft_step["toolOutput"]["data"]["reusedCount"],
                "agent_draft_status": applied_draft.json()["data"]["status"],
                "agent_draft_list_count": len(persisted_drafts),
                "agent_draft_apply_count": applied_draft_step["toolOutput"]["data"]["appliedCount"],
                "agent_draft_formal_task_count": len(store.list_goal_tasks(draft_goal_id)),
                "agent_draft_readback_status": applied_draft_run["status"],
                "agent_draft_readback_task_total": (
                    applied_draft_run["contextSnapshot"]["summary"]["taskTotal"]
                ),
                "agent_draft_readback_applied_count": (
                    applied_draft_run["contextSnapshot"]["drafts"]["appliedCount"]
                ),
                "agent_draft_snapshot_matches_get": (
                    persisted_draft_run["contextSnapshot"] == applied_draft_run["contextSnapshot"]
                    and persisted_draft_run["decisionSnapshot"] == applied_draft_run["decisionSnapshot"]
                ),
                "agent_draft_duplicate_task_count": len(store.list_goal_tasks(draft_goal_id)),
                "agent_context_flashcard_before_confirmed_write": (
                    agent_context_before_custom_flashcard["summary"]["flashcardTotal"]
                ),
                "agent_context_flashcard_after_confirmed_write": (
                    agent_context_after_custom_flashcard["summary"]["flashcardTotal"]
                ),
                "agent_decision_after_confirmed_write_has_review_queue": (
                    "review_queue"
                    in [
                        problem["type"]
                        for problem in agent_decision_after_custom_flashcard["problems"]
                    ]
                ),
                "qa_record_count": len(material_qa_records),
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
