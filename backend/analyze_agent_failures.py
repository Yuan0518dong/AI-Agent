from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = PROJECT_ROOT / "backend" / "evaluation" / "agent_scenarios.json"
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "evaluation" / "第七版Batch4Agent真实模型评测报告.json"

FAILURE_FAMILY_BY_CATEGORY = {
    "happy_path": "semantic_routing",
    "insufficient_material": "scope_and_evidence",
    "confirmation": "confirmation_state",
    "tool_failure": "tool_failure_recovery",
    "terminal": "terminal_control",
    "feedback_memory": "feedback_memory",
    "guard": "guard_validation",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_failures(scenarios: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    scenario_by_id = {scenario["id"]: scenario for scenario in scenarios}
    if len(scenario_by_id) != len(scenarios):
        raise ValueError("Scenario IDs must be unique.")

    failed_cases = [case for case in report["cases"] if not case["passed"]]
    runs_by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    family_counts: Counter[str] = Counter()

    for case in failed_cases:
        scenario = scenario_by_id.get(case["scenarioId"])
        if scenario is None:
            raise ValueError(f"Unknown scenario in report: {case['scenarioId']}")

        expected = scenario["expected"]
        observed_tools = case["toolSequence"]
        allowed_tools = set(expected["allowedTools"])
        forbidden_tools = set(expected["forbiddenTools"])
        missing_required = [tool for tool in expected["requiredTools"] if tool not in observed_tools]
        unexpected_tools = [tool for tool in observed_tools if tool not in allowed_tools]
        used_forbidden = [tool for tool in observed_tools if tool in forbidden_tools]
        failure_family = FAILURE_FAMILY_BY_CATEGORY.get(case["category"], "other")
        family_counts[failure_family] += 1

        runs_by_scenario[case["scenarioId"]].append(
            {
                "runId": case["runId"],
                "repeat": case["repeat"],
                "observedTools": observed_tools,
                "missingRequiredTools": missing_required,
                "unexpectedTools": unexpected_tools,
                "usedForbiddenTools": used_forbidden,
                "terminalStatus": case["terminalStatus"],
                "terminalMismatch": case["terminalStatus"] not in expected["terminalStatuses"],
                "confirmationIncomplete": case["category"] == "confirmation" and not case["confirmationComplete"],
                "fallbackDecisionCount": case["fallbackDecisionCount"],
                "failureFamily": failure_family,
            }
        )

    runs_per_scenario = int(report["metadata"]["runsPerScenario"])
    scenario_summaries = []
    for scenario_id in sorted(runs_by_scenario):
        scenario = scenario_by_id[scenario_id]
        runs = sorted(runs_by_scenario[scenario_id], key=lambda item: item["repeat"])
        scenario_summaries.append(
            {
                "scenarioId": scenario_id,
                "category": scenario["category"],
                "objective": scenario["objective"],
                "failureCount": len(runs),
                "systematicAcrossRepeats": len(runs) == runs_per_scenario,
                "expected": scenario["expected"],
                "failedRuns": runs,
            }
        )

    systematic_count = sum(item["systematicAcrossRepeats"] for item in scenario_summaries)
    metrics = report["metrics"]
    return {
        "metadata": {
            "sourceReportExecutionMode": report["metadata"]["executionMode"],
            "scenarioFixtureSha256": report["metadata"]["scenarioFixtureSha256"],
            "analysisRule": "Classify every preserved failed run without changing fixtures or pass criteria.",
        },
        "baseline": {
            "runCount": report["metadata"]["runCount"],
            "scenarioCount": report["metadata"]["scenarioCount"],
            "runsPerScenario": runs_per_scenario,
            "toolSelectionSuccessRate": metrics["toolSelectionSuccessRate"],
            "confirmationCompleteness": metrics["confirmationCompleteness"],
            "recoverySuccessRate": metrics["recoverySuccessRate"],
            "fallbackDecisionCount": metrics["fallbackDecisionCount"],
            "providerRequests": metrics["providerRequests"],
            "estimatedCostUsd": metrics["estimatedCostUsd"],
        },
        "summary": {
            "failedRunCount": len(failed_cases),
            "failingScenarioCount": len(scenario_summaries),
            "systematicScenarioCount": systematic_count,
            "intermittentScenarioCount": len(scenario_summaries) - systematic_count,
            "failureRunsByFamily": dict(sorted(family_counts.items())),
        },
        "scenarios": scenario_summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify preserved failures in a real Agent evaluation report.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, help="Optional JSON output path; stdout is always emitted.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = analyze_failures(load_json(args.scenarios), load_json(args.report))
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
