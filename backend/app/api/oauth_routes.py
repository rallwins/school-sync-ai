"""Google OAuth + calendar listing. Tokens never appear in any response or redirect."""

from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.providers.base import CalendarProvider, ProviderError, ProviderNotConfigured
from app.providers.oauth import GoogleOAuth, OAuthError


class CreateCalendarReq(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    time_zone: str
    confirm: bool = False


def build_oauth_router(
    oauth: GoogleOAuth, providers: dict[str, CalendarProvider], frontend_url: str
) -> APIRouter:
    r = APIRouter(prefix="/api")
    back = frontend_url.rstrip("/") + "/connect"

    @r.get("/oauth/google/start")
    def start() -> dict[str, str]:
        try:
            return {"auth_url": oauth.start()}
        except ProviderNotConfigured as e:
            raise HTTPException(503, {"code": "provider_not_configured", "message": str(e)})

    @r.get("/oauth/google/callback")
    def callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
        """Browser lands here from Google; always bounce back to the app with a short status code
        (never the provider's message, the code, or any token)."""

        def done(status: str, reason: str = "") -> RedirectResponse:
            q = {"google": status, **({"reason": reason} if reason else {})}
            return RedirectResponse(f"{back}?{urlencode(q)}", status_code=302)

        if error:  # user pressed "Cancel" at Google
            return done("error", "denied")
        if not code or not state:
            return done("error", "bad_request")
        try:
            oauth.callback(code, state)
        except ProviderNotConfigured:
            return done("error", "not_configured")
        except OAuthError:
            return done("error", "oauth_failed")
        return done("connected")

    @r.post("/oauth/google/disconnect")
    def disconnect() -> dict[str, bool]:
        oauth.disconnect()
        return {"connected": False}

    @r.get("/providers/{provider_id}/calendars")
    def calendars(provider_id: str) -> list[dict[str, str]]:
        p = providers.get(provider_id)
        if p is None:
            raise HTTPException(
                503, {"code": "provider_not_configured", "message": "Not configured."}
            )
        try:
            return [{"id": c.id, "name": c.name} for c in p.list_calendars()]
        except ProviderNotConfigured as e:
            raise HTTPException(409, {"code": "not_connected", "message": str(e)})
        except ProviderError as e:
            raise HTTPException(502, {"code": "provider_error", "message": str(e)})

    @r.post("/providers/{provider_id}/calendars")
    def create_calendar(provider_id: str, req: CreateCalendarReq) -> dict[str, str]:
        """Create a NEW calendar in the account. This writes to a real account, so it needs an
        explicit confirm, and it never creates a second calendar with an existing name."""
        p = providers.get(provider_id)
        if p is None:
            raise HTTPException(
                503, {"code": "provider_not_configured", "message": "Not configured."}
            )
        if not req.confirm:
            raise HTTPException(
                400,
                {
                    "code": "confirmation_required",
                    "message": "Creating a calendar requires explicit confirmation.",
                },
            )
        name = req.name.strip()
        if not name:
            raise HTTPException(422, {"code": "bad_name", "message": "Calendar name is empty."})
        try:
            ZoneInfo(req.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, {"code": "bad_timezone", "message": req.time_zone})
        try:
            same = next(
                (c for c in p.list_calendars() if c.name.strip().lower() == name.lower()), None
            )
            if same is not None:
                raise HTTPException(
                    409,
                    {
                        "code": "calendar_exists",
                        "message": f"A calendar named {same.name} already exists; use it instead.",
                        "calendar": {"id": same.id, "name": same.name},
                    },
                )
            made = p.create_calendar(name, req.time_zone)
        except ProviderNotConfigured as e:
            raise HTTPException(409, {"code": "not_connected", "message": str(e)})
        except ProviderError as e:
            raise HTTPException(502, {"code": "provider_error", "message": str(e)})
        oauth.store.audit("calendar.created", provider_id)
        return {"id": made.id, "name": made.name}

    return r
