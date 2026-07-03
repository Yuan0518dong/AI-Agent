from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services import store


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    store.set_db_path(tmp_path / "test_ai_agent.db")
    store.reset()
    yield
    store.reset()


def test_register_writes_user_to_sqlite_without_plain_password():
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
    assert stored_user["password_salt"]


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
