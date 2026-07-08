import json
from typing import Any

from backend.app.services import agent_tool_registry_service, llm_provider


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
        return _decision_from_model_data(data, fallback_decision, mode)
    except (KeyError, TypeError, ValueError, TimeoutError):
        return _fallback_decision(fallback_decision, mode, "LLM decision fell back to rule-based.")


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


def _decision_from_model_data(
    data: dict[str, Any],
    fallback_decision: dict,
    mode: str,
) -> dict:
    next_action = str(data.get("nextAction") or "")
    if not agent_tool_registry_service.is_known_action(next_action):
        raise ValueError("Unknown nextAction from model.")

    proposed_actions = _normalize_model_actions(data.get("proposedActions", []))
    if not proposed_actions:
        proposed_actions = [
            _model_action(
                next_action,
                str(data.get("reason") or fallback_decision.get("reason") or ""),
                {},
                bool(data.get("requiresConfirmation", False)),
            )
        ]

    decision = {
        "generatedAt": fallback_decision["generatedAt"],
        "mode": mode,
        "requestedMode": mode,
        "fallbackReason": "",
        "scope": fallback_decision["scope"],
        "stateSummary": str(data.get("stateSummary") or fallback_decision["stateSummary"]),
        "problems": data.get("problems") if isinstance(data.get("problems"), list) else fallback_decision["problems"],
        "nextAction": next_action,
        "reason": str(data.get("reason") or fallback_decision["reason"]),
        "requiresConfirmation": any(action["requiresConfirmation"] for action in proposed_actions),
        "proposedActions": proposed_actions,
        "feedbackMemory": fallback_decision.get("feedbackMemory", {}),
        "reflection": str(data.get("reflection") or ""),
    }
    return decision


def _normalize_model_actions(actions: Any) -> list[dict]:
    if not isinstance(actions, list):
        return []

    normalized_actions = []
    for item in actions[:4]:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or item.get("actionType") or "")
        if not agent_tool_registry_service.is_known_action(action_type):
            raise ValueError("Unknown action type from model.")
        normalized_actions.append(
            _model_action(
                action_type,
                str(item.get("description") or item.get("reason") or ""),
                item.get("payload") if isinstance(item.get("payload"), dict) else {},
                bool(item.get("requiresConfirmation", False)),
                str(item.get("label") or action_type),
            )
        )
    return normalized_actions


def _model_action(
    action_type: str,
    description: str,
    payload: dict,
    requires_confirmation: bool,
    label: str | None = None,
) -> dict:
    action = {
        "type": action_type,
        "label": label or action_type,
        "description": description,
        "payload": payload,
        "requiresConfirmation": requires_confirmation,
        "status": "proposed",
    }
    return agent_tool_registry_service.enrich_action(action)


def _fallback_decision(fallback_decision: dict, requested_mode: str, reason: str) -> dict:
    return {
        **fallback_decision,
        "mode": "rule-based",
        "requestedMode": requested_mode,
        "fallbackReason": reason,
        "reflection": "",
    }


def _normalize_mode(mode: str) -> str:
    if mode not in VALID_DECISION_MODES:
        raise ValueError("Invalid decision mode")
    return mode
