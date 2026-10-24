"""Export, import-history and sync routes. Sync never runs without explicit confirmation bound
to the exact previewed plan (plan_token)."""

from dataclasses import asdict
from datetime import time

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.deduplication.reconcile import counts, diff_imports, plan_sync, plan_token
from app.imports.executor import execute_plan, rollback_batch
from app.imports.store import Store
from app.providers.base import CalendarProvider, ProviderError
from app.providers.export_files import build_csv, build_ics
from app.providers.shape import NotExportable
from app.schemas import CalendarEvent
from app.validation.readiness import is_ready


class ExportReq(BaseModel):
    events: list[CalendarEvent]
    day_start: time | None = None  # user-supplied school start; never assumed


class ImportReq(BaseModel):
    source_hash: str
    school_name: str
    academic_year: str
    timezone: str
    events: list[CalendarEvent]


class SyncReq(BaseModel):
    provider: str = "mock"
    calendar_id: str = "demo"
    events: list[CalendarEvent]
    day_start: time | None = None


class ExecuteReq(SyncReq):
    confirm: bool = False
    plan_token: str = ""


class RollbackReq(BaseModel):
    confirm: bool = False


def _err(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def build_router(
    store: Store, providers: dict[str, CalendarProvider], sync_enabled: bool
) -> APIRouter:
    r = APIRouter(prefix="/api")

    def require_ready(events: list[CalendarEvent]) -> None:
        bad = [e.event_title for e in events if not is_ready(e)]
        if bad:
            raise _err(422, "events_not_ready", f"{len(bad)} event(s) need review", titles=bad)

    def get_provider(name: str) -> CalendarProvider:
        if not sync_enabled:
            raise _err(503, "sync_disabled", "Sync is disabled by the operator kill switch.")
        p = providers.get(name)
        if p is None:
            raise _err(503, "provider_not_configured", f"Provider '{name}' is not configured.")
        return p

    @r.get("/providers")
    def list_providers() -> list[dict[str, object]]:
        out: list[dict[str, object]] = [
            {"id": "file", "label": "File export (ICS/CSV)", "available": True}
        ]
        for pid, label in (("mock", "Demo calendar (in-memory)"), ("google", "Google Calendar"),
                           ("microsoft", "Microsoft Outlook")):  # fmt: skip
            ok = sync_enabled and pid in providers and getattr(providers[pid], "ready", True)
            why = (
                "sync disabled"
                if not sync_enabled
                else "not configured"
                if pid not in providers
                else "not connected"
            )
            out.append({"id": pid, "label": label, "available": ok, "reason": None if ok else why})  # fmt: skip
        return out

    @r.post("/export/ics")
    def export_ics(req: ExportReq) -> Response:
        require_ready(req.events)
        try:
            data = build_ics(req.events, day_start=req.day_start)
        except NotExportable as e:
            raise _err(422, "not_exportable", str(e))
        return Response(data, media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="schoolsync.ics"'})  # fmt: skip

    @r.post("/export/csv")
    def export_csv(req: ExportReq) -> Response:
        require_ready(req.events)
        try:
            data = build_csv(req.events, day_start=req.day_start)
        except NotExportable as e:
            raise _err(422, "not_exportable", str(e))
        return Response(data, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="schoolsync.csv"'})  # fmt: skip

    @r.post("/imports")
    def save_import(req: ImportReq) -> dict[str, object]:
        prev = store.previous_import(req.school_name, req.academic_year)
        if prev is not None and prev.source_hash == req.source_hash:
            return {"import_id": prev.id, "already_imported": True, "diff": None}
        row = store.save_import(req.source_hash, req.school_name, req.academic_year,
                                req.timezone, req.events)  # fmt: skip
        diff = (diff_imports(prev.events, req.events, prev.source_hash, req.source_hash)
                if prev else None)  # fmt: skip
        return {"import_id": row.id, "already_imported": False,
                "diff": asdict(diff) if diff else None}  # fmt: skip

    @r.get("/imports")
    def list_imports() -> list[dict[str, object]]:
        return [{"id": i.id, "created_at": i.created_at, "school": i.school,
                 "academic_year": i.academic_year, "events": len(i.events)}
                for i in store.list_imports()]  # fmt: skip

    def make_plan(req: SyncReq) -> tuple[CalendarProvider, list]:  # type: ignore[type-arg]
        p = get_provider(req.provider)
        if not req.events:
            raise _err(422, "no_events", "No events supplied.")
        lo = min(e.start_date for e in req.events)
        hi = max(e.end_date for e in req.events)
        try:
            existing = p.list_events(req.calendar_id, lo, hi)
        except ProviderError as e:
            raise _err(502, "provider_error", str(e))
        items = plan_sync(
            req.events, store.manifest(p.name, req.calendar_id), existing, req.day_start
        )
        return p, items

    @r.post("/sync/preview")
    def preview(req: SyncReq) -> dict[str, object]:
        _, items = make_plan(req)
        return {"items": [asdict(i) for i in items], "counts": counts(items),
                "plan_token": plan_token(items)}  # fmt: skip

    @r.post("/sync/execute")
    def execute(req: ExecuteReq) -> dict[str, object]:
        if not req.confirm:
            raise _err(400, "confirmation_required", "Sync requires explicit confirmation.")
        p, items = make_plan(req)
        if plan_token(items) != req.plan_token:
            raise _err(409, "plan_changed", "The destination or events changed since the "
                       "preview. Preview again before confirming.")  # fmt: skip
        rep = execute_plan(items, req.events, p, req.calendar_id, store, day_start=req.day_start)
        return {"batch_id": rep.batch_id,
                "summary": {s: rep.count(s) for s in ("created", "updated", "adopted", "skipped",
                                                      "failed", "not_executed")},
                "results": [asdict(x) for x in rep.results]}  # fmt: skip

    @r.post("/sync/rollback/{batch_id}")
    def rollback(batch_id: str, req: RollbackReq) -> dict[str, object]:
        if not sync_enabled:
            raise _err(503, "sync_disabled", "Sync is disabled by the operator kill switch.")
        if not req.confirm:
            raise _err(400, "confirmation_required", "Rollback requires explicit confirmation.")
        out = []
        for p in providers.values():
            out += rollback_batch(batch_id, p, store)
        return {"batch_id": batch_id, "results": [asdict(x) for x in out]}

    return r
