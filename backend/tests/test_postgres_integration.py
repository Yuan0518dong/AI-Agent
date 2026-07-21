import os
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fsrs import Card
from sqlalchemy import text

from backend.app.main import app
from backend.app.services import database, llm_provider, material_store, store


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def postgres_database(monkeypatch):
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", database_url)
    monkeypatch.setenv("RATE_LIMIT_HASH_SALT", f"postgres-integration-{uuid4().hex}")
    database.set_sqlite_test_mode(False)
    store.init_db()
    yield
    database.set_sqlite_test_mode(True)


def test_postgres_schema_session_hash_and_atomic_usage_counter():
    engine = database.get_engine()
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one() == "vector"
        assert connection.execute(text("SELECT to_regclass('public.auth_sessions')")).scalar_one() == "auth_sessions"
        assert connection.execute(text("SELECT to_regclass('public.model_usage_counters')")).scalar_one() == "model_usage_counters"

    client = TestClient(app)
    email = f"postgres-{uuid4().hex}@example.test"
    response = client.post(
        "/api/auth/register",
        json={"name": "Postgres", "email": email, "password": "secret123"},
    )
    assert response.status_code == 200
    raw_cookie = response.cookies.get("ai_agent_session")
    assert raw_cookie

    with engine.connect() as connection:
        token_hash = connection.execute(
            text(
                """
                SELECT auth_sessions.token_hash
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE users.email = :email
                """
            ),
            {"email": email},
        ).scalar_one()
    assert token_hash != raw_cookie
    assert len(token_hash) == 64

    now = store.now_iso()
    reservations = [("test_quota", f"owner-{uuid4().hex}", "2026-07-16", 1, 1)]
    assert store.reserve_model_usage_limits(reservations, now) is True
    assert store.reserve_model_usage_limits(reservations, now) is False


def test_postgres_batch3_pgvector_schema_has_2048_vector_and_cosine_hnsw_index():
    engine = database.get_engine()
    query_vector = "[1," + ",".join("0" for _ in range(2047)) + "]"
    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one() == "vector"
        column_type = connection.execute(
            text(
                """
                SELECT format_type(attribute.atttypid, attribute.atttypmod)
                FROM pg_attribute AS attribute
                JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                WHERE relation.relname = 'material_chunks'
                  AND attribute.attname = 'embedding_vector'
                  AND attribute.attnum > 0
                  AND NOT attribute.attisdropped
                """
            )
        ).scalar_one()
        assert column_type == "vector(2048)"
        index_definition = connection.execute(
            text("SELECT pg_get_indexdef('idx_material_chunks_embedding_vector_hnsw'::regclass)")
        ).scalar_one().lower()
        assert "using hnsw" in index_definition
        assert "halfvec_cosine_ops" in index_definition
        assert "halfvec(2048)" in index_definition

        # Execute the application query, then prove its candidate stage uses
        # HNSW before the full-precision vector rerank.
        dense_results = material_store._postgres_dense_search([1.0] + [0.0] * 2047, None)
        assert len(dense_results) <= 20
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        explain_plan = "\n".join(
            connection.execute(
                text(
                    """
                    EXPLAIN (COSTS OFF)
                    WITH candidates AS MATERIALIZED (
                        SELECT material_chunks.id
                        FROM material_chunks
                        JOIN materials ON materials.id = material_chunks.material_id
                        WHERE embedding_vector IS NOT NULL
                        ORDER BY embedding_vector::halfvec(2048) <=> CAST(:embedding AS halfvec(2048))
                        LIMIT 100
                    )
                    SELECT material_chunks.id
                    FROM candidates
                    JOIN material_chunks ON material_chunks.id = candidates.id
                    JOIN materials ON materials.id = material_chunks.material_id
                    ORDER BY material_chunks.embedding_vector <=> CAST(:embedding AS vector)
                    LIMIT 20
                    """
                ),
                {"embedding": query_vector},
            ).scalars()
        )
    assert "idx_material_chunks_embedding_vector_hnsw" in explain_plan


def test_postgres_auth_rate_limits_and_usage_reservations_are_atomic(monkeypatch):
    suffix = uuid4().hex
    monkeypatch.setenv("RATE_LIMIT_HASH_SALT", f"postgres-integration-{suffix}")
    monkeypatch.setenv("REGISTER_IP_HOURLY_LIMIT", "1")
    monkeypatch.setenv("LOGIN_IP_15_MINUTE_LIMIT", "1")
    monkeypatch.setenv("DEMO_IP_HOURLY_LIMIT", "1")
    email = f"rate-limit-{suffix}@example.test"

    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"name": "Rate Limit", "email": email, "password": "secret123"},
        )
        assert registered.status_code == 200
        register_limited = client.post(
            "/api/auth/register",
            json={
                "name": "Rate Limit Again",
                "email": f"rate-limit-again-{suffix}@example.test",
                "password": "secret123",
            },
        )
        assert register_limited.status_code == 429
        assert register_limited.json()["error"]["type"] == "rate_limited"
        assert int(register_limited.headers["Retry-After"]) > 0

        logged_in = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        assert logged_in.status_code == 200
        login_limited = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        assert login_limited.status_code == 429
        assert login_limited.json()["error"]["type"] == "rate_limited"

        first_demo = client.post("/api/auth/demo")
        assert first_demo.status_code == 200
        demo_limited = client.post("/api/auth/demo")
        assert demo_limited.status_code == 429
        assert demo_limited.json()["error"]["type"] == "rate_limited"

        goal = client.post(
            "/api/goals",
            json={
                "name": "PostgreSQL LLM quota",
                "subject": "Databases",
                "level": "基础",
                "deadline": "2026-12-31",
                "daily_minutes": 30,
                "notes": "Verify that the LLM API quota is stored atomically.",
            },
        )
        assert goal.status_code == 200
        material = client.post(
            "/api/materials",
            json={
                "goalId": goal.json()["data"]["id"],
                "title": "Transaction notes",
                "type": "text",
                "content": "A PostgreSQL transaction commits related writes atomically.",
                "url": "",
            },
        )
        assert material.status_code == 200
        material_id = material.json()["data"]["id"]
        assert client.post(f"/api/materials/{material_id}/chunks").status_code == 200

        class JsonResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "answer": "Transactions group related writes.",
                                            "basis": "The provided material states this.",
                                            "suggestion": "Review transaction boundaries.",
                                            "isFromMaterial": True,
                                            "confidence": "high",
                                            "nextAction": "answer_only",
                                            "requiresConfirmation": False,
                                            "insufficiencyReason": "",
                                            "reviewDrafts": [],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        monkeypatch.setenv("REGISTERED_DAILY_LLM_LIMIT", "1")
        monkeypatch.setenv("DEMO_DAILY_LLM_LIMIT", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("LLM_API_KEY", "postgres-integration-key")
        monkeypatch.setenv("LLM_MODEL", "postgres-integration-model")
        monkeypatch.setenv("LLM_BASE_URL", "https://provider.test/v1")
        monkeypatch.setattr(llm_provider.urllib.request, "urlopen", lambda *args, **kwargs: JsonResponse())
        first_answer = client.post(
            "/api/agent/ask",
            json={
                "question": "PostgreSQL transaction commits related writes atomically",
                "materialId": material_id,
            },
        )
        assert first_answer.status_code == 200
        assert first_answer.json()["data"]["mode"] == "openai-compatible"
        assert first_answer.json()["data"]["references"]
        quota_limited_answer = client.post(
            "/api/agent/ask",
            json={
                "question": "PostgreSQL transaction commits related writes atomically",
                "materialId": material_id,
            },
        )
        assert quota_limited_answer.status_code == 429
        assert quota_limited_answer.json()["error"]["type"] == "rate_limited"

    reservations = [
        ("postgres_concurrent_llm", f"owner-{suffix}", store.today_iso(), 1, 1),
    ]

    def reserve_once() -> bool:
        return store.reserve_model_usage_limits(reservations, store.now_iso())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve_once(), range(2)))

    assert sorted(results) == [False, True]


def test_postgres_material_batch_writes_work_through_sqlalchemy_compatibility_layer():
    with TestClient(app) as client:
        email = f"material-{uuid4().hex}@example.test"
        registered = client.post(
            "/api/auth/register",
            json={"name": "Material", "email": email, "password": "secret123"},
        )
        assert registered.status_code == 200

        goal_response = client.post(
            "/api/goals",
            json={
                "name": "PostgreSQL material flow",
                "subject": "Databases",
                "level": "基础",
                "deadline": "2026-12-31",
                "daily_minutes": 30,
                "notes": "Exercise batch storage on PostgreSQL.",
            },
        )
        assert goal_response.status_code == 200
        goal_id = goal_response.json()["data"]["id"]

        material_response = client.post(
            "/api/materials",
            json={
                "goalId": goal_id,
                "title": "PostgreSQL storage notes",
                "type": "text",
                "content": "PostgreSQL uses transactions. Batch writes keep related chunks consistent.",
                "url": "",
            },
        )
        assert material_response.status_code == 200
        material_id = material_response.json()["data"]["id"]

        chunks_response = client.post(f"/api/materials/{material_id}/chunks")
        assert chunks_response.status_code == 200
        assert chunks_response.json()["data"]

        summary_response = client.post(f"/api/materials/{material_id}/summarize")
        assert summary_response.status_code == 200

        flashcards_response = client.post(f"/api/materials/{material_id}/flashcards")
        assert flashcards_response.status_code == 200
        assert flashcards_response.json()["data"]

        quiz_response = client.post(f"/api/materials/{material_id}/quiz", params={"count": 1})
        assert quiz_response.status_code == 200
        assert quiz_response.json()["data"]


def test_postgres_fsrs_schedule_and_quiz_history_protection():
    engine = database.get_engine()
    with engine.connect() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'flashcards'
                    """
                )
            )
        }
        assert {"fsrs_card", "due_at", "last_reviewed_at", "review_count", "last_rating"} <= columns
        assert connection.execute(
            text("SELECT to_regclass('public.idx_flashcards_due_at')")
        ).scalar_one() == "idx_flashcards_due_at"

    with TestClient(app) as client:
        email = f"loop-postgres-{uuid4().hex}@example.test"
        registered = client.post(
            "/api/auth/register",
            json={"name": "Postgres Loop", "email": email, "password": "secret123"},
        )
        assert registered.status_code == 200
        goal = client.post(
            "/api/goals",
            json={
                "name": "PostgreSQL review loop",
                "subject": "Databases",
                "level": "basic",
                "deadline": "2026-12-31",
                "daily_minutes": 30,
                "notes": "Exercise FSRS persistence.",
            },
        ).json()["data"]
        material = client.post(
            "/api/materials",
            json={
                "goalId": goal["id"],
                "title": "FSRS storage notes",
                "type": "text",
                "content": "A scheduled card uses one transaction for its source and projection.",
                "url": "",
            },
        ).json()["data"]
        flashcard = client.post(
            f"/api/materials/{material['id']}/flashcards/custom",
            json={"front": "What is stored?", "back": "FSRS JSON and a due projection."},
        ).json()["data"]
        assert flashcard["dueAt"] == Card.from_json(flashcard["fsrsCard"]).due.isoformat()

        review = client.post(
            f"/api/materials/{material['id']}/flashcards/{flashcard['id']}/reviews",
            json={"rating": "good"},
        )
        assert review.status_code == 200
        assert review.json()["data"]["reviewCount"] == 1
        assert review.json()["data"]["lastRating"] == "good"

        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    """
                    SELECT status, fsrs_card, due_at, last_reviewed_at, review_count, last_rating
                    FROM flashcards WHERE id = :flashcard_id
                    """
                ),
                {"flashcard_id": flashcard["id"]},
            ).mappings().one()
        assert persisted["status"] == "known"
        assert persisted["review_count"] == 1
        assert persisted["last_rating"] == "good"
        assert persisted["last_reviewed_at"]
        assert persisted["due_at"] == Card.from_json(persisted["fsrs_card"]).due.isoformat()

        question = {
            "id": store.make_id("quiz"),
            "materialId": material["id"],
            "question": "What protects the weak-point history?",
            "type": "short-answer",
            "options": [],
            "answer": "Do not replace attempted questions.",
            "explanation": "Attempts define unresolved weak points.",
            "createdAt": store.now_iso(),
            "updatedAt": store.now_iso(),
        }
        material_store.replace_quiz_questions_for_material(material["id"], [question])
        material_store.save_quiz_attempt(
            {
                "id": store.make_id("attempt"),
                "quizId": question["id"],
                "materialId": material["id"],
                "userAnswer": "Replace it",
                "isCorrect": False,
                "score": 20,
                "feedback": "Wrong answer.",
                "suggestion": "Keep the original questions.",
                "mode": "mock",
                "createdAt": store.now_iso(),
            }
        )
        assert material_store.has_quiz_attempts_for_material(material["id"]) is True
        with pytest.raises(material_store.QuizHistoryExistsError, match="quiz_history_exists"):
            material_store.replace_quiz_questions_for_material(material["id"], [question])
        weak_points = client.get("/api/review/weak-points", params={"goalId": goal["id"]})
        assert weak_points.status_code == 200
        assert weak_points.json()["data"][0]["resolved"] is False
