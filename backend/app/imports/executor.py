"""Idempotent sync executor + batch rollback.

Duplicate-safety on retry: before every create (and before retrying one after a transient
failure, which may have succeeded server-side) the provider is asked for an event carrying our
owner id. If found it is adopted into the manifest instead of being created again.
Failures are per-event (partial success); conflicts and removals are never executed here.
"""

import time as _time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import time
from functools import partial

from app.deduplication.identity import compute_fingerprint
from app.deduplication.reconcile import PlanItem
from app.imports.store import ManifestRecord, Store
from app.providers.base import (
    BATCH_PROP,
    FP_PROP,
    OWNER_PROP,
    CalendarProvider,
    NotOwned,
    ProviderError,
    ProviderEvent,
    RateLimited,
    TransientError,
)
from app.providers.shape import shape_event
from app.schemas import CalendarEvent


@dataclass
class ItemResult:
    stable_id: str
    title: str
    status: str  # created | updated | adopted | skipped | failed | not_executed
    detail: str = ""
    provider_event_id: str | None = None


@dataclass
class SyncReport:
    batch_id: str
    results: list[ItemResult]

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)


def to_provider_event(
    ev: CalendarEvent, sid: str, batch_id: str, day_start: time | None
) -> ProviderEvent:
    s = shape_event(ev, day_start)
    return ProviderEvent(
        id="",
        title=s.title,
        start_date=ev.start_date,
        end_date=ev.end_date,
        all_day=s.all_day,
        start_time=s.start_time,
        end_time=s.end_time,
        timezone=None if s.all_day else ev.timezone,
        description=s.description,
        private_props={OWNER_PROP: sid, FP_PROP: compute_fingerprint(ev), BATCH_PROP: batch_id},
    )


def _with_retries[T](
    fn: Callable[[], T],
    *,
    attempts: int,
    sleep: Callable[[float], None],
    between: Callable[[], T | None],
) -> T:
    """Run fn; on TransientError wait, call `between` (reconcile) and retry, bounded."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except RateLimited as e:
            last = e
            sleep(min(e.retry_after, 30.0))
        except TransientError as e:
            last = e
            sleep(min(0.5 * 2**i, 8.0))
        found = between()
        if found is not None:
            return found
    raise ProviderError(f"gave up after {attempts} attempts: {last}")


def execute_plan(
    items: Sequence[PlanItem],
    events: Sequence[CalendarEvent],
    provider: CalendarProvider,
    calendar_id: str,
    store: Store,
    *,
    day_start: time | None = None,
    attempts: int = 4,
    sleep: Callable[[float], None] = _time.sleep,
) -> SyncReport:
    batch_id = uuid.uuid4().hex[:12]
    by_id = {e.event_id_internal: e for e in events}
    results: list[ItemResult] = []

    prior = store.manifest(provider.name, calendar_id)

    def record(sid: str, pe: ProviderEvent, ev: CalendarEvent, batch: str) -> None:
        store.upsert_mapping(
            ManifestRecord(sid, provider.name, calendar_id, pe.id, compute_fingerprint(ev), batch)
        )

    for it in items:
        base = (it.stable_id, it.title)
        if it.action in ("skip", "conflict", "propose_remove"):
            results.append(ItemResult(*base, "skipped" if it.action == "skip" else "not_executed",
                                      it.reason, it.provider_event_id))  # fmt: skip
            continue
        ev = by_id.get(it.event_id_internal or "")
        if ev is None:
            results.append(ItemResult(*base, "failed", "event missing from request"))
            continue
        try:
            pev = to_provider_event(ev, it.stable_id, batch_id, day_start)
            if it.action == "create":
                existing = provider.find_by_owner_id(calendar_id, it.stable_id)
                if existing is not None:
                    record(
                        it.stable_id, existing, ev, existing.private_props.get(BATCH_PROP, batch_id)
                    )
                    results.append(ItemResult(*base, "adopted",
                                              "already in destination (found by owner id)",
                                              existing.id))  # fmt: skip
                    continue
                created = _with_retries(
                    partial(provider.create_event, calendar_id, pev),
                    attempts=attempts,
                    sleep=sleep,
                    between=partial(provider.find_by_owner_id, calendar_id, it.stable_id),
                )
                record(it.stable_id, created, ev, created.private_props.get(BATCH_PROP, batch_id))
                results.append(ItemResult(*base, "created", "", created.id))
            else:  # update (app-owned only; provider enforces ownership too)
                assert it.provider_event_id
                eid = it.provider_event_id
                # keep the original batch so rolling back a later batch never deletes older events
                keep = prior[it.stable_id].batch_id if it.stable_id in prior else batch_id
                pev.private_props[BATCH_PROP] = keep
                updated = _with_retries(
                    partial(provider.update_event, calendar_id, eid, pev),
                    attempts=attempts,
                    sleep=sleep,
                    between=lambda: None,
                )
                record(it.stable_id, updated, ev, keep)
                results.append(ItemResult(*base, "updated", "", updated.id))
        except NotOwned as e:
            results.append(ItemResult(*base, "failed", f"refused: {e}"))
        except ProviderError as e:
            results.append(ItemResult(*base, "failed", str(e)))
    store.audit("sync.executed", f"batch={batch_id} results={len(results)}")
    return SyncReport(batch_id, results)


def rollback_batch(batch_id: str, provider: CalendarProvider, store: Store) -> list[ItemResult]:
    """Delete only events mapped to this batch (and still carrying our owner id)."""
    out: list[ItemResult] = []
    for m in store.batch_mappings(batch_id):
        if m.provider != provider.name:
            continue
        try:
            provider.delete_event(m.calendar_id, m.provider_event_id)
            store.mark_rolled_back(m)
            out.append(ItemResult(m.stable_id, "", "deleted", "", m.provider_event_id))
        except ProviderError as e:
            out.append(ItemResult(m.stable_id, "", "failed", str(e), m.provider_event_id))
    store.audit("sync.rollback", f"batch={batch_id} n={len(out)}")
    return out
