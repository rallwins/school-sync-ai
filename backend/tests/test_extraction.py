from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.color_mapping.lab import delta_e, match_color
from app.extraction.pipeline import ImportContext, extract_events
from app.grid_detection.grid import detect_cells
from app.legend.parse import parse_legend
from app.pdf.layout import extract_layout
from app.schemas import DurationKind as K
from app.schemas import ValidationStatus as S
from app.validation.classify import classify

CTX = ImportContext("Maple Grove Academy", "2025-2026", "America/Chicago", "doc1")


@pytest.fixture(scope="module")
def layout(calendar_pdf):
    return extract_layout(calendar_pdf, "hash")


@pytest.fixture(scope="module")
def result(layout):
    return extract_events(layout, CTX)


def by_start(result, d):
    return next(e for e in result.events if e.start_date == date.fromisoformat(d))


# ---- grid / dates ----
def test_grid_dates_and_adjacent_month(layout):
    year, month, cells = detect_cells(layout.pages[0])  # Sep 2025, Sunday-first
    assert (year, month) == (2025, 9)
    assert all(c.day_number_ok for c in cells)
    by = {c.day: c for c in cells}
    assert by[date(2025, 9, 1)].in_month and by[date(2025, 9, 1)].day.weekday() == 0
    assert not by[date(2025, 8, 31)].in_month  # adjacent-month cell
    assert not by[date(2025, 10, 4)].in_month


def test_year_boundary_page(layout):
    year, month, cells = detect_cells(layout.pages[3])  # Jan 2026
    assert (year, month) == (2026, 1)
    assert date(2025, 12, 28) in {c.day for c in cells if not c.in_month}


# ---- legend / colour ----
def test_legend_parsed_with_labels(result, truth):
    got = {e.label: e.rgb for e in result.legend}
    for v in truth["legend"].values():
        assert got[v["label"]] == tuple(v["rgb255"])


def test_color_match_tolerates_scan_drift(result):
    holiday = next(e for e in result.legend if e.label.startswith("Holiday"))
    drifted = tuple(min(255, c + 9) for c in holiday.rgb)
    m = match_color(drifted, result.legend)  # type: ignore[arg-type]
    assert m.entry == holiday and m.delta_e is not None and m.delta_e > 0


def test_unlisted_color_does_not_match(result):
    assert match_color((224, 195, 240), result.legend).entry is None


def test_delta_e_basic():
    assert delta_e((255, 255, 255), (255, 255, 255)) == 0
    assert delta_e((0, 0, 0), (255, 255, 255)) == pytest.approx(100, abs=0.5)


# ---- events vs fixture truth ----
def test_event_count_and_pages(result):
    assert result.pages_processed == [1, 2, 3, 4] and not result.pages_skipped
    assert len(result.events) == 8


def test_all_day_holiday(result):
    e = by_start(result, "2025-09-01")
    assert (e.event_title, e.duration_kind, e.is_all_day) == ("Labor Day", K.ALL_DAY, True)
    assert e.validation_status == S.CONFIRMED and e.source_region.page == 1


def test_early_dismissal_keeps_printed_time(result):
    e = by_start(result, "2025-09-26")
    assert e.duration_kind == K.HALF_DAY and e.end_time == time(12, 30)
    assert e.start_time is None and not e.is_all_day


def test_half_day_without_time_not_assumed(result):
    e = by_start(result, "2025-10-17")
    assert e.duration_kind == K.HALF_DAY and e.end_time is None and e.start_time is None
    assert e.validation_status == S.NEEDS_REVIEW
    assert any(w.code == "half_day_time_unknown" and w.critical for w in e.warnings)


def test_legend_alone_defines_work_day_as_closure(result):
    e = by_start(result, "2025-10-13")
    assert e.duration_kind == K.ALL_DAY and e.category_label.startswith("Teacher Work Day")


def test_unlisted_colour_without_text_is_ambiguous_not_invented(result):
    e = by_start(result, "2025-10-31")
    assert e.validation_status == S.AMBIGUOUS and e.duration_kind == K.UNKNOWN
    assert e.category_id is None and "untitled" in e.event_title
    assert any(w.critical for w in e.warnings)


def test_multi_day_block_merged(result):
    e = by_start(result, "2025-12-22")
    assert e.end_date == date(2025, 12, 31) and e.event_title == "Winter Break"


def test_every_event_has_evidence_and_fingerprint(result):
    for e in result.events:
        r = e.source_region
        assert r.page >= 1 and r.x1 > r.x0 and r.cell_label
        assert len(e.normalized_fingerprint) == 32


def test_extraction_is_stable_across_runs(layout):
    a = [e.normalized_fingerprint for e in extract_events(layout, CTX).events]
    b = [e.normalized_fingerprint for e in extract_events(layout, CTX).events]
    assert a == b and len(set(a)) == len(a)


# ---- classifier rules ----
def test_text_vs_legend_conflict_is_ambiguous():
    c = classify("Half Day", "Holiday / No School", color_present=True, color_matched=True)
    assert c.status == S.AMBIGUOUS and c.kind == K.UNKNOWN
    assert c.warnings[0].code == "legend_text_conflict"


def test_color_only_never_becomes_all_day_silently():
    c = classify("Spirit Night", None, color_present=False, color_matched=False)
    assert c.kind == K.UNKNOWN and c.status == S.NEEDS_REVIEW


def test_explicit_timed_event():
    c = classify("Open House 6:00 PM", None, color_present=False, color_matched=False)
    assert c.kind == K.TIMED and c.start_time == time(18, 0) and c.title == "Open House"


def test_invalid_timezone_rejected(layout):
    with pytest.raises(Exception):  # noqa: B017
        extract_events(layout, ImportContext("s", "y", "Mars/Olympus", "d"))


def test_extract_endpoint(calendar_pdf):
    c = TestClient(app)
    r = c.post(
        "/api/uploads/extract",
        files={"file": ("c.pdf", calendar_pdf)},
        data={
            "school_name": "Maple Grove Academy",
            "academic_year": "2025-2026",
            "timezone": "America/Chicago",
        },
    )
    assert r.status_code == 200 and len(r.json()["events"]) == 8
    bad = c.post(
        "/api/uploads/extract",
        files={"file": ("c.pdf", calendar_pdf)},
        data={"school_name": "x", "academic_year": "y", "timezone": "Nope/Zone"},
    )
    assert bad.status_code == 422


def test_legend_parse_standalone(layout):
    assert len(parse_legend(layout)) == 4
