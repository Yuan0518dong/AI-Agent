from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator


_active_user_id: ContextVar[str | None] = ContextVar("active_model_usage_user_id", default=None)
_embedding_kind: ContextVar[str | None] = ContextVar("active_embedding_usage_kind", default=None)
_prepaid_embedding_chunks: ContextVar[bool] = ContextVar(
    "active_prepaid_embedding_chunks",
    default=False,
)
_llm_request_observer: ContextVar[Callable[[str, dict[str, int]], None] | None] = ContextVar(
    "active_llm_request_observer",
    default=None,
)
_llm_format_repair_enabled: ContextVar[bool] = ContextVar(
    "active_llm_format_repair_enabled",
    default=True,
)
_llm_completion_limit: ContextVar[int | None] = ContextVar(
    "active_llm_completion_limit",
    default=None,
)


@contextmanager
def user_usage_scope(user_id: str | None) -> Iterator[None]:
    token = _active_user_id.set(user_id)
    try:
        yield
    finally:
        _active_user_id.reset(token)


@contextmanager
def embedding_usage_scope(kind: str, *, prepaid_chunks: bool = False) -> Iterator[None]:
    if kind not in {"chunk", "query"}:
        raise ValueError("Embedding usage kind must be 'chunk' or 'query'.")
    kind_token = _embedding_kind.set(kind)
    prepaid_token = _prepaid_embedding_chunks.set(prepaid_chunks)
    try:
        yield
    finally:
        _prepaid_embedding_chunks.reset(prepaid_token)
        _embedding_kind.reset(kind_token)


@contextmanager
def llm_request_observer(observer: Callable[[str, dict[str, int]], None]) -> Iterator[None]:
    """Observe a bounded evaluation's real provider requests and token usage.

    Product requests do not install an observer. The Batch 4 runner uses this
    scope to stop before a configured request ceiling and to collect only the
    aggregate usage returned by a provider, never prompts or responses.
    """

    token = _llm_request_observer.set(observer)
    try:
        yield
    finally:
        _llm_request_observer.reset(token)


@contextmanager
def llm_format_repair_scope(enabled: bool) -> Iterator[None]:
    """Temporarily control whether invalid model JSON gets a repair request."""

    token = _llm_format_repair_enabled.set(enabled)
    try:
        yield
    finally:
        _llm_format_repair_enabled.reset(token)


def llm_format_repair_is_enabled() -> bool:
    return _llm_format_repair_enabled.get()


@contextmanager
def llm_completion_limit(max_tokens: int) -> Iterator[None]:
    """Apply a temporary, positive completion-token cap to compatible calls."""

    if max_tokens <= 0:
        raise ValueError("LLM completion limit must be positive.")
    token = _llm_completion_limit.set(max_tokens)
    try:
        yield
    finally:
        _llm_completion_limit.reset(token)


def current_llm_completion_limit() -> int | None:
    return _llm_completion_limit.get()


def consume_llm_call(
    *,
    request_utf8_bytes: int | None = None,
    max_completion_tokens: int | None = None,
) -> None:
    observer = _llm_request_observer.get()
    if observer:
        request_details = {}
        if request_utf8_bytes is not None:
            request_details["requestUtf8Bytes"] = max(request_utf8_bytes, 0)
        if max_completion_tokens is not None:
            request_details["maxCompletionTokens"] = max(max_completion_tokens, 0)
        observer("request", request_details)
    user_id = _active_user_id.get()
    if not user_id:
        return
    from backend.app.services import rate_limit_service

    rate_limit_service.consume_llm_quota(user_id)


def record_llm_response_usage(response: dict[str, Any]) -> None:
    """Forward OpenAI-compatible aggregate usage fields to an active observer."""

    observer = _llm_request_observer.get()
    if not observer:
        return
    usage = response.get("usage") if isinstance(response, dict) else None
    if (
        not isinstance(usage, dict)
        or "prompt_tokens" not in usage
        or "completion_tokens" not in usage
    ):
        observer("response", {})
        return
    observer(
        "response",
        {
            "promptTokens": _nonnegative_int(usage.get("prompt_tokens")),
            "completionTokens": _nonnegative_int(usage.get("completion_tokens")),
        },
    )


def _nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def consume_embedding_call() -> None:
    user_id = _active_user_id.get()
    kind = _embedding_kind.get()
    if not user_id or not kind:
        return
    if kind == "chunk" and _prepaid_embedding_chunks.get():
        return

    from backend.app.services import rate_limit_service

    if kind == "chunk":
        rate_limit_service.consume_embedding_chunk_quota(user_id, 1)
    else:
        rate_limit_service.consume_embedding_query_quota(user_id)
