"""Duplicate detection, import diffing and the create/update/skip/conflict plan.

Layers (strongest first):
  A. internal/app-owned: stable id found in the manifest or as an owned provider event.
  B. provider duplicate: an UNOWNED event with identical title/date/time -> skip, never touch.
  C. probable duplicate/conflict: similar title and overlapping dates but different time or
     duration -> conflict for human review.
Removals are only ever *proposed*. Unowned provider events are never updated or deleted.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, time
from typing import Literal

from app.deduplication.identity import (
    compute_fingerprint,
    norm_title,
    stable_ids,
    sync_fingerprint,
    title_similarity,
)
from app.imports.store import ManifestRecord
from app.providers.base import FP_PROP, OWNER_PROP, ProviderEvent
from app.providers.shape import shape_event
from app.schemas import CalendarEvent
from app.validation.readiness import is_ready

Action = Literal["create", "update", "skip", "conflict", "propose_remove"]
FUZZY_TITLE = 0.75


@dataclass
class PlanItem:
    action: Action
    stable_id: str
    title: str
    start_date: date
    end_date: date
    reason: str
    event_id_internal: str | None = None
    provider_event_id: str | None = None
    matched_title: str | None = None


def _overlaps(a0: date, a1: date, b0: date, b1: date) -> bool:
    return a0 <= b1 and b0 <= a1


def _same_slot(ev: CalendarEvent, pe: ProviderEvent, day_start: time | None) -> bool:
    s = shape_event(ev, day_start)
    return (
        norm_title(s.title) == norm_title(pe.title)
        and ev.start_date == pe.start_date
        and ev.end_date == pe.end_date
        and s.all_day == pe.all_day
        and (s.all_day or (s.start_time == pe.start_time and s.end_time == pe.end_time))
    )


def plan_sync(
    events: Sequence[CalendarEvent],
    manifest: dict[str, ManifestRecord],
    provider_events: Sequence[ProviderEvent],
    day_start: time | None = None,
) -> list[PlanItem]:
    sids = stable_ids(events)
    owned = {pe.private_props[OWNER_PROP]: pe for pe in provider_events if pe.owned}
    foreign = [pe for pe in provider_events if not pe.owned]
    items: list[PlanItem] = []

    for ev in events:
        sid = sids[ev.event_id_internal]

        def mk(
            action: Action,
            reason: str,
            peid: str | None = None,
            matched: str | None = None,
            ev: CalendarEvent = ev,
            sid: str = sid,
        ) -> PlanItem:
            return PlanItem(action, sid, ev.event_title, ev.start_date, ev.end_date, reason,
                            ev.event_id_internal, peid, matched)  # fmt: skip

        if not is_ready(ev):
            items.append(mk("skip", "needs review; not ready to sync"))
            continue
        fp = sync_fingerprint(ev)
        pe = owned.get(sid)
        rec = manifest.get(sid)
        if pe is not None:  # layer A: ours, found in the destination
            if pe.private_props.get(FP_PROP) == fp:
                items.append(mk("skip", "already synced, unchanged", pe.id))
            else:
                items.append(mk("update", "source changed since last sync", pe.id))
            continue
        if rec is not None:
            items.append(mk(
                "conflict",
                "synced before but no longer in the destination; not recreated automatically",
                rec.provider_event_id,
            ))  # fmt: skip
            continue
        dup = next((f for f in foreign if _same_slot(ev, f, day_start)), None)
        if dup is not None:  # layer B
            items.append(mk("skip", "identical event already exists (not created by "
                            "SchoolSync); left untouched", dup.id, dup.title))  # fmt: skip
            continue
        near = next(
            (
                f for f in foreign
                if _overlaps(ev.start_date, ev.end_date, f.start_date, f.end_date)
                and title_similarity(ev.event_title, f.title)
                >= FUZZY_TITLE
            ),
            None,
        )  # fmt: skip
        if near is not None:  # layer C
            items.append(mk("conflict", "similar event on overlapping dates with different "
                            "time/duration; review manually", near.id, near.title))  # fmt: skip
            continue
        items.append(mk("create", "new event"))

    current = set(sids.values())
    for sid, rec in manifest.items():
        if sid not in current:
            items.append(PlanItem(
                "propose_remove", stable_id=sid, title="(previously synced event)",
                start_date=date.min, end_date=date.min,
                reason="no longer in the source; removal requires explicit confirmation",
                provider_event_id=rec.provider_event_id,
            ))  # fmt: skip
    return items


def counts(items: Sequence[PlanItem]) -> dict[str, int]:
    out = {"create": 0, "update": 0, "skip": 0, "conflict": 0, "propose_remove": 0}
    for i in items:
        out[i.action] += 1
    return out


def plan_token(items: Sequence[PlanItem]) -> str:
    """Binds a confirmation to the exact plan the user previewed."""
    blob = json.dumps([asdict(i) for i in items], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


# ---- revised-PDF comparison ----------------------------------------------------------------


@dataclass
class ImportDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]
    identical_source: bool


def diff_imports(
    prev: Sequence[CalendarEvent],
    new: Sequence[CalendarEvent],
    prev_hash: str | None = None,
    new_hash: str | None = None,
) -> ImportDiff:
    """Compare by stable id (school/year/start date). Returns human-readable lines."""
    ps, ns = stable_ids(prev), stable_ids(new)
    pm = {ps[e.event_id_internal]: e for e in prev}
    nm = {ns[e.event_id_internal]: e for e in new}
    added = [f"{e.start_date} {e.event_title}" for k, e in nm.items() if k not in pm]
    removed = [f"{e.start_date} {e.event_title}" for k, e in pm.items() if k not in nm]
    changed, same = [], []
    for k, e in nm.items():
        if k in pm:
            if compute_fingerprint(e) != compute_fingerprint(pm[k]):
                changed.append(f"{e.start_date} {pm[k].event_title} -> {e.event_title}")
            else:
                same.append(f"{e.start_date} {e.event_title}")
    return ImportDiff(sorted(added), sorted(removed), sorted(changed), sorted(same),
                      bool(prev_hash and prev_hash == new_hash))  # fmt: skip
