from backend.app.services import llm_provider


def test_mock_llm_provider_generates_material_answer():
    provider = llm_provider.MockLLMProvider()
    answer = provider.generate_answer(
        llm_provider.LLMAnswerContext(
            question="How does retrieval work?",
            goal={
                "id": "goal_1",
                "name": "Agent learning",
                "subject": "AI Agent",
                "level": "basic",
                "daily_minutes": 30,
            },
            material_id="material_1",
            references=[
                {
                    "materialId": "material_1",
                    "materialTitle": "RAG notes",
                    "chunkIndex": 0,
                    "content": "Retrieval finds relevant chunks before answering.",
                    "score": 3,
                }
            ],
        )
    )

    assert answer.mode == "mock"
    assert answer.is_from_material is True
    assert answer.confidence == "high"
    assert answer.source_title == "RAG notes"
    assert "资料片段" in answer.answer
    assert "Agent learning" in answer.suggestion


def test_mock_llm_provider_generates_fallback_answer():
    provider = llm_provider.MockLLMProvider()
    answer = provider.generate_answer(
        llm_provider.LLMAnswerContext(
            question="unrelated topic",
            goal=None,
            material_id="material_1",
            references=[],
        )
    )

    assert answer.mode == "mock"
    assert answer.is_from_material is False
    assert answer.confidence == "low"
    assert answer.source_title == ""
    assert "资料不足" in answer.answer
    assert "补充更相关的资料" in answer.suggestion


def test_unknown_llm_provider_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    provider = llm_provider.get_llm_provider()

    assert isinstance(provider, llm_provider.MockLLMProvider)


def test_openai_compatible_provider_requires_key_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    provider = llm_provider.get_llm_provider()

    assert isinstance(provider, llm_provider.MockLLMProvider)


def test_openai_compatible_provider_selected_with_config(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")

    provider = llm_provider.get_llm_provider()

    assert isinstance(provider, llm_provider.OpenAICompatibleLLMProvider)
    assert provider.model == "test-model"
    assert provider.base_url == "https://example.test/v1"


def test_openai_compatible_provider_maps_json_response(monkeypatch):
    provider = llm_provider.OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
    )

    def fake_completion(payload):
        assert payload["model"] == "test-model"
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"answer":"Retrieval grounds the answer.",'
                            '"basis":"Based on the retrieved chunk.",'
                            '"suggestion":"Turn this into one flashcard.",'
                            '"isFromMaterial":true,'
                            '"confidence":"high"}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(provider, "_post_chat_completion", fake_completion)

    answer = provider.generate_answer(
        llm_provider.LLMAnswerContext(
            question="How does retrieval work?",
            goal=None,
            material_id="material_1",
            references=[
                {
                    "materialId": "material_1",
                    "materialTitle": "RAG notes",
                    "chunkIndex": 0,
                    "content": "Retrieval finds relevant chunks before answering.",
                    "score": 3,
                }
            ],
        )
    )

    assert answer.mode == "openai-compatible"
    assert answer.answer == "Retrieval grounds the answer."
    assert answer.basis == "Based on the retrieved chunk."
    assert answer.suggestion == "Turn this into one flashcard."
    assert answer.is_from_material is True
    assert answer.confidence == "high"
    assert answer.source_title == "RAG notes"
