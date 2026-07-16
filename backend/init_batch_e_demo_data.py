"""Create idempotent local data for the Batch E browser demonstration.

Run this after the backend is available on http://127.0.0.1:8001:
    python backend/init_batch_e_demo_data.py

The script only uses existing public endpoints and never reads or prints provider keys.
"""

from __future__ import annotations

import json
import sys
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "http://127.0.0.1:8001/api"
DEMO_EMAIL = "batch-e-demo@example.test"
DEMO_PASSWORD = "BatchEDemo123!"
CONFIRMATION_GOAL = "Batch E demo - confirmation and resume"
REJECTION_GOAL = "Batch E demo - rejection"
RETRIEVAL_GOAL = "Batch E demo - grounded retrieval"
RETRIEVAL_MATERIAL = "Learning agent runtime notes"
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))


def request(method: str, path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Origin": "http://127.0.0.1:8001"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=payload, headers=headers, method=method)
    with OPENER.open(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(result.get("message") or f"Unexpected response from {path}")
    return result["data"]


def establish_demo_session() -> None:
    try:
        request(
            "POST",
            "/auth/register",
            {"name": "Batch E Demo", "email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise
        request("POST", "/auth/login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def ensure_goal(name: str, notes: str) -> dict:
    existing = request("GET", "/goals")
    matched = next((goal for goal in existing if goal["name"] == name), None)
    if matched:
        return matched
    return request(
        "POST",
        "/goals",
        {
            "name": name,
            "subject": "Learning Agent",
            "level": "intermediate",
            "deadline": "2026-12-31",
            "daily_minutes": 30,
            "notes": notes,
        },
    )


def ensure_retrieval_material(goal_id: str) -> dict:
    query = urllib.parse.urlencode({"goalId": goal_id})
    materials = request("GET", f"/materials?{query}")
    material = next((item for item in materials if item["title"] == RETRIEVAL_MATERIAL), None)
    if not material:
        material = request(
            "POST",
            "/materials",
            {
                "goalId": goal_id,
                "title": RETRIEVAL_MATERIAL,
                "type": "text",
                "content": (
                    "A controllable learning agent runs a bounded loop: observe context, decide with a "
                    "registered tool schema, validate with a guard, execute, persist the observation, and "
                    "decide again. Formal task or flashcard writes require confirmation and idempotency."
                ),
            },
        )
    request("POST", f"/materials/{material['id']}/chunks")
    return material


def main() -> int:
    try:
        establish_demo_session()
        confirmation_goal = ensure_goal(
            CONFIRMATION_GOAL,
            "Use this empty goal to show a task draft waiting for confirmation and resume.",
        )
        rejection_goal = ensure_goal(
            REJECTION_GOAL,
            "Use this separate empty goal to show that rejected formal writes do not reach formal data.",
        )
        retrieval_goal = ensure_goal(
            RETRIEVAL_GOAL,
            "Use this goal to show a processed material and a grounded retrieval run.",
        )
        material = ensure_retrieval_material(retrieval_goal["id"])
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as error:
        print(f"Batch E demo initialization failed: {error}", file=sys.stderr)
        print("Start the backend first: python -m uvicorn backend.app.main:app --reload --port 8001", file=sys.stderr)
        return 1

    print("Batch E demo data is ready.")
    print(f"Local demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Confirmation goal: {confirmation_goal['id']}")
    print(f"Rejection goal: {rejection_goal['id']}")
    print(f"Retrieval goal: {retrieval_goal['id']}")
    print(f"Processed material: {material['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
