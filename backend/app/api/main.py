import hmac
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.oauth_routes import build_oauth_router
from app.api.sync_routes import build_router
from app.config import get_settings
from app.extraction.pipeline import ImportContext, extract_events
from app.imports.store import Store
from app.ingestion.validate import UploadRejected, validate_pdf
from app.pdf.layout import extract_layout
from app.providers.base import CalendarProvider
from app.providers.google import GoogleCalendarProvider
from app.providers.mock import MockProvider
from app.providers.oauth import GoogleOAuth, TokenVault, install_log_redaction
from app.schemas import DocumentLayout, ExtractionResult


def create_app(
    store: Store | None = None,
    providers: dict[str, CalendarProvider] | None = None,
    http_client: httpx.Client | None = None,
) -> FastAPI:
    settings = get_settings()
    install_log_redaction()
    app = FastAPI(title="SchoolSync AI", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    if settings.api_key:
        expected = settings.api_key

        @app.middleware("http")
        async def require_api_key(request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path.startswith("/api") and request.method != "OPTIONS":
                given = request.headers.get("x-api-key", "")
                if not hmac.compare_digest(given.encode(), expected.encode()):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": {
                                "code": "unauthorized",
                                "message": "Missing or invalid API key.",
                            }
                        },
                    )
            return await call_next(request)

    store = store or Store(settings.data_dir / "schoolsync.sqlite3")
    # Only the in-memory demo provider is wired; Google/Microsoft adapters are not implemented.
    if providers is None:
        # The demo calendar lives in memory; give it a per-process manifest namespace so rows
        # from a previous run (when its events no longer exist) are not mistaken for deletions.
        demo = MockProvider()
        demo.name = f"mock-{uuid.uuid4().hex[:6]}"
        providers = {"mock": demo}
    http = http_client or httpx.Client()
    oauth = GoogleOAuth(settings, http, store, TokenVault(store, settings.token_encryption_key))
    if oauth.configured and "google" not in providers:
        providers["google"] = GoogleCalendarProvider(
            http, oauth.access_token, lambda: oauth.connected
        )
    app.include_router(build_oauth_router(oauth, providers))
    app.include_router(build_router(store, providers, settings.sync_enabled))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/uploads/layout", response_model=DocumentLayout)
    async def upload_layout(file: UploadFile = File(...)) -> DocumentLayout:
        # Read at most limit+1 bytes so oversized uploads are rejected without buffering them all.
        data = await file.read(settings.max_upload_bytes + 1)
        try:
            v = validate_pdf(
                data, max_bytes=settings.max_upload_bytes, max_pages=settings.max_pages
            )
        except UploadRejected as e:
            status = 413 if e.code == "too_large" else 422
            raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
        return extract_layout(v.data, v.sha256)

    @app.post("/api/uploads/extract", response_model=ExtractionResult)
    async def upload_extract(
        file: UploadFile = File(...),
        school_name: str = Form(..., max_length=200),
        academic_year: str = Form(..., max_length=20),
        timezone: str = Form(...),
        color_tolerance: float = Form(12.0, ge=1.0, le=40.0),
    ) -> ExtractionResult:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, detail={"code": "bad_timezone", "message": timezone})
        data = await file.read(settings.max_upload_bytes + 1)
        try:
            v = validate_pdf(
                data, max_bytes=settings.max_upload_bytes, max_pages=settings.max_pages
            )
        except UploadRejected as e:
            status = 413 if e.code == "too_large" else 422
            raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
        ctx = ImportContext(school_name, academic_year, timezone, v.sha256[:16], color_tolerance)
        return extract_events(extract_layout(v.data, v.sha256), ctx)

    return app


app = create_app()
