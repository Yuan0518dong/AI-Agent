import json
from collections import Counter
from pathlib import Path


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "agent_scenarios.json"


def test_agent_evaluation_fixture_has_required_20_case_distribution():
    scenarios = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    assert len(scenarios) == 20
    assert len({scenario["id"] for scenario in scenarios}) == 20
    assert Counter(scenario["category"] for scenario in scenarios) == {
        "happy_path": 5,
        "insufficient_material": 3,
        "guard": 3,
        "confirmation": 3,
        "tool_failure": 2,
        "terminal": 2,
        "feedback_memory": 2,
    }
    for scenario in scenarios:
        assert scenario["decisionMode"] == "hybrid"
        assert 1 <= scenario["maxSteps"] <= 8
        expected = scenario["expected"]
        assert set(expected) == {
            "allowedTools",
            "requiredTools",
            "forbiddenTools",
            "terminalStatuses",
            "stateAssertions",
        }
