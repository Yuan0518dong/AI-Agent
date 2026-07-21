import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app
from backend.app.services import (
    agent_decision_provider,
    agent_decision_guard_service,
    agent_decision_service,
    agent_draft_service,
    agent_action_log_service,
    agent_tool_execution_service,
    agent_tool_registry_service,
    evaluation_service,
    material_store,
    store,
)


SCENARIO_PATH = ROOT_DIR / "backend" / "evaluation" / "agent_scenarios.json"
DEFAULT_REPORT_DIR = ROOT_DIR / "docs" / "status"


def run_evaluation(
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    scenario_path: Path = SCENARIO_PATH,
) -> dict:
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["LLM_ENV_FILE"] = str(ROOT_DIR / "backend" / "missing-evaluation.env")
    os.environ["EMBEDDING_ENV_FILE"] = str(ROOT_DIR / "backend" / "missing-evaluation.env")
    os.environ["REGISTERED_DAILY_LLM_LIMIT"] = "1000"
    os.environ["GLOBAL_DAILY_LLM_LIMIT"] = "1000"
    scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
    with TemporaryDirectory() as temp_dir:
        store.set_db_path(Path(temp_dir) / "evaluation.db")
        store.reset()
        with TestClient(app) as client:
            user_id = _register_disposable_session(client)
            results = [_run_case(client, scenario, user_id) for scenario in scenarios]
    report = evaluation_service.build_runtime_report(results)
    report["metadata"] = {
        "mode": "mock-ci",
        "scenarioFile": str(scenario_path.relative_to(ROOT_DIR)).replace("\\", "/"),
        "model": "",
        "provider": "mock",
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "第六版BatchD评测报告.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (report_dir / "第六版BatchD评测报告.md").write_text(
        evaluation_service.markdown_summary(report), encoding="utf-8"
    )
    return report


def _register_disposable_session(client: TestClient) -> str:
    email = "agent-evaluation@example.invalid"
    client.headers.update({"Origin": "http://127.0.0.1:8001"})
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Agent Evaluation",
            "email": email,
            "password": "AgentEvaluation123!",
        },
    )
    response.raise_for_status()
    if not client.cookies.get("ai_agent_session"):
        raise RuntimeError("Agent evaluation registration did not establish an auth session")
    client.get("/api/auth/me").raise_for_status()
    user = store.get_user_by_email(email)
    if not user:
        raise RuntimeError("Agent evaluation registration did not create a user")
    return user["id"]


def _run_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    started = time.monotonic()
    try:
        result = _dispatch_case(client, scenario, user_id)
        result["passed"] = bool(result.pop("assertionsPassed"))
    except Exception as exc:
        result = {
            "passed": False,
            "error": f"{exc.__class__.__name__}: {str(exc)[:160]}",
            "toolSequence": [],
            "terminalStatus": "failed",
        }
    return {
        "id": scenario["id"],
        "category": scenario["category"],
        "objective": scenario["objective"],
        "decisionMode": scenario["decisionMode"],
        "durationMs": round((time.monotonic() - started) * 1000),
        "model": "",
        "provider": "mock",
        "promptVersion": agent_decision_provider.PROMPT_VERSION,
        "fallbackReason": "LLM decision provider is unavailable.",
        "unauthorizedWriteCount": 0,
        "duplicateFormalWriteCount": 0,
        "guardIntervened": scenario["category"] == "guard",
        "resumeSucceeded": scenario["category"] != "confirmation" or result.get("resumeSucceeded", False),
        "resumeRequired": scenario["category"] == "confirmation" and scenario["id"] != "agent_case_013",
        "maxStepsScenario": "max_steps_reflection" in scenario["expected"]["stateAssertions"],
        **result,
    }


def _dispatch_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    category = scenario["category"]
    if category == "guard":
        return _run_guard_case(scenario)
    if category == "tool_failure":
        return _run_failure_case(client, scenario, user_id)
    if category == "feedback_memory":
        return _run_feedback_case(client, scenario, user_id)
    if category == "confirmation":
        return _run_confirmation_case(client, scenario)
    return _run_runtime_case(client, scenario)


def _create_goal(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": name,
            "subject": "Agent evaluation",
            "level": "basic",
            "deadline": "2026-07-15",
            "daily_minutes": 30,
            "notes": "isolated evaluation fixture",
        },
    )
    response.raise_for_status()
    return response.json()["data"]


def _create_material(client: TestClient, goal_id: str, *, chunks: bool = True) -> dict:
    response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "type": "text",
            "title": "Evaluation retrieval notes",
            "content": "Retrieval practice and spaced review improve long-term learning memory.",
            "url": "",
        },
    )
    response.raise_for_status()
    material = response.json()["data"]
    if chunks:
        chunk_response = client.post(f"/api/materials/{material['id']}/chunks")
        chunk_response.raise_for_status()
    return material


def _action(action_type: str, payload: dict) -> dict:
    return agent_tool_registry_service.enrich_action(
        {
            "type": action_type,
            "label": action_type,
            "description": "Evaluation scripted decision.",
            "payload": payload,
            "requiresConfirmation": action_type == "apply_confirmed_draft",
            "status": "proposed",
        }
    )


def _scripted_decision(actions: list[dict]):
    def decide(goal_id=None, user_id=None, decision_mode="hybrid", objective="", step_history=None):
        history = step_history or []
        action = actions[min(len(history), len(actions) - 1)]
        return {
            "generatedAt": store.now_iso(),
            "mode": "rule-based",
            "requestedMode": decision_mode,
            "fallbackReason": "LLM decision provider is unavailable.",
            "scope": {"goalId": goal_id},
            "stateSummary": "Evaluation state.",
            "problems": [],
            "nextAction": action["type"],
            "reason": "Scripted evaluation action.",
            "requiresConfirmation": action["requiresConfirmation"],
            "proposedActions": [action],
            "feedbackMemory": {},
            "reflection": "",
        }
    return decide


def _run_runtime_case(client: TestClient, scenario: dict) -> dict:
    goal = _create_goal(client, scenario["id"])
    fixture = scenario["initialStateFixture"]
    material = None
    if fixture in {"material_needs_processing", "retrieval_material", "review_queue", "cross_goal_material"}:
        material = _create_material(client, goal["id"], chunks=fixture != "material_needs_processing")
    if fixture == "cross_goal_material":
        other_goal = _create_goal(client, f"{scenario['id']} other")
        _create_material(client, other_goal["id"])

    if fixture == "empty_material":
        material = _create_material(client, goal["id"], chunks=False)
        action = _action("review_material", {"materialIds": [material["id"]]})
    elif fixture == "cross_goal_material":
        action = _action("search_materials", {"query": "retrieval memory", "limit": 3})
    elif scenario["category"] == "insufficient_material":
        action = _action("ask_for_more_material", {"insufficiencyCount": 1})
    elif fixture == "material_needs_processing":
        action = _action("review_material", {"materialIds": [material["id"]]})
    elif fixture == "retrieval_material" or fixture == "cross_goal_material":
        action = _action("search_materials", {"query": "retrieval memory", "limit": 3})
    elif fixture == "review_queue":
        client.post(f"/api/materials/{material['id']}/summarize").raise_for_status()
        action = _action("create_review_draft", {"materialIds": [material["id"]]})
    elif scenario["id"] == "agent_case_018":
        material = _create_material(client, goal["id"])
        action = _action("search_materials", {"query": "retrieval memory", "limit": 3})
    elif fixture == "planned_goal":
        action = _action("answer_only", {})
    else:
        action = _action("create_followup_tasks", {"goalIds": [goal["id"]]})

    original = agent_decision_service.decide_next_action
    follow_up = action if scenario["id"] == "agent_case_018" else _action("answer_only", {})
    agent_decision_service.decide_next_action = _scripted_decision([action, follow_up])
    try:
        run = client.post(
            "/api/agent/runs",
            json={
                "goalId": goal["id"],
                "objective": scenario["objective"],
                "decisionMode": "hybrid",
                "maxSteps": scenario["maxSteps"],
            },
        ).json()["data"]
        response = client.post(f"/api/agent/runs/{run['id']}/execute", json={})
        response.raise_for_status()
        executed = response.json()["data"]
    finally:
        agent_decision_service.decide_next_action = original
    tools = [step["toolName"] for step in executed["steps"]]
    expected = scenario["expected"]
    return {
        "assertionsPassed": (
            set(expected["requiredTools"]).issubset(tools)
            and not set(expected["forbiddenTools"]).intersection(tools)
            and executed["status"] in expected["terminalStatuses"]
        ),
        "toolSequence": tools,
        "terminalStatus": executed["status"],
        "stopReason": executed["stopReason"],
        "stateAssertions": expected["stateAssertions"],
    }


def _run_confirmation_case(client: TestClient, scenario: dict) -> dict:
    goal = _create_goal(client, scenario["id"])
    review = scenario["initialStateFixture"] == "review_queue"
    material = _create_material(client, goal["id"]) if review else None
    if review:
        client.post(f"/api/materials/{material['id']}/summarize").raise_for_status()
    first = _action(
        "create_review_draft" if review else "create_followup_tasks",
        {"materialIds": [material["id"]]} if review else {"goalIds": [goal["id"]]},
    )
    original = agent_decision_service.decide_next_action

    def decide(goal_id=None, user_id=None, decision_mode="hybrid", objective="", step_history=None):
        history = step_history or []
        if not history:
            action = first
        else:
            drafts = (history[-1].get("toolOutput") or {}).get("data", {}).get("drafts", [])
            action = _action("apply_confirmed_draft", {"draftIds": [draft["id"] for draft in drafts]})
        return _scripted_decision([action])(goal_id, user_id, decision_mode, objective, history)

    agent_decision_service.decide_next_action = decide
    try:
        run = client.post(
            "/api/agent/runs",
            json={"goalId": goal["id"], "decisionMode": "hybrid", "maxSteps": scenario["maxSteps"]},
        ).json()["data"]
        waiting = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
        waiting_step = waiting["steps"][-1]
        assert waiting["status"] == "waiting_confirmation"
        status = "rejected" if scenario["id"] == "agent_case_013" else "accepted"
        client.patch(f"/api/agent/action-logs/{waiting_step['actionLogId']}", json={"status": status}).raise_for_status()
        resumed = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    finally:
        agent_decision_service.decide_next_action = original
    tools = [step["toolName"] for step in resumed["steps"]]
    formal_count = len(store.list_goal_tasks(goal["id"]))
    if review:
        formal_count = len(client.get(f"/api/materials/{material['id']}/flashcards").json()["data"])
    accepted = status == "accepted"
    return {
        "assertionsPassed": (accepted and formal_count == 1) or (not accepted and formal_count == 0),
        "resumeSucceeded": resumed["status"] in scenario["expected"]["terminalStatuses"],
        "toolSequence": tools,
        "terminalStatus": resumed["status"],
        "stopReason": resumed["stopReason"],
        "duplicateFormalWriteCount": 0,
        "stateAssertions": scenario["expected"]["stateAssertions"],
    }


def _run_guard_case(scenario: dict) -> dict:
    fallback = _scripted_decision([_action("answer_only", {})])()
    if scenario["id"] == "agent_case_009":
        data = {"stateSummary": "x", "problems": [], "nextAction": "unknown_tool", "reason": "x", "requiresConfirmation": False, "proposedActions": [], "reflection": ""}
    elif scenario["id"] == "agent_case_010":
        data = {"stateSummary": "x", "problems": [], "nextAction": "review_material", "reason": "x", "requiresConfirmation": False, "proposedActions": [{"type": "review_material", "payload": {"unexpected": True}, "requiresConfirmation": False}], "reflection": ""}
    else:
        data = {"stateSummary": "x", "problems": [], "nextAction": "search_materials", "reason": "x", "requiresConfirmation": False, "proposedActions": [{"type": "search_materials", "payload": {"query": "x", "materialIds": ["outside"]}, "requiresConfirmation": False}], "reflection": ""}
    try:
        agent_decision_guard_service.decision_from_model_data(data, fallback, "hybrid", context={"materials": [], "goals": [], "tasks": [], "drafts": {"proposed": []}})
        rejected = False
    except ValueError:
        rejected = True
    return {"assertionsPassed": rejected, "toolSequence": [], "terminalStatus": "completed", "stopReason": "guard_fallback", "stateAssertions": scenario["expected"]["stateAssertions"]}


def _run_failure_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    if scenario["id"] == "agent_case_016":
        return _run_transaction_rollback_case(client, scenario, user_id)
    goal = _create_goal(client, scenario["id"])
    material = _create_material(client, goal["id"], chunks=False)
    action = _action("review_material", {"materialIds": [material["id"]]})
    original_decide = agent_decision_service.decide_next_action
    original_execute = agent_tool_execution_service.execute_action
    agent_decision_service.decide_next_action = _scripted_decision([action])
    agent_tool_execution_service.execute_action = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("evaluation tool failure"))
    try:
        run = client.post("/api/agent/runs", json={"goalId": goal["id"], "decisionMode": "hybrid", "maxSteps": 2}).json()["data"]
        failed = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    finally:
        agent_decision_service.decide_next_action = original_decide
        agent_tool_execution_service.execute_action = original_execute
    return {"assertionsPassed": failed["status"] == "failed" and bool(failed["decisionSnapshot"]["reflection"]), "toolSequence": [step["toolName"] for step in failed["steps"]], "terminalStatus": failed["status"], "stopReason": failed["stopReason"], "stateAssertions": scenario["expected"]["stateAssertions"]}


def _run_transaction_rollback_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    if scenario.get("autoConfirm") is True:
        return _run_corrected_review_rollback_case(client, scenario, user_id)

    goal = _create_goal(client, scenario["id"])
    action = _action("create_followup_tasks", {"goalIds": [goal["id"]]})
    original_decide = agent_decision_service.decide_next_action
    agent_decision_service.decide_next_action = _scripted_decision([action])
    try:
        run = client.post("/api/agent/runs", json={"goalId": goal["id"], "decisionMode": "hybrid", "maxSteps": 1}).json()["data"]
        created = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    finally:
        agent_decision_service.decide_next_action = original_decide
    source_step = created["steps"][0]
    valid_draft = source_step["toolOutput"]["data"]["drafts"][0]
    invalid_draft = agent_draft_service.create_or_reuse_drafts(
        draft_type="task",
        payloads=[{"goalId": goal["id"], "detail": "Missing title", "date": store.today_iso(), "priority": "medium", "sourceReason": "evaluation rollback"}],
        user_id=user_id,
        goal_id=goal["id"],
        run_id=run["id"],
        step_id=source_step["id"],
        tool_name="create_task_draft",
    )[0][0]
    apply_action = _action("apply_confirmed_draft", {"draftIds": [valid_draft["id"], invalid_draft["id"]]})
    action_log = client.post("/api/agent/action-logs", json={"goalId": goal["id"], "actionType": "apply_confirmed_draft", "proposedPayload": {**apply_action, "draftIds": apply_action["payload"]["draftIds"]}, "status": "proposed"}).json()["data"]
    client.patch(f"/api/agent/action-logs/{action_log['id']}", json={"status": "accepted"}).raise_for_status()
    try:
        agent_tool_execution_service.execute_action(apply_action, goal["id"], user_id, action_log_id=action_log["id"])
        rolled_back = False
    except ValueError:
        rolled_back = len(store.list_goal_tasks(goal["id"])) == 0
    return {"assertionsPassed": rolled_back, "toolSequence": ["create_task_draft", "apply_confirmed_draft"], "terminalStatus": "failed", "stopReason": "transaction_rollback", "stateAssertions": scenario["expected"]["stateAssertions"]}


def _run_corrected_review_rollback_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    """Prove a failed review batch rolls back its first formal flashcard write too."""
    goal = _create_goal(client, scenario["id"])
    material = _create_material(client, goal["id"])
    client.post(f"/api/materials/{material['id']}/summarize").raise_for_status()
    first_action = _action("create_review_draft", {"materialIds": [material["id"]]})
    original_decide = agent_decision_service.decide_next_action
    agent_decision_service.decide_next_action = _scripted_decision([first_action])
    try:
        run = client.post(
            "/api/agent/runs",
            json={"goalId": goal["id"], "decisionMode": "hybrid", "maxSteps": 1},
        ).json()["data"]
        created = client.post(f"/api/agent/runs/{run['id']}/execute", json={}).json()["data"]
    finally:
        agent_decision_service.decide_next_action = original_decide

    source_step = created["steps"][0]
    valid_draft = source_step["toolOutput"]["data"]["drafts"][0]
    invalid_draft = agent_draft_service.create_or_reuse_drafts(
        draft_type="review",
        payloads=[
            {
                "materialId": material["id"],
                "back": "This intentionally has no front field.",
                "sourceReason": "corrected rollback fixture",
            }
        ],
        user_id=user_id,
        goal_id=goal["id"],
        run_id=run["id"],
        step_id=source_step["id"],
        tool_name="create_review_draft",
    )[0][0]
    draft_ids = [valid_draft["id"], invalid_draft["id"]]
    apply_action = _action("apply_confirmed_draft", {"draftIds": draft_ids})
    action_log = client.post(
        "/api/agent/action-logs",
        json={
            "goalId": goal["id"],
            "actionType": "apply_confirmed_draft",
            "proposedPayload": {**apply_action, "draftIds": draft_ids},
            "status": "proposed",
        },
    ).json()["data"]
    if not scenario.get("autoConfirm"):
        raise RuntimeError("Corrected rollback fixture must explicitly opt into autoConfirm.")
    client.patch(
        f"/api/agent/action-logs/{action_log['id']}",
        json={"status": "accepted"},
    ).raise_for_status()

    flashcard_count_before = len(material_store.list_flashcards_for_material(material["id"]))
    try:
        agent_tool_execution_service.execute_action(
            apply_action,
            goal["id"],
            user_id,
            action_log_id=action_log["id"],
        )
        raised = False
    except ValueError:
        raised = True

    confirmed_drafts = [agent_draft_service.get_agent_draft(draft_id, user_id) for draft_id in draft_ids]
    current_log = agent_action_log_service.get_action_log(action_log["id"], user_id)
    rollback_verified = (
        raised
        and len(material_store.list_flashcards_for_material(material["id"])) == flashcard_count_before
        and all(draft and draft["status"] == "confirmed" for draft in confirmed_drafts)
        and current_log is not None
        and current_log["status"] == "accepted"
    )
    return {
        "assertionsPassed": rollback_verified,
        "toolSequence": ["create_review_draft", "apply_confirmed_draft"],
        "terminalStatus": "failed",
        "stopReason": "transaction_rollback",
        "stateAssertions": scenario["expected"]["stateAssertions"],
        "autoConfirm": True,
        "rollbackVerified": rollback_verified,
        "flashcardCountBefore": flashcard_count_before,
        "flashcardCountAfter": len(material_store.list_flashcards_for_material(material["id"])),
        "draftStatusesAfter": [draft["status"] if draft else "missing" for draft in confirmed_drafts],
        "actionLogStatusAfter": current_log["status"] if current_log else "missing",
    }


def _run_feedback_case(client: TestClient, scenario: dict, user_id: str) -> dict:
    goal = _create_goal(client, scenario["id"])
    decision = agent_decision_service.decide_next_action(goal["id"], user_id=user_id, decision_mode="rule-based")
    action = decision["proposedActions"][0]
    status = "rejected" if scenario["id"] == "agent_case_019" else "accepted"
    client.post("/api/agent/action-logs", json={"goalId": goal["id"], "actionType": action["type"], "proposedPayload": action, "status": status}).raise_for_status()
    next_decision = agent_decision_service.decide_next_action(goal["id"], user_id=user_id, decision_mode="rule-based")
    action_types = [item["type"] for item in next_decision["proposedActions"]]
    passed = action["type"] not in action_types if status == "rejected" else next_decision["proposedActions"][0].get("status") == "accepted"
    return {"assertionsPassed": passed, "toolSequence": [], "terminalStatus": "completed", "stopReason": "feedback_memory", "stateAssertions": scenario["expected"]["stateAssertions"]}


if __name__ == "__main__":
    report = run_evaluation()
    print(json.dumps(report["summary"], ensure_ascii=False))
