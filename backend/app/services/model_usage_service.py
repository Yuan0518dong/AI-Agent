from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_active_user_id: ContextVar[str | None] = ContextVar("active_model_usage_user_id", default=None)
_embedding_kind: ContextVar[str | None] = ContextVar("active_embedding_usage_kind", default=None)
_prepaid_embedding_chunks: ContextVar[bool] = ContextVar(
    "active_prepaid_embedding_chunks",
    default=False,
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


def consume_llm_call() -> None:
    user_id = _active_user_id.get()
    if not user_id:
        return
    from backend.app.services import rate_limit_service

    rate_limit_service.consume_llm_quota(user_id)


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
