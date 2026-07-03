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
