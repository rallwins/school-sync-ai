"""Google OAuth + calendar listing. Tokens never appear in any response or redirect."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.providers.base import CalendarProvider, ProviderError, ProviderNotConfigured
from app.providers.oauth import GoogleOAuth, OAuthError


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

    return r
