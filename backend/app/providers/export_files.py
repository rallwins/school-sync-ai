"""File-export adapter: RFC 5545 ICS (via icalendar) and CSV.

ICS: all-day events use VALUE=DATE with an exclusive DTEND; timed events carry TZID. A timed
event with no end time gets DTSTART only (no invented duration). UIDs derive from the stable
event id, so re-importing a revised file lets clients that honour UID update in place. Clients
differ in how they treat repeat imports; this does not guarantee duplicate prevention.
"""

import csv
import io
from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from app.deduplication.identity import compute_fingerprint, stable_ids
from app.providers.shape import fmt12, shape_event
from app.schemas import CalendarEvent

UID_DOMAIN = "schoolsync.local"


def build_ics(
    events: Iterable[CalendarEvent],
    *,
    day_start: time | None = None,
    now: datetime | None = None,
) -> bytes:
    evs = list(events)
    sids = stable_ids(evs)
    stamp = now or datetime.now(UTC)
    cal = Calendar()
    cal.add("prodid", "-//SchoolSync AI//Calendar Export//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    for ev in evs:
        s = shape_event(ev, day_start)
        ie = Event()
        ie.add("uid", f"{sids[ev.event_id_internal]}@{UID_DOMAIN}")
        ie.add("dtstamp", stamp)
        ie.add("summary", s.title)
        ie.add("description", s.description)
        if s.all_day:
            ie.add("dtstart", ev.start_date)
            ie.add("dtend", ev.end_date + timedelta(days=1))
        else:
            tz = ZoneInfo(ev.timezone)
            assert s.start_time is not None
            ie.add("dtstart", datetime.combine(ev.start_date, s.start_time, tzinfo=tz))
            if s.end_time is not None:
                ie.add("dtend", datetime.combine(ev.end_date, s.end_time, tzinfo=tz))
        ie.add("x-schoolsync-fingerprint", compute_fingerprint(ev))
        ie.add("x-schoolsync-source-hash", ev.source_hash)
        ie.add("x-schoolsync-source-page", str(ev.source_region.page))
        cal.add_component(ie)
    cal.add_missing_timezones()
    return bytes(cal.to_ical())


def _safe(cell: str) -> str:
    """Neutralise spreadsheet formula injection (cells starting with = + - @ tab CR)."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@", "\t", "\r") else cell


def build_csv(events: Iterable[CalendarEvent], *, day_start: time | None = None) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(
        ["Subject", "Start Date", "Start Time", "End Date", "End Time",
         "All Day Event", "Description", "Location", "Private"]
    )  # fmt: skip
    for ev in events:
        s = shape_event(ev, day_start)
        w.writerow(
            [
                _safe(s.title),
                ev.start_date.strftime("%m/%d/%Y"),
                "" if s.all_day or not s.start_time else fmt12(s.start_time),
                ev.end_date.strftime("%m/%d/%Y"),
                "" if s.all_day or not s.end_time else fmt12(s.end_time),
                "True" if s.all_day else "False",
                _safe(s.description),
                "",
                "False",
            ]
        )
    return out.getvalue()
