"""Provider-neutral 'how this event is written to a calendar'. Shared by ICS, CSV and adapters.

Half-day rule: a half day has a printed dismissal time but no known start. Without a
user-supplied school-day start it is written as an ALL-DAY event with the dismissal time in the
title (visible in month grids). With a user-supplied start it becomes a timed event and the
description says the start came from the user's profile. Nothing is assumed.
"""

from dataclasses import dataclass
from datetime import time

from app.schemas import CalendarEvent, DurationKind


class NotExportable(ValueError):
    pass


@dataclass(frozen=True)
class Shape:
    title: str
    description: str
    all_day: bool
    start_time: time | None
    end_time: time | None


def fmt12(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def shape_event(ev: CalendarEvent, day_start: time | None = None) -> Shape:
    notes = []
    if ev.category_label:
        notes.append(f"Category: {ev.category_label}")
    notes.append(f"Source: {ev.school_name} {ev.academic_year}, page {ev.source_region.page}")
    if ev.source_text:
        notes.append(f"Printed text: {ev.source_text}")
    title = ev.event_title

    if ev.duration_kind == DurationKind.ALL_DAY:
        return Shape(title, "\n".join(notes), True, None, None)
    if ev.duration_kind == DurationKind.HALF_DAY:
        if ev.end_time is None:
            raise NotExportable("half-day without dismissal time")
        if day_start is not None and day_start < ev.end_time:
            notes.append("Start time comes from your school schedule profile (user-supplied).")
            return Shape(title, "\n".join(notes), False, day_start, ev.end_time)
        notes.append(f"Early dismissal at {fmt12(ev.end_time)}; school start time not known.")
        return Shape(
            f"{title} (dismissal {fmt12(ev.end_time)})", "\n".join(notes), True, None, None
        )
    if ev.duration_kind == DurationKind.TIMED:
        if ev.start_time is None:
            raise NotExportable("timed event without start time")
        return Shape(title, "\n".join(notes), False, ev.start_time, ev.end_time)
    raise NotExportable("duration unknown")
