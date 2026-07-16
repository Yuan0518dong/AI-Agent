from fastapi.testclient import TestClient

from backend.app.main import app


TEST_PASSWORD = "secret123"
SESSION_COOKIE_NAME = "ai_agent_session"


def register_session(
    client: TestClient,
    *,
    email: str,
    name: str | None = None,
    password: str = TEST_PASSWORD,
) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "name": name or email.split("@", 1)[0],
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE_NAME)
    return response.json()["data"]


def new_session_client(
    *,
    email: str,
    name: str | None = None,
    password: str = TEST_PASSWORD,
) -> tuple[TestClient, dict]:
    client = TestClient(app)
    return client, register_session(client, email=email, name=name, password=password)


def copy_session_cookie(source: TestClient, target: TestClient) -> None:
    token = source.cookies.get(SESSION_COOKIE_NAME)
    assert token
    target.cookies.set(SESSION_COOKIE_NAME, token)
