"""Shared builders for Milestone 3 tests."""

from datetime import date, time

from app.extraction.pipeline import ImportContext, extract_events
from app.pdf.layout import extract_layout
from app.schemas import CalendarEvent, DurationKind


def ready_events(pdf: bytes, source_hash: str = "h1") -> list[CalendarEvent]:
    """Fixture events with the two ambiguous ones resolved the way a user would."""
    res = extract_events(
        extract_layout(pdf, source_hash),
        ImportContext("Maple Grove Academy", "2025-2026", "America/Chicago", "doc"),
    )
    out = []
    for e in res.events:
        if e.start_date == date(2025, 10, 17):  # half day, user supplies dismissal
            e = e.model_copy(update={"end_time": time(11, 45), "user_confirmed": True})
        elif e.start_date == date(2025, 10, 31):  # unlisted colour; user decides
            e = e.model_copy(
                update={
                    "event_title": "Staff Development Day",
                    "duration_kind": DurationKind.ALL_DAY,
                    "is_all_day": True,
                    "user_confirmed": True,
                }
            )
        out.append(e)
    return out


def by_date(events: list[CalendarEvent], d: str) -> CalendarEvent:
    return next(e for e in events if e.start_date == date.fromisoformat(d))
