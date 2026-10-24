"""Server-side mirror of the UI readiness rule. The server never trusts the client's idea of
'ready': export and sync re-check every event."""

from app.schemas import CalendarEvent, DurationKind, ValidationStatus


def confirm_blockers(e: CalendarEvent) -> list[str]:
    out: list[str] = []
    t = e.event_title.strip().lower()
    if not t or "untitled" in t:
        out.append("title missing")
    if e.duration_kind == DurationKind.UNKNOWN:
        out.append("duration unknown")
    if e.duration_kind == DurationKind.HALF_DAY and e.end_time is None:
        out.append("half-day dismissal time missing")
    if e.duration_kind == DurationKind.TIMED and e.start_time is None:
        out.append("start time missing")
    return out


def is_ready(e: CalendarEvent) -> bool:
    if confirm_blockers(e):
        return False
    if e.user_confirmed:
        return True
    clean = e.validation_status in (ValidationStatus.CONFIRMED, ValidationStatus.INFERRED)
    return clean and not any(w.critical for w in e.warnings)
