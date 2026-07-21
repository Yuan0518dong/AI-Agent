import pytest

from backend.app.services import (
    agent_action_policy_service,
    agent_decision_guard_service,
    agent_tool_execution_service,
    agent_tool_registry_service,
)


def _fallback() -> dict:
    return {
        "generatedAt": "2026-07-21T00:00:00Z",
        "scope": {"goalId": "goal_1"},
        "stateSummary": "Scoped learning context.",
        "problems": [],
        "reason": "Use the current learning state.",
        "feedbackMemory": {},
    }


def _context(*, weak_material_ids: list[str] | None = None, materials: list[dict] | None = None) -> dict:
    if materials is None:
        materials = [
            {"id": "material_1", "goalId": "goal_1"},
            {"id": "material_2", "goalId": "goal_1"},
        ]
    return {
        "scope": {"goalId": "goal_1"},
        "summary": {
            "goalCount": 1,
            "materialTotal": len(materials),
            "materialsWithoutChunks": 0,
            "qaInsufficiencyCount": 0,
            "quizWeakAttemptCount": len(weak_material_ids or []),
        },
        "materials": materials,
        "quiz": {"weakAttempts": [{"materialId": value} for value in (weak_material_ids or [])]},
        "review": {"new": 0, "review": 0},
        "drafts": {"proposedCount": 0, "proposed": []},
        "goals": [{"id": "goal_1"}],
        "tasks": [],
        "agentRun": {"objective": "Create a review draft from weak quiz results.", "stepHistory": []},
    }


def _model_review_decision(action_type: str, payload: dict) -> dict:
    return {
        "nextAction": action_type,
        "reason": "Create a scoped review draft.",
        "proposedActions": [{"type": action_type, "payload": payload}],
    }


def test_model_contract_exposes_only_canonical_review_action():
    actions = {action["type"]: action for action in agent_tool_registry_service.list_model_actions()}

    assert "create_review_draft" in actions
    assert "create_flashcards" not in actions
    assert "create_quiz" not in actions
    assert actions["create_review_draft"]["inputSchema"] == {"materialIds": "list[str] required"}


@pytest.mark.parametrize("legacy_action", ["create_flashcards", "create_quiz"])
def test_guard_accepts_legacy_review_actions_and_normalizes_them(legacy_action: str):
    decision = agent_decision_guard_service.decision_from_model_data(
        _model_review_decision(legacy_action, {"weakAttemptCount": 1}),
        _fallback(),
        "hybrid",
        context=_context(weak_material_ids=["material_2", "material_2", "material_1"]),
        allowed_action_types={"create_review_draft"},
    )

    assert decision["nextAction"] == "create_review_draft"
    assert decision["proposedActions"][0]["type"] == "create_review_draft"
    assert decision["proposedActions"][0]["payload"] == {"materialIds": ["material_2", "material_1"]}


@pytest.mark.parametrize(
    ("data", "category"),
    [
        ({"nextAction": "create_review_draft", "reason": "x", "proposedActions": []}, "payload_invalid"),
        (_model_review_decision("unknown_tool", {}), "disallowed_action"),
        (_model_review_decision("create_review_draft", {}), "missing_required_field"),
        (_model_review_decision("create_review_draft", {"materialIds": ["material_1", "material_1"]}), "payload_invalid"),
        (_model_review_decision("create_review_draft", {"materialIds": ["material_other"]}), "scope_invalid"),
        ({"nextAction": "create_review_draft", "proposedActions": []}, "schema_invalid"),
    ],
)
def test_guard_uses_only_redacted_failure_categories(data: dict, category: str):
    with pytest.raises(agent_decision_guard_service.DecisionGuardError) as exc_info:
        agent_decision_guard_service.decision_from_model_data(
            data,
            _fallback(),
            "hybrid",
            context=_context(),
            allowed_action_types={"create_review_draft"},
        )

    assert exc_info.value.category == category
    assert str(exc_info.value) == f"Decision Guard rejected model output: {category}."


def test_guard_rejects_model_submitted_weak_attempt_count_as_payload_invalid():
    with pytest.raises(agent_decision_guard_service.DecisionGuardError) as exc_info:
        agent_decision_guard_service.decision_from_model_data(
            _model_review_decision(
                "create_review_draft",
                {"materialIds": ["material_1"], "weakAttemptCount": 1},
            ),
            _fallback(),
            "hybrid",
            context=_context(),
            allowed_action_types={"create_review_draft"},
        )

    assert exc_info.value.category == "payload_invalid"


def test_runtime_policy_constructs_deduplicated_review_material_ids_from_weak_attempts():
    context = _context(weak_material_ids=["material_2", "material_1", "material_2"])

    allowed = agent_action_policy_service.allowed_action_types(context, _fallback())
    decision = agent_action_policy_service.build_deterministic_decision(
        context,
        _fallback(),
        allowed,
        "hybrid",
    )

    assert allowed == {"create_review_draft"}
    assert decision is not None
    assert decision["proposedActions"][0]["payload"] == {"materialIds": ["material_2", "material_1"]}


def test_runtime_policy_returns_material_gap_when_review_scope_is_empty():
    context = _context(materials=[])

    allowed = agent_action_policy_service.allowed_action_types(context, _fallback())
    decision = agent_action_policy_service.build_deterministic_decision(
        context,
        _fallback(),
        allowed,
        "hybrid",
    )

    assert allowed == {"ask_for_more_material"}
    assert decision is not None
    assert decision["nextAction"] == "ask_for_more_material"


def test_runtime_policy_keeps_mastery_checks_out_of_review_draft_creation():
    context = _context()
    context["agentRun"]["objective"] = "Please redo quiz and check mastery."

    assert agent_action_policy_service.allowed_action_types(context, _fallback()) == {"answer_only"}


def test_review_executor_rejects_zero_drafts_before_any_persistence():
    with pytest.raises(ValueError, match="at least one scoped material ID"):
        agent_tool_execution_service._create_review_draft({}, "goal_1", "user_1", "review", None, None)
