import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.extraction.school_name import (
    _candidate,
    collapse_letter_spaced,
    detect_school_name,
)
from app.imports.store import Store
from app.pdf.layout import extract_layout
from app.providers.mock import MockProvider


def client() -> TestClient:
    return TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))


# ---- the parser ----
def test_detects_name_from_each_fixture(calendar_pdf):
    assert detect_school_name(extract_layout(calendar_pdf, "h")).name == "Maple Grove Academy"
    from tests.conftest import SYN

    for pdf, want in (
        ("riverbend_2027_28.pdf", "Riverbend Elementary"),
        ("cedar_hill_2025_26.pdf", "Cedar Hill School"),
    ):
        import runpy

        runpy.run_path(
            str(SYN / ("generate_fixture_b.py" if "river" in pdf else "generate_fixture_c.py")),
            run_name="__main__",
        )
        assert detect_school_name(extract_layout((SYN / pdf).read_bytes(), "h")).name == want


def test_letter_spaced_name_is_collapsed_and_keyword_split():
    toks, changed = collapse_letter_spaced(list("CONTINUUMSCHOOL"))
    assert changed and toks == ["CONTINUUM", "SCHOOL"]
    assert _candidate(list("CONTINUUMSCHOOL")) == ("Continuum School", True)


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Maple Grove Academy - September 2025", "Maple Grove Academy"),
        ("Riverbend Elementary February 2028", "Riverbend Elementary"),
        ("ST. MARY'S HIGH SCHOOL", "St. Mary's High School"),
        ("University of Springfield", "University of Springfield"),
    ],
)
def test_accepts_plausible_names(line, expected):
    assert _candidate(line.split())[0] == expected


@pytest.mark.parametrize(
    "line",
    [
        "School Closes for Learners",  # event text: keyword does not end the line
        "Jan 5 School Reopens for Learners",  # digits
        "ACADEMIC YEAR 2025-2026 | FAMILY CALENDAR",
        "School",  # keyword alone
        "Annual Calendar 2025 - 2026",
        "School Closes for Learners (EY3 - G5) School",  # digits
    ],
)
def test_rejects_event_rows_and_headers(line):
    assert _candidate(line.split()) is None


# ---- the API ----
def test_blank_school_name_is_detected_and_reported(calendar_pdf):
    r = client().post(
        "/api/uploads/extract",
        files={"file": ("c.pdf", calendar_pdf)},
        data={"academic_year": "2025-2026", "timezone": "Asia/Kolkata"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["school_name"] == "Maple Grove Academy" and d["school_name_source"].startswith(
        "detected from"
    )
    assert all(e["school_name"] == "Maple Grove Academy" for e in d["events"])


def test_typed_school_name_wins_over_detection(calendar_pdf):
    d = (
        client()
        .post(
            "/api/uploads/extract",
            files={"file": ("c.pdf", calendar_pdf)},
            data={
                "school_name": "My Own Name",
                "academic_year": "2025-2026",
                "timezone": "Asia/Kolkata",
            },
        )
        .json()
    )
    assert d["school_name"] == "My Own Name" and d["school_name_source"] == "you entered it"


def test_undetectable_name_asks_the_user_instead_of_guessing():
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 700, "Some calendar with no school name")
    c.save()
    r = client().post(
        "/api/uploads/extract",
        files={"file": ("c.pdf", buf.getvalue())},
        data={"academic_year": "2025-2026", "timezone": "Asia/Kolkata"},
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "school_name_required"
