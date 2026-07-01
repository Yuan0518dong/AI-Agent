from datetime import date, datetime, timezone
from uuid import uuid4


goals: dict[str, dict] = {}
tasks: dict[str, dict] = {}
checkins: list[dict] = []


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()

