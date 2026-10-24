"""Google OAuth endpoints. Tokens never appear in responses."""

from fastapi import APIRouter, HTTPException

from app.providers.base import CalendarProvider, ProviderError, ProviderNotConfigured
from app.providers.oauth import GoogleOAuth, OAuthError


def build_oauth_router(oauth: GoogleOAuth, providers: dict[str, CalendarProvider]) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/oauth/google/start")
    def start() -> dict[str, str]:
        try:
            return {"auth_url": oauth.start()}
        except ProviderNotConfigured as e:
            raise HTTPException(503, {"code": "provider_not_configured", "message": str(e)})

    @r.get("/oauth/google/callback")
    def callback(code: str = "", state: str = "") -> dict[str, bool]:
        if not code or not state:
            raise HTTPException(400, {"code": "bad_request", "message": "Missing code or state."})
        try:
            oauth.callback(code, state)
        except ProviderNotConfigured as e:
            raise HTTPException(503, {"code": "provider_not_configured", "message": str(e)})
        except OAuthError as e:
            raise HTTPException(400, {"code": "oauth_failed", "message": str(e)})
        return {"connected": True}

    @r.get("/providers/google/calendars")
    def calendars() -> list[dict[str, str]]:
        p = providers.get("google")
        if p is None:
            raise HTTPException(
                503, {"code": "provider_not_configured", "message": "Google not configured."}
            )
        try:
            return [{"id": c.id, "name": c.name} for c in p.list_calendars()]
        except ProviderNotConfigured as e:
            raise HTTPException(409, {"code": "not_connected", "message": str(e)})
        except ProviderError as e:
            raise HTTPException(502, {"code": "provider_error", "message": str(e)})

    return r
