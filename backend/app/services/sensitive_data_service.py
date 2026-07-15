"""Shared redaction for persisted Agent diagnostics and user-visible errors."""

from __future__ import annotations

import re
from typing import Any


REDACTED = "[redacted]"
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|token|password|secret)", re.IGNORECASE
)
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
ASSIGNMENT_PATTERN = re.compile(
    r"\b(api[_ -]?key|authorization|token|password|secret)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
KNOWN_KEY_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{8,})\b")


def redact(value: Any, key: str = "") -> Any:
    """Return a structural copy with credential-like data removed."""
    if key and SENSITIVE_KEY_PATTERN.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(name): redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str, max_length: int | None = None) -> str:
    redacted = BEARER_PATTERN.sub("Bearer [redacted]", value or "")
    redacted = ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", redacted)
    redacted = KNOWN_KEY_PATTERN.sub(REDACTED, redacted)
    if max_length is not None:
        return redacted[:max_length]
    return redacted
