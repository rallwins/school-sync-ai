import pymupdf
from fastapi.testclient import TestClient

from app.api.main import app
from app.pdf.layout import extract_layout

client = TestClient(app)


def test_layout_has_text_and_legend_swatches(calendar_pdf, truth):
    layout = extract_layout(calendar_pdf, "h")
    assert layout.page_count == 4 and not layout.warnings
    p1 = layout.pages[0]
    assert p1.has_text_layer
    words = {s.text for s in p1.spans}
    assert {"Labor", "Day", "September", "2025", "Early", "Dismissal"} <= words
    # every legend colour appears as a vector fill on every page
    legend_rgbs = {tuple(v["rgb255"]) for v in truth["legend"].values()}
    for page in layout.pages:
        fills = {f.rgb for f in page.fills}
        assert legend_rgbs <= fills


def test_cell_fill_is_found_under_its_text(calendar_pdf, truth):
    """Sep 1 'Labor' text must sit inside a fill matching the holiday legend colour."""
    p1 = extract_layout(calendar_pdf, "h").pages[0]
    holiday = tuple(truth["legend"]["holiday"]["rgb255"])
    labor = next(s for s in p1.spans if s.text == "Labor")
    cx, cy = (labor.x0 + labor.x1) / 2, (labor.y0 + labor.y1) / 2
    containing = [
        f for f in p1.fills if f.x0 <= cx <= f.x1 and f.y0 <= cy <= f.y1 and f.rgb == holiday
    ]
    assert containing


def test_scanned_page_is_flagged_not_silently_empty():
    doc = pymupdf.open()
    doc.new_page()
    layout = extract_layout(doc.tobytes(), "h")
    assert not layout.pages[0].has_text_layer
    assert "OCR required" in layout.warnings[0]


def test_fixture_is_deterministic(calendar_pdf):
    import runpy

    from tests.conftest import SYN

    runpy.run_path(str(SYN / "generate_fixtures.py"), run_name="__main__")
    assert (SYN / "maple_grove_2025_26.pdf").read_bytes() == calendar_pdf


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_ok(calendar_pdf):
    r = client.post("/api/uploads/layout", files={"file": ("c.pdf", calendar_pdf)})
    assert r.status_code == 200
    assert r.json()["page_count"] == 4


def test_upload_rejects_non_pdf():
    r = client.post("/api/uploads/layout", files={"file": ("x.pdf", b"hello")})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_pdf"


def test_upload_rejects_oversize(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 50)
    # app captured settings at creation, so build a fresh app against the patched singleton
    from app.api.main import create_app

    c = TestClient(create_app())
    r = c.post("/api/uploads/layout", files={"file": ("x.pdf", b"%PDF-" + b"0" * 500)})
    assert r.status_code == 413
