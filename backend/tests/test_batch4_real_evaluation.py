import pytest

from backend import evaluate_batch4_real
from backend.batch4_real_evaluation_preflight import RealEvaluationAuthorizationError
from backend.app.services import model_usage_service


def test_real_runner_checks_authorization_before_loading_a_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        evaluate_batch4_real.llm_provider,
        "get_llm_provider",
        lambda: (_ for _ in ()).throw(AssertionError("provider must not load before authorization")),
    )

    with pytest.raises(RealEvaluationAuthorizationError):
        evaluate_batch4_real.run_real_agent_evaluation(tmp_path, environ={})


def test_usage_ledger_enforces_the_request_ceiling_and_costs_complete_usage():
    ledger = evaluate_batch4_real.UsageLedger(max_requests=2, max_cost_usd=0.01)

    ledger.observe("request", {"requestUtf8Bytes": 100, "maxCompletionTokens": 350})
    ledger.observe("response", {"promptTokens": 100, "completionTokens": 20})
    ledger.observe("request", {"requestUtf8Bytes": 200, "maxCompletionTokens": 350})
    ledger.observe("response", {"promptTokens": 200, "completionTokens": 30})

    assert ledger.request_count == 2
    assert ledger.usage_response_count == 2
    assert ledger.prompt_tokens == 300
    assert ledger.completion_tokens == 50
    assert ledger.estimated_cost_usd() == 0.000056

    with pytest.raises(evaluate_batch4_real.RealEvaluationRequestLimitError):
        ledger.observe("request", {"requestUtf8Bytes": 1, "maxCompletionTokens": 350})


def test_usage_ledger_rejects_unbounded_or_over_budget_requests():
    ledger = evaluate_batch4_real.UsageLedger(max_requests=1, max_cost_usd=0.01)

    with pytest.raises(evaluate_batch4_real.RealEvaluationConfigurationError):
        ledger.observe("request", {})
    with pytest.raises(evaluate_batch4_real.RealEvaluationCostLimitError):
        ledger.observe(
            "request",
            {
                "requestUtf8Bytes": evaluate_batch4_real.MAX_REAL_AGENT_PROMPT_UTF8_BYTES + 1,
                "maxCompletionTokens": evaluate_batch4_real.MAX_REAL_AGENT_COMPLETION_TOKENS,
            },
        )


def test_real_runner_prompt_audit_stays_within_the_reserved_envelope():
    audit = evaluate_batch4_real.audit_real_agent_prompt_envelopes()

    assert audit["mode"] == "fake-provider-offline"
    assert audit["scenarioCount"] == 20
    assert audit["executionDecisionRequests"] > 0
    assert audit["maxRequestUtf8Bytes"] <= audit["promptReservationCapUtf8Bytes"]
    assert audit["allRequestsHaveCompletionCap"] is True


def test_missing_provider_usage_is_not_misreported_as_zero_tokens():
    events = []

    with model_usage_service.llm_request_observer(lambda event, payload: events.append((event, payload))):
        model_usage_service.record_llm_response_usage({"usage": {}})

    assert events == [("response", {})]


def test_fallback_count_includes_a_terminal_decision_without_a_persisted_step():
    fallback = {"fallbackReason": "policy fallback", "nextAction": "", "proposedActions": []}

    assert evaluate_batch4_real._count_persisted_fallback_decisions(
        {"steps": [], "decisionSnapshot": fallback}
    ) == 1
    assert evaluate_batch4_real._count_persisted_fallback_decisions(
        {
            "steps": [{"decisionSnapshot": fallback}],
            "decisionSnapshot": fallback,
        }
    ) == 1


def test_persisted_decision_count_includes_deterministic_terminal_decision_once():
    deterministic = {
        "nextAction": "search_materials",
        "decisionPolicy": {"status": "deterministic"},
    }

    decisions = evaluate_batch4_real._persisted_decisions_matching(
        {"steps": [], "decisionSnapshot": deterministic},
        lambda decision: (decision.get("decisionPolicy") or {}).get("status") == "deterministic",
    )
    duplicate = evaluate_batch4_real._persisted_decisions_matching(
        {
            "steps": [{"decisionSnapshot": deterministic}],
            "decisionSnapshot": deterministic,
        },
        lambda decision: (decision.get("decisionPolicy") or {}).get("status") == "deterministic",
    )

    assert decisions == [deterministic]
    assert duplicate == [deterministic]


def test_real_agent_report_keeps_only_aggregate_evidence():
    report = evaluate_batch4_real.evaluation_service.build_batch4_real_agent_report(
        [
            {
                "runId": "agent_case_001#1",
                "scenarioId": "agent_case_001",
                "category": "confirmation",
                "passed": True,
                "toolSelectionPassed": True,
                "guardIntervened": False,
                "confirmationComplete": True,
                "confirmationDisposition": "accepted",
                "recoverySucceeded": True,
                "durationMs": 100,
            },
            {
                "runId": "agent_case_009#1",
                "scenarioId": "agent_case_009",
                "category": "guard",
                "passed": True,
                "toolSelectionPassed": True,
                "guardIntervened": True,
                "confirmationComplete": False,
                "confirmationDisposition": "not_requested",
                "recoverySucceeded": False,
                "durationMs": 200,
            },
        ],
        provider_requests=2,
        usage_response_count=2,
        prompt_tokens=300,
        completion_tokens=50,
        estimated_cost_usd=0.000056,
        reserved_prompt_tokens=400,
        reserved_completion_tokens=700,
        reserved_cost_usd=0.000252,
    )

    assert report["metrics"]["toolSelectionSuccessRate"] == 1.0
    assert report["metrics"]["guardRecall"] == 1.0
    assert report["metrics"]["confirmationCompleteness"] == 1.0
    assert report["metrics"]["recoverySuccessRate"] == 1.0
    assert report["metrics"]["fallbackDecisionCount"] == 0
    assert report["metrics"]["deterministicDecisionCount"] == 0
    assert report["metrics"]["runsWithDeterministicDecision"] == 0
    assert "credentials" in report["metadata"]["credentialPolicy"].lower()
    assert "modelResponse" not in report["cases"][0]
