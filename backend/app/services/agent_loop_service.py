import json

from backend.app.services import (
    agent_action_log_service,
    agent_context_service,
    agent_decision_service,
    agent_run_service,
    agent_tool_execution_service,
    sensitive_data_service,
    store,
)


TERMINAL_STATUSES = {"completed", "failed", "max_steps", "cancelled", "closed"}
REFLECTION_STATUSES = {"completed", "failed", "max_steps", "cancelled"}


def execute_agent_run(
    run_id: str,
    user_id: str | None = None,
    max_steps: int | None = None,
    *,
    single_step: bool = False,
) -> dict | None:
    run = agent_run_service.get_agent_run(run_id, user_id)
    if not run:
        return None
    if run["status"] in TERMINAL_STATUSES:
        return run
    if not agent_run_service.claim_agent_run_execution(run_id, user_id):
        return agent_run_service.get_agent_run(run_id, user_id)

    step_budget = max_steps or run["maxSteps"]
    scope_user_id = run["userId"]
    run.update({"status": "running", "stopReason": "", "error": ""})
    _set_run_state(run, "running", max_steps=step_budget)
    if _is_cancelled(run):
        return agent_run_service.get_agent_run(run_id, user_id)
    steps = agent_run_service.list_agent_run_steps(run_id)
    readback_context = None
    readback_decision = None
    waiting_step = next(
        (step for step in reversed(steps) if step["status"] == "waiting_confirmation"),
        None,
    )
    if waiting_step and not _resume_waiting_step(run, waiting_step, scope_user_id):
        return agent_run_service.get_agent_run(run_id, user_id)

    steps = agent_run_service.list_agent_run_steps(run_id)
    completed_waiting_step = next(
        (step for step in steps if waiting_step and step["id"] == waiting_step["id"]),
        None,
    )
    if (
        completed_waiting_step
        and completed_waiting_step["toolName"] == "apply_confirmed_draft"
        and completed_waiting_step["status"] == "completed"
    ):
        readback = _readback_after_confirmed_apply(run, steps)
        if not readback:
            return agent_run_service.get_agent_run(run_id, user_id)
        readback_context, readback_decision = readback

    # A confirmation is itself the step this interaction was asked to advance.
    # The next request will use the persisted readback to create a later step.
    if single_step and waiting_step:
        if run["status"] == "running":
            _set_run_state(run, "decided", current_step=len(steps))
        return agent_run_service.get_agent_run(run_id, user_id)

    while len(steps) < step_budget:
        if _is_cancelled(run):
            return agent_run_service.get_agent_run(run_id, user_id)
        if readback_context is not None and readback_decision is not None:
            context = readback_context
            decision = readback_decision
            readback_context = None
            readback_decision = None
        else:
            context = agent_context_service.build_agent_context(run["goalId"], scope_user_id)
            decision = agent_decision_service.decide_next_action(
                run["goalId"],
                scope_user_id,
                run["decisionMode"],
                run["objective"],
                steps,
            )
        action = _select_next_action(decision, steps)
        if _is_cancelled(run):
            return agent_run_service.get_agent_run(run_id, user_id)
        if not action:
            _set_run_state(
                run,
                "completed",
                "no_progress",
                context=context,
                decision=decision,
                current_step=len(steps),
            )
            return agent_run_service.get_agent_run(run_id, user_id)

        step_index = len(steps) + 1
        if action.get("requiresConfirmation") and action.get("status") != "accepted":
            action_log = agent_action_log_service.create_action_log(
                {
                    "goalId": run["goalId"],
                    "actionType": action["type"],
                    "observation": decision.get("stateSummary", ""),
                    "decision": decision,
                    "proposedPayload": {
                        **action,
                        "draftIds": (action.get("payload") or {}).get("draftIds", []),
                        "agentRunId": run_id,
                        "stepIndex": step_index,
                    },
                    "status": "proposed",
                },
                scope_user_id,
            )
            _insert_step(
                run,
                step_index,
                context,
                decision,
                action,
                {"observation": "Waiting for user confirmation before tool execution."},
                "waiting_confirmation",
                action_log["id"],
            )
            if _is_cancelled(run):
                return agent_run_service.get_agent_run(run_id, user_id)
            _set_run_state(
                run,
                "waiting_confirmation",
                "confirmation_required",
                context=context,
                decision=decision,
                current_step=step_index,
            )
            return agent_run_service.get_agent_run(run_id, user_id)

        step_id = _insert_step(
            run,
            step_index,
            context,
            decision,
            action,
            {"observation": "Executing registered tool."},
            "running",
        )
        try:
            tool_output = agent_tool_execution_service.execute_action(
                action,
                run["goalId"],
                scope_user_id,
                run["objective"],
                run_id=run["id"],
                step_id=step_id,
            )
            if _is_cancelled(run):
                _update_step(
                    step_id,
                    "cancelled",
                    {"observation": "Run cancelled after the tool returned; no later action was executed."},
                )
                return agent_run_service.get_agent_run(run_id, user_id)
            action_log_id = _record_applied_action(
                run,
                decision,
                action,
                tool_output,
                scope_user_id,
            )
            _update_step(step_id, "completed", tool_output, action_log_id=action_log_id)
        except agent_tool_execution_service.ToolExecutionTimeout as exc:
            error = sensitive_data_service.redact_text(str(exc), max_length=240)
            _update_step(step_id, "failed", {}, error)
            if _is_cancelled(run):
                return agent_run_service.get_agent_run(run_id, user_id)
            stop_reason = (
                "tool_timeout_read_retry_exhausted"
                if exc.retryable
                else "tool_timeout_write_no_retry"
            )
            _set_run_state(
                run,
                "failed",
                stop_reason,
                error,
                context,
                decision,
                step_index,
            )
            return agent_run_service.get_agent_run(run_id, user_id)
        except Exception as exc:
            error = sensitive_data_service.redact_text(str(exc) or exc.__class__.__name__, max_length=240)
            _update_step(step_id, "failed", {}, error)
            _set_run_state(
                run,
                "failed",
                "tool_error",
                error,
                context,
                decision,
                step_index,
            )
            return agent_run_service.get_agent_run(run_id, user_id)

        steps = agent_run_service.list_agent_run_steps(run_id)
        if tool_output.get("terminal"):
            _set_run_state(
                run,
                "completed",
                "completed",
                context=context,
                decision=decision,
                current_step=step_index,
            )
            return agent_run_service.get_agent_run(run_id, user_id)

        if single_step:
            if len(steps) >= step_budget:
                _set_run_state(run, "max_steps", "max_steps", current_step=len(steps))
            else:
                _set_run_state(
                    run,
                    "decided",
                    context=context,
                    decision=decision,
                    current_step=step_index,
                )
            return agent_run_service.get_agent_run(run_id, user_id)

    _set_run_state(run, "max_steps", "max_steps", current_step=len(steps))
    return agent_run_service.get_agent_run(run_id, user_id)


def advance_agent_run(
    run_id: str,
    user_id: str | None = None,
) -> dict | None:
    """Run one interactive increment without changing the run's total budget."""
    return execute_agent_run(run_id, user_id, single_step=True)


def _resume_waiting_step(run: dict, step: dict, user_id: str | None) -> bool:
    if _is_cancelled(run):
        return False
    action_log = agent_action_log_service.get_action_log(step["actionLogId"], user_id)
    if not action_log or action_log["status"] in {"proposed", "later"}:
        _set_run_state(run, "waiting_confirmation", "confirmation_required")
        return False

    if action_log["status"] == "rejected":
        _update_step(
            step["id"],
            "rejected",
            {"observation": "The user rejected this tool action."},
        )
        _set_run_state(run, "running", "user_rejected")
        return True

    action = step["actionSnapshot"]
    try:
        tool_output = agent_tool_execution_service.execute_action(
            action,
            run["goalId"],
            user_id,
            run["objective"],
            run_id=run["id"],
            step_id=step["id"],
            action_log_id=action_log["id"],
        )
        if _is_cancelled(run):
            _update_step(
                step["id"],
                "cancelled",
                {"observation": "Run cancelled after the confirmation tool returned."},
            )
            return False
    except agent_tool_execution_service.ToolExecutionTimeout as exc:
        error = sensitive_data_service.redact_text(str(exc), max_length=240)
        _update_step(step["id"], "failed", {}, error)
        if not _is_cancelled(run):
            _set_run_state(run, "failed", "tool_timeout_write_no_retry", error)
        return False
    except Exception as exc:
        error = sensitive_data_service.redact_text(str(exc) or exc.__class__.__name__, max_length=240)
        _update_step(step["id"], "failed", {}, error)
        _set_run_state(run, "failed", "tool_error", error)
        return False

    if action["toolName"] != "apply_confirmed_draft":
        agent_action_log_service.update_action_log_status(action_log["id"], "applied", user_id)
    _update_step(step["id"], "completed", tool_output)
    _set_run_state(run, "running", "")
    return True


def _readback_after_confirmed_apply(
    run: dict,
    steps: list[dict],
) -> tuple[dict, dict] | None:
    """Persist the post-apply observation before considering the remaining budget."""
    run_user_id = run["userId"]
    try:
        context = agent_context_service.build_agent_context(run["goalId"], run_user_id)
    except Exception as exc:
        _set_run_state(
            run,
            "failed",
            "context_readback_error",
            _readback_error("Context", exc),
            current_step=len(steps),
        )
        return None

    try:
        decision = agent_decision_service.decide_next_action_from_context(
            context,
            goal_id=run["goalId"],
            user_id=run_user_id,
            decision_mode=run["decisionMode"],
            objective=run["objective"],
            step_history=steps,
        )
    except Exception as exc:
        _set_run_state(
            run,
            "failed",
            "decision_readback_error",
            _readback_error("Decision", exc),
            context=context,
            current_step=len(steps),
        )
        return None

    _set_run_state(
        run,
        "running",
        context=context,
        decision=decision,
        current_step=len(steps),
    )
    return context, decision


def _readback_error(stage: str, exc: Exception) -> str:
    return f"{stage} readback failed ({exc.__class__.__name__})."


def _select_next_action(decision: dict, steps: list[dict]) -> dict | None:
    attempted = {
        _action_fingerprint(step["actionSnapshot"])
        for step in steps
        if step["status"] in {"completed", "rejected", "waiting_confirmation"}
    }
    for action in decision.get("proposedActions") or []:
        if _action_fingerprint(action) not in attempted:
            return action
    return None


def _action_fingerprint(action: dict) -> str:
    return json.dumps(
        {"type": action.get("type"), "payload": action.get("payload") or {}},
        ensure_ascii=False,
        sort_keys=True,
    )


def _record_applied_action(
    run: dict,
    decision: dict,
    action: dict,
    tool_output: dict,
    user_id: str | None,
) -> str:
    existing_log_id = (action.get("payload") or {}).get("actionLogId")
    if existing_log_id:
        existing = agent_action_log_service.get_action_log(existing_log_id, user_id)
        if existing and existing["status"] == "accepted":
            agent_action_log_service.update_action_log_status(existing_log_id, "applied", user_id)
            return existing_log_id

    action_log = agent_action_log_service.create_action_log(
        {
            "goalId": run["goalId"],
            "actionType": action["type"],
            "observation": tool_output.get("observation", ""),
            "decision": decision,
            "proposedPayload": {**action, "agentRunId": run["id"]},
            "status": "applied",
        },
        user_id,
    )
    return action_log["id"]


def _insert_step(
    run: dict,
    step_index: int,
    context: dict,
    decision: dict,
    action: dict,
    tool_output: dict,
    status: str,
    action_log_id: str | None = None,
    error: str = "",
    step_id: str | None = None,
) -> str:
    now = store.now_iso()
    persisted_step_id = step_id or store.make_id("agentstep")
    with store.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_run_steps (
                id, run_id, step_index, context_snapshot, decision_snapshot,
                action_snapshot, tool_name, tool_input, tool_output,
                action_log_id, status, error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                persisted_step_id,
                run["id"],
                step_index,
                json.dumps(sensitive_data_service.redact(context), ensure_ascii=False),
                json.dumps(sensitive_data_service.redact(decision), ensure_ascii=False),
                json.dumps(sensitive_data_service.redact(action), ensure_ascii=False),
                action.get("toolName", ""),
                json.dumps(sensitive_data_service.redact(action.get("payload") or {}), ensure_ascii=False),
                json.dumps(sensitive_data_service.redact(tool_output), ensure_ascii=False),
                action_log_id,
                status,
                sensitive_data_service.redact_text(error, max_length=240),
                now,
                now,
            ),
        )
    return persisted_step_id


def _update_step(
    step_id: str,
    status: str,
    tool_output: dict,
    error: str = "",
    action_log_id: str | None = None,
) -> None:
    with store.db_connection() as conn:
        conn.execute(
            """
            UPDATE agent_run_steps
            SET status = ?, tool_output = ?, error = ?,
                action_log_id = COALESCE(?, action_log_id), updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(sensitive_data_service.redact(tool_output), ensure_ascii=False),
                sensitive_data_service.redact_text(error, max_length=240),
                action_log_id,
                store.now_iso(),
                step_id,
            ),
        )


def _set_run_state(
    run: dict,
    status: str,
    stop_reason: str = "",
    error: str = "",
    context: dict | None = None,
    decision: dict | None = None,
    current_step: int | None = None,
    max_steps: int | None = None,
) -> bool:
    context_snapshot = context or run["contextSnapshot"]
    decision_snapshot = decision or run["decisionSnapshot"]
    safe_error = sensitive_data_service.redact_text(error, max_length=240)
    if status in REFLECTION_STATUSES:
        decision_snapshot = {
            **decision_snapshot,
            "reflection": _build_terminal_reflection(
                run,
                status,
                stop_reason,
                safe_error,
                current_step if current_step is not None else run["currentStep"],
            ),
        }
    persisted_context = sensitive_data_service.redact(context_snapshot)
    persisted_decision = sensitive_data_service.redact(decision_snapshot)
    feedback_summary = agent_run_service.build_feedback_summary(run["goalId"], run["userId"])
    with store.db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, stop_reason = ?, error = ?, context_snapshot = ?,
                decision_snapshot = ?, feedback_summary = ?, current_step = ?,
                max_steps = ?, updated_at = ?
            WHERE id = ? AND (? = 'cancelled' OR status != 'cancelled')
            """,
            (
                status,
                stop_reason,
                safe_error,
                json.dumps(persisted_context, ensure_ascii=False),
                json.dumps(persisted_decision, ensure_ascii=False),
                json.dumps(feedback_summary, ensure_ascii=False),
                current_step if current_step is not None else run["currentStep"],
                max_steps if max_steps is not None else run["maxSteps"],
                store.now_iso(),
                run["id"],
                status,
            ),
        )
    if cursor.rowcount == 0:
        latest = agent_run_service.get_agent_run(run["id"], run["userId"])
        if latest:
            run.update(latest)
        return False
    run.update(
        {
            "status": status,
            "stopReason": stop_reason,
            "error": safe_error,
            "contextSnapshot": persisted_context,
            "decisionSnapshot": persisted_decision,
            "currentStep": current_step if current_step is not None else run["currentStep"],
            "maxSteps": max_steps if max_steps is not None else run["maxSteps"],
        }
    )
    return True


def _build_terminal_reflection(
    run: dict,
    status: str,
    stop_reason: str,
    error: str,
    current_step: int,
) -> str:
    steps = agent_run_service.list_agent_run_steps(run["id"])
    tool_names = [step["toolName"] for step in steps if step.get("toolName")]
    tool_summary = ", ".join(tool_names[-4:]) or "no tool execution"
    if status == "failed":
        detail = _redact_reflection_error(error) or "unspecified runtime failure"
        return (
            f"Run failed after {current_step} persisted step(s). Recent tools: {tool_summary}. "
            f"Error: {detail}"
        )
    if status == "max_steps":
        return (
            f"Run stopped at the step budget after {current_step} persisted step(s). "
            f"Recent tools: {tool_summary}."
        )
    if status == "cancelled":
        return (
            f"Run was cancelled after {current_step} persisted step(s). "
            f"Recent tools: {tool_summary}."
        )
    if stop_reason == "no_progress":
        return (
            f"Run stopped with no new executable action after {current_step} persisted step(s). "
            f"Recent tools: {tool_summary}."
        )
    return (
        f"Run completed after {current_step} persisted step(s). Recent tools: {tool_summary}."
    )


def _redact_reflection_error(error: str) -> str:
    normalized = " ".join((error or "").split())
    return sensitive_data_service.redact_text(normalized, max_length=240)


def _is_cancelled(run: dict) -> bool:
    return agent_run_service.is_agent_run_cancelled(run["id"], run.get("userId"))
