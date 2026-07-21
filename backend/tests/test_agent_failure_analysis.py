import json
from pathlib import Path

from backend.analyze_agent_failures import analyze_failures


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "backend" / "evaluation" / "agent_scenarios.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "evaluation" / "第七版Batch4Agent真实模型评测报告.json"


def test_real_agent_failure_analysis_preserves_the_frozen_baseline():
    scenarios = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    result = analyze_failures(scenarios, report)

    assert result["baseline"] == {
        "runCount": 60,
        "scenarioCount": 20,
        "runsPerScenario": 3,
        "toolSelectionSuccessRate": 0.6333,
        "confirmationCompleteness": 0.5556,
        "recoverySuccessRate": 1.0,
        "fallbackDecisionCount": 84,
        "providerRequests": 107,
        "estimatedCostUsd": 0.042727,
    }
    assert result["summary"] == {
        "failedRunCount": 22,
        "failingScenarioCount": 8,
        "systematicScenarioCount": 7,
        "intermittentScenarioCount": 1,
        "failureRunsByFamily": {
            "confirmation_state": 4,
            "feedback_memory": 3,
            "scope_and_evidence": 3,
            "semantic_routing": 6,
            "terminal_control": 3,
            "tool_failure_recovery": 3,
        },
    }

    by_id = {scenario["scenarioId"]: scenario for scenario in result["scenarios"]}
    assert set(by_id) == {
        "agent_case_003",
        "agent_case_004",
        "agent_case_008",
        "agent_case_013",
        "agent_case_014",
        "agent_case_016",
        "agent_case_018",
        "agent_case_019",
    }
    assert by_id["agent_case_013"]["failureCount"] == 1
    assert not by_id["agent_case_013"]["systematicAcrossRepeats"]
    assert all(
        scenario["systematicAcrossRepeats"]
        for scenario_id, scenario in by_id.items()
        if scenario_id != "agent_case_013"
    )


def test_failure_analysis_rejects_duplicate_scenario_ids():
    scenarios = [{"id": "duplicate"}, {"id": "duplicate"}]

    try:
        analyze_failures(scenarios, {"cases": []})
    except ValueError as exc:
        assert str(exc) == "Scenario IDs must be unique."
    else:
        raise AssertionError("Expected duplicate scenario IDs to be rejected.")
