from datetime import date

import pytest

from app.deduplication.reconcile import counts, diff_imports, plan_sync
from app.imports.executor import execute_plan, rollback_batch
from app.imports.store import Store
from app.providers.base import (
    OWNER_PROP,
    NotOwned,
    ProviderEvent,
    RateLimited,
    TransientError,
)
from app.providers.mock import MockProvider
from app.schemas import DurationKind
from tests.test_m3_helpers import by_date, ready_events

CAL = "demo"


@pytest.fixture
def events(calendar_pdf):
    return ready_events(calendar_pdf)


@pytest.fixture
def store():
    return Store(":memory:")


def run(events, provider, store, sleeps=None, **kw):
    items = plan_sync(
        events,
        store.manifest("mock", CAL),
        provider.list_events(CAL, date(2025, 1, 1), date(2026, 12, 31)),
    )
    rep = execute_plan(
        items,
        events,
        provider,
        CAL,
        store,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
        **kw,
    )
    return items, rep


def test_first_sync_creates_everything(events, store):
    p = MockProvider()
    items, rep = run(events, p, store)
    assert counts(items)["create"] == len(events) and rep.count("created") == len(events)
    assert len(p.events[CAL]) == len(events)


def test_same_pdf_twice_creates_zero_duplicates(events, store, calendar_pdf):
    p = MockProvider()
    run(events, p, store)
    n_calls = p.create_calls
    items, rep = run(ready_events(calendar_pdf), p, store)  # fresh extraction of the same PDF
    assert counts(items)["skip"] == len(events) and counts(items)["create"] == 0
    assert p.create_calls == n_calls and rep.count("created") == 0
    assert len(p.events[CAL]) == len(events)


def test_unready_events_are_never_synced(calendar_pdf, store):
    from app.extraction.pipeline import ImportContext, extract_events
    from app.pdf.layout import extract_layout

    raw = extract_events(
        extract_layout(calendar_pdf, "h"), ImportContext("S", "Y", "UTC", "d")
    ).events
    p = MockProvider()
    items = plan_sync(raw, {}, [])
    unready = [i for i in items if i.reason.startswith("needs review")]
    assert len(unready) == 2 and counts(items)["create"] == len(raw) - 2
    assert p.create_calls == 0


def test_revised_pdf_updates_changed_proposes_removal_keeps_unrelated(events, store, calendar_pdf):
    p = MockProvider()
    run(events, p, store)
    foreign = ProviderEvent("user-1", "Dentist", date(2025, 9, 1), date(2025, 9, 1), False)
    p.events[CAL]["user-1"] = foreign

    revised = ready_events(calendar_pdf, "rev")
    revised = [
        e.model_copy(update={"event_title": "Labor Day Holiday"})
        if e.start_date == date(2025, 9, 1)
        else e
        for e in revised
        if e.start_date != date(2026, 1, 19)
    ]  # MLK removed from source
    items, rep = run(revised, p, store)
    c = counts(items)
    assert c["update"] == 1 and c["propose_remove"] == 1 and c["create"] == 0
    assert rep.count("updated") == 1 and rep.count("not_executed") == 1
    assert any(e.title == "Labor Day Holiday" for e in p.events[CAL].values())
    assert len(p.events[CAL]) == len(events) + 1  # removal NOT executed; Dentist untouched
    assert p.events[CAL]["user-1"] == foreign

    d = diff_imports(events, revised, "h1", "rev")
    assert d.removed and d.changed and len(d.unchanged) == len(events) - 2 and not d.added


def test_identical_unowned_event_is_skipped_not_touched(events, store):
    p = MockProvider()
    twin = ProviderEvent("x1", "Labor Day", date(2025, 9, 1), date(2025, 9, 1), True)
    p.events[CAL]["x1"] = twin
    items, _ = run(events, p, store)
    it = next(i for i in items if i.start_date == date(2025, 9, 1))
    assert it.action == "skip" and "not created by SchoolSync" in it.reason
    assert p.events[CAL]["x1"] == twin and OWNER_PROP not in p.events[CAL]["x1"].private_props


def test_same_title_same_date_different_duration_is_conflict(events, store):
    p = MockProvider()
    timed = ProviderEvent("x2", "Labor Day", date(2025, 9, 1), date(2025, 9, 1), False)
    p.events[CAL]["x2"] = timed
    items, rep = run(events, p, store)
    it = next(i for i in items if i.start_date == date(2025, 9, 1))
    assert it.action == "conflict" and it.matched_title == "Labor Day"
    assert rep.count("not_executed") >= 1 and p.events[CAL]["x2"] == timed


def test_fuzzy_title_overlap_is_conflict(events, store):
    p = MockProvider()
    p.events[CAL]["x3"] = ProviderEvent(
        "x3", "Labour Day - no school", date(2025, 9, 1), date(2025, 9, 1), True
    )
    items = plan_sync(events, {}, p.list_events(CAL, date(2025, 1, 1), date(2026, 12, 31)))
    assert next(i for i in items if i.start_date == date(2025, 9, 1)).action == "conflict"


def test_transient_failures_are_retried_with_backoff(events, store):
    p = MockProvider()
    calls = {"n": 0}

    def flaky(op, ev):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise TransientError("503")

    p.fail_before = flaky
    sleeps: list[float] = []
    _, rep = run(events[:1], p, store, sleeps)
    assert rep.count("created") == 1 and sleeps == [0.5, 1.0] and len(p.events[CAL]) == 1


def test_rate_limit_waits_retry_after(events, store):
    p = MockProvider()
    first = {"done": False}

    def limited(op, ev):
        if not first["done"]:
            first["done"] = True
            raise RateLimited(retry_after=3.0)

    p.fail_before = limited
    sleeps: list[float] = []
    _, rep = run(events[:1], p, store, sleeps)
    assert rep.count("created") == 1 and sleeps == [3.0]


def test_lost_response_on_create_does_not_duplicate(events, store):
    p = MockProvider()
    p.lose_response_on_create = {1}  # server stored it, client saw a timeout
    _, rep = run(events[:2], p, store, [])
    assert len(p.events[CAL]) == 2 and p.create_calls == 2  # not 3
    assert rep.count("created") + rep.count("adopted") == 2
    # and the manifest knows both
    assert len(store.manifest("mock", CAL)) == 2


def test_partial_success_reports_failure_and_continues(events, store):
    p = MockProvider()
    p.permanent_fail_titles = {"MLK Day"}
    _, rep = run(events, p, store)
    assert rep.count("failed") == 1 and rep.count("created") == len(events) - 1
    assert next(r for r in rep.results if r.status == "failed").title == "MLK Day"


def test_gives_up_after_bounded_retries(events, store):
    p = MockProvider()

    def always(op, ev):
        raise TransientError("down")

    p.fail_before = always
    _, rep = run(events[:1], p, store, [], attempts=3)
    assert rep.count("failed") == 1 and "gave up after 3" in rep.results[0].detail


def test_pagination_returns_all_pages(events, store):
    p = MockProvider(page_size=2)
    run(events, p, store)
    p.pages_fetched = 0
    got = p.list_events(CAL, date(2025, 1, 1), date(2026, 12, 31))
    assert len(got) == len(events) and p.pages_fetched == 4  # 8 events / 2 per page


def test_update_of_unowned_event_is_refused(events, store):
    p = MockProvider()
    p.events[CAL]["x"] = ProviderEvent("x", "Mine", date(2025, 9, 1), date(2025, 9, 1), True)
    with pytest.raises(NotOwned):
        p.update_event(
            CAL, "x", ProviderEvent("", "Hijack", date(2025, 9, 1), date(2025, 9, 1), True)
        )
    with pytest.raises(NotOwned):
        p.delete_event(CAL, "x")


def test_rollback_deletes_only_that_batch(events, store, calendar_pdf):
    p = MockProvider()
    run(events[:3], p, store)
    _, rep2 = run(events, p, store)  # first 3 skipped, 5 created in batch 2
    assert rep2.count("created") == len(events) - 3
    foreign = ProviderEvent("u", "Dentist", date(2025, 9, 2), date(2025, 9, 2), False)
    p.events[CAL]["u"] = foreign
    out = rollback_batch(rep2.batch_id, p, store)
    assert len(out) == len(events) - 3 and all(o.status == "deleted" for o in out)
    assert len(p.events[CAL]) == 3 + 1  # batch-1 events and the foreign event survive
    assert by_date(events, "2025-09-01").event_title in {e.title for e in p.events[CAL].values()}


def test_update_keeps_original_batch_for_rollback(events, store):
    p = MockProvider()
    run(events[:2], p, store)
    changed = [e.model_copy(update={"event_title": e.event_title + " X"}) for e in events[:2]]
    _, rep2 = run(changed, p, store)
    assert rep2.count("updated") == 2
    assert rollback_batch(rep2.batch_id, p, store) == []  # nothing belongs to batch 2
    assert len(p.events[CAL]) == 2


def test_removed_in_destination_is_conflict_not_recreated(events, store):
    p = MockProvider()
    run(events[:2], p, store)
    p.events[CAL].clear()  # user deleted them in the calendar app
    items, _ = run(events[:2], p, store)
    assert counts(items)["conflict"] == 2 and p.create_calls == 2


def test_duration_kind_enum_roundtrip():
    assert DurationKind("half_day") is DurationKind.HALF_DAY
