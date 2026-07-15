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


def _rate(matching: list[dict], total: int) -> float:
    return round(len(matching) / total, 4) if total else 0.0
