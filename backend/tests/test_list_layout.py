"""List-style calendars (two months per page, events in a side list). Written before the
implementation, against fixture C, whose structure mirrors a real calendar that failed."""

import json
import runpy
from datetime import date

import pytest

from app.extraction.pipeline import ImportContext, extract_events
from app.pdf.layout import extract_layout
from app.schemas import DurationKind as K
from app.schemas import ValidationStatus as S
from tests.conftest import SYN

CTX = ImportContext("Cedar Hill School", "2025-2026", "Asia/Kolkata", "c")


@pytest.fixture(scope="module")
def result():
    runpy.run_path(str(SYN / "generate_fixture_c.py"), run_name="__main__")
    return extract_events(extract_layout((SYN / "cedar_hill_2025_26.pdf").read_bytes(), "hc"), CTX)


@pytest.fixture(scope="module")
def truth():
    return json.loads((SYN / "cedar_hill_2025_26.truth.json").read_text())


def at(result, d, title=None):
    return next(
        e
        for e in result.events
        if e.start_date == date.fromisoformat(d) and (title is None or e.event_title == title)
    )


def test_pages_and_legend(result):
    assert result.pages_processed == [2, 3] and result.pages_skipped == [1]  # cover skipped
    assert [e.label for e in result.legend] == [
        "Student Days", "Public Holidays", "School Opening & Reopening Days", "Important Days"]  # fmt: skip


def test_every_truth_event_found_exactly(result, truth):
    got = {(e.event_title, e.start_date.isoformat(), e.end_date.isoformat()) for e in result.events}
    want = {(t["title"], t["start"], t["end"]) for t in truth["events"]}
    assert got == want and len(result.events) == len(truth["events"]) == 13


def test_kind_status_category_match_truth(result, truth):
    for t in truth["events"]:
        e = at(result, t["start"], t["title"])
        assert (e.duration_kind.value, e.validation_status.value, e.category_label) == (
            t["duration_kind"], t["status"], t["category"]), t["title"]  # fmt: skip
        assert e.source_region.page == t["page"]


def test_year_resolved_across_year_boundary(result):
    assert at(result, "2026-01-05").event_title == "School Reopens for Learners"
    assert at(result, "2025-12-25").event_title == "Christmas"


def test_pair_and_range_dates(result):
    assert at(result, "2025-09-18").end_date == date(2025, 9, 19)  # "Sep 18 | 19"
    assert at(result, "2025-09-08").end_date == date(2025, 9, 12)  # "Sep 8-12"


def test_wrapped_holiday_title_is_joined(result):
    assert at(result, "2025-10-20").event_title == "Diwali Festival of Lights Holiday"


def test_timed_event_from_list_text(result):
    e = at(result, "2025-09-26")
    assert (
        e.duration_kind == K.TIMED
        and str(e.start_time) == "16:30:00"
        and e.event_title == "Open House"
    )


def test_notes_box_and_legend_text_do_not_become_events(result):
    titles = " ".join(e.event_title for e in result.events)
    for junk in ("Academic Year", "Semesters", "Note", "Student Days", "Jun 16"):
        assert junk not in titles


def test_colour_only_all_day_is_inferred_not_confirmed(result):
    e = at(result, "2025-09-01")
    assert e.duration_kind == K.ALL_DAY and e.validation_status == S.INFERRED
    assert any(w.code == "kind_from_colour_only" for w in e.warnings)


def test_unknown_duration_events_need_review_not_silently_all_day(result):
    e = at(result, "2025-10-27")
    assert e.duration_kind == K.UNKNOWN and e.validation_status == S.NEEDS_REVIEW
    assert any(w.code == "duration_unknown" and w.critical for w in e.warnings)


def test_every_event_has_evidence(result):
    for e in result.events:
        r = e.source_region
        assert (
            r.page in (2, 3)
            and r.x1 > r.x0
            and r.y1 > r.y0
            and r.cell_label == e.start_date.isoformat()
        )
        assert e.extraction_method == "vector_pdf_list_layout"


def test_audience_columns_not_read_is_disclosed(result):
    assert any("audience" in w.lower() for w in result.warnings)


def test_no_event_for_date_missing_from_grid():
    from app.grid_detection.list_layout import parse_date_prefix

    assert parse_date_prefix(["Sep", "31", "Ghost"]) is None  # September has 30 days
    assert parse_date_prefix(["Jun", "16-Oct", "31"]) is None  # semester range text
    assert parse_date_prefix(["Jun", "27", "|", "28", "Parents"]) == (6, 27, 28, ["Parents"])
    assert parse_date_prefix(["Jun", "2-13", "PD"]) == (6, 2, 13, ["PD"])
