"""Google Calendar API v3 adapter (CalendarProvider).

STATUS: implemented and unit-tested against a mocked HTTP transport only. It has never been run
against the real Google API.

Ownership: events we write carry extendedProperties.private (OWNER_PROP etc.). Update and
delete first GET the event and refuse (NotOwned) unless it carries OWNER_PROP, so an unrelated
event can never be changed even if its id is passed in by mistake.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx

from app.providers.base import (
    OWNER_PROP,
    CalendarInfo,
    NotOwned,
    ProviderError,
    ProviderEvent,
    ProviderNotConfigured,
    RateLimited,
    TransientError,
)

BASE = "https://www.googleapis.com/calendar/v3"


def _check(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code == 429 or (r.status_code == 403 and "rateLimit" in r.text):
        raise RateLimited(float(r.headers.get("Retry-After", "1")))
    if r.status_code >= 500:
        raise TransientError(f"Google API HTTP {r.status_code}")
    if r.status_code in (401, 403):
        raise ProviderError(f"Google API denied the request (HTTP {r.status_code}); reconnect.")
    raise ProviderError(f"Google API HTTP {r.status_code}")


def to_google(ev: ProviderEvent) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": ev.title,
        "description": ev.description,
        "extendedProperties": {"private": dict(ev.private_props)},
    }
    if ev.all_day:
        body["start"] = {"date": ev.start_date.isoformat()}
        body["end"] = {"date": (ev.end_date + timedelta(days=1)).isoformat()}  # exclusive
    else:
        assert ev.start_time is not None and ev.timezone
        start = datetime.combine(ev.start_date, ev.start_time)
        # Google requires an end; with none known we use a zero-length event, not an invented one.
        end = datetime.combine(ev.end_date, ev.end_time) if ev.end_time else start
        body["start"] = {"dateTime": start.isoformat(), "timeZone": ev.timezone}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": ev.timezone}
    return body


def from_google(item: dict[str, Any]) -> ProviderEvent:
    s, e = item["start"], item["end"]
    props = (item.get("extendedProperties") or {}).get("private") or {}
    if "date" in s:
        return ProviderEvent(
            id=item["id"], title=item.get("summary", ""),
            start_date=date.fromisoformat(s["date"]),
            end_date=date.fromisoformat(e["date"]) - timedelta(days=1),
            all_day=True, description=item.get("description", ""), private_props=dict(props),
        )  # fmt: skip
    sd, ed = datetime.fromisoformat(s["dateTime"]), datetime.fromisoformat(e["dateTime"])
    return ProviderEvent(
        id=item["id"], title=item.get("summary", ""), start_date=sd.date(), end_date=ed.date(),
        all_day=False, start_time=time(sd.hour, sd.minute),
        end_time=None if ed == sd else time(ed.hour, ed.minute),
        timezone=s.get("timeZone"), description=item.get("description", ""),
        private_props=dict(props),
    )  # fmt: skip


class GoogleCalendarProvider:
    name = "google"

    def __init__(
        self,
        http: httpx.Client,
        token: Callable[[], str],
        ready: Callable[[], bool] = lambda: True,
    ) -> None:
        self.http, self._token, self._ready = http, token, ready

    @property
    def ready(self) -> bool:
        return self._ready()

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        if not self.ready:
            raise ProviderNotConfigured("Google is not connected.")
        try:
            r = self.http.request(
                method, BASE + path, headers={"Authorization": f"Bearer {self._token()}"},
                timeout=15, **kw,
            )  # fmt: skip
        except httpx.TimeoutException as e:
            raise TransientError("Google API timeout") from e
        except httpx.HTTPError as e:
            raise TransientError("Google API network error") from e
        _check(r)
        return r

    def _paged(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(100):  # hard bound on pages
            q = dict(params, **({"pageToken": token} if token else {}))
            data = self._req("GET", path, params=q).json()
            items += data.get("items", [])
            token = data.get("nextPageToken")
            if not token:
                return items
        raise ProviderError("Too many result pages; refusing to continue.")

    def list_calendars(self) -> list[CalendarInfo]:
        rows = self._paged(
            "/users/me/calendarList", {"minAccessRole": "writer", "maxResults": "250"}
        )
        return [CalendarInfo(r["id"], r.get("summary", r["id"])) for r in rows]

    def list_events(self, calendar_id: str, start: date, end: date) -> list[ProviderEvent]:
        rows = self._paged(
            f"/calendars/{calendar_id}/events",
            {
                "timeMin": f"{start.isoformat()}T00:00:00Z",
                "timeMax": f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z",
                "singleEvents": "true",
                "maxResults": "250",
            },
        )
        return [from_google(r) for r in rows if "start" in r and "end" in r]

    def find_by_owner_id(self, calendar_id: str, stable_id: str) -> ProviderEvent | None:
        rows = self._paged(
            f"/calendars/{calendar_id}/events",
            {"privateExtendedProperty": f"{OWNER_PROP}={stable_id}", "maxResults": "5"},
        )
        return from_google(rows[0]) if rows else None

    def create_event(self, calendar_id: str, ev: ProviderEvent) -> ProviderEvent:
        return from_google(
            self._req("POST", f"/calendars/{calendar_id}/events", json=to_google(ev)).json()
        )

    def _owned(self, calendar_id: str, event_id: str) -> None:
        cur = from_google(self._req("GET", f"/calendars/{calendar_id}/events/{event_id}").json())
        if not cur.owned:
            raise NotOwned(f"event {event_id} was not created by SchoolSync")

    def update_event(self, calendar_id: str, event_id: str, ev: ProviderEvent) -> ProviderEvent:
        self._owned(calendar_id, event_id)
        r = self._req("PUT", f"/calendars/{calendar_id}/events/{event_id}", json=to_google(ev))
        return from_google(r.json())

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._owned(calendar_id, event_id)
        self._req("DELETE", f"/calendars/{calendar_id}/events/{event_id}")
