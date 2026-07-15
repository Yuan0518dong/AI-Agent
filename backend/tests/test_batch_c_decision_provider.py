import json

from backend.app.services import agent_decision_provider, agent_tool_registry_service


def _context(*, oversized: bool = False) -> dict:
    preview = "evidence " * 4_000 if oversized else "Retrieval evidence for the learning goal."
    return {
        "scope": {"goalId": "goal_1", "goalCount": 1, "materialCount": 1},
        "summary": {"goalCount": 1, "taskTotal": 0, "flashcardTotal": 0},
        "goals": [{"id": "goal_1", "name": "Agent learning"}],
        "tasks": [],
        "materials": [
            {
                "id": "material_1",
                "goalId": "goal_1",
                "title": "Retrieval notes",
                "contentPreview": preview,
                "chunkCount": 1,
                "flashcardStats": {"total": 0},
                "quizStats": {"questionCount": 0},
            }
        ],
        "qa": {"insufficiencyCount": 0},
        "review": {"new": 0, "review": 0},
        "quiz": {"questionTotal": 0, "weakAttemptCount": 0},
        "drafts": {"proposed": []},
        "progress": [],
        "agentRun": {
            "objective": "Find grounded evidence for the next learning action.",
            "stepHistory": [{"stepIndex": 1, "toolName": "search_materials", "status": "completed"}],
        },
    }


def _fallback() -> dict:
    action = agent_tool_registry_service.enrich_action(
        {
            "type": "review_material",
            "label": "Review material",
            "description": "Inspect the current material.",
            "payload": {},
            "requiresConfirmation": False,
            "status": "proposed",
        }
    )
    return {
        "generatedAt": "2026-07-15T00:00:00Z",
        "mode": "rule-based",
        "requestedMode": "rule-based",
        "fallbackReason": "",
        "scope": {"goalId": "goal_1"},
        "stateSummary": "1 goal",
        "problems": [],
        "nextAction": "review_material",
        "reason": "Inspect the current material.",
        "requiresConfirmation": False,
        "proposedActions": [action],
        "feedbackMemory": {},
        "reflection": "",
    }


def _model_decision(action_type: str = "review_material", payload: dict | None = None) -> str:
    return json.dumps(
        {
            "stateSummary": "The material is ready for review.",
            "problems": [],
            "nextAction": action_type,
            "reason": "Use the scoped learning evidence.",
            "requiresConfirmation": False,
            "proposedActions": [
                {
                    "type": action_type,
                    "label": action_type,
                    "description": "Use the registered tool.",
                    "payload": payload or {},
                    "requiresConfirmation": False,
                }
            ],
            "reflection": "This is cleared until the Run reaches a terminal state.",
        },
        ensure_ascii=False,
    )


def test_batch_c_prompt_contains_context_objective_tools_and_previous_steps(monkeypatch):
    captured_payloads = []

    class Provider:
        mode = "openai-compatible"
        model = "decision-test"

        def _post_chat_completion(self, payload):
            captured_payloads.append(payload)
            return {"choices": [{"message": {"content": _model_decision()}}]}

    monkeypatch.setattr(agent_decision_provider.llm_provider, "get_llm_provider", lambda: Provider())

    decision = agent_decision_provider.decide_with_llm_json(_context(), _fallback(), "hybrid")

    prompt = json.loads(captured_payloads[0]["messages"][1]["content"])
    assert prompt["context"]["materials"][0]["id"] == "material_1"
    assert prompt["runObjective"] == "Find grounded evidence for the next learning action."
    assert prompt["previousSteps"][0]["toolName"] == "search_materials"
    assert {tool["name"] for tool in prompt["availableTools"]} >= {"review_material", "search_materials"}
    assert decision["reflection"] == ""
    assert decision["providerMetadata"] == {
        "provider": "openai-compatible",
        "model": "decision-test",
        "promptVersion": "batch-c-v1",
        "durationMs": decision["providerMetadata"]["durationMs"],
        "formatRepairAttempted": False,
        "contextWindow": {
            "trimmed": False,
            "originalCharacters": decision["providerMetadata"]["contextWindow"]["originalCharacters"],
            "promptCharacters": decision["providerMetadata"]["contextWindow"]["promptCharacters"],
        },
    }


def test_batch_c_retries_one_format_repair_before_accepting_decision(monkeypatch):
    calls = []

    class Provider:
        mode = "openai-compatible"
        model = "decision-test"

        def _post_chat_completion(self, payload):
            calls.append(payload)
            content = "not valid json" if len(calls) == 1 else _model_decision()
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(agent_decision_provider.llm_provider, "get_llm_provider", lambda: Provider())

    decision = agent_decision_provider.decide_with_llm_json(_context(), _fallback(), "hybrid")

    assert decision["mode"] == "hybrid"
    assert len(calls) == 2
    assert decision["providerMetadata"]["formatRepairAttempted"] is True


def test_batch_c_guard_rejects_out_of_scope_model_payload_after_one_repair(monkeypatch):
    calls = []

    class Provider:
        mode = "openai-compatible"
        model = "decision-test"

        def _post_chat_completion(self, payload):
            calls.append(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": _model_decision(
                                "search_materials",
                                {"query": "retrieval", "materialIds": ["material_other"]},
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(agent_decision_provider.llm_provider, "get_llm_provider", lambda: Provider())

    decision = agent_decision_provider.decide_with_llm_json(_context(), _fallback(), "hybrid")

    assert decision["mode"] == "rule-based"
    assert len(calls) == 2
    assert "outside current scope" in decision["fallbackReason"]
    assert decision["decisionGuard"]["repairAttempted"] is True


def test_batch_c_records_context_trimming_metadata(monkeypatch):
    captured_payloads = []

    class Provider:
        mode = "openai-compatible"
        model = "decision-test"

        def _post_chat_completion(self, payload):
            captured_payloads.append(payload)
            return {"choices": [{"message": {"content": _model_decision()}}]}

    monkeypatch.setattr(agent_decision_provider.llm_provider, "get_llm_provider", lambda: Provider())

    decision = agent_decision_provider.decide_with_llm_json(
        _context(oversized=True),
        _fallback(),
        "hybrid",
    )

    prompt = json.loads(captured_payloads[0]["messages"][1]["content"])
    assert decision["providerMetadata"]["contextWindow"]["trimmed"] is True
    assert decision["providerMetadata"]["contextWindow"]["originalCharacters"] > 12_000
    assert "contentPreview" not in prompt["context"]["materials"][0]


def test_batch_c_timeout_falls_back_without_format_retry(monkeypatch):
    calls = []

    class Provider:
        mode = "openai-compatible"
        model = "decision-test"

        def _post_chat_completion(self, payload):
            calls.append(payload)
            raise TimeoutError("simulated provider timeout")

    monkeypatch.setattr(agent_decision_provider.llm_provider, "get_llm_provider", lambda: Provider())

    decision = agent_decision_provider.decide_with_llm_json(_context(), _fallback(), "hybrid")

    assert decision["mode"] == "rule-based"
    assert decision["requestedMode"] == "hybrid"
    assert decision["fallbackReason"] == "LLM decision provider failed (TimeoutError)."
    assert len(calls) == 1
    assert decision["providerMetadata"]["formatRepairAttempted"] is False
