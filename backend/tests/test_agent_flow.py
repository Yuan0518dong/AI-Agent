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
    assert decision["requiresConfirmation"] is True
    assert decision["feedbackMemory"]["recentActionCount"] == 0


def test_agent_tools_registry_is_exposed_and_decision_actions_are_enriched():
    tools_response = client.get("/api/agent/tools")

    assert tools_response.status_code == 200
    tools = tools_response.json()["data"]
    tool_names = {tool["name"] for tool in tools}
    assert {"review_material", "create_review_draft", "create_task_draft"}.issubset(tool_names)

    goal = create_goal("Tool registry goal")
    decision_response = client.post("/api/agent/decide", params={"goalId": goal["id"]})

    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    action = decision["proposedActions"][0]
    assert action["type"] == "create_followup_tasks"
    assert action["toolName"] == "create_task_draft"
    assert action["riskLevel"] == "high"
    assert action["draftOnly"] is True
    assert action["applyTarget"] == "task_drafts"
    assert action["requiresConfirmation"] is True


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
    assert decision["requiresConfirmation"] is True

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
    assert agent_run["status"] == "decided"
    assert agent_run["contextSummary"]["goalCount"] == 1
    assert agent_run["contextSummary"]["materialTotal"] == 1
    assert agent_run["decisionSummary"]["nextAction"]
    assert agent_run["feedbackSummary"]["total"] == 0
    assert agent_run["contextSnapshot"]["materials"][0]["id"] == material["id"]
    assert agent_run["decisionSnapshot"]["scope"]["goalId"] == goal["id"]

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
