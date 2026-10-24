"""In-memory provider used for demos and tests. Nothing leaves the process.

Failure injection lets tests exercise retries, rate limits, pagination and the 'request
succeeded but response was lost' timeout case that causes duplicate creates in real systems.
"""

import itertools
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from app.providers.base import (
    OWNER_PROP,
    CalendarInfo,
    NotOwned,
    ProviderError,
    ProviderEvent,
    TransientError,
)


class MockProvider:
    name = "mock"

    def __init__(self, page_size: int = 50) -> None:
        self.calendars = {"demo": CalendarInfo("demo", "Demo calendar (in-memory)")}
        self.events: dict[str, dict[str, ProviderEvent]] = {"demo": {}}
        self.page_size = page_size
        self.pages_fetched = 0
        self.create_calls = 0
        self._ids = itertools.count(1)
        # hook(op, event) may raise TransientError; 'lost_response' ops run, then raise.
        self.fail_before: Callable[[str, ProviderEvent | None], None] | None = None
        self.lose_response_on_create: set[int] = set()  # 1-based create call numbers
        self.permanent_fail_titles: set[str] = set()

    def list_calendars(self) -> list[CalendarInfo]:
        return list(self.calendars.values())

    def create_calendar(self, name: str, time_zone: str) -> CalendarInfo:
        cid = f"cal-{next(self._ids)}"
        self.calendars[cid] = CalendarInfo(cid, name)
        self.events[cid] = {}
        return CalendarInfo(cid, name)

    def _cal(self, cid: str) -> dict[str, ProviderEvent]:
        if cid not in self.events:
            raise ProviderError(f"unknown calendar {cid}")
        return self.events[cid]

    def list_events(self, calendar_id: str, start: date, end: date) -> list[ProviderEvent]:
        out: list[ProviderEvent] = []
        items = [
            e
            for e in self._cal(calendar_id).values()
            if e.end_date >= start and e.start_date <= end
        ]
        # paginate like a real API; callers must see every page
        for i in range(0, len(items), self.page_size):
            self.pages_fetched += 1
            out.extend(replace(e) for e in items[i : i + self.page_size])
        return out

    def find_by_owner_id(self, calendar_id: str, stable_id: str) -> ProviderEvent | None:
        for e in self._cal(calendar_id).values():
            if e.private_props.get(OWNER_PROP) == stable_id:
                return replace(e)
        return None

    def create_event(self, calendar_id: str, ev: ProviderEvent) -> ProviderEvent:
        self.create_calls += 1
        n = self.create_calls
        if self.fail_before:
            self.fail_before("create", ev)
        if ev.title in self.permanent_fail_titles:
            raise ProviderError("400 bad request (permanent)")
        stored = replace(ev, id=f"mock-{next(self._ids)}")
        self._cal(calendar_id)[stored.id] = stored
        if n in self.lose_response_on_create:
            raise TransientError("timeout after server accepted the request")
        return replace(stored)

    def update_event(self, calendar_id: str, event_id: str, ev: ProviderEvent) -> ProviderEvent:
        cur = self._cal(calendar_id).get(event_id)
        if cur is None:
            raise ProviderError("not found")
        if not cur.owned:
            raise NotOwned(f"event {event_id} was not created by SchoolSync")
        if self.fail_before:
            self.fail_before("update", ev)
        stored = replace(ev, id=event_id)
        self._cal(calendar_id)[event_id] = stored
        return replace(stored)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        cur = self._cal(calendar_id).get(event_id)
        if cur is None:
            return
        if not cur.owned:
            raise NotOwned(f"event {event_id} was not created by SchoolSync")
        del self._cal(calendar_id)[event_id]
