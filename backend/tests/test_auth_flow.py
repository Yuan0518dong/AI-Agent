import hashlib

from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import (
    agent_tool_execution_service,
    auth_service,
    embedding_provider,
    llm_provider,
    material_ai_service,
    model_usage_service,
    rate_limit_service,
    store,
)
from backend.tests.auth_helpers import SESSION_COOKIE_NAME, register_session


client = TestClient(app)


class _JsonHttpResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self.payload


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    client.cookies.clear()
    store.set_db_path(tmp_path / "test_ai_agent.db")
    store.reset()
    register_session(client, email="auth-default@example.com", name="Auth Default")
    yield
    client.cookies.clear()
    store.reset()


def test_register_writes_argon2id_user_without_plain_password():
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Chen",
            "email": "Chen@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Chen"
    assert data["email"] == "chen@example.com"
    assert "password" not in data
    assert "password_hash" not in data

    stored_user = store.get_user_by_email("chen@example.com")
    assert stored_user is not None
    assert stored_user["password_hash"] != "secret123"
    assert stored_user["password_hash"].startswith("$argon2id$")
    assert stored_user["password_algorithm"] == "argon2id"
    assert stored_user["password_salt"] == ""
    assert PasswordHasher().verify(stored_user["password_hash"], "secret123")


def test_register_rejects_duplicate_email():
    payload = {
        "name": "Chen",
        "email": "chen@example.com",
        "password": "secret123",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 200

    duplicate_response = client.post("/api/auth/register", json=payload)

    assert duplicate_response.status_code == 409


def test_login_returns_public_user_with_valid_password():
    client.post(
        "/api/auth/register",
        json={
            "name": "Chen",
            "email": "chen@example.com",
            "password": "secret123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "email": "chen@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "chen@example.com"
    assert "password_hash" not in data


def test_login_rejects_wrong_password():
    client.post(
        "/api/auth/register",
        json={
            "name": "Chen",
            "email": "chen@example.com",
            "password": "secret123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "email": "chen@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401


def test_register_validation_rejects_invalid_payload():
    response = client.post(
        "/api/auth/register",
        json={
            "name": "",
            "email": "invalid-email",
            "password": "123",
        },
    )

    assert response.status_code == 422


def test_all_business_routes_require_a_cookie_session_and_return_error_contract():
    client.cookies.clear()

    responses = [
        client.get("/api/goals"),
        client.post("/api/materials", json={}),
        client.get("/api/agent/tools"),
    ]

    for response in responses:
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["type"] == "auth_required"
        assert body["error"]["message"]
        assert body["error"]["fieldErrors"] == {}
        assert body["requestId"]
        assert response.headers["X-Request-Id"] == body["requestId"]


def test_me_and_logout_revoke_the_cookie_backed_session():
    token = client.cookies.get(SESSION_COOKIE_NAME)
    assert token
    assert client.get("/api/auth/me").status_code == 200

    with store.db_connection() as conn:
        row = conn.execute(
            "SELECT token_hash, revoked_at FROM auth_sessions WHERE token_hash = ?",
            (auth_service.hash_session_token(token),),
        ).fetchone()
    assert row is not None
    assert row["token_hash"] == auth_service.hash_session_token(token)
    assert token != row["token_hash"]
    assert row["revoked_at"] is None

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["data"] == {"loggedOut": True}
    assert client.get("/api/auth/me").status_code == 401
    with store.db_connection() as conn:
        revoked = conn.execute(
            "SELECT revoked_at FROM auth_sessions WHERE token_hash = ?",
            (auth_service.hash_session_token(token),),
        ).fetchone()
    assert revoked["revoked_at"]


def test_legacy_pbkdf2_login_rehashes_to_argon2id():
    password = "legacy-secret123"
    salt = "legacy-salt"
    legacy_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        auth_service.LEGACY_PASSWORD_ITERATIONS,
    ).hex()
    now = store.now_iso()
    store.create_user(
        {
            "id": store.make_id("user"),
            "name": "Legacy User",
            "email": "legacy@example.com",
            "password_hash": legacy_hash,
            "password_salt": salt,
            "account_type": "registered",
            "password_algorithm": auth_service.LEGACY_PASSWORD_ALGORITHM,
            "expires_at": None,
            "created_at": now,
            "updated_at": now,
        }
    )
    client.cookies.clear()

    response = client.post(
        "/api/auth/login",
        json={"email": "legacy@example.com", "password": password},
    )

    assert response.status_code == 200
    upgraded = store.get_user_by_email("legacy@example.com")
    assert upgraded["password_algorithm"] == auth_service.PASSWORD_ALGORITHM
    assert upgraded["password_salt"] == ""
    assert upgraded["password_hash"].startswith("$argon2id$")
    assert PasswordHasher().verify(upgraded["password_hash"], password)


def test_session_cookie_uses_http_only_samesite_lax_and_secure_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client.cookies.clear()

    response = client.post(
        "/api/auth/register",
        headers={"Origin": "http://127.0.0.1:8001"},
        json={"name": "Cookie User", "email": "cookie@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    cookie_header = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE_NAME}=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Secure" in cookie_header


def test_demo_creates_isolated_seeded_data_without_model_or_plaintext_session(monkeypatch):
    def fail_if_model_is_requested():
        raise AssertionError("Demo seeding must not call a model provider")

    monkeypatch.setattr(llm_provider, "get_llm_provider", fail_if_model_is_requested)
    client.cookies.clear()
    first_response = client.post("/api/auth/demo")

    assert first_response.status_code == 200
    first_user = first_response.json()["data"]
    assert first_user["accountType"] == "demo"
    first_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert first_token
    first_internal = store.get_user_by_email(first_user["email"])
    assert first_internal is not None
    assert first_internal["expires_at"]

    first_goals = client.get("/api/goals").json()["data"]
    assert len(first_goals) == 1
    first_goal = first_goals[0]
    assert len(client.get(f"/api/goals/{first_goal['id']}/tasks").json()["data"]) == 3
    first_materials = client.get("/api/materials").json()["data"]
    assert len(first_materials) == 1
    material_id = first_materials[0]["id"]
    assert client.get(f"/api/materials/{material_id}/summary").json()["data"] is not None
    assert len(client.get(f"/api/materials/{material_id}/flashcards").json()["data"]) >= 1
    assert len(client.get(f"/api/materials/{material_id}/quiz").json()["data"]) >= 1
    runs = client.get("/api/agent/runs").json()["data"]
    assert len(runs) == 1
    assert runs[0]["status"] == "waiting_confirmation"

    with store.db_connection() as conn:
        session = conn.execute(
            "SELECT token_hash FROM auth_sessions WHERE user_id = ?",
            (first_internal["id"],),
        ).fetchone()
    assert session["token_hash"] == auth_service.hash_session_token(first_token)
    assert first_token != session["token_hash"]

    with TestClient(app) as second_client:
        second_response = second_client.post("/api/auth/demo")
        assert second_response.status_code == 200
        second_user = second_response.json()["data"]
        second_goals = second_client.get("/api/goals").json()["data"]

        assert second_user["email"] != first_user["email"]
        assert [goal["id"] for goal in second_goals] != [first_goal["id"]]
        forged = client.get("/api/goals", headers={"X-User-Id": store.get_user_by_email(second_user["email"])["id"]})
        assert [goal["id"] for goal in forged.json()["data"]] == [first_goal["id"]]


def test_rate_limits_return_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("REGISTER_IP_HOURLY_LIMIT", "1")
    client.cookies.clear()
    store.reset()

    first = client.post(
        "/api/auth/register",
        json={"name": "First", "email": "first-rate@example.com", "password": "secret123"},
    )
    second = client.post(
        "/api/auth/register",
        json={"name": "Second", "email": "second-rate@example.com", "password": "secret123"},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "rate_limited"
    assert int(second.headers["Retry-After"]) > 0


def test_model_usage_rejects_an_oversized_first_reservation():
    now = store.now_iso()
    assert store.increment_model_usage("test", "owner", "2026-07-16", 101, 100, now) is None
    assert store.reserve_model_usage_limits(
        [("test-batch", "owner", "2026-07-16", 101, 100)],
        now,
    ) is False


def test_demo_embedding_quotas_reject_first_oversized_reservation_and_limit_queries(monkeypatch):
    client.cookies.clear()
    demo_response = client.post("/api/auth/demo")
    assert demo_response.status_code == 200
    demo_user = store.get_user_by_email(demo_response.json()["data"]["email"])
    assert demo_user is not None

    with pytest.raises(HTTPException) as oversized:
        rate_limit_service.consume_embedding_chunk_quota(demo_user["id"], 101)
    assert oversized.value.status_code == 429

    monkeypatch.setenv("DEMO_DAILY_EMBEDDING_QUERY_LIMIT", "1")
    rate_limit_service.consume_embedding_query_quota(demo_user["id"])
    with pytest.raises(HTTPException) as query_limit:
        rate_limit_service.consume_embedding_query_quota(demo_user["id"])
    assert query_limit.value.status_code == 429


def test_demo_llm_quota_defaults_to_ten_calls_per_day():
    client.cookies.clear()
    demo_response = client.post("/api/auth/demo")
    assert demo_response.status_code == 200
    demo_user = store.get_user_by_email(demo_response.json()["data"]["email"])
    assert demo_user is not None

    for _ in range(10):
        rate_limit_service.consume_llm_quota(demo_user["id"])
    with pytest.raises(HTTPException) as exhausted:
        rate_limit_service.consume_llm_quota(demo_user["id"])
    assert exhausted.value.status_code == 429


def test_missing_agent_run_does_not_charge_and_real_provider_calls_are_metered(monkeypatch):
    monkeypatch.setenv("REGISTERED_DAILY_LLM_LIMIT", "1")

    missing = client.post("/api/agent/runs/missing-run/execute", json={})
    assert missing.status_code == 404

    monkeypatch.setattr(
        llm_provider.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _JsonHttpResponse(b'{"choices":[{"message":{"content":"{}"}}]}'),
    )
    user = store.get_user_by_email("auth-default@example.com")
    assert user is not None
    provider = llm_provider.OpenAICompatibleLLMProvider("key", "https://provider.test/v1", "test-model")

    with model_usage_service.user_usage_scope(user["id"]):
        assert provider._post_chat_completion({"model": "test-model"})["choices"]
        with pytest.raises(HTTPException) as exhausted:
            provider._post_chat_completion({"model": "test-model"})
    assert exhausted.value.status_code == 429


def test_agent_tool_thread_preserves_provider_usage_scope(monkeypatch):
    monkeypatch.setenv("REGISTERED_DAILY_LLM_LIMIT", "1")
    monkeypatch.setattr(
        llm_provider.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _JsonHttpResponse(b'{"choices":[{"message":{"content":"{}"}}]}'),
    )
    user = store.get_user_by_email("auth-default@example.com")
    assert user is not None
    provider = llm_provider.OpenAICompatibleLLMProvider("key", "https://provider.test/v1", "test-model")

    with model_usage_service.user_usage_scope(user["id"]):
        result = agent_tool_execution_service._call_with_deadline(
            lambda: {"result": provider._post_chat_completion({"model": "test-model"})},
            1,
        )
    assert result["result"]["choices"]
    with model_usage_service.user_usage_scope(user["id"]):
        with pytest.raises(HTTPException) as exhausted:
            provider._post_chat_completion({"model": "test-model"})
    assert exhausted.value.status_code == 429


def test_real_embedding_query_calls_are_metered(monkeypatch):
    monkeypatch.setenv("DEMO_DAILY_EMBEDDING_QUERY_LIMIT", "1")
    vector = [0.25] * embedding_provider.EMBEDDING_DIMENSIONS
    payload = ('{"data":[{"embedding":[' + ",".join("0.25" for _ in vector) + "]}]} ").encode()
    monkeypatch.setattr(
        embedding_provider.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _JsonHttpResponse(payload),
    )
    client.cookies.clear()
    demo_response = client.post("/api/auth/demo")
    assert demo_response.status_code == 200
    demo_user = store.get_user_by_email(demo_response.json()["data"]["email"])
    assert demo_user is not None
    provider = embedding_provider.OpenAICompatibleEmbeddingProvider(
        "key",
        "https://provider.test/v1",
        "embedding-3",
    )

    with model_usage_service.user_usage_scope(demo_user["id"]):
        with model_usage_service.embedding_usage_scope("query"):
            assert provider.embed("retrieval query") == vector
        with model_usage_service.embedding_usage_scope("query"):
            with pytest.raises(HTTPException) as exhausted:
                provider.embed("second query")
    assert exhausted.value.status_code == 429


def test_model_quota_rejection_is_not_swallowed_by_summary_fallback(monkeypatch):
    monkeypatch.setenv("REGISTERED_DAILY_LLM_LIMIT", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.test/v1")
    monkeypatch.setattr(
        llm_provider.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _JsonHttpResponse(b'{"choices":[{"message":{"content":"{}"}}]}'),
    )
    user = store.get_user_by_email("auth-default@example.com")
    assert user is not None
    material = {"title": "Quota summary", "type": "text", "content": "Provider quota must fail visibly."}

    with model_usage_service.user_usage_scope(user["id"]):
        material_ai_service.summarize_material(material)
        with pytest.raises(HTTPException) as exhausted:
            material_ai_service.summarize_material(material)
    assert exhausted.value.status_code == 429


def test_api_errors_always_use_the_request_id_envelope(monkeypatch):
    unknown = client.get("/api/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["type"] == "not_found"
    assert unknown.json()["requestId"] == unknown.headers["X-Request-Id"]

    def fail_goal_lookup(*args, **kwargs):
        raise RuntimeError("database connection unavailable")

    monkeypatch.setattr(store, "list_goals", fail_goal_lookup)
    unexpected = client.get("/api/goals")
    assert unexpected.status_code == 500
    assert unexpected.json()["error"]["type"] == "internal_error"
    assert unexpected.json()["requestId"] == unexpected.headers["X-Request-Id"]


def test_production_write_requests_require_an_allowed_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client.cookies.clear()

    blocked = client.post("/api/auth/demo")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["type"] == "origin_required"

    allowed = client.post("/api/auth/demo", headers={"Origin": "http://127.0.0.1:8001"})
    assert allowed.status_code == 200


def test_account_export_uses_server_data_and_account_deletion_revokes_the_session():
    goal = client.post(
        "/api/goals",
        json={
            "name": "Export goal",
            "subject": "Data",
            "level": "basic",
            "deadline": "2026-08-01",
            "daily_minutes": 30,
            "notes": "account export coverage",
        },
    ).json()["data"]
    material = client.post(
        "/api/materials",
        json={
            "goalId": goal["id"],
            "title": "Export material",
            "type": "text",
            "content": "Only server-side data belongs in this export.",
        },
    ).json()["data"]

    export_response = client.get("/api/auth/export")
    assert export_response.status_code == 200
    exported = export_response.json()["data"]
    assert exported["account"]["email"] == "auth-default@example.com"
    assert [item["id"] for item in exported["goals"]] == [goal["id"]]
    assert [item["id"] for item in exported["materials"]] == [material["id"]]
    assert "password_hash" not in export_response.text
    assert "token_hash" not in export_response.text
    user = store.get_user_by_email("auth-default@example.com")
    assert user is not None
    owner_hash = rate_limit_service._hash_identifier(user["id"])
    assert store.increment_model_usage("llm_user", owner_hash, "2026-07-17", 1, 30, store.now_iso()) == 1

    rejected = client.request("DELETE", "/api/auth/account", json={"confirmation": "remove"})
    assert rejected.status_code == 422
    assert client.get("/api/auth/me").status_code == 200

    deleted = client.request("DELETE", "/api/auth/account", json={"confirmation": "DELETE"})
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted": True}
    assert client.get("/api/auth/me").status_code == 401
    assert store.get_user_by_email("auth-default@example.com") is None
    with store.db_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS total FROM goals").fetchone()["total"] == 0
        assert conn.execute("SELECT COUNT(*) AS total FROM materials").fetchone()["total"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS total FROM model_usage_counters WHERE owner_hash = ?",
            (owner_hash,),
        ).fetchone()["total"] == 0


def test_demo_confirmation_can_advance_its_persisted_waiting_step():
    client.cookies.clear()
    demo_response = client.post("/api/auth/demo")
    assert demo_response.status_code == 200
    run = client.get("/api/agent/runs").json()["data"][0]
    detail = client.get(f"/api/agent/runs/{run['id']}").json()["data"]
    waiting_step = detail["steps"][0]
    assert waiting_step["status"] == "waiting_confirmation"
    assert waiting_step["actionSnapshot"]["toolName"] == "create_task_draft"

    assert client.patch(
        f"/api/agent/action-logs/{waiting_step['actionLogId']}",
        json={"status": "accepted"},
    ).status_code == 200
    advanced = client.post(f"/api/agent/runs/{run['id']}/advance")

    assert advanced.status_code == 200
    advanced_run = advanced.json()["data"]
    assert advanced_run["status"] == "decided"
    assert advanced_run["steps"][0]["status"] == "completed"
    assert advanced_run["steps"][0]["toolOutput"]["data"]["createdCount"] == 1


def test_demo_rejection_and_cancellation_keep_the_run_in_a_safe_state():
    client.cookies.clear()
    assert client.post("/api/auth/demo").status_code == 200
    run = client.get("/api/agent/runs").json()["data"][0]
    detail = client.get(f"/api/agent/runs/{run['id']}").json()["data"]
    waiting_step = detail["steps"][0]

    assert client.patch(
        f"/api/agent/action-logs/{waiting_step['actionLogId']}",
        json={"status": "rejected"},
    ).status_code == 200
    rejected = client.post(f"/api/agent/runs/{run['id']}/advance")
    assert rejected.status_code == 200
    rejected_run = rejected.json()["data"]
    assert rejected_run["status"] == "decided"
    assert rejected_run["steps"][0]["status"] == "rejected"

    cancelled = client.post(f"/api/agent/runs/{run['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"


def test_production_rate_limit_security_requires_a_secret_and_trusted_proxy_cidrs(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RATE_LIMIT_HASH_SALT", raising=False)
    with pytest.raises(RuntimeError, match="RATE_LIMIT_HASH_SALT"):
        rate_limit_service.require_runtime_security_configuration()

    monkeypatch.setenv("RATE_LIMIT_HASH_SALT", "a" * 32)
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS"):
        rate_limit_service.require_runtime_security_configuration()
