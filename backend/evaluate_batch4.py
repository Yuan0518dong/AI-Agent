"""Offline Batch 4 evaluation runner.

This runner intentionally uses the deterministic Mock providers.  It produces
fixed-set evidence for Batch 4 and never loads or prints provider credentials.
Use ``build_real_model_budget`` before authorizing the separate real-model run.
"""

import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import evaluate_agent
from backend.app.main import app
from backend.app.services import agent_service, embedding_provider, evaluation_service, material_store, store


EVALUATION_DIR = ROOT_DIR / "backend" / "evaluation"
DEFAULT_REPORT_DIR = ROOT_DIR / "docs" / "evaluation"
CORPUS_PATH = EVALUATION_DIR / "v7_retrieval_corpus.json"
RETRIEVAL_PATH = EVALUATION_DIR / "v7_retrieval_cases.json"
QA_PATH = EVALUATION_DIR / "v7_qa_cases.json"
SCENARIO_PATH = EVALUATION_DIR / "agent_scenarios.json"
DEEPSEEK_V4_FLASH_CACHE_MISS_INPUT_USD_PER_MILLION = 0.14
DEEPSEEK_V4_FLASH_OUTPUT_USD_PER_MILLION = 0.28
# The fixed-path Mock audit reaches 11,404 bytes before the scoped
# max_tokens field is added. The real runner rejects a larger request before
# sending it, allowing this rounded cap to bound paid input usage safely.
MAX_REAL_AGENT_PROMPT_UTF8_BYTES = 12_000
MAX_REAL_AGENT_COMPLETION_TOKENS = 350


class _FailingEmbeddingProvider:
    mode = "keyword"

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("Batch 4 keyword baseline disables dense retrieval.")


def run_batch4_evaluation(report_dir: Path = DEFAULT_REPORT_DIR) -> dict:
    """Run the fixed retrieval and QA sets plus the 20-case Mock regression."""

    _set_offline_environment()
    corpus = _load_json(CORPUS_PATH)
    retrieval_cases = _load_json(RETRIEVAL_PATH)
    qa_cases = _load_json(QA_PATH)
    with TemporaryDirectory() as temp_dir:
        store.set_db_path(Path(temp_dir) / "batch4_evaluation.db")
        store.reset()
        with TestClient(app) as client:
            user_id = _register_disposable_session(client)
            document_by_material_id = _seed_corpus(client, corpus)
            retrieval_results = _evaluate_retrieval(client, retrieval_cases, document_by_material_id)
            qa_results = _evaluate_qa(qa_cases, document_by_material_id, user_id)

    retrieval_report = evaluation_service.build_batch4_retrieval_report(
        retrieval_results, corpus_count=len(corpus)
    )
    retrieval_report["metadata"].update(_fixture_metadata(CORPUS_PATH, RETRIEVAL_PATH))
    qa_report = evaluation_service.build_batch4_qa_report(qa_results)
    qa_report["metadata"].update(_fixture_metadata(CORPUS_PATH, QA_PATH))

    with TemporaryDirectory() as agent_temp_dir:
        legacy_agent_report = evaluate_agent.run_evaluation(Path(agent_temp_dir))
    agent_report = evaluation_service.build_batch4_agent_report(legacy_agent_report["cases"])
    agent_report["metadata"].update(_fixture_metadata(SCENARIO_PATH))
    budget = build_real_model_budget()
    reports = {
        "retrieval": retrieval_report,
        "qa": qa_report,
        "agentMock": agent_report,
        "realModelBudget": budget,
    }
    _write_reports(report_dir, reports)
    return reports


def verify_repeatability() -> dict:
    """Verify stable rankings and classification metrics across two fresh runs.

    Latencies are intentionally excluded: they are measured observations rather
    than deterministic outputs.
    """

    with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
        first = run_batch4_evaluation(Path(first_dir))
        second = run_batch4_evaluation(Path(second_dir))
    comparable = {
        "retrieval": {
            mode: first["retrieval"][mode]
            for mode in ("keyword", "dense", "hybrid")
        },
        "qa": first["qa"]["metrics"],
        "agent": first["agentMock"]["metrics"],
    }
    repeat = {
        "retrieval": {
            mode: second["retrieval"][mode]
            for mode in ("keyword", "dense", "hybrid")
        },
        "qa": second["qa"]["metrics"],
        "agent": second["agentMock"]["metrics"],
    }
    for section in ("retrieval", "qa", "agent"):
        _remove_latency_fields(comparable[section])
        _remove_latency_fields(repeat[section])
    return {
        "passed": comparable == repeat,
        "checked": ["rankings", "retrieval metrics", "QA classifications", "Mock Agent metrics"],
        "excluded": ["p50LatencyMs", "p95LatencyMs"],
    }


def build_real_model_budget() -> dict:
    """Calculate, but do not send, the bounded real Agent evaluation workload."""

    scenarios = _load_json(SCENARIO_PATH)
    runs_per_scenario = 3
    agent_runs = len(scenarios) * runs_per_scenario
    base_agent_decision_upper_bound = sum(item["maxSteps"] for item in scenarios) * runs_per_scenario
    accepted_confirmation_cases = sum(
        1
        for item in scenarios
        if item["category"] == "confirmation" and item["id"] != "agent_case_013"
    )
    confirmation_resume_readbacks = accepted_confirmation_cases * runs_per_scenario
    agent_decision_upper_bound = base_agent_decision_upper_bound + confirmation_resume_readbacks
    input_token_upper_bound = agent_decision_upper_bound * MAX_REAL_AGENT_PROMPT_UTF8_BYTES
    output_token_upper_bound = agent_decision_upper_bound * MAX_REAL_AGENT_COMPLETION_TOKENS
    estimated_cost = round(
        input_token_upper_bound / 1_000_000 * DEEPSEEK_V4_FLASH_CACHE_MISS_INPUT_USD_PER_MILLION
        + output_token_upper_bound / 1_000_000 * DEEPSEEK_V4_FLASH_OUTPUT_USD_PER_MILLION,
        6,
    )
    return {
        "status": "approval_required",
        "provider": "DeepSeek via configured OpenAI-compatible provider",
        "noRequestSent": True,
        "agentScenarioCount": len(scenarios),
        "runsPerScenario": runs_per_scenario,
        "agentFullRuns": agent_runs,
        "agentDecisionRequests": {
            "minimum": agent_runs,
            "maximum": agent_decision_upper_bound,
            "baseStepBound": base_agent_decision_upper_bound,
            "acceptedConfirmationReadbacks": confirmation_resume_readbacks,
        },
        "qaModelRequests": 0,
        "scope": {
            "included": "20 fixed Agent scenarios x 3 real DeepSeek runs, including accepted-confirmation readbacks.",
            "excluded": "The fixed QA set remains an offline deterministic evaluation; it does not make paid calls in this Batch 4 runner.",
            "formatRepair": "Disabled only inside the bounded real evaluation so malformed JSON falls back safely without an unbudgeted retry.",
            "runCreation": "Run creation uses a rule-based initial snapshot; each persisted execution decision uses the real provider, avoiding a discarded paid creation decision.",
        },
        "totalProviderRequests": {"minimum": agent_runs, "maximum": agent_decision_upper_bound},
        "tokenEstimate": {
            "promptReservationTokensPerRequest": MAX_REAL_AGENT_PROMPT_UTF8_BYTES,
            "completionTokensPerRequest": MAX_REAL_AGENT_COMPLETION_TOKENS,
            "promptReservationUpperBound": input_token_upper_bound,
            "upperBoundCompletionTokens": output_token_upper_bound,
            "promptReservationMethod": "Each real request is rejected before send when its UTF-8 payload exceeds 12,000 bytes; one byte per token is used as a conservative reservation bound.",
        },
        "estimatedCostUsd": estimated_cost,
        "estimatedCostWith20PercentBufferUsd": round(estimated_cost * 1.2, 6),
        "costFormula": "promptReservationUpperBound / 1,000,000 * inputUsdPerMillion + upperBoundCompletionTokens / 1,000,000 * outputUsdPerMillion",
        "pricingSnapshot": {
            "source": "https://api-docs.deepseek.com/quick_start/pricing",
            "checkedAt": "2026-07-20",
            "modelFamily": "DeepSeek V4 Flash non-thinking pricing snapshot",
            "inputCacheAssumption": "cache miss",
            "inputUsdPerMillion": DEEPSEEK_V4_FLASH_CACHE_MISS_INPUT_USD_PER_MILLION,
            "outputUsdPerMillion": DEEPSEEK_V4_FLASH_OUTPUT_USD_PER_MILLION,
        },
        "authorizationNeeded": "Approve at most 126 provider requests and a USD 0.27 ceiling before the real-model runner is enabled.",
    }


def _set_offline_environment() -> None:
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["LLM_ENV_FILE"] = str(ROOT_DIR / "backend" / "missing-batch4-evaluation.env")
    os.environ["EMBEDDING_ENV_FILE"] = str(ROOT_DIR / "backend" / "missing-batch4-evaluation.env")
    os.environ["REGISTERED_DAILY_LLM_LIMIT"] = "1000"
    os.environ["GLOBAL_DAILY_LLM_LIMIT"] = "1000"
    os.environ["REGISTERED_DAILY_EMBEDDING_QUERY_LIMIT"] = "1000"
    os.environ["REGISTERED_DAILY_EMBEDDING_CHUNK_LIMIT"] = "1000"


def _register_disposable_session(client: TestClient) -> str:
    client.headers.update({"Origin": "http://127.0.0.1:8001"})
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Batch 4 Evaluation",
            "email": "batch4-evaluation@example.invalid",
            "password": "Batch4Evaluation123!",
        },
    )
    response.raise_for_status()
    user = store.get_user_by_email("batch4-evaluation@example.invalid")
    if not user:
        raise RuntimeError("Batch 4 evaluation session did not create a user.")
    return user["id"]


def _seed_corpus(client: TestClient, corpus: list[dict]) -> dict[str, str]:
    goal = client.post(
        "/api/goals",
        json={
            "name": "Batch 4 固定评测资料",
            "subject": "AI Agent",
            "level": "有基础",
            "deadline": "2026-12-31",
            "daily_minutes": 30,
            "notes": "仅用于离线固定评测。",
        },
    ).json()["data"]
    document_by_material_id = {}
    for document in corpus:
        response = client.post(
            "/api/materials",
            json={
                "goalId": goal["id"],
                "type": "text",
                "title": document["title"],
                "content": document["content"],
                "url": "",
            },
        )
        response.raise_for_status()
        material = response.json()["data"]
        chunks = client.post(f"/api/materials/{material['id']}/chunks")
        chunks.raise_for_status()
        document_by_material_id[material["id"]] = document["id"]
    return document_by_material_id


def _evaluate_retrieval(
    client: TestClient, cases: list[dict], document_by_material_id: dict[str, str]
) -> list[dict]:
    results = []
    for case in cases:
        mode_results = {}
        for mode in ("keyword", "dense", "hybrid"):
            started = time.perf_counter()
            with _retrieval_mode(mode):
                response = client.get("/api/materials/search", params={"query": case["query"], "limit": 5})
            response.raise_for_status()
            mode_results[mode] = {
                "documentIds": _unique_document_ids(response.json()["data"], document_by_material_id),
                "latencyMs": round((time.perf_counter() - started) * 1000, 3),
            }
        results.append({
            "id": case["id"],
            "query": case["query"],
            "relevantDocumentIds": case["relevantDocumentIds"],
            "results": mode_results,
        })
    return results


def _evaluate_qa(cases: list[dict], document_by_material_id: dict[str, str], user_id: str) -> list[dict]:
    results = []
    for case in cases:
        started = time.perf_counter()
        answer = agent_service.answer_question(case["question"], limit=5, user_id=user_id)
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        cited_document_ids = _unique_document_ids(answer["references"], document_by_material_id)
        citation_evidence = [
            {
                "documentId": document_by_material_id.get(reference.get("materialId"), ""),
                "score": reference.get("score", 0),
                "searchMode": reference.get("searchMode", ""),
                "retrievalModes": reference.get("retrievalModes", []),
            }
            for reference in answer["references"]
        ]
        acceptable = set(case["acceptableDocumentIds"])
        refused = answer["mode"] == "grounded-refusal" and not answer["isFromMaterial"]
        citation_accurate = bool(cited_document_ids) and set(cited_document_ids).issubset(acceptable)
        grounded = (
            (refused and case["shouldRefuse"])
            or (not refused and answer["isFromMaterial"] and citation_accurate)
        )
        passed = refused == case["shouldRefuse"] and (case["shouldRefuse"] or grounded)
        results.append({
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "shouldRefuse": case["shouldRefuse"],
            "refused": refused,
            "isFromMaterial": answer["isFromMaterial"],
            "citationAccurate": citation_accurate if not case["shouldRefuse"] else refused,
            "grounded": grounded,
            "citedDocumentIds": cited_document_ids,
            "citationEvidence": citation_evidence,
            "acceptableDocumentIds": case["acceptableDocumentIds"],
            "latencyMs": latency_ms,
            "passed": passed,
        })
    return results


@contextmanager
def _retrieval_mode(mode: str):
    original_provider = embedding_provider.get_embedding_provider
    original_score = material_store._score_chunk
    try:
        if mode == "keyword":
            embedding_provider.get_embedding_provider = lambda: _FailingEmbeddingProvider()
        elif mode == "dense":
            material_store._score_chunk = lambda query, terms, haystack: 0
        elif mode != "hybrid":
            raise ValueError(f"Unknown retrieval mode: {mode}")
        yield
    finally:
        embedding_provider.get_embedding_provider = original_provider
        material_store._score_chunk = original_score


def _unique_document_ids(items: list[dict], document_by_material_id: dict[str, str]) -> list[str]:
    document_ids = []
    for item in items:
        document_id = document_by_material_id.get(item.get("materialId"))
        if document_id and document_id not in document_ids:
            document_ids.append(document_id)
    return document_ids


def _fixture_metadata(*paths: Path) -> dict:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return {
        "fixtureFiles": [str(path.relative_to(ROOT_DIR)).replace("\\", "/") for path in paths],
        "fixtureSha256": digest.hexdigest(),
    }


def _write_reports(report_dir: Path, reports: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "第七版Batch4检索评测报告.json": reports["retrieval"],
        "第七版Batch4问答评测报告.json": reports["qa"],
        "第七版Batch4AgentMock评测报告.json": reports["agentMock"],
        "第七版Batch4真实模型预算报告.json": reports["realModelBudget"],
    }
    for name, content in outputs.items():
        (report_dir / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report_dir / "第七版Batch4离线评测报告.md").write_text(
        _markdown_summary(reports), encoding="utf-8"
    )


def _markdown_summary(reports: dict) -> str:
    retrieval = reports["retrieval"]
    qa = reports["qa"]
    agent = reports["agentMock"]
    budget = reports["realModelBudget"]
    lines = [
        "# 第七版 Batch 4 离线评测报告",
        "",
        "运行模式：`mock-offline`。本报告不包含真实模型调用、Token 消耗或账单成本。",
        "",
        "## 检索集",
        "",
        f"固定资料 {retrieval['metadata']['documentCount']} 份，中文查询 {retrieval['metadata']['queryCount']} 条。",
        "",
        "| 模式 | Recall@3 | Recall@5 | MRR | nDCG@5 | p50 延迟 ms | p95 延迟 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in ("keyword", "dense", "hybrid"):
        metrics = retrieval[mode]
        lines.append(
            f"| {mode} | {metrics['recallAt3']} | {metrics['recallAt5']} | {metrics['mrr']} | {metrics['ndcgAt5']} | {metrics['p50LatencyMs']} | {metrics['p95LatencyMs']} |"
        )
    lines.extend([
        "",
        "## 问答集",
        "",
        f"固定问答 {qa['metadata']['caseCount']} 条，覆盖可回答、跨资料、资料不足和冲突资料。",
        "",
        "| 引用准确率 | Groundedness | 资料不足 Precision | 资料不足 Recall | 资料不足 F1 |",
        "|---:|---:|---:|---:|---:|",
        f"| {qa['metrics']['citationAccuracy']} | {qa['metrics']['groundedness']} | {qa['metrics']['insufficientPrecision']} | {qa['metrics']['insufficientRecall']} | {qa['metrics']['insufficientF1']} |",
        "",
        "冲突资料样例只核验引用集合是否落在两份条件化资料中；当前回答链路没有自动判定资料冲突或裁决优先级。",
        "",
        "## Agent Mock 回归",
        "",
        "| 场景 | 工具选择成功率 | Guard 召回 | 确认完整性 | 恢复成功率 | p50 延迟 ms | p95 延迟 ms | Token | 成本 USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| 20 个固定场景，Mock | {agent['metrics']['toolSelectionSuccessRate']} | {agent['metrics']['guardRecall']} | {agent['metrics']['confirmationCompleteness']} | {agent['metrics']['recoverySuccessRate']} | {agent['metrics']['p50LatencyMs']} | {agent['metrics']['p95LatencyMs']} | 0 | 0.0 |",
        "",
        "## 真实模型预算门槛",
        "",
        f"真实 Agent 场景需要 {budget['agentFullRuns']} 个完整 Run（20 x 3），模型请求上界 {budget['totalProviderRequests']['maximum']}，发送前按每请求 {budget['tokenEstimate']['promptReservationTokensPerRequest']} prompt Token 保守预留，总上界为 {budget['tokenEstimate']['promptReservationUpperBound']}；completion 上界为 {budget['tokenEstimate']['upperBoundCompletionTokens']}。",
        "未取得明确调用次数和预算授权，且未确认当前模型单价前，不发送批量请求。",
        "",
    ] )
    return "\n".join(lines)


def _remove_latency_fields(value) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if key in {"p50LatencyMs", "p95LatencyMs"}:
                value.pop(key)
            else:
                _remove_latency_fields(value[key])
    elif isinstance(value, list):
        for item in value:
            _remove_latency_fields(item)


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    result = run_batch4_evaluation()
    print(json.dumps({
        "retrieval": {mode: result["retrieval"][mode] for mode in ("keyword", "dense", "hybrid")},
        "qa": result["qa"]["metrics"],
        "agentMock": result["agentMock"]["metrics"],
        "realModelBudget": result["realModelBudget"],
    }, ensure_ascii=False, indent=2))
