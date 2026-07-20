from collections import Counter
from statistics import mean


def build_runtime_report(case_results: list[dict]) -> dict:
    total = len(case_results)
    passed = [item for item in case_results if item.get("passed")]
    failed = [item for item in case_results if not item.get("passed")]
    confirmation_cases = [item for item in case_results if item.get("resumeRequired")]
    max_step_cases = [item for item in case_results if item.get("maxStepsScenario")]
    guard_cases = [item for item in case_results if item.get("category") == "guard"]
    steps = [len(item.get("toolSequence") or []) for item in case_results]
    return {
        "summary": {
            "totalCases": total,
            "passedCases": len(passed),
            "failedCaseIds": [item["id"] for item in failed],
            "taskSuccessRate": _rate(passed, total),
            "unauthorizedWriteCount": sum(item.get("unauthorizedWriteCount", 0) for item in case_results),
            "guardInterventionRecall": _rate(
                [item for item in guard_cases if item.get("guardIntervened")], len(guard_cases)
            ),
            "runResumeSuccessRate": _rate(
                [item for item in confirmation_cases if item.get("resumeSucceeded")],
                len(confirmation_cases),
            ),
            "duplicateFormalWriteCount": sum(item.get("duplicateFormalWriteCount", 0) for item in case_results),
            "toolErrorRate": _rate(
                [item for item in case_results if item.get("terminalStatus") == "failed"], total
            ),
            "averageSteps": round(mean(steps), 2) if steps else 0,
            "maxSteps": max(steps, default=0),
            "maxStepsTerminationRate": _rate(
                [item for item in max_step_cases if item.get("terminalStatus") == "max_steps"],
                len(max_step_cases),
            ),
        },
        "cases": case_results,
        "toolCounts": dict(
            Counter(tool for item in case_results for tool in item.get("toolSequence") or [])
        ),
    }


def markdown_summary(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Agent Evaluation Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if key == "failedCaseIds":
            value = ", ".join(value) if value else "none"
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Cases", "", "| ID | Category | Status | Tools | Terminal | Duration ms |", "|---|---|---|---|---|---:|"])
    for item in report["cases"]:
        lines.append(
            "| {id} | {category} | {status} | {tools} | {terminal} | {duration} |".format(
                id=item["id"],
                category=item.get("category", ""),
                status="passed" if item.get("passed") else "failed",
                tools=" -> ".join(item.get("toolSequence") or []) or "none",
                terminal=item.get("terminalStatus", ""),
                duration=item.get("durationMs", 0),
            )
        )
    return "\n".join(lines) + "\n"


def build_retrieval_report(query_results: list[dict], provider: str, model: str) -> dict:
    def metrics(mode: str) -> dict:
        hits = []
        reciprocal_ranks = []
        for item in query_results:
            ranked_ids = item[mode]
            relevant_ids = set(item["relevantChunkIds"])
            hits.append(bool(relevant_ids.intersection(ranked_ids[:3])))
            rank = next((index + 1 for index, chunk_id in enumerate(ranked_ids) if chunk_id in relevant_ids), 0)
            reciprocal_ranks.append(1 / rank if rank else 0)
        return {
            "recallAt3": round(sum(hits) / len(hits), 4) if hits else 0.0,
            "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0,
        }

    return {
        "metadata": {"provider": provider, "model": model, "queryCount": len(query_results)},
        "keyword": metrics("keywordChunkIds"),
        "semantic": metrics("semanticChunkIds"),
        "queries": query_results,
    }


def build_batch4_retrieval_report(query_results: list[dict], *, corpus_count: int) -> dict:
    """Calculate fixed-set retrieval metrics without conflating dense and hybrid modes."""

    def metrics(mode: str) -> dict:
        recalls_at_3 = []
        recalls_at_5 = []
        reciprocal_ranks = []
        ndcgs_at_5 = []
        latencies = []
        for item in query_results:
            ranked_ids = item["results"][mode]["documentIds"]
            relevant_ids = set(item["relevantDocumentIds"])
            recalls_at_3.append(_recall_at_k(ranked_ids, relevant_ids, 3))
            recalls_at_5.append(_recall_at_k(ranked_ids, relevant_ids, 5))
            reciprocal_ranks.append(_reciprocal_rank(ranked_ids, relevant_ids))
            ndcgs_at_5.append(_ndcg_at_k(ranked_ids, relevant_ids, 5))
            latencies.append(item["results"][mode]["latencyMs"])
        return {
            "recallAt3": _mean_rate(recalls_at_3),
            "recallAt5": _mean_rate(recalls_at_5),
            "mrr": _mean_rate(reciprocal_ranks),
            "ndcgAt5": _mean_rate(ndcgs_at_5),
            "p50LatencyMs": _percentile(latencies, 50),
            "p95LatencyMs": _percentile(latencies, 95),
        }

    return {
        "metadata": {
            "executionMode": "mock-offline",
            "queryCount": len(query_results),
            "documentCount": corpus_count,
            "retrievalModes": ["keyword", "dense", "hybrid"],
        },
        "keyword": metrics("keyword"),
        "dense": metrics("dense"),
        "hybrid": metrics("hybrid"),
        "queries": query_results,
    }


def build_batch4_qa_report(case_results: list[dict]) -> dict:
    supported = [item for item in case_results if not item["shouldRefuse"]]
    insufficient = [item for item in case_results if item["shouldRefuse"]]
    citation_checks = [item["citationAccurate"] for item in supported]
    grounded_checks = [item["grounded"] for item in supported]
    true_positive = sum(1 for item in insufficient if item["refused"])
    false_positive = sum(1 for item in supported if item["refused"])
    false_negative = sum(1 for item in insufficient if not item["refused"])
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _f1(precision, recall)
    return {
        "metadata": {
            "executionMode": "mock-offline",
            "caseCount": len(case_results),
            "categoryCounts": dict(Counter(item["category"] for item in case_results)),
        },
        "metrics": {
            "citationAccuracy": _mean_rate(citation_checks),
            "groundedness": _mean_rate(grounded_checks),
            "insufficientPrecision": precision,
            "insufficientRecall": recall,
            "insufficientF1": f1,
            "p50LatencyMs": _percentile([item["latencyMs"] for item in case_results], 50),
            "p95LatencyMs": _percentile([item["latencyMs"] for item in case_results], 95),
        },
        "failureCaseIds": [item["id"] for item in case_results if not item["passed"]],
        "cases": case_results,
    }


def build_batch4_agent_report(case_results: list[dict]) -> dict:
    confirmation_cases = [item for item in case_results if item.get("category") == "confirmation"]
    resumable_cases = [item for item in confirmation_cases if item.get("resumeRequired")]
    guard_cases = [item for item in case_results if item.get("category") == "guard"]
    passed = [item for item in case_results if item.get("passed")]
    return {
        "metadata": {
            "executionMode": "mock-regression",
            "runCount": len(case_results),
            "realModelRunsPerScenario": 0,
            "tokenAccounting": "Mock provider makes no billable model request.",
        },
        "metrics": {
            "toolSelectionSuccessRate": _ratio(len(passed), len(case_results)),
            "guardRecall": _ratio(
                sum(1 for item in guard_cases if item.get("guardIntervened")), len(guard_cases)
            ),
            "confirmationCompleteness": _ratio(
                sum(1 for item in confirmation_cases if item.get("passed")), len(confirmation_cases)
            ),
            "recoverySuccessRate": _ratio(
                sum(1 for item in resumable_cases if item.get("resumeSucceeded")), len(resumable_cases)
            ),
            "p50LatencyMs": _percentile([item.get("durationMs", 0) for item in case_results], 50),
            "p95LatencyMs": _percentile([item.get("durationMs", 0) for item in case_results], 95),
            "promptTokens": 0,
            "completionTokens": 0,
            "estimatedCostUsd": 0.0,
        },
        "failureCaseIds": [item["id"] for item in case_results if not item.get("passed")],
        "cases": case_results,
    }


def build_batch4_real_agent_report(
    case_results: list[dict],
    *,
    provider_requests: int,
    usage_response_count: int,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float | None,
    reserved_prompt_tokens: int,
    reserved_completion_tokens: int,
    reserved_cost_usd: float,
) -> dict:
    """Summarize bounded real-provider Agent runs without retaining model text."""

    confirmation_cases = [item for item in case_results if item.get("category") == "confirmation"]
    recovery_cases = [
        item
        for item in confirmation_cases
        if item.get("confirmationDisposition") == "accepted"
    ]
    guard_cases = [item for item in case_results if item.get("category") == "guard"]
    return {
        "metadata": {
            "executionMode": "configured-deepseek-real-agent",
            "runCount": len(case_results),
            "scenarioCount": len({item.get("scenarioId") for item in case_results}),
            "runsPerScenario": 3,
            "credentialPolicy": "No credentials, provider configuration, prompts, or model responses are retained.",
            "guardMethod": "Guard cases inject a fixed invalid decision after a real provider response; this validates the guard, not the model's natural invalid-output rate.",
            "formatRepair": "Disabled for this bounded evaluation; malformed model JSON falls back safely without a second provider request.",
        },
        "metrics": {
            "toolSelectionSuccessRate": _ratio(
                sum(1 for item in case_results if item.get("toolSelectionPassed")),
                len(case_results),
            ),
            "guardRecall": _ratio(
                sum(1 for item in guard_cases if item.get("guardIntervened")),
                len(guard_cases),
            ),
            "confirmationCompleteness": _ratio(
                sum(1 for item in confirmation_cases if item.get("confirmationComplete")),
                len(confirmation_cases),
            ),
            "recoverySuccessRate": _ratio(
                sum(1 for item in recovery_cases if item.get("recoverySucceeded")),
                len(recovery_cases),
            ),
            "p50LatencyMs": _percentile([item.get("durationMs", 0) for item in case_results], 50),
            "p95LatencyMs": _percentile([item.get("durationMs", 0) for item in case_results], 95),
            "providerRequests": provider_requests,
            "usageResponseCount": usage_response_count,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "estimatedCostUsd": estimated_cost_usd,
            "reservedPromptTokens": reserved_prompt_tokens,
            "reservedCompletionTokens": reserved_completion_tokens,
            "reservedCostUsd": reserved_cost_usd,
            "fallbackDecisionCount": sum(
                int(item.get("fallbackDecisionCount") or 0) for item in case_results
            ),
            "deterministicDecisionCount": sum(
                int(item.get("deterministicDecisionCount") or 0) for item in case_results
            ),
            "runsWithDeterministicDecision": sum(
                1 for item in case_results if int(item.get("deterministicDecisionCount") or 0) > 0
            ),
        },
        "failureRunIds": [item["runId"] for item in case_results if not item.get("passed")],
        "cases": case_results,
    }


def _rate(matching: list[dict], total: int) -> float:
    return round(len(matching) / total, 4) if total else 0.0


def _recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return len(set(ranked_ids[:k]).intersection(relevant_ids)) / len(relevant_ids)


def _reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for index, document_id in enumerate(ranked_ids, start=1):
        if document_id in relevant_ids:
            return 1 / index
    return 0.0


def _ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    dcg = sum(
        1 / _log2(index + 1)
        for index, document_id in enumerate(ranked_ids[:k], start=1)
        if document_id in relevant_ids
    )
    ideal_count = min(len(relevant_ids), k)
    ideal_dcg = sum(1 / _log2(index + 1) for index in range(1, ideal_count + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _log2(value: int) -> float:
    from math import log2

    return log2(value)


def _mean_rate(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _percentile(values: list[int | float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1))))
    return round(float(ordered[index]), 3)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
