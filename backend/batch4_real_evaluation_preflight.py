"""Authorization gate for the paid Batch 4 DeepSeek evaluation.

The module deliberately does not instantiate a provider or create an HTTP
client. It can be tested freely, and a real runner must call this gate before
creating requests.
"""

import os
from dataclasses import dataclass

from backend.evaluate_batch4 import build_real_model_budget


class RealEvaluationAuthorizationError(RuntimeError):
    """Raised before any paid provider call is eligible to start."""


@dataclass(frozen=True)
class RealEvaluationAuthorization:
    max_requests: int
    max_cost_usd: float


def build_preflight() -> dict:
    budget = build_real_model_budget()
    return {
        "budget": budget,
        "providerRestriction": "Use only the DeepSeek-compatible provider already configured in backend/.env.",
        "credentialPolicy": "Provider configuration is never printed, persisted in reports, or committed.",
        "executionStatus": "blocked_until_explicit_authorization",
    }


def require_explicit_authorization(environ: dict[str, str] | None = None) -> RealEvaluationAuthorization:
    environment = environ if environ is not None else os.environ
    budget = build_real_model_budget()
    required_requests = budget["totalProviderRequests"]["maximum"]
    required_cost = budget["estimatedCostWith20PercentBufferUsd"]
    approved = environment.get("BATCH4_REAL_EVAL_APPROVED", "").strip().lower()
    if approved != "yes":
        raise RealEvaluationAuthorizationError(
            "Set BATCH4_REAL_EVAL_APPROVED=yes only after the user explicitly approves the Batch 4 run."
        )
    max_requests = _positive_int(environment.get("BATCH4_REAL_EVAL_MAX_REQUESTS", ""))
    max_cost = _positive_float(environment.get("BATCH4_REAL_EVAL_MAX_COST_USD", ""))
    if max_requests is None or max_requests < required_requests:
        raise RealEvaluationAuthorizationError(
            f"Authorization must allow at least {required_requests} provider requests."
        )
    if max_cost is None or max_cost < required_cost:
        raise RealEvaluationAuthorizationError(
            f"Authorization must allow at least USD {required_cost:.6f}."
        )
    return RealEvaluationAuthorization(max_requests=max_requests, max_cost_usd=max_cost)


def _positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
