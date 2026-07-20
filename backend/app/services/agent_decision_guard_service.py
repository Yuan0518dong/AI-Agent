from typing import Any

from backend.app.services import agent_tool_registry_service


def decision_from_model_data(
    data: dict[str, Any],
    fallback_decision: dict,
    mode: str,
    *,
    context: dict | None = None,
    allowed_action_types: set[str] | None = None,
) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Decision Guard rejected model output: payload must be an object.")

    _validate_required_decision_fields(data)
    next_action = _known_action(
        data.get("nextAction"),
        "nextAction",
        allowed_action_types,
    )
    proposed_actions = _normalize_actions(
        data.get("proposedActions"),
        next_action,
        data,
        fallback_decision,
        context,
        allowed_action_types,
    )
    if not proposed_actions or proposed_actions[0]["type"] != next_action:
        raise ValueError(
            "Decision Guard rejected model output: nextAction must match the first proposed action."
        )
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
        "reflection": "",
        "decisionGuard": {
            "status": guard_status,
            "checks": [
                "json_object",
                "required_fields",
                "known_action",
                "allowed_action",
                "payload_schema",
                "owner_scope",
                "tool_risk",
                "confirmation_required",
            ],
            "interventions": interventions,
            "errors": [],
        },
    }
    return decision


def fallback_guard(reason: str, *, repair_attempted: bool = False) -> dict:
    return {
        "status": "fallback",
        "checks": [
            "json_object",
            "required_fields",
            "known_action",
            "payload_schema",
            "tool_risk",
            "confirmation_required",
        ],
        "interventions": [],
        "errors": [reason],
        "repairAttempted": repair_attempted,
    }


def _validate_required_decision_fields(data: dict[str, Any]) -> None:
    required_fields = {
        "nextAction": str,
        "reason": str,
        "proposedActions": list,
    }
    missing_or_invalid = [
        field
        for field, expected_type in required_fields.items()
        if field not in data or not isinstance(data[field], expected_type)
    ]
    if missing_or_invalid:
        raise ValueError(
            "Decision Guard rejected model output: missing or invalid required fields: "
            + ", ".join(missing_or_invalid)
            + "."
        )
    optional_fields = {
        "stateSummary": str,
        "problems": list,
        "requiresConfirmation": bool,
        "reflection": str,
    }
    invalid_optional = [
        field
        for field, expected_type in optional_fields.items()
        if field in data and not isinstance(data[field], expected_type)
    ]
    if invalid_optional:
        raise ValueError(
            "Decision Guard rejected model output: invalid optional fields: "
            + ", ".join(invalid_optional)
            + "."
        )


def _normalize_actions(
    actions: Any,
    next_action: str,
    data: dict[str, Any],
    fallback_decision: dict,
    context: dict | None,
    allowed_action_types: set[str] | None,
) -> list[dict]:
    normalized_actions = []
    for item in actions[:4]:
        if not isinstance(item, dict):
            raise ValueError("Decision Guard rejected model output: proposedActions items must be objects.")
        action_type = _known_action(
            item.get("type") or item.get("actionType"),
            "proposedActions.type",
            allowed_action_types,
        )
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        _validate_payload_scope(action_type, payload, context)
        normalized_actions.append(
            _model_action(
                action_type,
                str(item.get("description") or item.get("reason") or data.get("reason") or ""),
                payload,
                bool(item.get("requiresConfirmation", False)),
                str(item.get("label") or action_type),
            )
        )
    return normalized_actions


def _known_action(
    raw_action: Any,
    field_name: str,
    allowed_action_types: set[str] | None = None,
) -> str:
    action_type = str(raw_action or "")
    if not agent_tool_registry_service.is_known_action(action_type):
        raise ValueError(f"Decision Guard rejected model output: unknown {field_name} {action_type}.")
    if allowed_action_types is not None and action_type not in allowed_action_types:
        raise ValueError(
            f"Decision Guard rejected model output: {field_name} {action_type} is not allowed in the current state."
        )
    return action_type


def _model_action(
    action_type: str,
    description: str,
    payload: dict,
    requires_confirmation: bool,
    label: str | None = None,
) -> dict:
    agent_tool_registry_service.validate_tool_input(action_type, payload)
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


def _validate_payload_scope(action_type: str, payload: dict, context: dict | None) -> None:
    if context is None:
        return
    permitted = {
        "goalIds": {item["id"] for item in context.get("goals", []) if item.get("id")},
        "materialIds": {item["id"] for item in context.get("materials", []) if item.get("id")},
        "materialId": {item["id"] for item in context.get("materials", []) if item.get("id")},
        "draftIds": {
            item["id"]
            for item in (context.get("drafts", {}).get("proposed") or [])
            if item.get("id")
        },
        "taskIds": {
            item["id"]
            for group in context.get("tasks", [])
            for collection in ("today", "overdueItems", "nextOpen")
            for item in group.get(collection, [])
            if item.get("id")
        },
    }
    for field, allowed_ids in permitted.items():
        if field not in payload:
            continue
        values = payload[field] if isinstance(payload[field], list) else [payload[field]]
        if any(value not in allowed_ids for value in values):
            raise ValueError(
                f"Decision Guard rejected model output: {action_type} payload {field} is outside current scope."
            )


def _confirmation_intervention(action: dict) -> dict | None:
    tool = agent_tool_registry_service.get_tool_for_action(action["type"])
    must_confirm = bool(tool["requiresConfirmation"] or tool["riskLevel"] == "high")
    if not must_confirm or action.get("_modelRequiresConfirmation") is True:
        return None
    return {
        "type": "force_confirmation",
        "actionType": action["type"],
        "toolName": action["toolName"],
        "riskLevel": action["riskLevel"],
        "reason": "Tool risk policy requires user confirmation before execution.",
    }
