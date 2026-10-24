"""Treat uploads as untrusted: size, magic bytes, parseability, page limits."""

import hashlib
from dataclasses import dataclass

import pymupdf


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedPdf:
    data: bytes
    sha256: str
    page_count: int


def validate_pdf(data: bytes, *, max_bytes: int, max_pages: int) -> ValidatedPdf:
    if not data:
        raise UploadRejected("empty", "File is empty.")
    if len(data) > max_bytes:
        raise UploadRejected("too_large", f"File exceeds {max_bytes} bytes.")
    if not data.startswith(b"%PDF-"):
        raise UploadRejected("not_pdf", "File does not look like a PDF (bad magic bytes).")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # any parser failure is a rejection
        raise UploadRejected("malformed", "PDF could not be parsed.") from exc
    try:
        if doc.needs_pass:
            raise UploadRejected("encrypted", "Encrypted PDFs are not supported.")
        if doc.page_count < 1:
            raise UploadRejected("no_pages", "PDF has no pages.")
        if doc.page_count > max_pages:
            raise UploadRejected("too_many_pages", f"PDF has more than {max_pages} pages.")
        return ValidatedPdf(data, hashlib.sha256(data).hexdigest(), doc.page_count)
    finally:
        doc.close()
