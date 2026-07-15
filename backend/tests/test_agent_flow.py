import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import (
    agent_context_service,
    agent_decision_provider,
    agent_decision_service,
    agent_draft_service,
    agent_loop_service,
    agent_run_service,
    agent_action_log_service,
    agent_tool_execution_service,
    agent_tool_registry_service,
    store,
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
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


def create_material(
    goal_id: str,
    title: str,
    content: str,
    generate_chunks: bool = True,
) -> dict:
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

    if generate_chunks:
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
    assert data["nextAction"] == "create_flashcards"
    assert data["requiresConfirmation"] is True
    assert data["insufficiencyReason"] == ""
    assert data["reviewDrafts"]
    assert data["reviewDrafts"][0]["type"] == "flashcard"
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
    assert history[0]["nextAction"] == data["nextAction"]
    assert history[0]["requiresConfirmation"] == data["requiresConfirmation"]
    assert history[0]["insufficiencyReason"] == data["insufficiencyReason"]
    assert history[0]["reviewDrafts"] == data["reviewDrafts"]


def test_agent_context_collects_learning_state():
    goal = create_goal("Context goal")
    material = create_material(
        goal["id"],
        "Context notes",
        "Retrieval practice connects materials, quiz feedback, and review cards.",
    )
    material_id = material["id"]

    plan_response = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 2, "regenerate": True},
    )
    assert plan_response.status_code == 200
    task_id = plan_response.json()["data"][0]["id"]
    assert client.post(f"/api/tasks/{task_id}/checkin", json={"done": True}).status_code == 200

    assert client.post(f"/api/materials/{material_id}/summarize").status_code == 200
    flashcard_response = client.post(
        f"/api/materials/{material_id}/flashcards/custom",
        json={"front": "What links the loop?", "back": "Material, quiz, and review state."},
    )
    assert flashcard_response.status_code == 200
    flashcard = flashcard_response.json()["data"]
    assert client.patch(
        f"/api/materials/{material_id}/flashcards/{flashcard['id']}",
        json={"status": "review"},
    ).status_code == 200

    quiz_response = client.post(f"/api/materials/{material_id}/quiz", params={"count": 1})
    assert quiz_response.status_code == 200
    quiz = quiz_response.json()["data"][0]
    attempt_response = client.post(
        f"/api/materials/{material_id}/quiz/{quiz['id']}/answer",
        json={"answer": "not sure"},
    )
    assert attempt_response.status_code == 200

    ask_response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "materialId": material_id,
            "question": "What does retrieval practice connect?",
        },
    )
    assert ask_response.status_code == 200

    context_response = client.get("/api/agent/context", params={"goalId": goal["id"]})

    assert context_response.status_code == 200
    context = context_response.json()["data"]
    assert context["scope"]["goalId"] == goal["id"]
    assert context["summary"]["goalCount"] == 1
    assert context["summary"]["materialTotal"] == 1
    assert context["summary"]["taskTotal"] == 2
    assert context["summary"]["taskCompleted"] == 1
    assert context["summary"]["flashcardTotal"] == 1
    assert context["goals"][0]["id"] == goal["id"]
    assert context["tasks"][0]["completed"] == 1
    assert context["materials"][0]["id"] == material_id
    assert context["materials"][0]["hasSummary"] is True
    assert context["materials"][0]["chunkCount"] >= 1
    assert context["materials"][0]["qaCount"] == 1
    assert context["materials"][0]["recentQa"][0]["nextAction"] == ask_response.json()["data"]["nextAction"]
    assert context["review"]["review"] == 1
    assert context["review"]["materialsNeedingReview"][0]["materialId"] == material_id
    assert context["quiz"]["questionTotal"] == 1
    assert context["quiz"]["attemptTotal"] == 1
    assert context["progress"][0]["goal_id"] == goal["id"]


def test_agent_context_supports_global_scope_and_missing_goal():
    first_goal = create_goal("First context goal")
    second_goal = create_goal("Second context goal")
    first_material = create_material(
        first_goal["id"],
        "First context notes",
        "First material has generated chunks for Agent context.",
    )
    second_material = create_material(
        second_goal["id"],
        "Second context notes",
        "Second material is also visible in global context.",
    )

    response = client.get("/api/agent/context")

    assert response.status_code == 200
    context = response.json()["data"]
    assert context["scope"]["goalId"] is None
    assert context["summary"]["goalCount"] == 2
    assert {goal["id"] for goal in context["goals"]} == {first_goal["id"], second_goal["id"]}
    assert {material["id"] for material in context["materials"]} == {
        first_material["id"],
        second_material["id"],
    }

    missing_response = client.get("/api/agent/context", params={"goalId": "goal_missing"})
    assert missing_response.status_code == 404


def test_agent_decision_prioritizes_context_problems():
    goal = create_goal("Decision goal")
    material = create_material(
        goal["id"],
        "Decision notes",
        "Decision making should use materials, quiz attempts, and review cards.",
    )
    material_id = material["id"]

    plan_response = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 1, "regenerate": True},
    )
    assert plan_response.status_code == 200
    assert client.post(f"/api/materials/{material_id}/summarize").status_code == 200
    flashcard_response = client.post(
        f"/api/materials/{material_id}/flashcards/custom",
        json={"front": "What needs review?", "back": "Weak points need review."},
    )
    flashcard = flashcard_response.json()["data"]
    assert client.patch(
        f"/api/materials/{material_id}/flashcards/{flashcard['id']}",
        json={"status": "review"},
    ).status_code == 200
    quiz_response = client.post(f"/api/materials/{material_id}/quiz", params={"count": 1})
    quiz = quiz_response.json()["data"][0]
    assert client.post(
        f"/api/materials/{material_id}/quiz/{quiz['id']}/answer",
        json={"answer": "not sure"},
    ).status_code == 200

    decision_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})

    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    assert decision["mode"] == "rule-based"
    assert decision["scope"]["goalId"] == goal["id"]
    assert decision["stateSummary"]
    assert decision["problems"]
    problem_types = {problem["type"] for problem in decision["problems"]}
    assert "weak_quiz_attempts" in problem_types
    assert "review_queue" in problem_types
    action_types = [action["type"] for action in decision["proposedActions"]]
    assert "create_flashcards" in action_types
    for action in decision["proposedActions"]:
        assert action["toolName"]
        assert action["riskLevel"] in {"low", "medium", "high"}
        assert "draftOnly" in action
        assert action["applyTarget"]
    assert decision["nextAction"] == decision["proposedActions"][0]["type"]
    assert decision["reason"]
    assert decision["requiresConfirmation"] is False
    assert decision["feedbackMemory"]["recentActionCount"] == 0


def test_agent_tools_registry_is_exposed_and_decision_actions_are_enriched():
    tools_response = client.get("/api/agent/tools")

    assert tools_response.status_code == 200
    tools = tools_response.json()["data"]
    tool_names = {tool["name"] for tool in tools}
    assert {
        "review_material",
        "search_materials",
        "answer_with_sources",
        "create_review_draft",
        "create_task_draft",
    }.issubset(tool_names)

    goal = create_goal("Tool registry goal")
    decision_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})

    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    action = decision["proposedActions"][0]
    assert action["type"] == "create_followup_tasks"
    assert action["toolName"] == "create_task_draft"
    assert action["riskLevel"] == "medium"
    assert action["draftOnly"] is True
    assert action["applyTarget"] == "task_drafts"
    assert action["requiresConfirmation"] is False


def test_agent_decision_hybrid_accepts_valid_llm_json(monkeypatch):
    class FakeDecisionProvider:
        mode = "openai-compatible"
        model = "test-decision-model"

        def _post_chat_completion(self, payload):
            assert payload["response_format"]["type"] == "json_object"
            assert '"availableTools"' in payload["messages"][1]["content"]
            assert '"review_material"' in payload["messages"][1]["content"]
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"stateSummary":"LLM sees a stable learning state.",'
                                '"problems":[{"type":"review_queue","severity":"low","message":"Review cards are waiting.","evidence":"1 card"}],'
                                '"nextAction":"review_material",'
                                '"reason":"Review existing material before adding more.",'
                                '"requiresConfirmation":false,'
                                '"proposedActions":[{"type":"review_material","label":"Review now","description":"Open the review queue.","payload":{},"requiresConfirmation":false}],'
                                '"reflection":"Prefer a low-risk review action."}'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        agent_decision_provider.llm_provider,
        "get_llm_provider",
        lambda: FakeDecisionProvider(),
    )
    goal = create_goal("Hybrid decision goal")

    response = client.post(
        "/api/agent/decide",
        params={"goalId": goal["id"], "decisionMode": "hybrid"},
    )

    assert response.status_code == 200
    decision = response.json()["data"]
    assert decision["mode"] == "hybrid"
    assert decision["requestedMode"] == "hybrid"
    assert decision["fallbackReason"] == ""
    assert decision["nextAction"] == "review_material"
    assert decision["reflection"] == ""
    assert decision["providerMetadata"]["provider"] == "openai-compatible"
    assert decision["providerMetadata"]["promptVersion"] == "batch-c-v1"
    assert decision["decisionGuard"]["status"] == "accepted"
    assert decision["decisionGuard"]["interventions"] == []
    assert decision["proposedActions"][0]["toolName"] == "review_material"
    assert decision["proposedActions"][0]["riskLevel"] == "low"


def test_agent_decision_guard_allows_llm_draft_creation_without_confirmation(monkeypatch):
    class RiskyDecisionProvider:
        mode = "openai-compatible"
        model = "test-decision-model"

        def _post_chat_completion(self, payload):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"stateSummary":"LLM wants to plan tasks.",'
                                '"problems":[],'
                                '"nextAction":"reschedule_tasks",'
                                '"reason":"Overdue tasks should be rescheduled.",'
                                '"requiresConfirmation":false,'
                                '"proposedActions":[{"type":"reschedule_tasks","label":"Reschedule now","description":"Move overdue tasks.","payload":{},"requiresConfirmation":false}],'
                                '"reflection":"Draft creation does not write a formal task."}'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        agent_decision_provider.llm_provider,
        "get_llm_provider",
        lambda: RiskyDecisionProvider(),
    )
    goal = create_goal("Decision guard goal")

    response = client.post(
        "/api/agent/decide",
        params={"goalId": goal["id"], "decisionMode": "hybrid"},
    )

    assert response.status_code == 200
    decision = response.json()["data"]
    action = decision["proposedActions"][0]
    assert decision["mode"] == "hybrid"
    assert decision["requiresConfirmation"] is False
    assert decision["decisionGuard"]["status"] == "accepted"
    assert decision["decisionGuard"]["interventions"] == []
    assert action["type"] == "reschedule_tasks"
    assert action["toolName"] == "create_task_draft"
    assert action["riskLevel"] == "medium"
    assert action["draftOnly"] is True
    assert action["requiresConfirmation"] is False


def test_agent_decision_hybrid_falls_back_on_invalid_llm_action(monkeypatch):
    class BadDecisionProvider:
        mode = "openai-compatible"
        model = "test-decision-model"

        def _post_chat_completion(self, payload):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"stateSummary":"bad",'
                                '"nextAction":"delete_everything",'
                                '"reason":"bad action",'
                                '"proposedActions":[{"type":"delete_everything"}]}'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        agent_decision_provider.llm_provider,
        "get_llm_provider",
        lambda: BadDecisionProvider(),
    )
    goal = create_goal("Hybrid fallback goal")

    response = client.post(
        "/api/agent/decide",
        params={"goalId": goal["id"], "decisionMode": "hybrid"},
    )

    assert response.status_code == 200
    decision = response.json()["data"]
    assert decision["mode"] == "rule-based"
    assert decision["requestedMode"] == "hybrid"
    assert "Decision Guard rejected model output" in decision["fallbackReason"]
    assert decision["decisionGuard"]["status"] == "fallback"


def test_agent_decision_guard_rejects_invalid_tool_payload(monkeypatch):
    class BadPayloadProvider:
        mode = "openai-compatible"
        model = "test-decision-model"

        def _post_chat_completion(self, payload):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"stateSummary":"bad payload",'
                                '"problems":[],'
                                '"nextAction":"review_material",'
                                '"reason":"bad payload",'
                                '"requiresConfirmation":false,'
                                '"proposedActions":[{"type":"review_material",'
                                '"payload":{"unexpected":true}}],'
                                '"reflection":""}'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        agent_decision_provider.llm_provider,
        "get_llm_provider",
        lambda: BadPayloadProvider(),
    )
    goal = create_goal("Guard payload validation")

    response = client.post(
        "/api/agent/decide",
        params={"goalId": goal["id"], "decisionMode": "hybrid"},
    )

    assert response.status_code == 200
    decision = response.json()["data"]
    assert decision["mode"] == "rule-based"
    assert "unknown fields" in decision["fallbackReason"]
    assert decision["decisionGuard"]["status"] == "fallback"
    assert decision["decisionGuard"]["errors"]
    assert decision["nextAction"] == "create_followup_tasks"
    assert decision["proposedActions"][0]["toolName"] == "create_task_draft"


def test_agent_decision_avoids_recently_rejected_action_type():
    goal = create_goal("Feedback memory goal")
    material = create_material(
        goal["id"],
        "Feedback memory notes",
        "Feedback memory should prevent repeated Agent suggestions.",
    )
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    flashcard_response = client.post(
        f"/api/materials/{material['id']}/flashcards/custom",
        json={"front": "What should be remembered?", "back": "Rejected suggestions."},
    )
    flashcard = flashcard_response.json()["data"]
    assert client.patch(
        f"/api/materials/{material['id']}/flashcards/{flashcard['id']}",
        json={"status": "review"},
    ).status_code == 200
    quiz_response = client.post(f"/api/materials/{material['id']}/quiz", params={"count": 1})
    quiz = quiz_response.json()["data"][0]
    assert client.post(
        f"/api/materials/{material['id']}/quiz/{quiz['id']}/answer",
        json={"answer": "not sure"},
    ).status_code == 200

    first_decision = client.post("/api/agent/decide", params={"goalId": goal["id"]}).json()["data"]
    assert first_decision["nextAction"] == "create_flashcards"

    assert client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": "create_flashcards",
            "observation": first_decision["stateSummary"],
            "decision": first_decision,
            "proposedPayload": first_decision["proposedActions"][0],
            "status": "rejected",
        },
    ).status_code == 200

    second_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})

    assert second_response.status_code == 200
    second_decision = second_response.json()["data"]
    action_types = [action["type"] for action in second_decision["proposedActions"]]
    assert "create_flashcards" not in action_types
    assert second_decision["nextAction"] == "review_material"
    assert second_decision["feedbackMemory"]["recentlyRejected"][0]["actionType"] == "create_flashcards"
    assert "rejected action type" in second_decision["reason"]


def test_agent_decision_remembers_accepted_action_before_repeating_it():
    goal = create_goal("Accepted memory goal")
    first_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})
    assert first_response.status_code == 200
    first_decision = first_response.json()["data"]
    assert first_decision["nextAction"] == "create_followup_tasks"

    assert client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": "create_followup_tasks",
            "observation": first_decision["stateSummary"],
            "decision": first_decision,
            "proposedPayload": first_decision["proposedActions"][0],
            "status": "accepted",
        },
    ).status_code == 200

    second_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})

    assert second_response.status_code == 200
    second_decision = second_response.json()["data"]
    assert second_decision["feedbackMemory"]["pendingAccepted"][0]["actionType"] == "create_followup_tasks"
    assert second_decision["proposedActions"][0]["status"] == "accepted"
    assert second_decision["proposedActions"][0]["payload"]["actionLogId"]
    assert second_decision["proposedActions"][0]["label"].startswith("Continue accepted action")


def test_agent_decision_handles_empty_context_and_missing_goal():
    response = client.post("/api/agent/decide")

    assert response.status_code == 200
    decision = response.json()["data"]
    assert decision["nextAction"] == "create_followup_tasks"
    assert decision["problems"][0]["type"] == "missing_goal"
    assert decision["requiresConfirmation"] is False

    missing_response = client.post("/api/agent/decide", params={"goalId": "goal_missing"})
    assert missing_response.status_code == 404


def test_agent_action_logs_persist_user_feedback():
    goal = create_goal("Action log goal")
    decision_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})
    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    proposed_action = decision["proposedActions"][0]

    create_response = client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": proposed_action["type"],
            "observation": decision["stateSummary"],
            "decision": decision,
            "proposedPayload": proposed_action,
            "status": "accepted",
        },
    )

    assert create_response.status_code == 200
    action_log = create_response.json()["data"]
    assert action_log["id"].startswith("actionlog_")
    assert action_log["goalId"] == goal["id"]
    assert action_log["actionType"] == proposed_action["type"]
    assert action_log["observation"] == decision["stateSummary"]
    assert action_log["decision"]["nextAction"] == decision["nextAction"]
    assert action_log["proposedPayload"]["type"] == proposed_action["type"]
    assert action_log["status"] == "accepted"
    assert action_log["createdAt"]
    assert action_log["updatedAt"]

    list_response = client.get("/api/agent/action-logs", params={"goalId": goal["id"]})
    assert list_response.status_code == 200
    logs = list_response.json()["data"]
    assert len(logs) == 1
    assert logs[0]["id"] == action_log["id"]

    update_response = client.patch(
        f"/api/agent/action-logs/{action_log['id']}",
        json={"status": "later"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "later"

    applied_response = client.patch(
        f"/api/agent/action-logs/{action_log['id']}",
        json={"status": "applied"},
    )
    assert applied_response.status_code == 200
    assert applied_response.json()["data"]["status"] == "applied"


def test_agent_run_records_context_decision_and_feedback_summary():
    goal = create_goal("Agent run goal")
    material = create_material(
        goal["id"],
        "Agent run notes",
        "Agent runs preserve context and decision snapshots.",
    )

    create_response = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "trigger": "manual"},
    )

    assert create_response.status_code == 200
    agent_run = create_response.json()["data"]
    assert agent_run["id"].startswith("agentrun_")
    assert agent_run["goalId"] == goal["id"]
    assert agent_run["trigger"] == "manual"
    assert agent_run["decisionMode"] == "hybrid"
    assert agent_run["status"] == "decided"
    assert agent_run["contextSummary"]["goalCount"] == 1
    assert agent_run["contextSummary"]["materialTotal"] == 1
    assert agent_run["decisionSummary"]["nextAction"]
    assert agent_run["feedbackSummary"]["total"] == 0
    assert agent_run["contextSnapshot"]["materials"][0]["id"] == material["id"]
    assert agent_run["decisionSnapshot"]["scope"]["goalId"] == goal["id"]
    assert agent_run["decisionSnapshot"]["requestedMode"] == "hybrid"
    assert agent_run["decisionSnapshot"]["providerMetadata"]["provider"] == "mock"

    list_response = client.get("/api/agent/runs", params={"goalId": goal["id"]})
    assert list_response.status_code == 200
    runs = list_response.json()["data"]
    assert len(runs) == 1
    assert runs[0]["id"] == agent_run["id"]
    assert "contextSnapshot" not in runs[0]
    assert "decisionSnapshot" not in runs[0]

    proposed_action = agent_run["decisionSnapshot"]["proposedActions"][0]
    assert client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": proposed_action["type"],
            "observation": agent_run["decisionSnapshot"]["stateSummary"],
            "decision": agent_run["decisionSnapshot"],
            "proposedPayload": proposed_action,
            "status": "accepted",
        },
    ).status_code == 200

    update_response = client.patch(
        f"/api/agent/runs/{agent_run['id']}",
        json={"status": "feedback_recorded"},
    )

    assert update_response.status_code == 200
    updated_run = update_response.json()["data"]
    assert updated_run["status"] == "feedback_recorded"
    assert updated_run["feedbackSummary"]["total"] == 1
    assert updated_run["feedbackSummary"]["byStatus"]["accepted"] == 1
    assert updated_run["feedbackSummary"]["latestStatus"] == "accepted"


def test_agent_loop_applies_accepted_task_draft_from_the_same_run():
    goal = create_goal("Agent loop goal")
    create_material(
        goal["id"],
        "Loop material",
        "The Agent should observe, decide, call a tool, and inspect the result.",
        generate_chunks=False,
    )
    run = client.post(
        "/api/agent/runs",
        json={
            "goalId": goal["id"],
            "objective": "Prepare the next grounded learning action.",
            "decisionMode": "rule-based",
            "maxSteps": 4,
        },
    ).json()["data"]

    first_execute = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert first_execute.status_code == 200
    waiting_run = first_execute.json()["data"]
    assert waiting_run["status"] == "waiting_confirmation"
    assert waiting_run["stopReason"] == "confirmation_required"
    assert waiting_run["currentStep"] == 3
    assert [step["status"] for step in waiting_run["steps"]] == [
        "completed",
        "completed",
        "waiting_confirmation",
    ]
    assert waiting_run["steps"][0]["toolName"] == "review_material"
    assert "Inspected 1 material" in waiting_run["steps"][0]["toolOutput"]["observation"]
    assert waiting_run["steps"][0]["toolOutput"]["data"]["generatedChunkSets"] == 1
    assert waiting_run["steps"][0]["toolOutput"]["data"]["generatedSummaries"] == 1
    processed_material = waiting_run["contextSnapshot"]["materials"][0]
    assert processed_material["chunkCount"] >= 1
    assert processed_material["hasSummary"] is True

    draft_step = waiting_run["steps"][1]
    assert draft_step["toolName"] == "create_task_draft"
    assert draft_step["toolOutput"]["data"]["createdCount"] == 1
    assert draft_step["toolOutput"]["data"]["reusedCount"] == 0
    task_draft = draft_step["toolOutput"]["data"]["drafts"][0]
    assert task_draft["id"].startswith("agentdraft_")
    assert task_draft["goalId"] == goal["id"]
    assert task_draft["stepId"] == draft_step["id"]
    assert task_draft["status"] == "proposed"
    assert task_draft["payload"].keys() >= {
        "goalId",
        "title",
        "detail",
        "date",
        "priority",
        "sourceReason",
    }
    assert store.list_goal_tasks(goal["id"]) == []
    draft_readback = client.get(f"/api/agent/drafts/{task_draft['id']}")
    assert draft_readback.status_code == 200
    assert draft_readback.json()["data"]["id"] == task_draft["id"]
    apply_step = waiting_run["steps"][2]
    assert apply_step["toolName"] == "apply_confirmed_draft"
    apply_action_log_id = apply_step["actionLogId"]
    assert client.patch(
        f"/api/agent/action-logs/{apply_action_log_id}",
        json={"status": "accepted"},
    ).json()["data"]["status"] == "accepted"
    assert client.get(f"/api/agent/drafts/{task_draft['id']}").json()["data"]["status"] == "confirmed"

    resumed_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert resumed_response.status_code == 200
    completed_run = resumed_response.json()["data"]
    assert completed_run["status"] == "completed"
    assert completed_run["steps"][2]["status"] == "completed"
    apply_output = completed_run["steps"][2]["toolOutput"]
    assert apply_output["data"]["appliedCount"] == 1
    assert apply_output["data"]["reusedCount"] == 0
    assert len(store.list_goal_tasks(goal["id"])) == 1
    applied_draft = client.get(f"/api/agent/drafts/{task_draft['id']}").json()["data"]
    assert applied_draft["status"] == "applied"
    assert len(applied_draft["appliedEntityIds"]) == 1
    action_log = client.get(
        "/api/agent/action-logs",
        params={"goalId": goal["id"]},
    ).json()["data"]
    assert any(log["id"] == apply_action_log_id and log["status"] == "applied" for log in action_log)
    assert completed_run["contextSnapshot"]["summary"]["taskTotal"] == 1

    duplicate_resume = client.post(f"/api/agent/runs/{run['id']}/execute", json={})
    assert duplicate_resume.status_code == 200
    assert len(store.list_goal_tasks(goal["id"])) == 1
    retry_output = agent_tool_execution_service.execute_action(
        completed_run["steps"][2]["actionSnapshot"],
        goal["id"],
        None,
        run["objective"],
        action_log_id=apply_action_log_id,
    )
    assert retry_output["data"]["appliedCount"] == 0
    assert retry_output["data"]["reusedCount"] == 1
    assert retry_output["data"]["appliedEntityIds"] == applied_draft["appliedEntityIds"]
    assert len(store.list_goal_tasks(goal["id"])) == 1


def test_agent_review_draft_persists_retries_idempotently_and_cascades_with_run():
    goal = create_goal("Review draft goal")
    material = create_material(
        goal["id"],
        "Review draft notes",
        "Review drafts should remain proposed until a later confirmed write.",
    )
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    planned_tasks = client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 1, "regenerate": True},
    ).json()["data"]
    quiz = client.post(f"/api/materials/{material['id']}/quiz", params={"count": 1}).json()["data"][0]
    assert client.post(
        f"/api/materials/{material['id']}/quiz/{quiz['id']}/answer",
        json={"answer": "incorrect"},
    ).status_code == 200

    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 1},
    ).json()["data"]
    execute_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert execute_response.status_code == 200
    executed_run = execute_response.json()["data"]
    assert executed_run["status"] == "max_steps"
    step = executed_run["steps"][0]
    assert step["toolName"] == "create_review_draft"
    output = step["toolOutput"]
    assert output["data"]["createdCount"] == 1
    assert output["data"]["reusedCount"] == 0
    draft = output["data"]["drafts"][0]
    assert draft["id"].startswith("agentdraft_")
    assert draft["runId"] == run["id"]
    assert draft["stepId"] == step["id"]
    assert draft["draftType"] == "review"
    assert draft["status"] == "proposed"
    assert draft["payload"].keys() >= {"materialId", "front", "back", "sourceReason"}
    assert len(store.list_goal_tasks(goal["id"])) == len(planned_tasks)
    assert client.get(f"/api/materials/{material['id']}/flashcards").json()["data"] == []

    retry_output = agent_tool_execution_service.execute_action(
        step["actionSnapshot"],
        goal["id"],
        None,
        run["objective"],
        run_id=run["id"],
        step_id=step["id"],
    )
    assert retry_output["data"]["createdCount"] == 0
    assert retry_output["data"]["reusedCount"] == 1
    assert retry_output["data"]["drafts"][0]["id"] == draft["id"]

    filtered = client.get(
        "/api/agent/drafts",
        params={"goalId": goal["id"], "draftType": "review", "status": "proposed"},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["data"]] == [draft["id"]]
    assert client.get(
        "/api/agent/drafts",
        params={"goalId": goal["id"], "draftType": "task", "status": "proposed"},
    ).json()["data"] == []
    assert agent_draft_service.is_valid_status_transition("proposed", "confirmed")
    assert agent_draft_service.is_valid_status_transition("proposed", "rejected")
    assert agent_draft_service.is_valid_status_transition("confirmed", "applied")
    assert not agent_draft_service.is_valid_status_transition("applied", "confirmed")
    assert not agent_draft_service.is_valid_status_transition("rejected", "applied")

    with store.db_connection() as conn:
        conn.execute("DELETE FROM agent_runs WHERE id = ?", (run["id"],))
    assert client.get(f"/api/agent/drafts/{draft['id']}").status_code == 404


def test_agent_drafts_are_isolated_by_user_header():
    first_user = client.post(
        "/api/auth/register",
        json={"name": "Draft First", "email": "first-draft@example.com", "password": "secret123"},
    ).json()["data"]
    second_user = client.post(
        "/api/auth/register",
        json={"name": "Draft Second", "email": "second-draft@example.com", "password": "secret123"},
    ).json()["data"]
    first_headers = {"X-User-Id": first_user["id"]}
    second_headers = {"X-User-Id": second_user["id"]}

    first_goal = client.post(
        "/api/goals",
        headers=first_headers,
        json={
            "name": "First draft goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    ).json()["data"]
    second_goal = client.post(
        "/api/goals",
        headers=second_headers,
        json={
            "name": "Second draft goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    ).json()["data"]

    first_run = client.post(
        "/api/agent/runs",
        headers=first_headers,
        json={"goalId": first_goal["id"], "maxSteps": 1},
    ).json()["data"]
    second_run = client.post(
        "/api/agent/runs",
        headers=second_headers,
        json={"goalId": second_goal["id"], "maxSteps": 1},
    ).json()["data"]
    first_draft = client.post(
        f"/api/agent/runs/{first_run['id']}/execute",
        headers=first_headers,
        json={},
    ).json()["data"]["steps"][0]["toolOutput"]["data"]["drafts"][0]
    second_draft = client.post(
        f"/api/agent/runs/{second_run['id']}/execute",
        headers=second_headers,
        json={},
    ).json()["data"]["steps"][0]["toolOutput"]["data"]["drafts"][0]

    first_list = client.get(
        "/api/agent/drafts",
        headers=first_headers,
        params={"goalId": first_goal["id"], "draftType": "task", "status": "proposed"},
    )
    assert first_list.status_code == 200
    assert [item["id"] for item in first_list.json()["data"]] == [first_draft["id"]]
    assert client.get(
        f"/api/agent/drafts/{second_draft['id']}",
        headers=first_headers,
    ).status_code == 404
    assert client.get(
        "/api/agent/drafts",
        headers=first_headers,
        params={"goalId": second_goal["id"]},
    ).status_code == 404


def test_agent_loop_rejects_confirmed_draft_without_formal_write():
    goal = create_goal("Rejected draft goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 3},
    ).json()["data"]

    waiting_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert waiting_response.status_code == 200
    waiting_run = waiting_response.json()["data"]
    assert waiting_run["status"] == "waiting_confirmation"
    draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert apply_step["toolName"] == "apply_confirmed_draft"
    reject_response = client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "rejected"},
    )
    assert reject_response.status_code == 200
    assert client.get(f"/api/agent/drafts/{draft['id']}").json()["data"]["status"] == "rejected"

    resumed_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert resumed_response.status_code == 200
    rejected_run = resumed_response.json()["data"]
    assert rejected_run["status"] == "completed"
    assert rejected_run["steps"][1]["status"] == "rejected"
    assert store.list_goal_tasks(goal["id"]) == []


def test_agent_loop_applies_review_draft_as_flashcard():
    goal = create_goal("Review apply goal")
    material = create_material(
        goal["id"],
        "Review apply material",
        "A confirmed review draft should become exactly one flashcard.",
    )
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    assert client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 1, "regenerate": True},
    ).status_code == 200
    quiz = client.post(f"/api/materials/{material['id']}/quiz", params={"count": 1}).json()["data"][0]
    assert client.post(
        f"/api/materials/{material['id']}/quiz/{quiz['id']}/answer",
        json={"answer": "incorrect"},
    ).status_code == 200
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 3},
    ).json()["data"]

    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    assert waiting_run["status"] == "waiting_confirmation"
    review_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    assert review_draft["draftType"] == "review"
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    completed_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    assert completed_run["steps"][1]["toolOutput"]["data"]["appliedCount"] == 1
    applied_draft = client.get(f"/api/agent/drafts/{review_draft['id']}").json()["data"]
    assert applied_draft["status"] == "applied"
    flashcards = client.get(f"/api/materials/{material['id']}/flashcards").json()["data"]
    assert [card["id"] for card in flashcards] == applied_draft["appliedEntityIds"]


def test_confirmed_draft_apply_rolls_back_formal_writes_on_payload_error():
    goal = create_goal("Draft transaction rollback goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 1},
    ).json()["data"]
    draft_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    valid_draft = draft_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    source_step = draft_run["steps"][0]
    invalid_draft = agent_draft_service.create_or_reuse_drafts(
        draft_type="task",
        payloads=[
            {
                "goalId": goal["id"],
                "detail": "This payload intentionally omits a title.",
                "date": store.today_iso(),
                "priority": "medium",
                "sourceReason": "Transaction rollback test.",
            }
        ],
        user_id=None,
        goal_id=goal["id"],
        run_id=run["id"],
        step_id=source_step["id"],
        tool_name="create_task_draft",
    )[0][0]
    action = agent_tool_registry_service.enrich_action(
        {
            "type": "apply_confirmed_draft",
            "label": "Apply rollback batch",
            "description": "Apply a batch that should roll back on validation failure.",
            "payload": {"draftIds": [valid_draft["id"], invalid_draft["id"]]},
            "requiresConfirmation": True,
            "status": "proposed",
        }
    )
    action_log = client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": "apply_confirmed_draft",
            "proposedPayload": {**action, "draftIds": action["payload"]["draftIds"]},
            "status": "proposed",
        },
    ).json()["data"]
    assert client.patch(
        f"/api/agent/action-logs/{action_log['id']}",
        json={"status": "accepted"},
    ).status_code == 200

    with pytest.raises(ValueError, match="title"):
        agent_tool_execution_service.execute_action(
            action,
            goal["id"],
            None,
            action_log_id=action_log["id"],
        )

    assert store.list_goal_tasks(goal["id"]) == []
    for draft_id in [valid_draft["id"], invalid_draft["id"]]:
        assert client.get(f"/api/agent/drafts/{draft_id}").json()["data"]["status"] == "confirmed"
    action_logs = client.get("/api/agent/action-logs", params={"goalId": goal["id"]}).json()["data"]
    assert any(log["id"] == action_log["id"] and log["status"] == "accepted" for log in action_logs)


def test_confirmed_draft_action_log_rejects_cross_user_draft_ids():
    first_user = client.post(
        "/api/auth/register",
        json={"name": "Apply First", "email": "apply-first@example.com", "password": "secret123"},
    ).json()["data"]
    second_user = client.post(
        "/api/auth/register",
        json={"name": "Apply Second", "email": "apply-second@example.com", "password": "secret123"},
    ).json()["data"]
    first_headers = {"X-User-Id": first_user["id"]}
    second_headers = {"X-User-Id": second_user["id"]}

    def create_owned_goal(headers: dict, name: str) -> dict:
        response = client.post(
            "/api/goals",
            headers=headers,
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

    first_goal = create_owned_goal(first_headers, "First apply goal")
    second_goal = create_owned_goal(second_headers, "Second apply goal")
    second_run = client.post(
        "/api/agent/runs",
        headers=second_headers,
        json={"goalId": second_goal["id"], "maxSteps": 3},
    ).json()["data"]
    second_waiting_run = client.post(
        f"/api/agent/runs/{second_run['id']}/execute",
        headers=second_headers,
        json={},
    ).json()["data"]
    second_draft = second_waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    malicious_action = agent_tool_registry_service.enrich_action(
        {
            "type": "apply_confirmed_draft",
            "label": "Apply other user's draft",
            "description": "This must be rejected by owner isolation.",
            "payload": {"draftIds": [second_draft["id"]]},
            "requiresConfirmation": True,
            "status": "proposed",
        }
    )
    malicious_log = client.post(
        "/api/agent/action-logs",
        headers=first_headers,
        json={
            "goalId": first_goal["id"],
            "actionType": "apply_confirmed_draft",
            "proposedPayload": {
                **malicious_action,
                "draftIds": malicious_action["payload"]["draftIds"],
            },
            "status": "proposed",
        },
    ).json()["data"]

    response = client.patch(
        f"/api/agent/action-logs/{malicious_log['id']}",
        headers=first_headers,
        json={"status": "accepted"},
    )

    assert response.status_code == 400
    assert client.get(
        f"/api/agent/drafts/{second_draft['id']}",
        headers=second_headers,
    ).json()["data"]["status"] == "proposed"


def test_agent_loop_stops_at_step_budget():
    goal = create_goal("Budgeted Agent loop")
    create_material(goal["id"], "Budget material", "This material still needs processing.")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 1},
    ).json()["data"]

    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "max_steps"
    assert data["stopReason"] == "max_steps"
    assert data["currentStep"] == 1
    assert len(data["steps"]) == 1
    assert "step budget" in data["decisionSnapshot"]["reflection"]


def test_agent_loop_records_tool_failure(monkeypatch):
    goal = create_goal("Failing Agent loop")
    create_material(goal["id"], "Failure material", "This material triggers a tool call.")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"]},
    ).json()["data"]

    def fail_tool(*args, **kwargs):
        raise RuntimeError("tool execution failed")

    monkeypatch.setattr(agent_tool_execution_service, "execute_action", fail_tool)
    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["stopReason"] == "tool_error"
    assert data["error"] == "tool execution failed"
    assert data["steps"][0]["status"] == "failed"
    assert "tool execution failed" in data["decisionSnapshot"]["reflection"]


def test_batch_c_repeated_action_stops_with_no_progress_reflection(monkeypatch):
    goal = create_goal("C repeated action goal")
    create_material(
        goal["id"],
        "C repeated action material",
        "Retrieval evidence must not cause the same action to execute twice.",
    )

    def repeated_decision(
        goal_id=None,
        user_id=None,
        decision_mode="hybrid",
        objective="",
        step_history=None,
    ):
        action = agent_tool_registry_service.enrich_action(
            {
                "type": "search_materials",
                "label": "Search evidence",
                "description": "Search once.",
                "payload": {"query": "retrieval evidence", "limit": 3},
                "requiresConfirmation": False,
                "status": "proposed",
            }
        )
        return {
            "generatedAt": store.now_iso(),
            "mode": "hybrid",
            "requestedMode": decision_mode,
            "fallbackReason": "",
            "scope": {"goalId": goal_id},
            "stateSummary": "test state",
            "problems": [],
            "nextAction": "search_materials",
            "reason": "test repeated action handling",
            "requiresConfirmation": False,
            "proposedActions": [action],
            "feedbackMemory": {},
            "reflection": "",
        }

    monkeypatch.setattr(agent_decision_service, "decide_next_action", repeated_decision)
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 2},
    ).json()["data"]

    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["stopReason"] == "no_progress"
    assert len(data["steps"]) == 1
    assert "no new executable action" in data["decisionSnapshot"]["reflection"]


def test_agent_loop_feeds_tool_observation_back_into_next_decision(monkeypatch):
    goal = create_goal("Observation feedback loop")
    material = create_material(
        goal["id"],
        "Review evidence",
        "Review tasks help learners remember important concepts.",
    )
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Find revision actions and finish.", "maxSteps": 3},
    ).json()["data"]
    decision_calls = []

    def fake_decision(
        goal_id=None,
        user_id=None,
        decision_mode="rule-based",
        objective="",
        step_history=None,
    ):
        history = step_history or []
        decision_calls.append(history)
        if not history:
            action_type = "search_materials"
            action_payload = {"query": "revision actions", "limit": 3}
        elif len(history) == 1:
            action_type = "answer_with_sources"
            action_payload = {
                "question": "How do revision actions help learners?",
                "materialId": material["id"],
                "limit": 3,
            }
        else:
            action_type = "answer_only"
            action_payload = {}
        action = agent_tool_registry_service.enrich_action(
            {
                "type": action_type,
                "label": action_type,
                "description": "test decision",
                "payload": action_payload,
                "requiresConfirmation": False,
                "status": "proposed",
            }
        )
        return {
            "generatedAt": store.now_iso(),
            "mode": "rule-based",
            "requestedMode": decision_mode,
            "fallbackReason": "",
            "scope": {"goalId": goal_id},
            "stateSummary": "test state",
            "problems": [],
            "nextAction": action_type,
            "reason": "test",
            "requiresConfirmation": False,
            "proposedActions": [action],
            "feedbackMemory": {},
            "reflection": "",
        }

    monkeypatch.setattr(agent_decision_service, "decide_next_action", fake_decision)
    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert [step["toolName"] for step in data["steps"]] == [
        "search_materials",
        "answer_with_sources",
        "answer_only",
    ]
    assert len(decision_calls) == 3
    search_output = decision_calls[1][0]["toolOutput"]
    assert "Retrieved 1 material reference" in search_output["observation"]
    assert search_output["data"]["references"][0]["materialId"] == material["id"]
    assert search_output["data"]["references"][0]["searchMode"] == "semantic"
    answer_output = decision_calls[2][1]["toolOutput"]
    assert answer_output["data"]["isFromMaterial"] is True
    assert answer_output["data"]["references"][0]["materialId"] == material["id"]
    qa_records = client.get(f"/api/materials/{material['id']}/qa").json()["data"]
    assert qa_records[0]["id"] == answer_output["data"]["id"]


def test_search_materials_tool_filters_results_to_goal_scope():
    target_goal = create_goal("Target search goal")
    other_goal = create_goal("Other search goal")
    target_material = create_material(
        target_goal["id"],
        "Target evidence",
        "Review tasks improve memory retention.",
    )
    create_material(
        other_goal["id"],
        "Other evidence",
        "Review tasks improve memory retention.",
    )
    action = agent_tool_registry_service.enrich_action(
        {
            "type": "search_materials",
            "label": "search",
            "description": "search",
            "payload": {"query": "revision actions", "limit": 10},
            "requiresConfirmation": False,
            "status": "proposed",
        }
    )

    output = agent_tool_execution_service.execute_action(action, target_goal["id"], None)

    assert [item["materialId"] for item in output["data"]["references"]] == [
        target_material["id"]
    ]


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"materialIds": "not-a-list"}, "must be a list of strings"),
        ({"materialIds": [], "unexpected": True}, "unknown fields"),
    ],
)
def test_agent_tool_executor_validates_model_payload(payload, error):
    action = agent_tool_registry_service.enrich_action(
        {
            "type": "review_material",
            "label": "review",
            "description": "review",
            "payload": payload,
            "requiresConfirmation": False,
            "status": "proposed",
        }
    )

    with pytest.raises(ValueError, match=error):
        agent_tool_execution_service.execute_action(action, None, None)


@pytest.mark.parametrize(
    "payload, error",
    [
        ({}, "missing required fields"),
        ({"query": "   "}, "non-empty string"),
        ({"query": "review", "limit": 0}, "between 1 and 20"),
    ],
)
def test_search_materials_tool_validates_query_and_limit(payload, error):
    action = agent_tool_registry_service.enrich_action(
        {
            "type": "search_materials",
            "label": "search",
            "description": "search",
            "payload": payload,
            "requiresConfirmation": False,
            "status": "proposed",
        }
    )

    with pytest.raises(ValueError, match=error):
        agent_tool_execution_service.execute_action(action, None, None)


def test_agent_action_log_validation_and_missing_resources():
    assert client.get("/api/agent/action-logs", params={"goalId": "goal_missing"}).status_code == 404
    assert client.post(
        "/api/agent/action-logs",
        json={
            "goalId": "goal_missing",
            "actionType": "review_material",
            "status": "accepted",
        },
    ).status_code == 404
    assert client.post(
        "/api/agent/action-logs",
        json={
            "actionType": "review_material",
            "status": "bad_status",
        },
    ).status_code == 422
    assert client.patch(
        "/api/agent/action-logs/actionlog_missing",
        json={"status": "accepted"},
    ).status_code == 404
    assert client.get("/api/agent/runs", params={"goalId": "goal_missing"}).status_code == 404
    assert client.post(
        "/api/agent/runs",
        json={"goalId": "goal_missing"},
    ).status_code == 404
    assert client.post(
        "/api/agent/runs",
        json={"trigger": "bad_trigger"},
    ).status_code == 422
    assert client.patch(
        "/api/agent/runs/agentrun_missing",
        json={"status": "closed"},
    ).status_code == 404


def test_agent_runs_are_isolated_by_user_header():
    first_user = client.post(
        "/api/auth/register",
        json={"name": "First", "email": "first-run@example.com", "password": "secret123"},
    ).json()["data"]
    second_user = client.post(
        "/api/auth/register",
        json={"name": "Second", "email": "second-run@example.com", "password": "secret123"},
    ).json()["data"]

    first_goal_response = client.post(
        "/api/goals",
        headers={"X-User-Id": first_user["id"]},
        json={
            "name": "First user run goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    )
    second_goal_response = client.post(
        "/api/goals",
        headers={"X-User-Id": second_user["id"]},
        json={
            "name": "Second user run goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    )
    first_goal = first_goal_response.json()["data"]
    second_goal = second_goal_response.json()["data"]

    first_run = client.post(
        "/api/agent/runs",
        headers={"X-User-Id": first_user["id"]},
        json={"goalId": first_goal["id"]},
    ).json()["data"]
    second_run = client.post(
        "/api/agent/runs",
        headers={"X-User-Id": second_user["id"]},
        json={"goalId": second_goal["id"]},
    ).json()["data"]

    first_runs = client.get(
        "/api/agent/runs",
        headers={"X-User-Id": first_user["id"]},
    ).json()["data"]
    second_runs = client.get(
        "/api/agent/runs",
        headers={"X-User-Id": second_user["id"]},
    ).json()["data"]

    assert [run["id"] for run in first_runs] == [first_run["id"]]
    assert [run["id"] for run in second_runs] == [second_run["id"]]
    assert client.get(
        f"/api/agent/runs/{second_run['id']}",
        headers={"X-User-Id": first_user["id"]},
    ).status_code == 404
    assert client.post(
        f"/api/agent/runs/{second_run['id']}/execute",
        headers={"X-User-Id": first_user["id"]},
        json={},
    ).status_code == 404


def test_agent_context_reads_back_confirmed_flashcard_write():
    goal = create_goal("Context readback goal")
    material = create_material(
        goal["id"],
        "Readback notes",
        "Confirmed drafts should become visible to the next Agent context build.",
    )

    before_context_response = client.get("/api/agent/context", params={"goalId": goal["id"]})
    assert before_context_response.status_code == 200
    before_context = before_context_response.json()["data"]
    assert before_context["summary"]["flashcardTotal"] == 0

    flashcard_response = client.post(
        f"/api/materials/{material['id']}/flashcards/custom",
        json={
            "front": "What proves the Agent write-back loop?",
            "back": "The next AgentContext reads the confirmed flashcard.",
        },
    )
    assert flashcard_response.status_code == 200

    after_context_response = client.get("/api/agent/context", params={"goalId": goal["id"]})
    assert after_context_response.status_code == 200
    after_context = after_context_response.json()["data"]
    assert after_context["summary"]["flashcardTotal"] == 1
    assert after_context["review"]["new"] == 1

    decision_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})
    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    problem_types = {problem["type"] for problem in decision["problems"]}
    assert "review_queue" in problem_types


def test_batch_b6_task_apply_forces_latest_readback_at_step_budget(monkeypatch):
    goal = create_goal("B6 task readback goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 2},
    ).json()["data"]
    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    task_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert apply_step["toolName"] == "apply_confirmed_draft"
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    readbacks = []
    original_decide = agent_decision_service.decide_next_action_from_context

    def capture_readback(context, **kwargs):
        readbacks.append((context, kwargs["step_history"]))
        return original_decide(context, **kwargs)

    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action_from_context",
        capture_readback,
    )
    execute_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert execute_response.status_code == 200
    executed_run = execute_response.json()["data"]
    assert executed_run["status"] == "max_steps"
    assert executed_run["stopReason"] == "max_steps"
    assert executed_run["currentStep"] == 2
    assert len(executed_run["steps"]) == 2
    assert executed_run["steps"][1]["status"] == "completed"
    applied_draft = client.get(f"/api/agent/drafts/{task_draft['id']}").json()["data"]
    assert applied_draft["status"] == "applied"
    assert len(applied_draft["appliedEntityIds"]) == 1
    applied_task_id = applied_draft["appliedEntityIds"][0]
    assert applied_task_id in [
        task["id"]
        for task_group in executed_run["contextSnapshot"]["tasks"]
        for task in task_group["nextOpen"]
    ]
    assert executed_run["contextSnapshot"]["summary"]["taskTotal"] == 1
    assert executed_run["contextSnapshot"]["drafts"]["proposedCount"] == 0
    assert executed_run["contextSnapshot"]["drafts"]["appliedCount"] == 1
    assert len(readbacks) == 1
    readback_context, readback_steps = readbacks[0]
    assert readback_context == executed_run["contextSnapshot"]
    assert len(readback_steps) == 2
    assert readback_steps[-1]["toolName"] == "apply_confirmed_draft"
    assert readback_steps[-1]["toolOutput"]["data"]["appliedEntityIds"] == [applied_task_id]
    assert all(
        action["type"] != "apply_confirmed_draft"
        for action in executed_run["decisionSnapshot"]["proposedActions"]
    )

    get_run = client.get(f"/api/agent/runs/{run['id']}").json()["data"]
    assert get_run["contextSnapshot"] == executed_run["contextSnapshot"]
    assert get_run["decisionSnapshot"] == executed_run["decisionSnapshot"]
    duplicate_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    assert duplicate_run["status"] == "max_steps"
    assert len(store.list_goal_tasks(goal["id"])) == 1


def test_batch_b6_reuses_readback_decision_when_step_budget_remains(monkeypatch):
    goal = create_goal("B6 readback decision reuse goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 3},
    ).json()["data"]
    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    task_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    readback_calls = []
    original_readback_decide = agent_decision_service.decide_next_action_from_context

    def capture_readback(context, **kwargs):
        readback_calls.append((context, kwargs))
        return original_readback_decide(context, **kwargs)

    def reject_duplicate_decision(*args, **kwargs):
        raise AssertionError("The loop regenerated the post-apply Decision.")

    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action_from_context",
        capture_readback,
    )
    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action",
        reject_duplicate_decision,
    )
    executed_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    assert executed_run["status"] == "completed"
    assert len(readback_calls) == 1
    readback_context, readback_kwargs = readback_calls[0]
    assert readback_context["summary"]["taskTotal"] == 1
    assert readback_context["drafts"]["proposedCount"] == 0
    assert readback_kwargs["step_history"][-1]["status"] == "completed"
    assert executed_run["steps"][2]["contextSnapshot"] == readback_context
    assert {
        **executed_run["steps"][2]["decisionSnapshot"],
        "reflection": executed_run["decisionSnapshot"]["reflection"],
    } == executed_run["decisionSnapshot"]
    assert all(
        task_draft["id"] not in (action.get("payload") or {}).get("draftIds", [])
        for action in executed_run["decisionSnapshot"]["proposedActions"]
    )


def test_batch_b6_review_apply_forces_latest_readback_at_step_budget():
    goal = create_goal("B6 review readback goal")
    material = create_material(
        goal["id"],
        "B6 review material",
        "A confirmed review draft must appear in the next Agent Context.",
    )
    assert client.post(f"/api/materials/{material['id']}/summarize").status_code == 200
    assert client.post(
        f"/api/goals/{goal['id']}/plans",
        json={"days": 1, "regenerate": True},
    ).status_code == 200
    quiz = client.post(
        f"/api/materials/{material['id']}/quiz",
        params={"count": 1},
    ).json()["data"][0]
    assert client.post(
        f"/api/materials/{material['id']}/quiz/{quiz['id']}/answer",
        json={"answer": "incorrect"},
    ).status_code == 200

    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 2},
    ).json()["data"]
    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    review_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    executed_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    applied_draft = client.get(f"/api/agent/drafts/{review_draft['id']}").json()["data"]
    flashcards = client.get(f"/api/materials/{material['id']}/flashcards").json()["data"]
    assert executed_run["status"] == "max_steps"
    assert executed_run["contextSnapshot"]["summary"]["flashcardTotal"] == 1
    assert executed_run["contextSnapshot"]["review"]["new"] == 1
    assert executed_run["contextSnapshot"]["review"]["materialsNeedingReview"] == [
        {
            "materialId": material["id"],
            "title": material["title"],
            "reviewCount": 0,
            "newCount": 1,
        }
    ]
    assert [card["id"] for card in flashcards] == applied_draft["appliedEntityIds"]
    assert executed_run["contextSnapshot"]["drafts"]["appliedCount"] == 1
    assert all(
        action["type"] != "apply_confirmed_draft"
        for action in executed_run["decisionSnapshot"]["proposedActions"]
    )
    duplicate_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    duplicate_flashcards = client.get(
        f"/api/materials/{material['id']}/flashcards"
    ).json()["data"]
    assert duplicate_run["status"] == "max_steps"
    assert [card["id"] for card in duplicate_flashcards] == applied_draft["appliedEntityIds"]


def test_batch_b6_context_readback_failure_keeps_applied_records(monkeypatch):
    goal = create_goal("B6 context failure goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 2},
    ).json()["data"]
    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    task_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    def fail_context(*args, **kwargs):
        raise RuntimeError("simulated context readback failure")

    monkeypatch.setattr(agent_context_service, "build_agent_context", fail_context)
    failed_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    assert failed_run["status"] == "failed"
    assert failed_run["stopReason"] == "context_readback_error"
    assert failed_run["error"] == "Context readback failed (RuntimeError)."
    assert failed_run["steps"][1]["status"] == "completed"
    assert len(store.list_goal_tasks(goal["id"])) == 1
    assert client.get(f"/api/agent/drafts/{task_draft['id']}").json()["data"]["status"] == "applied"
    action_logs = client.get("/api/agent/action-logs", params={"goalId": goal["id"]}).json()["data"]
    assert any(log["id"] == apply_step["actionLogId"] and log["status"] == "applied" for log in action_logs)
    duplicate_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    assert duplicate_run["status"] == "failed"
    assert len(store.list_goal_tasks(goal["id"])) == 1


def test_batch_b6_decision_readback_failure_keeps_latest_context(monkeypatch):
    goal = create_goal("B6 decision failure goal")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "maxSteps": 2},
    ).json()["data"]
    waiting_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    task_draft = waiting_run["steps"][0]["toolOutput"]["data"]["drafts"][0]
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200

    def fail_decision(*args, **kwargs):
        raise RuntimeError("simulated decision readback failure")

    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action_from_context",
        fail_decision,
    )
    failed_run = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]

    assert failed_run["status"] == "failed"
    assert failed_run["stopReason"] == "decision_readback_error"
    assert failed_run["error"] == "Decision readback failed (RuntimeError)."
    assert failed_run["contextSnapshot"]["summary"]["taskTotal"] == 1
    assert len(store.list_goal_tasks(goal["id"])) == 1
    assert client.get(f"/api/agent/drafts/{task_draft['id']}").json()["data"]["status"] == "applied"


def test_batch_b6_readback_uses_original_run_user_and_goal_scope(monkeypatch):
    first_user = client.post(
        "/api/auth/register",
        json={"name": "B6 First", "email": "b6-first@example.com", "password": "secret123"},
    ).json()["data"]
    second_user = client.post(
        "/api/auth/register",
        json={"name": "B6 Second", "email": "b6-second@example.com", "password": "secret123"},
    ).json()["data"]
    first_headers = {"X-User-Id": first_user["id"]}
    second_headers = {"X-User-Id": second_user["id"]}

    first_goal = client.post(
        "/api/goals",
        headers=first_headers,
        json={
            "name": "B6 first goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    ).json()["data"]
    second_goal = client.post(
        "/api/goals",
        headers=second_headers,
        json={
            "name": "B6 second goal",
            "subject": "AI Agent",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "",
        },
    ).json()["data"]
    run = client.post(
        "/api/agent/runs",
        headers=first_headers,
        json={"goalId": first_goal["id"], "maxSteps": 2},
    ).json()["data"]
    waiting_run = client.post(
        f"/api/agent/runs/{run['id']}/execute",
        headers=first_headers,
        json={},
    ).json()["data"]
    apply_step = waiting_run["steps"][1]
    assert client.patch(
        f"/api/agent/action-logs/{apply_step['actionLogId']}",
        headers=first_headers,
        json={"status": "accepted"},
    ).status_code == 200

    context_calls = []
    original_build_context = agent_context_service.build_agent_context

    def capture_scope(goal_id=None, user_id=None):
        context_calls.append((goal_id, user_id))
        return original_build_context(goal_id, user_id)

    monkeypatch.setattr(agent_context_service, "build_agent_context", capture_scope)
    executed_run = client.post(
        f"/api/agent/runs/{run['id']}/execute",
        headers=first_headers,
        json={},
    ).json()["data"]

    context = executed_run["contextSnapshot"]
    assert context_calls == [(first_goal["id"], first_user["id"])]
    assert context["scope"]["goalId"] == first_goal["id"]
    assert [goal["id"] for goal in context["goals"]] == [first_goal["id"]]
    assert [task_group["goalId"] for task_group in context["tasks"]] == [first_goal["id"]]
    assert second_goal["id"] not in [goal["id"] for goal in context["goals"]]


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


def test_agent_ask_matches_chinese_material_question():
    goal = create_goal("专注力训练")
    material = create_material(
        goal["id"],
        "番茄工作法学习笔记",
        (
            "番茄工作法是一种时间管理方法。它通常把学习或工作时间分成 25 分钟的专注时间和 5 分钟的短休息。"
            "番茄工作法的好处是帮助学习者减少分心，提高专注度，并且更容易记录自己实际投入的学习时间。"
            "如果任务太大，应该先把任务拆成更小的步骤。"
        ),
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "materialId": material["id"],
            "question": "番茄工作法为什么能提高专注度？",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["isFromMaterial"] is True
    assert data["confidence"] in {"medium", "high"}
    assert data["references"]
    assert data["references"][0]["materialId"] == material["id"]
    assert "番茄工作法" in data["answer"]


def test_agent_ask_falls_back_to_current_material_chunks_for_generic_question():
    goal = create_goal("古诗词赏析")
    material = create_material(
        goal["id"],
        "春江花月夜",
        (
            "春江潮水连海平，海上明月共潮生。"
            "滟滟随波千万里，何处春江无月明！"
            "江流宛转绕芳甸，月照花林皆似霰。"
            "江天一色无纤尘，皎皎空中孤月轮。"
        ),
    )

    response = client.post(
        "/api/agent/ask",
        json={
            "goalId": goal["id"],
            "materialId": material["id"],
            "question": "请基于《春江花月夜》解释这份资料的核心内容，并给我下一步复习建议。",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["isFromMaterial"] is True
    assert data["confidence"] in {"medium", "high"}
    assert data["references"]
    assert data["references"][0]["materialId"] == material["id"]
    assert data["references"][0]["materialTitle"] == "春江花月夜"
    assert "春江" in data["answer"]
    assert data["nextAction"] in {"review_material", "create_flashcards"}


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
    assert data["nextAction"] == "ask_for_more_material"
    assert data["requiresConfirmation"] is False
    assert data["insufficiencyReason"]
    assert data["reviewDrafts"] == []

    history = client.get(f"/api/materials/{material['id']}/qa").json()["data"]
    assert len(history) == 1
    assert history[0]["id"] == data["id"]
    assert history[0]["isFromMaterial"] is False
    assert history[0]["confidence"] == "low"
    assert history[0]["nextAction"] == "ask_for_more_material"
    assert history[0]["requiresConfirmation"] is False
    assert history[0]["insufficiencyReason"]
    assert history[0]["reviewDrafts"] == []


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


def _batch_f_decision(goal_id: str, action_type: str, payload: dict) -> dict:
    action = agent_tool_registry_service.enrich_action(
        {
            "type": action_type,
            "label": action_type,
            "description": "Batch F reliability test action.",
            "payload": payload,
            "requiresConfirmation": False,
            "status": "proposed",
        }
    )
    return {
        "generatedAt": store.now_iso(),
        "mode": "rule-based",
        "requestedMode": "rule-based",
        "fallbackReason": "",
        "scope": {"goalId": goal_id},
        "stateSummary": "Batch F test state.",
        "problems": [],
        "nextAction": action_type,
        "reason": "Batch F test decision.",
        "requiresConfirmation": False,
        "proposedActions": [action],
        "feedbackMemory": {},
        "reflection": "",
    }


def test_batch_f_cancel_api_is_idempotent_and_blocks_execution():
    goal = create_goal("Batch F cancelled run")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Cancel before execution.", "maxSteps": 2},
    ).json()["data"]

    first_cancel = client.post(f"/api/agent/runs/{run['id']}/cancel")
    assert first_cancel.status_code == 200
    assert first_cancel.json()["data"]["status"] == "cancelled"
    assert first_cancel.json()["data"]["stopReason"] == "cancelled"

    repeat_cancel = client.post(f"/api/agent/runs/{run['id']}/cancel")
    assert repeat_cancel.status_code == 200
    assert repeat_cancel.json()["data"]["status"] == "cancelled"

    execute_response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})
    assert execute_response.status_code == 200
    assert execute_response.json()["data"]["status"] == "cancelled"
    assert execute_response.json()["data"]["steps"] == []


def test_batch_f_concurrent_execute_claims_only_one_executor(monkeypatch):
    goal = create_goal("Batch F concurrent run")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Run once.", "maxSteps": 1},
    ).json()["data"]
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}

    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action",
        lambda goal_id=None, user_id=None, decision_mode="rule-based", objective="", step_history=None: _batch_f_decision(
            goal_id, "answer_only", {}
        ),
    )

    def slow_execute(*args, **kwargs):
        calls["count"] += 1
        started.set()
        assert release.wait(timeout=3)
        return {"observation": "finished once", "data": {}, "terminal": True}

    monkeypatch.setattr(agent_tool_execution_service, "execute_action", slow_execute)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(agent_loop_service.execute_agent_run, run["id"])
        assert started.wait(timeout=3)
        contender = agent_loop_service.execute_agent_run(run["id"])
        assert contender["status"] == "running"
        release.set()
        completed = first.result(timeout=5)

    assert completed["status"] == "completed"
    assert calls["count"] == 1
    assert len(completed["steps"]) == 1


def test_batch_f_cancelled_run_is_not_overwritten_by_inflight_executor(monkeypatch):
    goal = create_goal("Batch F inflight cancellation")
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Cancel in flight.", "maxSteps": 1},
    ).json()["data"]
    started = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action",
        lambda goal_id=None, user_id=None, decision_mode="rule-based", objective="", step_history=None: _batch_f_decision(
            goal_id, "answer_only", {}
        ),
    )

    def slow_execute(*args, **kwargs):
        started.set()
        assert release.wait(timeout=3)
        return {"observation": "late tool result", "data": {}, "terminal": True}

    monkeypatch.setattr(agent_tool_execution_service, "execute_action", slow_execute)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(agent_loop_service.execute_agent_run, run["id"])
        assert started.wait(timeout=3)
        cancelled = client.post(f"/api/agent/runs/{run['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["status"] == "cancelled"
        release.set()
        result = future.result(timeout=5)

    assert result["status"] == "cancelled"
    persisted = client.get(f"/api/agent/runs/{run['id']}").json()["data"]
    assert persisted["status"] == "cancelled"
    assert persisted["stopReason"] == "cancelled"


def test_batch_f_retries_timed_out_read_tool_once(monkeypatch):
    goal = create_goal("Batch F read retry")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action",
        lambda goal_id=None, user_id=None, decision_mode="rule-based", objective="", step_history=None: _batch_f_decision(
            goal_id, "search_materials", {"query": "reliability", "limit": 3}
        ),
    )
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Retry read tool.", "maxSteps": 1},
    ).json()["data"]
    calls = {"count": 0}

    def delayed_search(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            time.sleep(0.04)
        return {"observation": "retrieved after retry", "data": {"references": []}, "terminal": True}

    monkeypatch.setattr(agent_tool_execution_service, "_search_materials", delayed_search)
    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert calls["count"] == 2
    assert data["steps"][0]["toolOutput"]["execution"] == {
        "attemptCount": 2,
        "retryReason": "read_tool_timeout",
    }


def test_batch_f_does_not_retry_timed_out_write_tool(monkeypatch):
    goal = create_goal("Batch F write timeout")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(
        agent_decision_service,
        "decide_next_action",
        lambda goal_id=None, user_id=None, decision_mode="rule-based", objective="", step_history=None: _batch_f_decision(
            goal_id, "create_followup_tasks", {"goalIds": [goal_id]}
        ),
    )
    run = client.post(
        "/api/agent/runs",
        json={"goalId": goal["id"], "objective": "Do not retry writes.", "maxSteps": 1},
    ).json()["data"]
    calls = {"count": 0}

    def delayed_draft(*args, **kwargs):
        calls["count"] += 1
        time.sleep(0.04)
        return {"observation": "late write", "data": {}, "terminal": False}

    monkeypatch.setattr(agent_tool_execution_service, "_create_task_draft", delayed_draft)
    response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["stopReason"] == "tool_timeout_write_no_retry"
    assert calls["count"] == 1


def test_batch_f_redacts_step_and_action_log_diagnostics():
    goal = create_goal("Batch F redaction")
    run = agent_run_service.create_agent_run(goal["id"], objective="token=run-secret")
    action = _batch_f_decision(goal["id"], "answer_only", {})["proposedActions"][0]
    step_id = agent_loop_service._insert_step(
        run,
        1,
        {"apiKey": "context-secret", "safe": "visible"},
        {"authorization": "Bearer decision-secret"},
        {**action, "payload": {"secret": "action-secret"}},
        {"token": "output-secret", "note": "Authorization: Bearer output-secret"},
        "failed",
        error="api_key=error-secret",
    )
    agent_loop_service._update_step(
        step_id,
        "failed",
        {"password": "updated-secret"},
        "Bearer updated-error-secret",
    )
    action_log = agent_action_log_service.create_action_log(
        {
            "goalId": goal["id"],
            "actionType": "answer_only",
            "observation": "token=log-secret",
            "decision": {"api_key": "decision-secret"},
            "proposedPayload": {"authorization": "Bearer payload-secret"},
            "status": "proposed",
        }
    )

    step = agent_run_service.get_agent_run(run["id"])["steps"][0]
    serialized_step = json.dumps(step)
    serialized_log = json.dumps(action_log)
    for secret in (
        "run-secret",
        "context-secret",
        "decision-secret",
        "action-secret",
        "output-secret",
        "error-secret",
        "updated-secret",
        "updated-error-secret",
        "log-secret",
        "payload-secret",
    ):
        assert secret not in serialized_step
        assert secret not in serialized_log
    assert "[redacted]" in serialized_step
    assert "[redacted]" in serialized_log
