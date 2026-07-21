import json
import time
import urllib.error
from typing import Any

from backend.app.services import (
    agent_decision_guard_service,
    agent_tool_registry_service,
    llm_provider,
    model_usage_service,
)


VALID_DECISION_MODES = {"rule-based", "llm-json", "hybrid"}
PROMPT_VERSION = "agent-reliability-a3-compact-v1"
MAX_CONTEXT_CHARS = 12_000


def decide_with_llm_json(
    context: dict,
    fallback_decision: dict,
    requested_mode: str,
    *,
    allowed_action_types: set[str] | None = None,
) -> dict:
    mode = _normalize_mode(requested_mode)
    started_at = time.monotonic()
    provider = llm_provider.get_llm_provider()
    prompt_context, context_window = _prepare_prompt_context(context)
    repair_attempted = False
    if provider.mode == "mock" or not hasattr(provider, "_post_chat_completion"):
        return _fallback_decision(
            fallback_decision,
            mode,
            "LLM decision provider is unavailable.",
            provider,
            started_at,
            context_window,
            allowed_action_types=allowed_action_types,
        )

    try:
        payload = _build_decision_payload(
            prompt_context,
            fallback_decision,
            provider,
            allowed_action_types=allowed_action_types,
        )
        content = _post_decision_completion(payload, provider)
        try:
            decision = _decision_from_content(
                content,
                fallback_decision,
                mode,
                context,
                allowed_action_types,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if not model_usage_service.llm_format_repair_is_enabled():
                raise
            repair_attempted = True
            repaired_content = _request_format_repair(content, str(exc), provider)
            decision = _decision_from_content(
                repaired_content,
                fallback_decision,
                mode,
                context,
                allowed_action_types,
            )
        return _attach_provider_metadata(
            decision,
            provider,
            started_at,
            context_window,
            repair_attempted,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        TimeoutError,
        urllib.error.URLError,
        OSError,
    ) as exc:
        return _fallback_decision(
            fallback_decision,
            mode,
            _fallback_reason(exc),
            provider,
            started_at,
            context_window,
            repair_attempted,
            allowed_action_types,
            guard_error_category=getattr(exc, "category", None),
        )


def _post_decision_completion(payload: dict[str, Any], provider) -> str:
    result = provider._post_chat_completion(payload)
    return result["choices"][0]["message"]["content"]


def _build_decision_payload(
    context: dict,
    fallback_decision: dict,
    provider=None,
    *,
    allowed_action_types: set[str] | None = None,
) -> dict:
    provider = provider or llm_provider.get_llm_provider()
    payload = {
        "model": getattr(provider, "model", ""),
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a controllable learning Agent decision layer. "
                    "Return JSON only. Do not execute writes. "
                    "Return only nextAction, reason, and proposedActions. "
                    "Each proposed action only needs type and payload; label and description are optional. "
                    "nextAction and every proposedActions.type must exactly match a type from "
                    "availableActions. Use toolName only for explanation, never as the action type. "
                    "Each payload must use only the matching inputSchema. Do not repeat context summaries. "
                    "Do not invent IDs, SQL, tools, or fields. High-risk task actions must require "
                    "confirmation."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "promptVersion": PROMPT_VERSION,
                        "context": context,
                        "runObjective": (context.get("agentRun") or {}).get("objective", ""),
                        "previousSteps": (context.get("agentRun") or {}).get("stepHistory", []),
                        "availableActions": agent_tool_registry_service.list_model_actions(
                            allowed_action_types
                        ),
                        "fallbackDecision": {
                            "stateSummary": fallback_decision.get("stateSummary", ""),
                            "problems": fallback_decision.get("problems", []),
                            "nextAction": fallback_decision.get("nextAction", ""),
                            "proposedActions": fallback_decision.get("proposedActions", []),
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    completion_limit = model_usage_service.current_llm_completion_limit()
    if completion_limit is not None:
        payload["max_tokens"] = completion_limit
    return payload


def _request_format_repair(content: str, parse_error: str, provider) -> str:
    repair_payload = {
        "model": getattr(provider, "model", ""),
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only one valid JSON object that preserves the intended Agent decision. "
                    "Do not add tools, fields, markdown, or prose."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"invalidDecision": content[:8000], "parseError": parse_error},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    return _post_decision_completion(repair_payload, provider)


def _decision_from_content(
    content: str,
    fallback_decision: dict,
    mode: str,
    context: dict,
    allowed_action_types: set[str] | None = None,
) -> dict:
    data = _parse_model_json(content)
    return agent_decision_guard_service.decision_from_model_data(
        data,
        fallback_decision,
        mode,
        context=context,
        allowed_action_types=allowed_action_types,
    )


def _parse_model_json(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`").removeprefix("json").strip()
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(normalized[start : end + 1])


def _fallback_decision(
    fallback_decision: dict,
    requested_mode: str,
    reason: str,
    provider,
    started_at: float,
    context_window: dict,
    repair_attempted: bool = False,
    allowed_action_types: set[str] | None = None,
    guard_error_category: str | None = None,
) -> dict:
    constrained_fallback = _constrain_fallback_decision(
        fallback_decision,
        allowed_action_types,
    )
    decision = {
        **constrained_fallback,
        "mode": "rule-based",
        "requestedMode": requested_mode,
        "fallbackReason": reason,
        "decisionGuard": agent_decision_guard_service.fallback_guard(
            reason,
            repair_attempted=repair_attempted,
            error_category=guard_error_category,
        ),
        "reflection": "",
    }
    return _attach_provider_metadata(
        decision,
        provider,
        started_at,
        context_window,
        repair_attempted,
    )


def _constrain_fallback_decision(
    fallback_decision: dict,
    allowed_action_types: set[str] | None,
) -> dict:
    if allowed_action_types is None:
        return fallback_decision

    actions = [
        action
        for action in fallback_decision.get("proposedActions") or []
        if action.get("type") in allowed_action_types
    ]
    if actions:
        return {
            **fallback_decision,
            "nextAction": actions[0]["type"],
            "proposedActions": actions,
            "requiresConfirmation": any(action.get("requiresConfirmation") for action in actions),
        }
    return {
        **fallback_decision,
        "nextAction": "",
        "proposedActions": [],
        "requiresConfirmation": False,
        "reason": (
            f"{fallback_decision.get('reason', '')} "
            "The deterministic action policy removed fallback actions that were invalid for this Run state."
        ).strip(),
    }


def _attach_provider_metadata(
    decision: dict,
    provider,
    started_at: float,
    context_window: dict,
    repair_attempted: bool,
) -> dict:
    return {
        **decision,
        "providerMetadata": {
            "provider": getattr(provider, "mode", "unknown"),
            "model": getattr(provider, "model", ""),
            "promptVersion": PROMPT_VERSION,
            "durationMs": round((time.monotonic() - started_at) * 1000),
            "formatRepairAttempted": repair_attempted,
            "contextWindow": context_window,
        },
    }


def _prepare_prompt_context(context: dict) -> tuple[dict, dict]:
    candidate = {
        "scope": context.get("scope", {}),
        "summary": context.get("summary", {}),
        "goals": context.get("goals", []),
        "tasks": context.get("tasks", []),
        "materials": context.get("materials", []),
        "qa": context.get("qa", {}),
        "review": context.get("review", {}),
        "quiz": context.get("quiz", {}),
        "drafts": context.get("drafts", {}),
        "progress": context.get("progress", []),
        "agentRun": context.get("agentRun", {}),
    }
    original_characters = len(json.dumps(candidate, ensure_ascii=False))
    if original_characters <= MAX_CONTEXT_CHARS:
        return candidate, {
            "trimmed": False,
            "originalCharacters": original_characters,
            "promptCharacters": original_characters,
        }

    compact = {
        "scope": candidate["scope"],
        "summary": candidate["summary"],
        "goals": candidate["goals"][:5],
        "tasks": [
            {
                key: task.get(key)
                for key in ("goalId", "goalName", "total", "completed", "open", "overdue", "nextOpen")
            }
            for task in candidate["tasks"][:5]
        ],
        "materials": [
            {
                key: material.get(key)
                for key in ("id", "goalId", "title", "hasSummary", "chunkCount", "flashcardStats", "quizStats")
            }
            for material in candidate["materials"][:10]
        ],
        "qa": {"insufficiencyCount": candidate["qa"].get("insufficiencyCount", 0)},
        "review": candidate["review"],
        "quiz": {
            "questionTotal": candidate["quiz"].get("questionTotal", 0),
            "weakAttemptCount": candidate["quiz"].get("weakAttemptCount", 0),
        },
        "drafts": candidate["drafts"],
        "progress": candidate["progress"][:5],
        "agentRun": candidate["agentRun"],
    }
    prompt_characters = len(json.dumps(compact, ensure_ascii=False))
    return compact, {
        "trimmed": True,
        "originalCharacters": original_characters,
        "promptCharacters": prompt_characters,
    }


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, urllib.error.URLError, OSError)):
        return f"LLM decision provider failed ({exc.__class__.__name__})."
    if isinstance(exc, agent_decision_guard_service.DecisionGuardError):
        return f"Decision Guard rejected model output: {exc.category}."
    return str(exc).strip() or "LLM decision fell back to rule-based."


def _normalize_mode(mode: str) -> str:
    if mode not in VALID_DECISION_MODES:
        raise ValueError("Invalid decision mode")
    return mode
