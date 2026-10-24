"""Provider-neutral calendar interface. Provider-specific code never leaks into the core model.

Ownership: every event this app writes carries private properties (OWNER_PROP = stable id,
FP_PROP = fingerprint, BATCH_PROP = import batch). Update and delete are only legal on events
that carry OWNER_PROP; adapters must enforce that.
"""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Protocol

OWNER_PROP = "schoolsync_id"
FP_PROP = "schoolsync_fp"
BATCH_PROP = "schoolsync_batch"


class ProviderError(Exception):
    pass


class TransientError(ProviderError):
    """Timeout / 5xx: safe to retry after reconciling."""


class RateLimited(TransientError):
    def __init__(self, retry_after: float = 1.0):
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class NotOwned(ProviderError):
    """Attempt to modify an event this app did not create."""


class ProviderNotConfigured(ProviderError):
    pass


@dataclass
class ProviderEvent:
    id: str
    title: str
    start_date: date
    end_date: date  # inclusive
    all_day: bool
    start_time: time | None = None
    end_time: time | None = None
    timezone: str | None = None
    description: str = ""
    color_id: str | None = None  # provider colour id (Google colorId); None = calendar default
    private_props: dict[str, str] = field(default_factory=dict)

    @property
    def owned(self) -> bool:
        return OWNER_PROP in self.private_props


@dataclass
class CalendarInfo:
    id: str
    name: str


class CalendarProvider(Protocol):
    name: str

    def list_calendars(self) -> list[CalendarInfo]: ...
    def create_calendar(self, name: str, time_zone: str) -> CalendarInfo: ...
    def list_events(self, calendar_id: str, start: date, end: date) -> list[ProviderEvent]: ...
    def find_by_owner_id(self, calendar_id: str, stable_id: str) -> ProviderEvent | None: ...
    def create_event(self, calendar_id: str, ev: ProviderEvent) -> ProviderEvent: ...
    def update_event(self, calendar_id: str, event_id: str, ev: ProviderEvent) -> ProviderEvent: ...
    def delete_event(self, calendar_id: str, event_id: str) -> None: ...
