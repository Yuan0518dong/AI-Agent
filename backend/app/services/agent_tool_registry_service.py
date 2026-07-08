TOOLS = {
    "review_material": {
        "name": "review_material",
        "label": "Review or organize material",
        "description": "Route the user to material processing, review, or reading flow.",
        "riskLevel": "low",
        "requiresConfirmation": False,
        "draftOnly": False,
        "applyTarget": "materials",
        "inputSchema": {"materialIds": "list[str] optional"},
        "outputType": "route",
    },
    "create_review_draft": {
        "name": "create_review_draft",
        "label": "Create review draft",
        "description": "Create a review or flashcard draft before any formal write.",
        "riskLevel": "medium",
        "requiresConfirmation": True,
        "draftOnly": True,
        "applyTarget": "review_drafts",
        "inputSchema": {"materialIds": "list[str] optional", "weakAttemptCount": "int optional"},
        "outputType": "draft",
    },
    "create_task_draft": {
        "name": "create_task_draft",
        "label": "Create task draft",
        "description": "Create a task plan draft before updating formal tasks.",
        "riskLevel": "high",
        "requiresConfirmation": True,
        "draftOnly": True,
        "applyTarget": "task_drafts",
        "inputSchema": {"goalIds": "list[str] optional", "taskIds": "list[str] optional"},
        "outputType": "draft",
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
    "create_flashcards": "create_review_draft",
    "create_quiz": "create_review_draft",
    "reschedule_tasks": "create_task_draft",
    "create_followup_tasks": "create_task_draft",
    "ask_for_more_material": "suggest_material_gap",
    "answer_only": "answer_only",
}


def list_tools() -> list[dict]:
    return [TOOLS[name] for name in TOOLS]


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
