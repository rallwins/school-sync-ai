"""Generalisation checks on a structurally different fixture (Monday-first, leap year, drifted
colours, different legend wording). Written BEFORE running the extractor on it."""

import json
import runpy
from datetime import date, time

import pytest

from app.extraction.pipeline import ImportContext, extract_events
from app.grid_detection.grid import detect_cells
from app.pdf.layout import extract_layout
from app.schemas import DurationKind as K
from app.schemas import ValidationStatus as S
from tests.conftest import SYN


@pytest.fixture(scope="module")
def layout():
    runpy.run_path(str(SYN / "generate_fixture_b.py"), run_name="__main__")
    return extract_layout((SYN / "riverbend_2027_28.pdf").read_bytes(), "hb")


@pytest.fixture(scope="module")
def result(layout):
    return extract_events(
        layout, ImportContext("Riverbend Elementary", "2027-2028", "America/New_York", "b")
    )


def at(result, d):
    return next(e for e in result.events if e.start_date == date.fromisoformat(d))


def test_monday_first_leap_february_grid(layout):
    year, month, cells = detect_cells(layout.pages[0])
    assert (year, month) == (2028, 2)
    assert all(c.day_number_ok for c in cells)
    by = {c.day: c for c in cells}
    assert by[date(2028, 2, 29)].in_month and by[date(2028, 2, 29)].day.weekday() == 1  # Tuesday
    assert not by[date(2028, 1, 31)].in_month


def test_legend_with_different_wording(result):
    assert {e.label for e in result.legend} == {
        "Early Release Day",
        "Closed - No Classes",
        "Vacation / Recess",
    }


def test_leap_day_closure_with_drifted_colour_matches_legend(result):
    e = at(result, "2028-02-29")
    assert e.duration_kind == K.ALL_DAY and e.category_label == "Closed - No Classes"
    assert e.sampled_color != e.matched_legend_color  # drift was real, and tolerated
    assert e.validation_status == S.CONFIRMED


def test_early_release_phrase_and_time(result):
    e = at(result, "2028-03-10")
    assert e.duration_kind == K.HALF_DAY and e.end_time == time(13, 15)
    assert e.event_title == "Early Release"


def test_untinted_timed_event(result):
    e = at(result, "2028-03-14")
    assert e.duration_kind == K.TIMED and e.start_time == time(16, 0) and e.end_time is None
    assert e.event_title == "Parent Conferences" and e.sampled_color is None


def test_text_legend_conflict_is_flagged(result):
    e = at(result, "2028-03-21")
    assert e.validation_status == S.AMBIGUOUS and e.duration_kind == K.UNKNOWN
    assert any(w.code == "legend_text_conflict" for w in e.warnings)


def test_recess_block_merged_across_week_boundary(result):
    e = at(result, "2028-03-27")
    assert e.end_date == date(2028, 3, 31) and e.duration_kind == K.ALL_DAY


def test_exactly_five_events_no_extras(result):
    truth = json.loads((SYN / "riverbend_2027_28.truth.json").read_text())
    assert len(result.events) == len(truth["events"]) == 5
