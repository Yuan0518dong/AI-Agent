"""Bounded real-provider runner for the Batch 4 Agent evaluation.

This is deliberately separate from the deterministic offline retrieval and QA
evaluation. It requires explicit request/cost authorization before loading a
provider, uses only the configured DeepSeek-compatible provider, and writes
aggregate evidence without prompts, responses, credentials, or user data.
"""

import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import evaluate_agent
from backend.app.main import app
from backend.app.services import (
    agent_action_log_service,
    agent_decision_provider,
    agent_tool_execution_service,
    evaluation_service,
    llm_provider,
    material_ai_service,
    material_store,
    model_usage_service,
    store,
)
from backend.batch4_real_evaluation_preflight import require_explicit_authorization
from backend.evaluate_batch4 import (
    DEEPSEEK_V4_FLASH_CACHE_MISS_INPUT_USD_PER_MILLION,
    DEEPSEEK_V4_FLASH_OUTPUT_USD_PER_MILLION,
    MAX_REAL_AGENT_COMPLETION_TOKENS,
    MAX_REAL_AGENT_PROMPT_UTF8_BYTES,
    SCENARIO_PATH,
)


DEFAULT_REPORT_DIR = ROOT_DIR / "docs" / "evaluation"
CONFIGURED_ENV_PATH = ROOT_DIR / "backend" / ".env"


class RealEvaluationConfigurationError(RuntimeError):
    """Raised when the bounded runner cannot prove its allowed provider scope."""


class RealEvaluationRequestLimitError(RuntimeError):
    """Raised before a request would exceed the explicit authorization."""


class RealEvaluationCostLimitError(RuntimeError):
    """Raised before a request would exceed the explicit cost authorization."""


@dataclass
class UsageLedger:
    max_requests: int
    max_cost_usd: float
    request_count: int = 0
    usage_response_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reserved_prompt_tokens: int = 0
    reserved_completion_tokens: int = 0

    def observe(self, event: str, payload: dict[str, int]) -> None:
        if event == "request":
            if self.request_count >= self.max_requests:
                raise RealEvaluationRequestLimitError(
                    "The real evaluation reached its explicit provider request ceiling."
                )
            request_bytes = payload.get("requestUtf8Bytes")
            completion_limit = payload.get("maxCompletionTokens")
            if request_bytes is None or completion_limit != MAX_REAL_AGENT_COMPLETION_TOKENS:
                raise RealEvaluationConfigurationError(
                    "The real evaluation requires a measured request and the scoped completion cap."
                )
            if request_bytes > MAX_REAL_AGENT_PROMPT_UTF8_BYTES:
                raise RealEvaluationCostLimitError(
                    "The real evaluation rejected a request larger than its authorized prompt reservation."
                )
            projected_prompt_tokens = self.reserved_prompt_tokens + request_bytes
            projected_completion_tokens = self.reserved_completion_tokens + completion_limit
            projected_cost = _cost_from_tokens(
                projected_prompt_tokens,
                projected_completion_tokens,
            )
            if projected_cost > self.max_cost_usd:
                raise RealEvaluationCostLimitError(
                    "The real evaluation would exceed its explicit cost ceiling."
                )
            self.request_count += 1
            self.reserved_prompt_tokens = projected_prompt_tokens
            self.reserved_completion_tokens = projected_completion_tokens
            return
        if event == "response" and "promptTokens" in payload:
            self.usage_response_count += 1
            self.prompt_tokens += payload["promptTokens"]
            self.completion_tokens += payload["completionTokens"]

    def snapshot(self) -> tuple[int, int, int, int]:
        return (
            self.request_count,
            self.usage_response_count,
            self.prompt_tokens,
            self.completion_tokens,
        )

    def delta(self, before: tuple[int, int, int, int]) -> dict[str, int]:
        return {
            "providerRequests": self.request_count - before[0],
            "usageResponseCount": self.usage_response_count - before[1],
            "promptTokens": self.prompt_tokens - before[2],
            "completionTokens": self.completion_tokens - before[3],
        }

    def estimated_cost_usd(self) -> float | None:
        if self.usage_response_count != self.request_count:
            return None
        return _cost_from_tokens(self.prompt_tokens, self.completion_tokens)

    def reserved_cost_usd(self) -> float:
        return _cost_from_tokens(self.reserved_prompt_tokens, self.reserved_completion_tokens)


def run_real_agent_evaluation(
    report_dir: Path = DEFAULT_REPORT_DIR,
    *,
    environ: dict[str, str] | None = None,
) -> dict:
    """Run the fixed 20 x 3 Agent set only after explicit authorization.

    The authorization gate executes before the configured environment is read
    or a provider is instantiated. The runner never makes real QA, embedding,
    summary, or tool-answer requests, which keeps the budget reproducible.
    """

    authorization = require_explicit_authorization(environ)
    scenarios = _load_scenarios()
    ledger = UsageLedger(
        max_requests=authorization.max_requests,
        max_cost_usd=authorization.max_cost_usd,
    )

    with _configured_real_environment():
        provider = llm_provider.get_llm_provider()
        _assert_configured_deepseek_provider(provider)
        with TemporaryDirectory() as temp_dir:
            store.set_db_path(Path(temp_dir) / "batch4_real_agent_evaluation.db")
            store.reset()
            with TestClient(app) as client:
                user_id = evaluate_agent._register_disposable_session(client)
                with (
                    model_usage_service.llm_request_observer(ledger.observe),
                    model_usage_service.llm_format_repair_scope(False),
                    model_usage_service.llm_completion_limit(MAX_REAL_AGENT_COMPLETION_TOKENS),
                    _offline_tool_model_scope(),
                ):
                    results = [
                        _run_scenario_repeat(client, scenario, repeat, user_id, ledger)
                        for scenario in scenarios
                        for repeat in range(1, 4)
                    ]

    report = evaluation_service.build_batch4_real_agent_report(
        results,
        provider_requests=ledger.request_count,
        usage_response_count=ledger.usage_response_count,
        prompt_tokens=ledger.prompt_tokens,
        completion_tokens=ledger.completion_tokens,
        estimated_cost_usd=ledger.estimated_cost_usd(),
        reserved_prompt_tokens=ledger.reserved_prompt_tokens,
        reserved_completion_tokens=ledger.reserved_completion_tokens,
        reserved_cost_usd=ledger.reserved_cost_usd(),
    )
    report["metadata"].update(
        {
            "provider": "DeepSeek configured OpenAI-compatible provider",
            "promptVersion": agent_decision_provider.PROMPT_VERSION,
            "scenarioFixture": str(SCENARIO_PATH.relative_to(ROOT_DIR)).replace("\\", "/"),
            "scenarioFixtureSha256": hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest(),
            "authorizedRequestCeiling": authorization.max_requests,
            "authorizedCostCeilingUsd": authorization.max_cost_usd,
            "tokenCostMethod": "Reported prompt/completion tokens multiplied by the documented cache-miss rate; this is an estimate, not an invoice.",
            "promptReservation": "Each request was capped at 12,000 UTF-8 bytes before send; one byte per token was reserved conservatively.",
            "runCreation": "A rule-based initial snapshot avoids a discarded paid creation decision; execution uses real llm-json decisions.",
            "fallbackCountMethod": "Count persisted Step decisions plus a distinct terminal Run decision when it is not represented by a Step.",
            "deterministicDecisionMethod": "Count decisions whose decisionPolicy.status is deterministic, deduplicating the terminal Run snapshot against Step snapshots.",
        }
    )
    _write_report(report_dir, report)
    return report


def audit_real_agent_prompt_envelopes() -> dict:
    """Replay the fixed Agent path with a fake provider and measure envelopes.

    This verification never loads ``backend/.env`` or creates an HTTP request.
    It exists to prove that the real runner's pre-send cost reservation remains
    compatible with the current fixtures and runtime behavior.
    """

    original_provider_factory = llm_provider.get_llm_provider
    payloads: list[dict] = []

    class PromptAuditProvider:
        mode = "openai-compatible"
        model = "batch4-prompt-audit"

        def _post_chat_completion(self, payload: dict) -> dict:
            payloads.append(payload)
            prompt = json.loads(payload["messages"][1]["content"])
            fallback = prompt["fallbackDecision"]
            decision = {
                "stateSummary": fallback["stateSummary"],
                "problems": fallback["problems"],
                "nextAction": fallback["nextAction"],
                "reason": "Fixed offline prompt-envelope audit decision.",
                "requiresConfirmation": fallback["proposedActions"][0]["requiresConfirmation"],
                "proposedActions": fallback["proposedActions"],
                "reflection": "",
            }
            return {"choices": [{"message": {"content": json.dumps(decision)}}]}

    llm_provider.get_llm_provider = lambda: PromptAuditProvider()
    try:
        with _offline_prompt_audit_environment(), TemporaryDirectory() as temp_dir:
            store.set_db_path(Path(temp_dir) / "batch4_prompt_envelope_audit.db")
            store.reset()
            with TestClient(app) as client:
                user_id = evaluate_agent._register_disposable_session(client)
                with (
                    _offline_tool_model_scope(),
                    model_usage_service.llm_format_repair_scope(False),
                    model_usage_service.llm_completion_limit(MAX_REAL_AGENT_COMPLETION_TOKENS),
                ):
                    for scenario in _load_scenarios():
                        _run_scenario_repeat(
                            client,
                            scenario,
                            1,
                            user_id,
                            UsageLedger(max_requests=999, max_cost_usd=9),
                        )
    finally:
        llm_provider.get_llm_provider = original_provider_factory

    sizes = [len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) for payload in payloads]
    return {
        "mode": "fake-provider-offline",
        "scenarioCount": len(_load_scenarios()),
        "executionDecisionRequests": len(payloads),
        "maxRequestUtf8Bytes": max(sizes, default=0),
        "allRequestsHaveCompletionCap": all(
            payload.get("max_tokens") == MAX_REAL_AGENT_COMPLETION_TOKENS for payload in payloads
        ),
        "promptReservationCapUtf8Bytes": MAX_REAL_AGENT_PROMPT_UTF8_BYTES,
    }


def _load_scenarios() -> list[dict]:
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


@contextmanager
def _offline_prompt_audit_environment():
    values = {
        "LLM_PROVIDER": "mock",
        "EMBEDDING_PROVIDER": "mock",
        "LLM_ENV_FILE": str(ROOT_DIR / "backend" / "missing-batch4-prompt-audit.env"),
        "EMBEDDING_ENV_FILE": str(ROOT_DIR / "backend" / "missing-batch4-prompt-audit.env"),
    }
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _configured_real_environment():
    if not CONFIGURED_ENV_PATH.is_file():
        raise RealEvaluationConfigurationError("The configured DeepSeek environment file is unavailable.")
    if os.getenv("LLM_ENV_FILE", "").strip() and Path(os.environ["LLM_ENV_FILE"]).resolve() != CONFIGURED_ENV_PATH:
        raise RealEvaluationConfigurationError("The real evaluation only accepts the configured backend provider environment.")
    overridden_provider_keys = [
        key
        for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL")
        if os.getenv(key, "").strip()
    ]
    if overridden_provider_keys:
        raise RealEvaluationConfigurationError("The real evaluation refuses externally overridden provider settings.")

    values = {
        "LLM_ENV_FILE": str(CONFIGURED_ENV_PATH),
        "EMBEDDING_PROVIDER": "mock",
        "EMBEDDING_ENV_FILE": str(ROOT_DIR / "backend" / "missing-batch4-real-embedding.env"),
        "REGISTERED_DAILY_LLM_LIMIT": "1000",
        "GLOBAL_DAILY_LLM_LIMIT": "1000",
        "REGISTERED_DAILY_EMBEDDING_QUERY_LIMIT": "1000",
        "REGISTERED_DAILY_EMBEDDING_CHUNK_LIMIT": "1000",
    }
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _assert_configured_deepseek_provider(provider) -> None:
    if not isinstance(provider, llm_provider.OpenAICompatibleLLMProvider):
        raise RealEvaluationConfigurationError("The configured provider is not eligible for the real evaluation.")
    hostname = (urlparse(provider.base_url).hostname or "").lower()
    if not (hostname == "deepseek.com" or hostname.endswith(".deepseek.com")):
        raise RealEvaluationConfigurationError("The configured provider is not the approved DeepSeek endpoint.")


def _run_scenario_repeat(
    client: TestClient,
    scenario: dict,
    repeat: int,
    user_id: str,
    ledger: UsageLedger,
) -> dict:
    goal, fixture = _prepare_fixture(client, scenario, user_id)
    before = ledger.snapshot()
    started = time.monotonic()
    with _guard_injection_scope(scenario), _controlled_tool_failure_scope(scenario):
        created = client.post(
            "/api/agent/runs",
            json={
                "goalId": goal["id"],
                "objective": scenario["objective"],
                "decisionMode": "rule-based",
                "maxSteps": scenario["maxSteps"],
            },
        )
        created.raise_for_status()
        run_id = created.json()["data"]["id"]
        _set_evaluation_run_decision_mode(run_id)
        initial_response = client.post(f"/api/agent/runs/{run_id}/execute", json={})
        initial_response.raise_for_status()
        final_run = initial_response.json()["data"]
        confirmation_disposition = "not_requested"
        waiting_step = _latest_waiting_confirmation_step(final_run)
        if scenario["category"] == "confirmation" and waiting_step:
            confirmation_disposition = "rejected" if scenario["id"] == "agent_case_013" else "accepted"
            confirmed = client.patch(
                f"/api/agent/action-logs/{waiting_step['actionLogId']}",
                json={"status": confirmation_disposition},
            )
            confirmed.raise_for_status()
            resumed_response = client.post(f"/api/agent/runs/{run_id}/execute", json={})
            resumed_response.raise_for_status()
            final_run = resumed_response.json()["data"]

    duration_ms = round((time.monotonic() - started) * 1000)
    steps = final_run.get("steps") or []
    tools = [step.get("toolName", "") for step in steps if step.get("toolName")]
    deterministic_decisions = _persisted_decisions_matching(
        final_run,
        lambda decision: (decision.get("decisionPolicy") or {}).get("status") == "deterministic",
    )
    expected = scenario["expected"]
    tool_selection_passed = (
        set(expected["requiredTools"]).issubset(tools)
        and not set(expected["forbiddenTools"]).intersection(tools)
        and final_run["status"] in expected["terminalStatuses"]
    )
    guard_intervened = scenario["category"] == "guard" and any(
        (step.get("decisionSnapshot") or {}).get("decisionGuard", {}).get("status") == "fallback"
        for step in steps
    )
    confirmation_complete, recovery_succeeded = _confirmation_outcome(
        scenario,
        final_run,
        waiting_step,
        confirmation_disposition,
        fixture["formalRecordCountBefore"],
        goal["id"],
    )
    passed = tool_selection_passed
    if scenario["category"] == "guard":
        passed = passed and guard_intervened
    if scenario["category"] == "confirmation":
        passed = passed and confirmation_complete

    return {
        "runId": f"{scenario['id']}#{repeat}",
        "scenarioId": scenario["id"],
        "repeat": repeat,
        "category": scenario["category"],
        "passed": passed,
        "toolSelectionPassed": tool_selection_passed,
        "guardIntervened": guard_intervened,
        "confirmationComplete": confirmation_complete,
        "confirmationDisposition": confirmation_disposition,
        "recoverySucceeded": recovery_succeeded,
        "terminalStatus": final_run["status"],
        "toolSequence": tools,
        "durationMs": duration_ms,
        "fallbackDecisionCount": _count_persisted_fallback_decisions(final_run),
        "deterministicDecisionCount": len(deterministic_decisions),
        "deterministicActionTypes": [
            decision.get("nextAction", "")
            for decision in deterministic_decisions
            if decision.get("nextAction")
        ],
        **ledger.delta(before),
    }


def _count_persisted_fallback_decisions(final_run: dict) -> int:
    return len(
        _persisted_decisions_matching(
            final_run,
            lambda decision: bool(decision.get("fallbackReason")),
        )
    )


def _persisted_decisions_matching(final_run: dict, predicate) -> list[dict]:
    decisions = [
        step.get("decisionSnapshot") or {}
        for step in final_run.get("steps") or []
    ]
    fingerprints = {_decision_fingerprint(decision) for decision in decisions}
    terminal_decision = final_run.get("decisionSnapshot") or {}
    terminal_fingerprint = _decision_fingerprint(terminal_decision)
    if terminal_decision and terminal_fingerprint not in fingerprints:
        decisions.append(terminal_decision)
    return [decision for decision in decisions if predicate(decision)]


def _decision_fingerprint(decision: dict) -> str:
    return json.dumps(decision, ensure_ascii=False, sort_keys=True)


def _prepare_fixture(client: TestClient, scenario: dict, user_id: str) -> tuple[dict, dict]:
    goal = _create_goal(client, f"Batch4 {scenario['id']}")
    fixture_name = scenario["initialStateFixture"]
    material = None
    if fixture_name in {"material_needs_processing", "empty_material"}:
        material = _create_material(client, goal["id"], chunks=False)
    elif fixture_name in {"retrieval_material", "review_queue", "no_matching_material", "cross_goal_material"}:
        material = _create_material(client, goal["id"], chunks=True)
        _save_offline_summary(material["id"])

    if fixture_name == "review_queue" and material:
        response = client.post(f"/api/materials/{material['id']}/flashcards")
        response.raise_for_status()
    if fixture_name == "no_matching_material" and material:
        _save_insufficient_qa_record(material, goal)
    if fixture_name == "cross_goal_material":
        other_goal = _create_goal(client, f"Batch4 {scenario['id']} other")
        _create_material(client, other_goal["id"], chunks=True)
    if fixture_name == "planned_goal":
        _create_open_task(goal["id"])
    if scenario["category"] == "feedback_memory":
        action_type = "create_review_draft" if scenario["id"] == "agent_case_019" else "create_task_draft"
        action_status = "rejected" if scenario["id"] == "agent_case_019" else "accepted"
        agent_action_log_service.create_action_log(
            {
                "goalId": goal["id"],
                "actionType": action_type,
                "proposedPayload": {"type": action_type},
                "status": action_status,
            },
            user_id,
        )
    return goal, {"formalRecordCountBefore": len(store.list_goal_tasks(goal["id"]))}


def _create_goal(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/goals",
        json={
            "name": name,
            "subject": "Batch 4 evaluation",
            "level": "basic",
            "deadline": "2026-12-31",
            "daily_minutes": 30,
            "notes": "Isolated fixed Agent evaluation fixture.",
        },
    )
    response.raise_for_status()
    return response.json()["data"]


def _set_evaluation_run_decision_mode(run_id: str) -> None:
    """Avoid billing the API's discarded creation-time decision in the temp DB."""

    with store.db_connection() as conn:
        conn.execute(
            "UPDATE agent_runs SET decision_mode = ?, updated_at = ? WHERE id = ?",
            ("llm-json", store.now_iso(), run_id),
        )


def _create_material(client: TestClient, goal_id: str, *, chunks: bool) -> dict:
    response = client.post(
        "/api/materials",
        json={
            "goalId": goal_id,
            "type": "text",
            "title": "Batch 4 fixed learning note",
            "content": "Spaced retrieval and feedback improve durable learning when claims remain linked to source evidence.",
            "url": "",
        },
    )
    response.raise_for_status()
    material = response.json()["data"]
    if chunks:
        chunk_response = client.post(f"/api/materials/{material['id']}/chunks")
        chunk_response.raise_for_status()
    return material


def _save_offline_summary(material_id: str) -> None:
    now = store.now_iso()
    material_store.save_material_summary(
        material_id,
        {
            "overview": "Fixed evaluation material summary.",
            "keyPoints": ["source evidence", "retrieval practice", "feedback"],
            "difficulties": ["Keep generated claims grounded in material evidence."],
            "studyOrder": ["Read", "Retrieve", "Check evidence"],
            "actionItems": ["Review one source-backed question."],
            "aiMode": "offline-evaluation",
            "createdAt": now,
            "updatedAt": now,
        },
    )


def _save_insufficient_qa_record(material: dict, goal: dict) -> None:
    now = store.now_iso()
    material_store.save_qa_record(
        {
            "id": store.make_id("qa"),
            "materialId": material["id"],
            "goalId": goal["id"],
            "question": "Unsupported fixed evaluation question",
            "answer": "Insufficient material.",
            "basis": "No fixed source supports this question.",
            "suggestion": "Add a source.",
            "sourceTitle": material["title"],
            "isFromMaterial": False,
            "confidence": "low",
            "mode": "grounded-refusal",
            "nextAction": "ask_for_more_material",
            "requiresConfirmation": False,
            "insufficiencyReason": "No fixed source supports this question.",
            "reviewDrafts": [],
            "createdAt": now,
        }
    )


def _create_open_task(goal_id: str) -> None:
    now = store.now_iso()
    store.create_task(
        {
            "id": store.make_id("task"),
            "goal_id": goal_id,
            "title": "Fixed planned task",
            "detail": "Keep the evaluation context free of missing-task signals.",
            "date": store.today_iso(),
            "priority": "medium",
            "done": False,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
    )


def _latest_waiting_confirmation_step(agent_run: dict) -> dict | None:
    return next(
        (
            step
            for step in reversed(agent_run.get("steps") or [])
            if step.get("status") == "waiting_confirmation"
        ),
        None,
    )


def _confirmation_outcome(
    scenario: dict,
    final_run: dict,
    waiting_step: dict | None,
    disposition: str,
    formal_records_before: int,
    goal_id: str,
) -> tuple[bool, bool]:
    if scenario["category"] != "confirmation":
        return False, False
    steps = final_run.get("steps") or []
    resumed_step = next(
        (step for step in steps if waiting_step and step.get("id") == waiting_step.get("id")),
        None,
    )
    if not waiting_step or not resumed_step:
        return False, False
    current_records = len(store.list_goal_tasks(goal_id))
    if disposition == "rejected":
        return resumed_step.get("status") == "rejected" and current_records == formal_records_before, False
    completed = resumed_step.get("status") == "completed"
    no_duplicate = current_records <= formal_records_before + 1
    return completed and no_duplicate, completed and no_duplicate


@contextmanager
def _guard_injection_scope(scenario: dict):
    if scenario["category"] != "guard":
        yield
        return
    original = agent_decision_provider._post_decision_completion

    def inject_after_real_response(payload: dict, provider) -> str:
        original(payload, provider)
        return json.dumps(_guard_invalid_decision(scenario["id"]))

    agent_decision_provider._post_decision_completion = inject_after_real_response
    try:
        yield
    finally:
        agent_decision_provider._post_decision_completion = original


def _guard_invalid_decision(scenario_id: str) -> dict:
    base = {
        "stateSummary": "Controlled Batch 4 guard validation.",
        "problems": [],
        "reason": "Controlled invalid decision.",
        "requiresConfirmation": False,
        "reflection": "",
    }
    if scenario_id == "agent_case_009":
        return {**base, "nextAction": "unknown_tool", "proposedActions": []}
    if scenario_id == "agent_case_010":
        return {
            **base,
            "nextAction": "review_material",
            "proposedActions": [{"type": "review_material", "payload": {"unexpected": True}}],
        }
    return {
        **base,
        "nextAction": "search_materials",
        "proposedActions": [
            {"type": "search_materials", "payload": {"query": "fixed", "materialIds": ["outside"]}}
        ],
    }


@contextmanager
def _controlled_tool_failure_scope(scenario: dict):
    if scenario["category"] != "tool_failure":
        yield
        return
    original = agent_tool_execution_service.execute_action

    def controlled_failure(*args, **kwargs):
        raise RuntimeError("Batch 4 controlled tool failure.")

    agent_tool_execution_service.execute_action = controlled_failure
    try:
        yield
    finally:
        agent_tool_execution_service.execute_action = original


@contextmanager
def _offline_tool_model_scope():
    original_summary = material_ai_service._generate_summary_json
    original_answer = agent_tool_execution_service._answer_with_sources

    def offline_answer(payload: dict, goal_id: str | None, user_id: str | None, objective: str) -> dict:
        references = material_store.search_chunks(payload["question"], limit=int(payload.get("limit") or 3), user_id=user_id)
        if goal_id:
            references = [item for item in references if item.get("goalId") == goal_id]
        return {
            "observation": f"Offline evaluation tool returned {len(references)} source reference(s).",
            "data": {"referenceCount": len(references), "objective": objective},
            "terminal": False,
        }

    material_ai_service._generate_summary_json = lambda material: {}
    agent_tool_execution_service._answer_with_sources = offline_answer
    try:
        yield
    finally:
        material_ai_service._generate_summary_json = original_summary
        agent_tool_execution_service._answer_with_sources = original_answer


def _cost_from_tokens(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1_000_000 * DEEPSEEK_V4_FLASH_CACHE_MISS_INPUT_USD_PER_MILLION
        + completion_tokens / 1_000_000 * DEEPSEEK_V4_FLASH_OUTPUT_USD_PER_MILLION,
        6,
    )


def _write_report(report_dir: Path, report: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "第七版Batch4Agent真实模型评测报告.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics = report["metrics"]
    cost = metrics["estimatedCostUsd"]
    cost_value = str(cost) if cost is not None else "not computable: provider usage was incomplete"
    failed_runs = report["failureRunIds"]
    lines = [
        "# 第七版 Batch 4 Agent 真实模型评测报告",
        "",
        "本报告来自受授权的固定 Agent 场景运行；不保留凭据、Provider 配置、提示词或模型原文。",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 运行数 | {report['metadata']['runCount']} |",
        f"| 未满足场景断言的 Run | {len(failed_runs)} |",
        f"| 工具选择成功率 | {metrics['toolSelectionSuccessRate']} |",
        f"| Guard 召回 | {metrics['guardRecall']} |",
        f"| 确认完整性 | {metrics['confirmationCompleteness']} |",
        f"| 恢复成功率 | {metrics['recoverySuccessRate']} |",
        f"| p50 / p95 延迟 ms | {metrics['p50LatencyMs']} / {metrics['p95LatencyMs']} |",
        f"| Provider 请求 | {metrics['providerRequests']} |",
        f"| prompt / completion Token | {metrics['promptTokens']} / {metrics['completionTokens']} |",
        f"| Token 估算成本 USD | {cost_value} |",
        f"| 安全回退决策次数 | {metrics['fallbackDecisionCount']} |",
        f"| Runtime 确定性决策次数 | {metrics['deterministicDecisionCount']} |",
        f"| 包含 Runtime 确定性决策的 Run | {metrics['runsWithDeterministicDecision']} |",
        f"| 发送前保守预留 prompt / completion Token | {metrics['reservedPromptTokens']} / {metrics['reservedCompletionTokens']} |",
        f"| 发送前保守预留成本 USD | {metrics['reservedCostUsd']} |",
        "",
        "Guard 三个场景在真实 Provider 已返回一次决策后，向 Guard 输入固定非法 JSON；该指标验证拦截链路，不表示模型自然产生非法输出的比例。",
        "格式修复重试在本次受限评测中关闭，模型 JSON 异常会安全回退。Run 创建使用规则快照，执行阶段才使用真实 llm-json；每个请求在发送前限制为 12,000 UTF-8 字节和 350 completion token。",
        "工具选择和确认完整性未达到 1.0；逐 Run 的失败标记、工具序列、回退次数、Token 与延迟保留在同名 JSON，后续提示词或夹具调整必须重新完成 20 x 3 运行。",
    ]
    (report_dir / "第七版Batch4Agent真实模型评测报告.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    result = run_real_agent_evaluation()
    print(json.dumps({"runCount": result["metadata"]["runCount"], "metrics": result["metrics"]}, ensure_ascii=False))
