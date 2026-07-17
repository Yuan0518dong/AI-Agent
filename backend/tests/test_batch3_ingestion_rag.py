from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from backend.app.main import app
from backend.app.services import embedding_provider, material_processing_service, store
from backend.tests.auth_helpers import register_session


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("LLM_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("EMBEDDING_ENV_FILE", str(tmp_path / "missing.env"))
    client.cookies.clear()
    store.set_db_path(tmp_path / "batch3.db")
    store.reset()
    register_session(client, email="batch3@example.com", name="Batch 3")
    yield
    client.cookies.clear()
    store.reset()


def upload(filename: str, content: bytes, mime_type: str, title: str = ""):
    return client.post(
        "/api/materials/upload",
        data={"title": title},
        files={"file": (filename, content, mime_type)},
    )


def _text_pdf_bytes(*pages: str) -> bytes:
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            }
        )
        stream = DecodedStreamObject()
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _blank_pdf_bytes(page_count: int = 1, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_markdown_upload_runs_all_stages_and_keeps_heading_locations():
    response = upload(
        "learning.md",
        b"# Retrieval\n\nHybrid retrieval combines keyword and vector rankings.\n\n## Review\n\nUse RRF to rank learning evidence.",
        "text/markdown",
        "Retrieval notes",
    )

    assert response.status_code == 200
    material = response.json()["data"]
    assert material["type"] == "markdown"
    assert material["originalFilename"] == "learning.md"
    assert material["content"].startswith("# Retrieval")
    assert {stage["status"] for stage in material["processingStatus"].values()} == {"completed"}

    chunks = client.get(f"/api/materials/{material['id']}/chunks").json()["data"]
    assert chunks[0]["headingPath"] == "Retrieval"
    assert chunks[0]["paragraphIndex"] == 0
    assert "rawBytes" not in material
    assert "fileContent" not in material


def test_pdf_upload_preserves_page_numbers_and_releases_file_bytes():
    response = upload(
        "evidence.pdf",
        _text_pdf_bytes("Page one explains retrieval.", "Page two explains citations."),
        "application/pdf",
    )

    assert response.status_code == 200
    material = response.json()["data"]
    assert material["pageCount"] == 2
    assert material["originalFilename"] == "evidence.pdf"
    assert "Page one" in material["content"]
    assert "rawBytes" not in material["extractionMetadata"]
    chunks = client.get(f"/api/materials/{material['id']}/chunks").json()["data"]
    assert {chunk["pageNumber"] for chunk in chunks} == {1, 2}


@pytest.mark.parametrize(
    ("filename", "content", "mime", "message"),
    [
        ("archive.zip", b"PK\x03\x04not-an-upload", "application/zip", "压缩包"),
        ("wrong.pdf", b"not-pdf", "application/pdf", "签名"),
        ("notes.md", b"# heading", "application/pdf", "MIME"),
        ("../notes.md", b"# heading", "text/markdown", "路径"),
    ],
)
def test_upload_rejects_invalid_extension_mime_signature_and_path(filename, content, mime, message):
    response = upload(filename, content, mime)

    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


def test_upload_rejects_encrypted_oversized_and_scanned_pdfs():
    encrypted = upload("secret.pdf", _blank_pdf_bytes(encrypted=True), "application/pdf")
    scanned = upload("scan.pdf", _blank_pdf_bytes(), "application/pdf")
    too_many_pages = upload("many.pdf", _blank_pdf_bytes(51), "application/pdf")

    assert encrypted.status_code == 422
    assert "加密" in encrypted.json()["error"]["message"]
    assert scanned.status_code == 422
    assert "OCR 暂不支持" in scanned.json()["error"]["message"]
    assert too_many_pages.status_code == 422
    assert "50 页" in too_many_pages.json()["error"]["message"]


def test_failed_stage_is_retryable_without_reupload(monkeypatch):
    original = material_processing_service.summarize_material
    monkeypatch.setattr(
        material_processing_service,
        "summarize_material",
        lambda material, user_id=None: (_ for _ in ()).throw(RuntimeError("summary unavailable")),
    )
    response = upload("retry.md", b"# Retry\n\nA retryable processing stage.", "text/markdown")
    material = response.json()["data"]
    assert material["processingStatus"]["summary"] == {"status": "failed", "error": "summary unavailable"}
    assert material["processingStatus"]["flashcards"]["status"] == "pending"

    monkeypatch.setattr(material_processing_service, "summarize_material", original)
    retry = client.post(f"/api/materials/{material['id']}/processing/summary/retry")
    assert retry.status_code == 200
    assert retry.json()["data"]["processingStatus"]["summary"]["status"] == "completed"


def test_hybrid_rrf_citations_and_insufficient_answer_boundary():
    response = upload(
        "rag.md",
        b"# Retrieval Design\n\nHybrid retrieval combines keyword search and vector retrieval with RRF ranking.",
        "text/markdown",
    )
    material = response.json()["data"]
    search = client.get("/api/materials/search", params={"query": "hybrid retrieval", "limit": 5})
    assert search.status_code == 200
    result = search.json()["data"][0]
    assert result["searchMode"] == "hybrid"
    assert set(result["retrievalModes"]) == {"keyword", "semantic"}

    answer = client.post(
        "/api/agent/ask",
        json={"question": "hybrid retrieval 如何排序？", "materialId": material["id"]},
    )
    assert answer.status_code == 200
    reference = answer.json()["data"]["references"][0]
    assert reference["materialTitle"] == material["title"]
    assert reference["headingPath"] == "Retrieval Design"
    assert reference["content"]
    assert reference["searchMode"] == "hybrid"
    assert reference["score"] > 0

    insufficient = client.post(
        "/api/agent/ask",
        json={"question": "量子纠缠的贝尔不等式是什么？", "materialId": material["id"]},
    )
    data = insufficient.json()["data"]
    assert insufficient.status_code == 200
    assert data["isFromMaterial"] is False
    assert "资料不足" in data["answer"]
    assert data["references"] == []


def test_keyword_degradation_when_embeddings_are_unavailable(monkeypatch):
    material = upload(
        "keyword.txt",
        b"Keyword fallback keeps evidence available when embeddings fail.",
        "text/plain",
    ).json()["data"]

    class FailingProvider:
        def embed(self, text):
            raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(embedding_provider, "get_embedding_provider", lambda: FailingProvider())
    response = client.get("/api/materials/search", params={"query": "keyword fallback"})

    assert response.status_code == 200
    assert response.json()["data"][0]["materialId"] == material["id"]
    assert response.json()["data"][0]["searchMode"] == "keyword"


def test_batch3_migration_declares_vector_2048_and_halfvec_cosine_hnsw_index():
    migration = Path("backend/migrations/versions/20260717_02_ingestion_rag_pgvector.py").read_text(
        encoding="utf-8"
    )

    assert "vector(2048)" in migration
    assert "halfvec(2048)" in migration
    assert "halfvec_cosine_ops" in migration
    assert "USING hnsw" in migration
