import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.deduplication.identity import sync_fingerprint
from app.deduplication.reconcile import plan_sync
from app.imports.executor import execute_plan
from app.imports.store import Store
from app.providers.base import ProviderError, ProviderEvent
from app.providers.colors import GRAPHITE, google_color_for
from app.providers.google import GoogleCalendarProvider
from app.providers.mock import MockProvider
from tests.test_m3_helpers import ready_events

# Legend colours of a real school calendar (the PDF is private; only these colours are recorded)
REAL_LEGEND = {
    "Student Days": (255, 249, 233),
    "Public Holidays": (158, 209, 216),
    "School Opening & Reopening Days": (222, 159, 16),
    "Important Days": (240, 156, 86),
}


# ---------------- colour mapping ----------------
def test_real_legend_maps_to_distinct_dark_google_colours():
    got = {k: google_color_for(v).name for k, v in REAL_LEGEND.items()}
    assert got == {
        "Student Days": "Graphite",
        "Public Holidays": "Peacock",
        "School Opening & Reopening Days": "Banana",
        "Important Days": "Tangerine",
    }
    assert len(set(got.values())) == 4


def test_fixture_legend_categories_get_distinct_colours(calendar_pdf):
    events = ready_events(calendar_pdf)
    by_cat = {
        e.category_label: google_color_for(e.matched_legend_color).color_id
        for e in events
        if e.matched_legend_color
    }
    assert len(by_cat) == 4 and len(set(by_cat.values())) == 4


def test_no_colour_evidence_means_default_and_greys_are_graphite():
    assert google_color_for(None) is None
    assert google_color_for((255, 255, 255)) == GRAPHITE
    assert google_color_for((200, 200, 200)) == GRAPHITE


# ---------------- colours reach the provider ----------------
def run(events, prov, store):
    existing = prov.list_events("demo", date(2025, 1, 1), date(2026, 12, 31))
    items = plan_sync(events, store.manifest(prov.name, "demo"), existing)
    return items, execute_plan(items, events, prov, "demo", store, sleep=lambda s: None)


def test_synced_events_carry_the_category_colour(calendar_pdf):
    prov, store = MockProvider(), Store(":memory:")
    run(ready_events(calendar_pdf), prov, store)
    assert sum(1 for e in prov.events["demo"].values() if e.color_id) >= 6
    labor = next(e for e in prov.events["demo"].values() if e.title == "Labor Day")
    assert labor.color_id == google_color_for((244, 182, 182)).color_id


def test_changing_the_colour_updates_our_own_events_instead_of_skipping(calendar_pdf):
    prov, store = MockProvider(), Store(":memory:")
    events = ready_events(calendar_pdf)
    run(events, prov, store)
    recoloured = [
        e.model_copy(update={"matched_legend_color": (183, 215, 244)})
        if e.event_title == "Labor Day"
        else e
        for e in events
    ]
    assert (
        sync_fingerprint(recoloured[0]) != sync_fingerprint(events[0]) or recoloured[0] is events[0]
    )
    items, rep = run(recoloured, prov, store)
    assert sum(i.action == "update" for i in items) == 1 and rep.count("updated") == 1
    again, _ = run(recoloured, prov, store)
    assert all(i.action == "skip" for i in again)  # stable once applied


def test_google_payload_has_colorId_and_roundtrips():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"id": "g1", **seen})

    p = GoogleCalendarProvider(httpx.Client(transport=httpx.MockTransport(h)), lambda: "t")
    ev = ProviderEvent("", "X", date(2025, 9, 1), date(2025, 9, 1), True, color_id="7")
    out = p.create_event("c", ev)
    assert seen["colorId"] == "7" and out.color_id == "7"


def test_preview_lists_the_colour_each_category_will_get(calendar_pdf):
    client = TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))
    events = [json.loads(e.model_dump_json()) for e in ready_events(calendar_pdf)]
    body = {"provider": "mock", "calendar_id": "demo", "events": events}
    cc = {
        c["category"]: c
        for c in client.post("/api/sync/preview", json=body).json()["category_colors"]
    }
    assert len(cc) == 4 and all(c["hex"].startswith("#") and c["color_name"] for c in cc.values())


# ---------------- creating a calendar ----------------
@pytest.fixture
def api():
    return TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))


def test_create_calendar_requires_explicit_confirmation(api):
    r = api.post(
        "/api/providers/mock/calendars",
        json={"name": "Cedar Hill School", "time_zone": "Asia/Kolkata"},
    )
    assert r.status_code == 400 and r.json()["detail"]["code"] == "confirmation_required"
    assert len(api.get("/api/providers/mock/calendars").json()) == 1  # nothing was created


def test_create_calendar_succeeds_then_refuses_a_duplicate_name(api):
    body = {"name": "Cedar Hill School", "time_zone": "Asia/Kolkata", "confirm": True}
    made = api.post("/api/providers/mock/calendars", json=body)
    assert made.status_code == 200 and made.json()["name"] == "Cedar Hill School"
    dup = api.post("/api/providers/mock/calendars", json={**body, "name": "  cedar hill SCHOOL "})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "calendar_exists"
    assert dup.json()["detail"]["calendar"]["id"] == made.json()["id"]
    assert len(api.get("/api/providers/mock/calendars").json()) == 2  # demo + the one we made


def test_create_calendar_rejects_blank_name_and_bad_timezone(api):
    blank = api.post(
        "/api/providers/mock/calendars",
        json={"name": "   ", "time_zone": "Asia/Kolkata", "confirm": True},
    )
    assert blank.status_code == 422
    bad = api.post(
        "/api/providers/mock/calendars",
        json={"name": "X", "time_zone": "Mars/Base", "confirm": True},
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "bad_timezone"


def test_google_create_calendar_payload_and_permission_error():
    sent = {}

    def ok(req: httpx.Request) -> httpx.Response:
        sent.update(method=req.method, path=req.url.path, body=json.loads(req.content))
        return httpx.Response(
            200, json={"id": "new@group.calendar.google.com", "summary": "Cedar Hill School"}
        )

    p = GoogleCalendarProvider(httpx.Client(transport=httpx.MockTransport(ok)), lambda: "t")
    c = p.create_calendar("Cedar Hill School", "Asia/Kolkata")
    assert (sent["method"], sent["path"]) == ("POST", "/calendar/v3/calendars")
    assert sent["body"] == {"summary": "Cedar Hill School", "timeZone": "Asia/Kolkata"}
    assert c.id == "new@group.calendar.google.com"

    transport = httpx.MockTransport(lambda r: httpx.Response(403, text="insufficientPermissions"))
    denied = GoogleCalendarProvider(httpx.Client(transport=transport), lambda: "t")
    with pytest.raises(ProviderError, match="reconnect"):
        denied.create_calendar("X", "UTC")
