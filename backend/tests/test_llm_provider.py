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


def test_load_env_file_sets_missing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "LLM_PROVIDER=openai-compatible",
                "LLM_API_KEY=test-key",
                "LLM_MODEL=glm-test",
                "LLM_BASE_URL=https://example.test/v1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    llm_provider._load_env_file(env_file)

    assert llm_provider.os.getenv("LLM_PROVIDER") == "openai-compatible"
    assert llm_provider.os.getenv("LLM_API_KEY") == "test-key"
    assert llm_provider.os.getenv("LLM_MODEL") == "glm-test"
    assert llm_provider.os.getenv("LLM_BASE_URL") == "https://example.test/v1"


def test_load_env_file_does_not_override_existing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=from-file", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "from-shell")

    llm_provider._load_env_file(env_file)

    assert llm_provider.os.getenv("LLM_MODEL") == "from-shell"


def test_openai_compatible_provider_requires_key_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_ENV_FILE", str(tmp_path / "missing.env"))
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


def test_openai_compatible_provider_downgrades_insufficient_material(monkeypatch):
    provider = llm_provider.OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
    )

    def fake_completion(payload):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"answer":"资料不涉及登录和支付设计。",'
                            '"basis":"The note does not discuss authentication or payment systems.",'
                            '"suggestion":"请补充登录和支付相关资料。",'
                            '"isFromMaterial":true,'
                            '"confidence":"medium"}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(provider, "_post_chat_completion", fake_completion)

    answer = provider.generate_answer(
        llm_provider.LLMAnswerContext(
            question="如何设计登录和支付？",
            goal=None,
            material_id="material_1",
            references=[
                {
                    "materialId": "material_1",
                    "materialTitle": "Flashcard notes",
                    "chunkIndex": 0,
                    "content": "This note describes flashcards only.",
                    "score": 3,
                }
            ],
        )
    )

    assert answer.is_from_material is False
    assert answer.confidence == "low"


def test_openai_compatible_provider_downgrades_missing_question_terms(monkeypatch):
    provider = llm_provider.OpenAICompatibleLLMProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
    )

    def fake_completion(payload):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"answer":"LangChain can help implement spaced repetition.",'
                            '"basis":"Based on spaced repetition and flashcards.",'
                            '"suggestion":"Use LangChain to build a review flow.",'
                            '"isFromMaterial":true,'
                            '"confidence":"medium"}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(provider, "_post_chat_completion", fake_completion)

    answer = provider.generate_answer(
        llm_provider.LLMAnswerContext(
            question="这份资料是否说明了如何用 LangChain 实现间隔重复？",
            goal=None,
            material_id="material_1",
            references=[
                {
                    "materialId": "material_1",
                    "materialTitle": "Review notes",
                    "chunkIndex": 0,
                    "content": "Spaced repetition helps learners review difficult knowledge over time.",
                    "score": 3,
                }
            ],
        )
    )

    assert answer.is_from_material is False
    assert answer.confidence == "low"
    assert "LangChain" in answer.answer
    assert "未提及" in answer.answer
