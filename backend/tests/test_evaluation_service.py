from backend.app.services import evaluation_service


def test_runtime_report_calculates_required_metrics_and_markdown():
    report = evaluation_service.build_runtime_report(
        [
            {"id": "case_1", "category": "guard", "passed": True, "guardIntervened": True, "toolSequence": [], "terminalStatus": "completed", "durationMs": 10},
            {"id": "case_2", "category": "confirmation", "passed": True, "resumeRequired": True, "resumeSucceeded": True, "toolSequence": ["create_task_draft"], "terminalStatus": "max_steps", "durationMs": 20},
            {"id": "case_3", "category": "terminal", "passed": False, "maxStepsScenario": True, "toolSequence": ["review_material"], "terminalStatus": "max_steps", "durationMs": 30},
        ]
    )

    assert report["summary"]["taskSuccessRate"] == 0.6667
    assert report["summary"]["guardInterventionRecall"] == 1.0
    assert report["summary"]["runResumeSuccessRate"] == 1.0
    assert report["summary"]["maxStepsTerminationRate"] == 1.0
    assert report["summary"]["failedCaseIds"] == ["case_3"]
    assert "case_2" in evaluation_service.markdown_summary(report)


def test_retrieval_report_calculates_keyword_and_semantic_metrics():
    report = evaluation_service.build_retrieval_report(
        [
            {"id": "q1", "relevantChunkIds": ["a"], "keywordChunkIds": ["x", "a"], "semanticChunkIds": ["a"]},
            {"id": "q2", "relevantChunkIds": ["b"], "keywordChunkIds": ["x"], "semanticChunkIds": ["x", "b"]},
        ],
        "openai-compatible",
        "embedding-3",
    )

    assert report["keyword"] == {"recallAt3": 0.5, "mrr": 0.25}
    assert report["semantic"] == {"recallAt3": 1.0, "mrr": 0.75}
