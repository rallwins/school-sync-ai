# ADR 0002: Canonical event schema, all-day and timezone semantics

Status: accepted.

**Decision.**
- `CalendarEvent` (Pydantic v2, `backend/app/schemas.py`) is the single model; providers map to it.
- All-day events are **date-valued** (`start_date`, inclusive `end_date`), never midnight
  timestamps, so they cannot shift across timezones. ICS and Google use an exclusive end date at the
  edge (`end + 1 day`); the conversion lives in the export/adapter layer only.
- Timed events carry an IANA timezone (validated with `zoneinfo`) and are serialised with TZID
  (ICS) or `timeZone` (Google). An event with no known end time is written without an invented
  duration (ICS: DTSTART only; Google: zero-length).
- A half day has `duration_kind=half_day` and a printed dismissal time as `end_time`; the start is
  unknown. Without a user-supplied school start it exports as an all-day event with the dismissal
  time in the title; with one it becomes timed and the description says the start is user-supplied.
- `unknown` duration and time-less half days cannot be exported or synced until a person resolves
  them. The server re-checks this (`validation/readiness.py`); the UI check is a convenience.
- Weekday/date mismatches are reported, never "fixed" by moving a date.

**Consequences.** A multi-day block that spans a page break (e.g. Dec 22–31 plus Jan 1) is two
events from extraction; merging them is a review-time action, not automatic.
