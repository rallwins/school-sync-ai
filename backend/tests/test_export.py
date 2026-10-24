from datetime import UTC, date, datetime, time

import pytest
from icalendar import Calendar

from app.providers.export_files import build_csv, build_ics
from app.providers.shape import NotExportable
from app.schemas import DurationKind
from tests.test_m3_helpers import by_date, ready_events

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def parse(data: bytes) -> dict[str, object]:
    cal = Calendar.from_ical(data)
    return {str(c["summary"]): c for c in cal.walk("VEVENT")}


@pytest.fixture(scope="module")
def events(calendar_pdf):
    return ready_events(calendar_pdf)


def test_ics_all_day_is_date_valued_with_exclusive_end(events):
    ev = parse(build_ics(events, now=NOW))["Labor Day"]
    assert ev["dtstart"].dt == date(2025, 9, 1) and type(ev["dtstart"].dt) is date
    assert ev["dtend"].dt == date(2025, 9, 2)


def test_ics_multi_day_closure_across_year_end_has_exclusive_end(events):
    ev = parse(build_ics(events, now=NOW))["Winter Break"]
    # two events share the title; the Dec block is the multi-day one
    blocks = [
        c
        for c in Calendar.from_ical(build_ics(events, now=NOW)).walk("VEVENT")
        if c["dtstart"].dt == date(2025, 12, 22)
    ]
    assert blocks[0]["dtend"].dt == date(2026, 1, 1)
    assert ev is not None


def test_half_day_without_profile_is_all_day_with_visible_dismissal(events):
    cal = parse(build_ics(events, now=NOW))
    ev = cal["Early Dismissal (dismissal 12:30 PM)"]
    assert type(ev["dtstart"].dt) is date  # not an assumed timed event
    assert "school start time not known" in str(ev["description"])


def test_half_day_with_user_profile_is_timed_with_tzid(events):
    data = build_ics(events, day_start=time(8, 0), now=NOW)
    ev = parse(data)["Early Dismissal"]
    assert ev["dtstart"].dt.hour == 8 and ev["dtend"].dt.hour == 12 and ev["dtend"].dt.minute == 30
    assert ev["dtstart"].dt.tzinfo.key == "America/Chicago"
    assert b"BEGIN:VTIMEZONE" in data and b"TZID:America/Chicago" in data
    assert "user-supplied" in str(ev["description"])


def test_uid_is_stable_across_revised_pdf_and_exports(events, calendar_pdf):
    a = {
        c["dtstart"].dt: str(c["uid"])
        for c in Calendar.from_ical(build_ics(events, now=NOW)).walk("VEVENT")
    }
    revised = ready_events(calendar_pdf, source_hash="different-hash")
    b = {
        c["dtstart"].dt: str(c["uid"])
        for c in Calendar.from_ical(build_ics(revised, now=NOW)).walk("VEVENT")
    }
    assert a == b and len(set(a.values())) == len(a)
    assert all(u.endswith("@schoolsync.local") for u in a.values())


def test_ics_carries_provenance(events):
    ev = parse(build_ics(events, now=NOW))["Labor Day"]
    assert ev["x-schoolsync-source-page"] == "1" and len(str(ev["x-schoolsync-fingerprint"])) == 32


def test_unknown_duration_and_timeless_half_day_are_not_exportable(events):
    unknown = by_date(events, "2025-09-01").model_copy(
        update={"duration_kind": DurationKind.UNKNOWN, "is_all_day": False}
    )
    with pytest.raises(NotExportable):
        build_ics([unknown])
    half = by_date(events, "2025-10-17").model_copy(update={"end_time": None})
    with pytest.raises(NotExportable):
        build_csv([half])


def test_csv_columns_and_all_day_flag(events):
    rows = build_csv(events).strip().split("\r\n")
    assert rows[0].startswith("Subject,Start Date,Start Time,End Date,End Time,All Day Event")
    assert len(rows) == 1 + len(events)
    labor = next(r for r in rows if r.startswith("Labor Day"))
    assert "09/01/2025" in labor and ",True," in labor


def test_csv_neutralises_formula_injection(events):
    evil = by_date(events, "2025-09-01").model_copy(update={"event_title": '=HYPERLINK("x")'})
    assert build_csv([evil]).splitlines()[1].startswith(
        "\"'=HYPERLINK"
    ) or "'=HYPERLINK" in build_csv([evil])
