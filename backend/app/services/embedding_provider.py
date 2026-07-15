import hashlib
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    mode: str

    def embed(self, text: str) -> list[float]:
        ...


class MockEmbeddingProvider:
    """Deterministic local embeddings for tests and offline development."""

    mode = "mock"
    _SEMANTIC_GROUPS = (
        {"review", "revision", "revise", "repetition", "复习", "回顾", "温习"},
        {"task", "tasks", "action", "actions", "todo", "任务", "行动"},
        {"goal", "goals", "objective", "objectives", "目标", "目的"},
        {"plan", "plans", "planning", "schedule", "roadmap", "计划", "规划"},
        {"learn", "learning", "study", "studying", "学习", "研习"},
        {"retrieve", "retrieval", "search", "find", "检索", "搜索", "查找"},
        {"chunk", "chunks", "passage", "passages", "片段", "切片", "段落"},
        {"quiz", "test", "assessment", "测验", "测试", "自测"},
    )
    _HASH_DIMENSIONS = 32

    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        tokens = set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", normalized))
        vector = [float(any(term in normalized for term in group)) for group in self._SEMANTIC_GROUPS]
        hashed = [0.0] * self._HASH_DIMENSIONS
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            hashed[int.from_bytes(digest[:2], "big") % self._HASH_DIMENSIONS] += 0.25
        vector.extend(hashed)
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class OpenAICompatibleEmbeddingProvider:
    """Synchronous OpenAI-compatible embeddings client for real retrieval runs."""

    mode = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 20,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        normalized_text = text.strip()
        if not normalized_text:
            return []
        result = self._post_embeddings({"model": self.model, "input": normalized_text})
        items = result.get("data")
        if not isinstance(items, list) or not items:
            raise ValueError("Embedding response did not include data.")
        vector = items[0].get("embedding") if isinstance(items[0], dict) else None
        if not isinstance(vector, list) or not vector:
            raise ValueError("Embedding response did not include a vector.")
        if not all(isinstance(value, (int, float)) for value in vector):
            raise ValueError("Embedding response vector must contain numbers.")
        return [float(value) for value in vector]

    def _post_embeddings(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url=f"{self.base_url}/embeddings",
            data=body,
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def get_embedding_provider() -> EmbeddingProvider:
    _load_env_file()
    provider_name = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    if provider_name in {"openai-compatible", "openai", "local"}:
        api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv(
            "LLM_API_KEY", ""
        ).strip()
        base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or os.getenv(
            "LLM_BASE_URL", ""
        ).strip()
        model = os.getenv("EMBEDDING_MODEL", "").strip()
        timeout_seconds = _read_timeout_seconds()
        if provider_name != "local" and not api_key:
            return MockEmbeddingProvider()
        if base_url and model:
            return OpenAICompatibleEmbeddingProvider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )
    return MockEmbeddingProvider()


def embed_text(text: str) -> list[float]:
    try:
        return get_embedding_provider().embed(text)
    except Exception:
        return []


def _load_env_file() -> None:
    configured_path = os.getenv("EMBEDDING_ENV_FILE", "").strip() or os.getenv(
        "LLM_ENV_FILE", ""
    ).strip()
    env_paths = [Path(configured_path)] if configured_path else [
        Path(__file__).resolve().parents[2] / ".env"
    ]
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _read_timeout_seconds() -> float:
    try:
        timeout_seconds = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "20"))
    except ValueError:
        return 20
    return timeout_seconds if timeout_seconds > 0 else 20
