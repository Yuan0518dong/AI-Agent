TOOLS = {
    "review_material": {
        "name": "review_material",
        "label": "Review or organize material",
        "description": "Inspect materials and generate missing chunks or summaries before review.",
        "riskLevel": "low",
        "requiresConfirmation": False,
        "draftOnly": False,
        "applyTarget": "materials",
        "inputSchema": {
            "materialIds": "list[str] optional",
            "new": "int optional",
            "review": "int optional",
        },
        "outputType": "material_processing_result",
    },
    "search_materials": {
        "name": "search_materials",
        "label": "Search material evidence",
        "description": "Retrieve semantically relevant material chunks for the current objective.",
        "riskLevel": "low",
        "requiresConfirmation": False,
        "draftOnly": False,
        "applyTarget": "material_chunks",
        "inputSchema": {
            "query": "str required",
            "limit": "int optional",
            "materialIds": "list[str] optional",
        },
        "outputType": "references",
    },
    "answer_with_sources": {
        "name": "answer_with_sources",
        "label": "Answer with material sources",
        "description": "Generate and persist a grounded answer from retrieved material evidence.",
        "riskLevel": "low",
        "requiresConfirmation": False,
        "draftOnly": False,
        "applyTarget": "material_qa_records",
        "inputSchema": {
            "question": "str required",
            "materialId": "str optional",
            "limit": "int optional",
        },
        "outputType": "grounded_answer",
    },
    "create_review_draft": {
        "name": "create_review_draft",
        "label": "Create review draft",
        "description": "Create a review or flashcard draft before any formal write.",
        "riskLevel": "medium",
        "requiresConfirmation": False,
        "draftOnly": True,
        "applyTarget": "review_drafts",
        "inputSchema": {"materialIds": "list[str] optional", "weakAttemptCount": "int optional"},
        "outputType": "draft",
    },
    "create_task_draft": {
        "name": "create_task_draft",
        "label": "Create task draft",
        "description": "Create a task plan draft before updating formal tasks.",
        "riskLevel": "medium",
        "requiresConfirmation": False,
        "draftOnly": True,
        "applyTarget": "task_drafts",
        "inputSchema": {"goalIds": "list[str] optional", "taskIds": "list[str] optional"},
        "outputType": "draft",
    },
    "apply_confirmed_draft": {
        "name": "apply_confirmed_draft",
        "label": "Apply confirmed drafts",
        "description": "Write confirmed draft records to formal tasks or flashcards exactly once.",
        "riskLevel": "high",
        "requiresConfirmation": True,
        "draftOnly": False,
        "applyTarget": "formal_learning_records",
        "inputSchema": {"draftIds": "list[str] required"},
        "outputType": "applied_drafts",
    },
    "suggest_material_gap": {
        "name": "suggest_material_gap",
        "label": "Suggest material gap",
        "description": "Prefill a missing-material suggestion for user review.",
        "riskLevel": "medium",
        "requiresConfirmation": False,
        "draftOnly": True,
        "applyTarget": "materials",
        "inputSchema": {"insufficiencyCount": "int optional"},
        "outputType": "prefill",
    },
    "answer_only": {
        "name": "answer_only",
        "label": "Answer only",
        "description": "Give a learning suggestion without writing or drafting data.",
        "riskLevel": "low",
        "requiresConfirmation": False,
        "draftOnly": False,
        "applyTarget": "study",
        "inputSchema": {},
        "outputType": "message",
    },
}


ACTION_TOOL_MAP = {
    "review_material": "review_material",
    "search_materials": "search_materials",
    "answer_with_sources": "answer_with_sources",
    "create_flashcards": "create_review_draft",
    "create_quiz": "create_review_draft",
    "reschedule_tasks": "create_task_draft",
    "create_followup_tasks": "create_task_draft",
    "apply_confirmed_draft": "apply_confirmed_draft",
    "ask_for_more_material": "suggest_material_gap",
    "answer_only": "answer_only",
}


MODEL_ACTION_DESCRIPTIONS = {
    "review_material": "Process existing materials when chunks or summaries are missing.",
    "search_materials": "Retrieve scoped material evidence for the current objective.",
    "answer_with_sources": "Answer a question from scoped material evidence and persist its citations.",
    "create_flashcards": "Create a review or flashcard draft from weak learning evidence; do not write formally.",
    "create_quiz": "Create a quiz-oriented review draft; do not write formally.",
    "reschedule_tasks": "Create a task draft that reschedules existing overdue tasks; do not write formally.",
    "create_followup_tasks": "Create a new task-plan draft for the current goal; do not write formally.",
    "apply_confirmed_draft": "Apply existing confirmed draft IDs exactly once; user confirmation is mandatory.",
    "ask_for_more_material": "Create a missing-material suggestion when current evidence is insufficient.",
    "answer_only": "Return a learning suggestion without running a write or draft tool.",
}


def list_tools() -> list[dict]:
    return [TOOLS[name] for name in TOOLS]


def list_model_actions(allowed_action_types: set[str] | None = None) -> list[dict]:
    actions = []
    for action_type, tool_name in ACTION_TOOL_MAP.items():
        if allowed_action_types is not None and action_type not in allowed_action_types:
            continue
        tool = TOOLS[tool_name]
        actions.append(
            {
                "type": action_type,
                "toolName": tool_name,
                "description": MODEL_ACTION_DESCRIPTIONS[action_type],
                "riskLevel": tool["riskLevel"],
                "requiresConfirmation": tool["requiresConfirmation"],
                "draftOnly": tool["draftOnly"],
                "inputSchema": tool["inputSchema"],
                "outputType": tool["outputType"],
            }
        )
    return actions


def is_known_action(action_type: str) -> bool:
    return action_type in ACTION_TOOL_MAP


def get_tool_for_action(action_type: str) -> dict:
    tool_name = ACTION_TOOL_MAP.get(action_type, "answer_only")
    return TOOLS[tool_name]


def enrich_action(action: dict) -> dict:
    tool = get_tool_for_action(action["type"])
    requires_confirmation = action.get("requiresConfirmation", False) or bool(
        tool["requiresConfirmation"]
    )
    return {
        **action,
        "toolName": tool["name"],
        "toolLabel": tool["label"],
        "riskLevel": tool["riskLevel"],
        "draftOnly": tool["draftOnly"],
        "applyTarget": tool["applyTarget"],
        "requiresConfirmation": requires_confirmation,
    }


def validate_tool_input(action_type: str, payload: dict) -> None:
    if not is_known_action(action_type):
        raise ValueError("Unknown Agent action cannot be executed.")
    if not isinstance(payload, dict):
        raise ValueError("Tool input must be an object.")

    input_schema = get_tool_for_action(action_type).get("inputSchema") or {}
    allowed_fields = set(input_schema) | {"actionLogId"}
    unknown_fields = set(payload) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Tool input contains unknown fields: {', '.join(sorted(unknown_fields))}.")

    missing_fields = [
        field
        for field, expected in input_schema.items()
        if expected.endswith("required")
        and (field not in payload or payload[field] is None or payload[field] == "")
    ]
    if missing_fields:
        raise ValueError(f"Tool input is missing required fields: {', '.join(missing_fields)}.")

    for field, value in payload.items():
        if field == "actionLogId" or value is None:
            continue
        expected = input_schema.get(field, "")
        if expected.startswith("str") and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"Tool input {field} must be a non-empty string.")
        if expected.startswith("list[str]") and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError(f"Tool input {field} must be a list of strings.")
        if expected.startswith("int") and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"Tool input {field} must be an integer.")
    if action_type == "search_materials" and not 1 <= int(payload.get("limit", 5)) <= 20:
        raise ValueError("Tool input limit must be between 1 and 20.")
    if action_type == "answer_with_sources" and not 1 <= int(payload.get("limit", 3)) <= 10:
        raise ValueError("Tool input limit must be between 1 and 10.")
