"""Parse supported uploads in memory and return text plus source locations.

Original upload bytes deliberately never reach the filesystem.  The caller owns
the returned extracted text and persists only that text and the location metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 50


class UploadValidationError(ValueError):
    """A user-facing, deterministic upload validation failure."""


@dataclass(frozen=True)
class ExtractedMaterial:
    title: str
    source_type: str
    original_filename: str
    mime_type: str
    page_count: int | None
    content: str
    extraction_metadata: dict


def extract_uploaded_material(filename: str | None, mime_type: str | None, data: bytes) -> ExtractedMaterial:
    safe_filename = _validate_filename(filename)
    extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    normalized_mime = (mime_type or "").strip().lower()

    if not data:
        raise UploadValidationError("上传文件为空。")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("单个文件不能超过 5 MB。")
    if extension in {"zip", "rar", "7z", "gz", "tar"} or normalized_mime in {
        "application/zip",
        "application/x-zip-compressed",
        "application/x-rar-compressed",
        "application/x-7z-compressed",
    } or data.startswith(b"PK\x03\x04"):
        raise UploadValidationError("不支持压缩包上传。")

    if extension == "pdf":
        _validate_mime(normalized_mime, {"application/pdf", "application/x-pdf"})
        if not data.startswith(b"%PDF-"):
            raise UploadValidationError("PDF 文件签名无效。")
        return _extract_pdf(safe_filename, normalized_mime, data)
    if extension in {"md", "markdown"}:
        _validate_mime(normalized_mime, {"text/markdown", "text/plain"})
        content = _decode_text(data)
        return ExtractedMaterial(
            title=PurePath(safe_filename).stem,
            source_type="markdown",
            original_filename=safe_filename,
            mime_type=normalized_mime,
            page_count=None,
            content=content,
            extraction_metadata={"format": "markdown"},
        )
    if extension == "txt":
        _validate_mime(normalized_mime, {"text/plain"})
        content = _decode_text(data)
        return ExtractedMaterial(
            title=PurePath(safe_filename).stem,
            source_type="txt",
            original_filename=safe_filename,
            mime_type=normalized_mime,
            page_count=None,
            content=content,
            extraction_metadata={"format": "txt"},
        )
    raise UploadValidationError("仅支持 PDF、Markdown（.md）和 TXT 文件。")


def _extract_pdf(filename: str, mime_type: str, data: bytes) -> ExtractedMaterial:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise UploadValidationError("PDF 文件无法解析。") from exc

    if reader.is_encrypted:
        raise UploadValidationError("不支持加密 PDF。")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise UploadValidationError("PDF 不能超过 50 页。")

    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except (PdfReadError, ValueError) as exc:
            raise UploadValidationError("PDF 文本提取失败。") from exc
        if text:
            pages.append({"pageNumber": page_number, "text": text})

    if not pages:
        raise UploadValidationError("该 PDF 未提取到文本，扫描件和 OCR 暂不支持。")

    return ExtractedMaterial(
        title=PurePath(filename).stem,
        source_type="pdf",
        original_filename=filename,
        mime_type=mime_type,
        page_count=len(reader.pages),
        content="\n\n".join(page["text"] for page in pages),
        extraction_metadata={"format": "pdf", "pages": pages},
    )


def _validate_filename(filename: str | None) -> str:
    normalized = (filename or "").strip()
    if not normalized or normalized in {".", ".."}:
        raise UploadValidationError("文件名无效。")
    if any(marker in normalized for marker in ("/", "\\", ":", "\x00")) or ".." in normalized:
        raise UploadValidationError("文件名不能包含路径。")
    if PurePath(normalized).name != normalized or not re.fullmatch(r"[^<>|?*]+", normalized):
        raise UploadValidationError("文件名无效。")
    return normalized


def _validate_mime(mime_type: str, allowed: set[str]) -> None:
    if mime_type not in allowed:
        raise UploadValidationError("文件 MIME 类型与允许的资料类型不匹配。")


def _decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise UploadValidationError("文本文件包含二进制内容。")
    try:
        text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise UploadValidationError("文本文件必须是 UTF-8 编码。") from exc
    if not text:
        raise UploadValidationError("上传文件未包含可提取文本。")
    return text
