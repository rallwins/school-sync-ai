import pymupdf
import pytest

from app.ingestion.validate import UploadRejected, validate_pdf

LIMITS = {"max_bytes": 1_000_000, "max_pages": 10}


def test_valid_pdf_accepted_and_hashed(calendar_pdf):
    v = validate_pdf(calendar_pdf, **LIMITS)
    assert v.page_count == 4
    assert len(v.sha256) == 64
    assert v.sha256 == validate_pdf(calendar_pdf, **LIMITS).sha256


@pytest.mark.parametrize(
    "data,code",
    [
        (b"", "empty"),
        (b"GIF89a not a pdf", "not_pdf"),
        (b"%PDF-1.7\ngarbage that is not a real pdf", "malformed"),
    ],
)
def test_rejects_bad_input(data, code):
    with pytest.raises(UploadRejected) as e:
        validate_pdf(data, **LIMITS)
    assert e.value.code == code


def test_rejects_oversize(calendar_pdf):
    with pytest.raises(UploadRejected) as e:
        validate_pdf(calendar_pdf, max_bytes=100, max_pages=10)
    assert e.value.code == "too_large"


def test_rejects_too_many_pages(calendar_pdf):
    with pytest.raises(UploadRejected) as e:
        validate_pdf(calendar_pdf, max_bytes=1_000_000, max_pages=2)
    assert e.value.code == "too_many_pages"


def test_rejects_encrypted():
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(UploadRejected) as e:
        validate_pdf(data, **LIMITS)
    assert e.value.code == "encrypted"
