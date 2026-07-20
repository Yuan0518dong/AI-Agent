import json

from backend import evaluate_batch4


def test_batch4_fixed_sets_meet_required_size_and_categories():
    corpus = json.loads(evaluate_batch4.CORPUS_PATH.read_text(encoding="utf-8"))
    retrieval_cases = json.loads(evaluate_batch4.RETRIEVAL_PATH.read_text(encoding="utf-8"))
    qa_cases = json.loads(evaluate_batch4.QA_PATH.read_text(encoding="utf-8"))

    assert len(corpus) >= 10
    assert len(retrieval_cases) >= 50
    assert all(any("\u4e00" <= char <= "\u9fff" for char in item["query"]) for item in retrieval_cases)
    assert len(qa_cases) >= 30
    assert {item["category"] for item in qa_cases} == {
        "answerable",
        "cross_material",
        "insufficient_material",
        "conflicting_material",
    }


def test_batch4_offline_evaluation_writes_complete_fixed_set_reports(tmp_path):
    reports = evaluate_batch4.run_batch4_evaluation(tmp_path)

    retrieval = reports["retrieval"]
    assert retrieval["metadata"]["documentCount"] == 10
    assert retrieval["metadata"]["queryCount"] == 50
    for mode in ("keyword", "dense", "hybrid"):
        assert set(retrieval[mode]) == {
            "recallAt3",
            "recallAt5",
            "mrr",
            "ndcgAt5",
            "p50LatencyMs",
            "p95LatencyMs",
        }
        assert 0.0 <= retrieval[mode]["recallAt5"] <= 1.0

    qa = reports["qa"]
    assert qa["metadata"]["caseCount"] == 32
    assert qa["metadata"]["categoryCounts"] == {
        "answerable": 8,
        "cross_material": 8,
        "insufficient_material": 8,
        "conflicting_material": 8,
    }
    assert set(qa["metrics"]) >= {
        "citationAccuracy",
        "groundedness",
        "insufficientPrecision",
        "insufficientRecall",
        "insufficientF1",
    }
    assert qa["metrics"]["insufficientF1"] >= 0.8

    agent = reports["agentMock"]
    assert agent["metadata"]["runCount"] == 20
    assert agent["metadata"]["realModelRunsPerScenario"] == 0
    assert agent["metrics"]["promptTokens"] == 0
    assert agent["metrics"]["estimatedCostUsd"] == 0.0
    assert agent["metrics"]["recoverySuccessRate"] == 1.0

    budget = reports["realModelBudget"]
    assert budget["noRequestSent"] is True
    assert budget["agentFullRuns"] == 60
    assert budget["totalProviderRequests"]["maximum"] == 126
    assert budget["estimatedCostUsd"] == 0.224028
    assert budget["estimatedCostWith20PercentBufferUsd"] == 0.268834

    assert (tmp_path / "第七版Batch4离线评测报告.md").exists()
    assert (tmp_path / "第七版Batch4检索评测报告.json").exists()
    assert (tmp_path / "第七版Batch4问答评测报告.json").exists()
    assert (tmp_path / "第七版Batch4AgentMock评测报告.json").exists()
    assert (tmp_path / "第七版Batch4真实模型预算报告.json").exists()
