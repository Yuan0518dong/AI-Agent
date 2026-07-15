import json

from backend import evaluate_agent


def test_agent_evaluation_runs_all_fixtures_and_writes_reports(tmp_path):
    report = evaluate_agent.run_evaluation(tmp_path)

    assert report["summary"]["totalCases"] == 20
    assert report["summary"]["passedCases"] == 20
    assert report["summary"]["failedCaseIds"] == []
    assert report["summary"]["guardInterventionRecall"] == 1.0
    assert report["summary"]["runResumeSuccessRate"] == 1.0
    assert report["summary"]["maxStepsTerminationRate"] == 1.0
    persisted = json.loads((tmp_path / "第六版BatchD评测报告.json").read_text(encoding="utf-8"))
    assert persisted["summary"] == report["summary"]
    assert "agent_case_020" in (tmp_path / "第六版BatchD评测报告.md").read_text(encoding="utf-8")
