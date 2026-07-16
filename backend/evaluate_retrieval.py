import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app
from backend.app.services import embedding_provider, evaluation_service, store


CASE_PATH = ROOT_DIR / "backend" / "evaluation" / "retrieval_cases.json"
REPORT_DIR = ROOT_DIR / "docs" / "status"
MATERIALS = {
    "Spaced repetition": "Widening review intervals strengthen long-term memory and reduce forgetting.",
    "Retrieval practice": "Learners retrieve relevant evidence before answering and then compare the answer with notes.",
    "Weak quiz review": "A weak quiz result should trigger review drafts and focused flashcards for missed concepts.",
    "Container deployment": "A container image packages an application for deployment to an isolated runtime.",
}
MATERIAL_CHUNK_IDS = {
    "Spaced repetition": "chunk_eval_spaced_repetition",
    "Retrieval practice": "chunk_eval_retrieval_practice",
    "Weak quiz review": "chunk_eval_weak_quiz_review",
    "Container deployment": "chunk_eval_container_deployment",
}


class _FailingEmbeddingProvider:
    mode = "keyword"

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("keyword baseline disables embedding queries")


def _register_disposable_session(client: TestClient) -> None:
    client.headers.update({"Origin": "http://127.0.0.1:8001"})
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Retrieval Evaluation",
            "email": "retrieval-evaluation@example.invalid",
            "password": "RetrievalEvaluation123!",
        },
    )
    response.raise_for_status()
    if not client.cookies.get("ai_agent_session"):
        raise RuntimeError("Retrieval evaluation registration did not establish an auth session")
    client.get("/api/auth/me").raise_for_status()


def run_retrieval_evaluation(report_dir: Path = REPORT_DIR) -> dict:
    os.environ["EMBEDDING_PROVIDER"] = "openai-compatible"
    os.environ["EMBEDDING_MODEL"] = os.getenv("EMBEDDING_MODEL", "embedding-3")
    cases = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    original_provider = embedding_provider.get_embedding_provider
    with TemporaryDirectory() as temp_dir:
        store.set_db_path(Path(temp_dir) / "retrieval_evaluation.db")
        store.reset()
        with TestClient(app) as client:
            _register_disposable_session(client)
            goal = _create_goal(client)
            for title, content in MATERIALS.items():
                material = _create_material(client, goal["id"], title, content)
                client.post(f"/api/materials/{material['id']}/chunks").raise_for_status()
                with store.db_connection() as conn:
                    conn.execute(
                        "UPDATE material_chunks SET id = ? WHERE material_id = ?",
                        (MATERIAL_CHUNK_IDS[title], material["id"]),
                    )
            provider = original_provider()
            if provider.mode == "mock":
                raise RuntimeError("Real embedding configuration is required for D3 retrieval evaluation.")
            query_results = []
            for case in cases:
                embedding_provider.get_embedding_provider = lambda: _FailingEmbeddingProvider()
                keyword = client.get("/api/materials/search", params={"query": case["query"], "limit": 3}).json()["data"]
                embedding_provider.get_embedding_provider = original_provider
                semantic = client.get("/api/materials/search", params={"query": case["query"], "limit": 3}).json()["data"]
                query_results.append(
                    {
                        "id": case["id"],
                        "relevantChunkIds": case["relevantChunkIds"],
                        "keywordChunkIds": [item["id"] for item in keyword],
                        "semanticChunkIds": [item["id"] for item in semantic],
                    }
                )
    embedding_provider.get_embedding_provider = original_provider
    report = evaluation_service.build_retrieval_report(
        query_results,
        provider.mode,
        getattr(provider, "model", ""),
    )
    report["metadata"]["caseFile"] = str(CASE_PATH.relative_to(ROOT_DIR)).replace("\\", "/")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "第六版BatchD检索评测报告.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = "\n".join(
        [
            "# Batch D Retrieval Evaluation",
            "",
            f"Provider: `{report['metadata']['provider']}`",
            f"Model: `{report['metadata']['model']}`",
            "",
            "| Mode | Recall@3 | MRR |",
            "|---|---:|---:|",
            f"| keyword | {report['keyword']['recallAt3']} | {report['keyword']['mrr']} |",
            f"| semantic | {report['semantic']['recallAt3']} | {report['semantic']['mrr']} |",
            "",
        ]
    )
    (report_dir / "第六版BatchD检索评测报告.md").write_text(markdown, encoding="utf-8")
    return report


def _create_goal(client: TestClient) -> dict:
    response = client.post("/api/goals", json={"name": "Retrieval evaluation", "subject": "AI Agent", "level": "basic", "deadline": "2026-07-15", "daily_minutes": 30, "notes": ""})
    response.raise_for_status()
    return response.json()["data"]


def _create_material(client: TestClient, goal_id: str, title: str, content: str) -> dict:
    response = client.post("/api/materials", json={"goalId": goal_id, "type": "text", "title": title, "content": content, "url": ""})
    response.raise_for_status()
    return response.json()["data"]


if __name__ == "__main__":
    print(json.dumps(run_retrieval_evaluation(), ensure_ascii=False))
