import json
from typing import Any

from backend.app.services import agent_decision_guard_service, llm_provider


VALID_DECISION_MODES = {"rule-based", "llm-json", "hybrid"}


def decide_with_llm_json(
    context: dict,
    fallback_decision: dict,
    requested_mode: str,
) -> dict:
    mode = _normalize_mode(requested_mode)
    try:
        payload = _build_decision_payload(context, fallback_decision)
        content = _post_decision_completion(payload)
        data = _parse_model_json(content)
        return agent_decision_guard_service.decision_from_model_data(data, fallback_decision, mode)
    except (KeyError, TypeError, ValueError, TimeoutError) as exc:
        return _fallback_decision(fallback_decision, mode, str(exc) or "LLM decision fell back to rule-based.")


def _post_decision_completion(payload: dict[str, Any]) -> str:
    provider = llm_provider.get_llm_provider()
    if provider.mode == "mock" or not hasattr(provider, "_post_chat_completion"):
        raise ValueError("LLM decision provider is unavailable.")

    result = provider._post_chat_completion(payload)
    return result["choices"][0]["message"]["content"]


def _build_decision_payload(context: dict, fallback_decision: dict) -> dict:
    return {
        "model": getattr(llm_provider.get_llm_provider(), "model", ""),
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a controllable learning Agent decision layer. "
                    "Return JSON only. Do not execute writes. "
                    "Allowed nextAction values are: answer_only, review_material, "
                    "create_flashcards, create_quiz, reschedule_tasks, "
                    "create_followup_tasks, ask_for_more_material. "
                    "High-risk task actions must require confirmation."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "contextSummary": context.get("summary", {}),
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


def _fallback_decision(fallback_decision: dict, requested_mode: str, reason: str) -> dict:
    return {
        **fallback_decision,
        "mode": "rule-based",
        "requestedMode": requested_mode,
        "fallbackReason": reason,
        "decisionGuard": agent_decision_guard_service.fallback_guard(reason),
        "reflection": "",
    }


def _normalize_mode(mode: str) -> str:
    if mode not in VALID_DECISION_MODES:
        raise ValueError("Invalid decision mode")
    return mode
