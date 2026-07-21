import json

from backend import evaluate_agent_reliability


def test_rel_offline_evaluation_keeps_legacy_evidence_and_verifies_corrected_rollback(tmp_path):
    report = evaluate_agent_reliability.run_reliability_evaluation(tmp_path)

    assert report["metadata"]["providerRequests"] == 0
    assert report["metadata"]["realProviderEvaluated"] is False
    assert report["legacySuite"]["fixture"]["path"] == "backend/evaluation/agent_scenarios.json"
    assert report["correctedSuite"]["fixture"]["path"] == "backend/evaluation/agent_scenarios_corrected.json"
    assert report["correctedSuite"]["offlineMockRegression"]["metrics"] == {
        "toolSelectionSuccessRate": 1.0,
        "guardRecall": 1.0,
        "confirmationCompleteness": 1.0,
        "recoverySuccessRate": 1.0,
        "p50LatencyMs": report["correctedSuite"]["offlineMockRegression"]["metrics"]["p50LatencyMs"],
        "p95LatencyMs": report["correctedSuite"]["offlineMockRegression"]["metrics"]["p95LatencyMs"],
        "promptTokens": 0,
        "completionTokens": 0,
        "estimatedCostUsd": 0.0,
    }
    rollback = report["correctedSuite"]["rollbackCase"]
    assert rollback["autoConfirm"] is True
    assert rollback["rollbackVerified"] is True
    assert rollback["flashcardCountBefore"] == rollback["flashcardCountAfter"] == 0
    assert rollback["draftStatusesAfter"] == ["confirmed", "confirmed"]
    assert rollback["actionLogStatusAfter"] == "accepted"
    assert all(item["sha256"] for item in report["legacySuite"]["preservedReports"])
    assert [item["label"] for item in report["legacySuite"]["historicalRealProviderRuns"]] == ["A0", "A2", "A3"]
    assert report["correctedSuite"]["providerAccounting"] == {
        "providerRequests": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "estimatedCostUsd": 0.0,
        "deterministicDecisionCount": 0,
        "failureRunIds": [],
    }

    persisted = json.loads((tmp_path / "legacy-corrected-offline-report.json").read_text(encoding="utf-8"))
    assert persisted["correctedSuite"]["rollbackCase"] == rollback
    assert "0 Provider requests" in (tmp_path / "legacy-corrected-offline-report.md").read_text(encoding="utf-8")
