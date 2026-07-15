from backend.app.services import embedding_provider


def test_openai_compatible_embedding_provider_selected_with_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-test")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "7")

    provider = embedding_provider.get_embedding_provider()

    assert isinstance(provider, embedding_provider.OpenAICompatibleEmbeddingProvider)
    assert provider.model == "embedding-test"
    assert provider.base_url == "https://example.test/v1"
    assert provider.timeout_seconds == 7


def test_openai_compatible_embedding_provider_maps_response(monkeypatch):
    provider = embedding_provider.OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="embedding-test",
    )

    def fake_post(payload):
        assert payload == {"model": "embedding-test", "input": "learning retrieval"}
        return {"data": [{"index": 0, "embedding": [0, 0.5, 1]}]}

    monkeypatch.setattr(provider, "_post_embeddings", fake_post)

    assert provider.embed(" learning retrieval ") == [0.0, 0.5, 1.0]


def test_embedding_provider_falls_back_to_mock_without_real_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

    assert isinstance(embedding_provider.get_embedding_provider(), embedding_provider.MockEmbeddingProvider)
