# ADR 0004: Provider adapter abstraction

Status: accepted. Google adapter implemented against mocked HTTP only; Microsoft not implemented.

**Decision.** `CalendarProvider` (`providers/base.py`) is a small protocol: list calendars, list
events in a range, find by owner id, create, update, delete. The core model and planner never see
provider JSON. Adapters: file export (`export_files.py`, pure functions), in-memory mock (tests and
demo), Google (`google.py`), Microsoft (`stubs.py`, reports "not configured"). Shared provider-neutral
rendering lives in `providers/shape.py` so ICS, CSV and adapters make the same half-day decision.

Errors are normalised to `TransientError`, `RateLimited(retry_after)`, `NotOwned`,
`ProviderNotConfigured`, `ProviderError`; the executor retries only the transient ones, bounded.

**Consequences.** Adding Microsoft Graph means implementing the protocol and mapping
`singleValueExtendedProperties` for the owner id; no planner changes. Google behaviour is
verified by tests that assert request shapes, not by real calls; treat it as unproven until run
against a test calendar.
