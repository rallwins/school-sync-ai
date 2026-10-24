"""Google Calendar and Microsoft Graph adapters: NOT IMPLEMENTED.

They exist so the registry, API and UI treat them as separate adapters that report 'not
configured' instead of pretending. Implementing them needs OAuth credentials and a test
calendar, and must go through the CalendarProvider interface in base.py.
"""

from app.providers.base import ProviderNotConfigured


class _Unconfigured:
    name = "unconfigured"
    reason = "OAuth credentials not configured; adapter not implemented yet."

    def __getattr__(self, item: str) -> object:
        raise ProviderNotConfigured(self.reason)


class GoogleProvider(_Unconfigured):
    name = "google"


class MicrosoftProvider(_Unconfigured):
    name = "microsoft"
