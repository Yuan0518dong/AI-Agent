import pytest

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

    vector = [0.5] * embedding_provider.EMBEDDING_DIMENSIONS

    def fake_post(payload):
        assert payload == {
            "model": "embedding-test",
            "input": "learning retrieval",
            "dimensions": embedding_provider.EMBEDDING_DIMENSIONS,
        }
        return {"data": [{"index": 0, "embedding": vector}]}

    monkeypatch.setattr(provider, "_post_embeddings", fake_post)

    assert provider.embed(" learning retrieval ") == vector


def test_openai_compatible_embedding_provider_rejects_wrong_dimension(monkeypatch):
    provider = embedding_provider.OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="embedding-3",
    )
    monkeypatch.setattr(provider, "_post_embeddings", lambda payload: {"data": [{"embedding": [0.5]}]})

    try:
        provider.embed("dimension contract")
    except ValueError as exc:
        assert "expected 2048" in str(exc)
    else:
        raise AssertionError("wrong vector dimensions must be rejected")


def test_embedding_provider_falls_back_to_mock_without_real_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

    assert isinstance(embedding_provider.get_embedding_provider(), embedding_provider.MockEmbeddingProvider)


def test_real_embedding_startup_contract_requires_embedding_3_and_2048_dimensions(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-3")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "2048")
    embedding_provider.require_embedding_contract()

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")
    with pytest.raises(RuntimeError, match="2048"):
        embedding_provider.require_embedding_contract()
