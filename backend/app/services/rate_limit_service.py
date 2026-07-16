import hashlib
import ipaddress
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from backend.app.services import store


DEFAULT_RATE_LIMIT_HASH_SALT = "local-development-rate-limit-salt"


def require_runtime_security_configuration() -> None:
    if os.getenv("APP_ENV", "development").strip().lower() != "production":
        return

    salt = os.getenv("RATE_LIMIT_HASH_SALT", "").strip()
    if len(salt) < 32 or salt == DEFAULT_RATE_LIMIT_HASH_SALT:
        raise RuntimeError(
            "RATE_LIMIT_HASH_SALT must be a non-default value of at least 32 characters in production."
        )

    if _trust_proxy_headers() and not _trusted_proxy_networks():
        raise RuntimeError(
            "TRUST_PROXY_HEADERS=true requires TRUSTED_PROXY_CIDRS in production."
        )


def consume_ip_limit(request: Request, scope: str, *, limit_env: str, default_limit: int, window_seconds: int) -> None:
    now = _now()
    window_start = _window_start(now, window_seconds)
    remaining_seconds = max(1, int((window_start + timedelta(seconds=window_seconds) - now).total_seconds()))
    count = store.increment_rate_limit(
        scope,
        _hash_identifier(_client_ip(request)),
        window_start.isoformat(),
        _int_setting(limit_env, default_limit),
        now.isoformat(),
    )
    if count is None:
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(remaining_seconds)},
        )


def consume_llm_quota(user_id: str) -> None:
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="登录会话已失效")

    now = _now()
    period_start = now.date().isoformat()
    account_limit = _int_setting(
        "DEMO_DAILY_LLM_LIMIT" if user["account_type"] == "demo" else "REGISTERED_DAILY_LLM_LIMIT",
        10 if user["account_type"] == "demo" else 30,
    )
    reserved = store.reserve_model_usage_limits(
        [
            ("llm_global", _hash_identifier("global"), period_start, 1, _int_setting("GLOBAL_DAILY_LLM_LIMIT", 300)),
            ("llm_user", _hash_identifier(user_id), period_start, 1, account_limit),
        ],
        now.isoformat(),
    )
    if not reserved:
        raise HTTPException(
            status_code=429,
            detail="今日模型调用额度已用完，请明天再试",
            headers={"Retry-After": str(_seconds_until_tomorrow(now))},
        )


def consume_embedding_chunk_quota(user_id: str, chunk_count: int) -> None:
    if chunk_count <= 0:
        return
    user = store.get_user_by_id(user_id)
    if not user or user["account_type"] != "demo":
        return

    now = _now()
    reserved = store.reserve_model_usage_limits(
        [
            (
                "embedding_chunks_demo",
                _hash_identifier(user_id),
                now.date().isoformat(),
                chunk_count,
                _int_setting("DEMO_DAILY_EMBEDDING_CHUNK_LIMIT", 100),
            )
        ],
        now.isoformat(),
    )
    if not reserved:
        raise HTTPException(
            status_code=429,
            detail="今日演示资料处理额度已用完，请明天再试",
            headers={"Retry-After": str(_seconds_until_tomorrow(now))},
        )


def consume_embedding_query_quota(user_id: str) -> None:
    user = store.get_user_by_id(user_id)
    if not user or user["account_type"] != "demo":
        return

    now = _now()
    reserved = store.reserve_model_usage_limits(
        [
            (
                "embedding_queries_demo",
                _hash_identifier(user_id),
                now.date().isoformat(),
                1,
                _int_setting("DEMO_DAILY_EMBEDDING_QUERY_LIMIT", 100),
            )
        ],
        now.isoformat(),
    )
    if not reserved:
        raise HTTPException(
            status_code=429,
            detail="今日演示检索额度已用完，请明天再试",
            headers={"Retry-After": str(_seconds_until_tomorrow(now))},
        )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and _is_trusted_proxy(request):
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _hash_identifier(value: str) -> str:
    salt = os.getenv("RATE_LIMIT_HASH_SALT", DEFAULT_RATE_LIMIT_HASH_SALT)
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def _is_trusted_proxy(request: Request) -> bool:
    if not _trust_proxy_headers() or not request.client:
        return False
    try:
        client_ip = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(client_ip in network for network in _trusted_proxy_networks())


def _trust_proxy_headers() -> bool:
    return os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes"}


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for raw_network in os.getenv("TRUSTED_PROXY_CIDRS", "").split(","):
        value = raw_network.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _window_start(now: datetime, seconds: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), timezone.utc)


def _seconds_until_tomorrow(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))
