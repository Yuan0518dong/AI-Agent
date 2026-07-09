from typing import Any

from backend.app.services import agent_tool_registry_service


def decision_from_model_data(
    data: dict[str, Any],
    fallback_decision: dict,
    mode: str,
) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Decision Guard rejected model output: payload must be an object.")

    next_action = _known_action(data.get("nextAction"), "nextAction")
    proposed_actions = _normalize_actions(data.get("proposedActions"), next_action, data, fallback_decision)
    guard_status = "accepted"
    interventions: list[dict] = []

    for action in proposed_actions:
        intervention = _confirmation_intervention(action)
        if intervention:
            interventions.append(intervention)
            guard_status = "sanitized"
        action.pop("_modelRequiresConfirmation", None)

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
        "decisionGuard": {
            "status": guard_status,
            "checks": ["json_object", "known_action", "tool_risk", "confirmation_required"],
            "interventions": interventions,
            "errors": [],
        },
    }
    return decision


def fallback_guard(reason: str) -> dict:
    return {
        "status": "fallback",
        "checks": ["json_object", "known_action", "tool_risk", "confirmation_required"],
        "interventions": [],
        "errors": [reason],
    }


def _normalize_actions(
    actions: Any,
    next_action: str,
    data: dict[str, Any],
    fallback_decision: dict,
) -> list[dict]:
    if not isinstance(actions, list):
        return [
            _model_action(
                next_action,
                str(data.get("reason") or fallback_decision.get("reason") or ""),
                {},
                bool(data.get("requiresConfirmation", False)),
            )
        ]

    normalized_actions = []
    for item in actions[:4]:
        if not isinstance(item, dict):
            continue
        action_type = _known_action(item.get("type") or item.get("actionType"), "proposedActions.type")
        normalized_actions.append(
            _model_action(
                action_type,
                str(item.get("description") or item.get("reason") or ""),
                item.get("payload") if isinstance(item.get("payload"), dict) else {},
                bool(item.get("requiresConfirmation", False)),
                str(item.get("label") or action_type),
            )
        )

    if normalized_actions:
        return normalized_actions

    return [
        _model_action(
            next_action,
            str(data.get("reason") or fallback_decision.get("reason") or ""),
            {},
            bool(data.get("requiresConfirmation", False)),
        )
    ]


def _known_action(raw_action: Any, field_name: str) -> str:
    action_type = str(raw_action or "")
    if not agent_tool_registry_service.is_known_action(action_type):
        raise ValueError(f"Decision Guard rejected model output: unknown {field_name} {action_type}.")
    return action_type


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
        "_modelRequiresConfirmation": requires_confirmation,
        "status": "proposed",
    }
    return agent_tool_registry_service.enrich_action(action)


def _confirmation_intervention(action: dict) -> dict | None:
    tool = agent_tool_registry_service.get_tool_for_action(action["type"])
    must_confirm = bool(tool["requiresConfirmation"] or tool["draftOnly"] or tool["riskLevel"] == "high")
    if not must_confirm or action.get("_modelRequiresConfirmation") is True:
        return None
    return {
        "type": "force_confirmation",
        "actionType": action["type"],
        "toolName": action["toolName"],
        "riskLevel": action["riskLevel"],
        "reason": "Tool risk policy requires user confirmation before execution.",
    }
