from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader


MAX_PDF_PAGES = 15
MAX_DOCX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain"}


class CvExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CvUploadInfo:
    filename: str
    content_type: str
    format: str


@dataclass(frozen=True)
class ExtractedCv:
    text: str
    page_count: int | None


def validate_upload(filename: str | None, claimed_content_type: str | None, data: bytes) -> CvUploadInfo:
    safe_name = Path(filename or "").name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise CvExtractionError("unsupported_file", "Upload a PDF, DOCX, or TXT CV")
    if claimed_content_type and claimed_content_type not in {ALLOWED_EXTENSIONS[extension], "application/octet-stream"}:
        raise CvExtractionError("invalid_content_type", "The CV file type does not match its extension")
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise CvExtractionError("invalid_pdf_signature", "The uploaded file is not a valid PDF")
    if extension == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise CvExtractionError("invalid_docx_signature", "The uploaded file is not a valid DOCX document")
    if extension == ".txt" and b"\x00" in data:
        raise CvExtractionError("invalid_text", "The uploaded text CV is not valid plain text")
    return CvUploadInfo(filename=safe_name or f"cv{extension}", content_type=ALLOWED_EXTENSIONS[extension], format=extension[1:])


def extract_cv(data: bytes, content_type: str) -> ExtractedCv:
    if content_type == "application/pdf":
        return _extract_pdf(data)
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(data)
    if content_type == "text/plain":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CvExtractionError("invalid_text", "Please upload UTF-8 plain text") from exc
        return ExtractedCv(text=_usable_text(text), page_count=None)
    raise CvExtractionError("unsupported_file", "Upload a PDF, DOCX, or TXT CV")


def _extract_pdf(data: bytes) -> ExtractedCv:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
    except Exception as exc:
        raise CvExtractionError("malformed_pdf", "The uploaded PDF could not be read") from exc
    if reader.is_encrypted:
        raise CvExtractionError("encrypted_pdf", "Password-protected CV PDFs are not supported")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise CvExtractionError("too_many_pages", "CV PDFs may contain at most 15 pages")
    try:
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise CvExtractionError("malformed_pdf", "The uploaded PDF could not be read") from exc
    return ExtractedCv(text=_usable_text(text, scanned_message=True), page_count=len(reader.pages))


def _extract_docx(data: bytes) -> ExtractedCv:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 200 or sum(info.file_size for info in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise CvExtractionError("unsafe_docx", "The DOCX file is too large to process safely")
            if any(info.filename.startswith(("/", "\\")) or ".." in Path(info.filename).parts for info in infos):
                raise CvExtractionError("unsafe_docx", "The DOCX file is not safe to process")
        document = Document(io.BytesIO(data))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    except CvExtractionError:
        raise
    except Exception as exc:
        raise CvExtractionError("malformed_docx", "The uploaded DOCX could not be read") from exc
    return ExtractedCv(text=_usable_text(text), page_count=None)


def _usable_text(text: str, scanned_message: bool = False) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) < 80:
        message = (
            "This CV appears to be scanned or image-based. Please upload a text-based PDF or DOCX."
            if scanned_message
            else "The CV does not contain enough readable text"
        )
        raise CvExtractionError("scanned_pdf" if scanned_message else "empty_cv", message)
    return normalized
