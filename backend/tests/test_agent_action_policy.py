from backend.app.services import agent_action_policy_service, agent_tool_registry_service


def _context(
    objective: str,
    *,
    summary: dict | None = None,
    drafts: dict | None = None,
    steps: list[dict] | None = None,
) -> dict:
    return {
        "summary": {
            "goalCount": 1,
            "taskTotal": 0,
            "materialTotal": 1,
            "materialsWithoutChunks": 0,
            "qaInsufficiencyCount": 0,
            "quizWeakAttemptCount": 0,
            **(summary or {}),
        },
        "review": {"review": 0, "new": 0},
        "drafts": drafts or {"proposedCount": 0, "proposed": []},
        "agentRun": {"objective": objective, "stepHistory": steps or []},
    }


def _fallback(*, rejected: list[dict] | None = None, accepted: list[dict] | None = None) -> dict:
    return {
        "feedbackMemory": {
            "recentlyRejected": rejected or [],
            "pendingAccepted": accepted or [],
        }
    }


def test_policy_requires_existing_proposed_drafts_to_be_applied_before_new_actions():
    allowed = agent_action_policy_service.allowed_action_types(
        _context(
            "Create another task plan.",
            drafts={"proposedCount": 1, "proposed": [{"id": "draft_1"}]},
        ),
        _fallback(),
    )

    assert allowed == {"apply_confirmed_draft"}


def test_policy_routes_evidence_objective_from_search_to_grounded_answer():
    before_search = agent_action_policy_service.allowed_action_types(
        _context("Find grounded revision evidence."),
        _fallback(),
    )
    after_search = agent_action_policy_service.allowed_action_types(
        _context(
            "Find grounded revision evidence.",
            steps=[{"toolName": "search_materials", "status": "completed"}],
        ),
        _fallback(),
    )

    assert before_search == {"search_materials"}
    assert after_search == {"answer_with_sources", "ask_for_more_material", "answer_only"}


def test_policy_avoids_a_rejected_review_tool_even_when_memory_uses_tool_name():
    allowed = agent_action_policy_service.allowed_action_types(
        _context("Avoid a recently rejected review action."),
        _fallback(rejected=[{"actionType": "create_review_draft"}]),
    )

    assert allowed == {"answer_only"}


def test_policy_resumes_an_accepted_task_tool_name_without_unrelated_actions():
    allowed = agent_action_policy_service.allowed_action_types(
        _context("Resume an accepted action without a duplicate formal write."),
        _fallback(accepted=[{"actionType": "create_task_draft"}]),
    )

    assert allowed == {"create_followup_tasks", "reschedule_tasks", "apply_confirmed_draft"}


def test_policy_routes_missing_chunks_before_semantic_evidence_work():
    allowed = agent_action_policy_service.allowed_action_types(
        _context("Handle a material without usable evidence.", summary={"materialsWithoutChunks": 1}),
        _fallback(),
    )

    assert allowed == {"review_material", "ask_for_more_material", "answer_only"}


def test_policy_exposes_only_action_types_that_the_guard_accepts():
    allowed = {"create_followup_tasks", "answer_only"}
    actions = agent_tool_registry_service.list_model_actions(allowed)

    assert {action["type"] for action in actions} == allowed
    assert all(agent_tool_registry_service.is_known_action(action["type"]) for action in actions)


def test_policy_routes_invalid_draft_rollback_to_the_apply_action():
    allowed = agent_action_policy_service.allowed_action_types(
        _context("Roll back an invalid draft batch."),
        _fallback(),
    )

    assert allowed == {"apply_confirmed_draft"}
