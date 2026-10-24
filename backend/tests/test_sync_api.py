import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.imports.store import Store
from app.providers.mock import MockProvider
from tests.test_m3_helpers import ready_events


@pytest.fixture
def env(calendar_pdf):
    mock = MockProvider()
    client = TestClient(create_app(Store(":memory:"), {"mock": mock}))
    events = [json.loads(e.model_dump_json()) for e in ready_events(calendar_pdf)]
    return client, mock, events


def test_providers_listing_is_honest(env):
    client, _, _ = env
    by_id = {p["id"]: p for p in client.get("/api/providers").json()}
    assert by_id["file"]["available"] and by_id["mock"]["available"]
    assert not by_id["google"]["available"] and not by_id["microsoft"]["available"]


def test_export_endpoints_download_and_enforce_readiness(env, calendar_pdf):
    client, _, events = env
    r = client.post("/api/export/ics", json={"events": events})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert b"BEGIN:VCALENDAR" in r.content and "attachment" in r.headers["content-disposition"]
    assert client.post("/api/export/csv", json={"events": events}).text.startswith("Subject,")

    from app.extraction.pipeline import ImportContext, extract_events
    from app.pdf.layout import extract_layout

    raw = extract_events(
        extract_layout(calendar_pdf, "h"), ImportContext("S", "Y", "UTC", "d")
    ).events
    bad = client.post(
        "/api/export/ics", json={"events": [json.loads(e.model_dump_json()) for e in raw]}
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "events_not_ready"
    assert len(bad.json()["detail"]["titles"]) == 2


def test_sync_requires_confirmation_and_matching_plan_token(env):
    client, mock, events = env
    body = {"provider": "mock", "calendar_id": "demo", "events": events}
    pre = client.post("/api/sync/preview", json=body).json()
    assert pre["counts"]["create"] == 8 and mock.create_calls == 0  # preview writes nothing

    no = client.post(
        "/api/sync/execute", json={**body, "confirm": False, "plan_token": pre["plan_token"]}
    )
    assert no.status_code == 400 and mock.create_calls == 0
    stale = client.post("/api/sync/execute", json={**body, "confirm": True, "plan_token": "bogus"})
    assert stale.status_code == 409 and mock.create_calls == 0

    ok = client.post(
        "/api/sync/execute", json={**body, "confirm": True, "plan_token": pre["plan_token"]}
    )
    assert ok.status_code == 200 and ok.json()["summary"]["created"] == 8

    again = client.post("/api/sync/preview", json=body).json()
    assert again["counts"]["skip"] == 8 and again["counts"]["create"] == 0


def test_rollback_via_api_requires_confirm(env):
    client, mock, events = env
    body = {"provider": "mock", "calendar_id": "demo", "events": events}
    tok = client.post("/api/sync/preview", json=body).json()["plan_token"]
    batch = client.post(
        "/api/sync/execute", json={**body, "confirm": True, "plan_token": tok}
    ).json()["batch_id"]
    assert client.post(f"/api/sync/rollback/{batch}", json={}).status_code == 400
    assert len(mock.events["demo"]) == 8
    r = client.post(f"/api/sync/rollback/{batch}", json={"confirm": True})
    assert r.status_code == 200 and len(mock.events["demo"]) == 0


def test_unconfigured_provider_is_refused(env):
    client, _, events = env
    r = client.post("/api/sync/preview", json={"provider": "google", "events": events})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "provider_not_configured"


def test_kill_switch_disables_sync(calendar_pdf, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "sync_enabled", False)
    client = TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))
    events = [json.loads(e.model_dump_json()) for e in ready_events(calendar_pdf)]
    assert (
        client.post("/api/sync/preview", json={"events": events}).json()["detail"]["code"]
        == "sync_disabled"
    )
    assert client.post("/api/sync/rollback/x", json={"confirm": True}).status_code == 503
    assert (
        client.post("/api/export/ics", json={"events": events}).status_code == 200
    )  # export still works


def test_import_history_dedups_same_pdf_and_diffs_revision(env, calendar_pdf):
    client, _, events = env
    meta = {
        "school_name": "Maple Grove Academy",
        "academic_year": "2025-2026",
        "timezone": "America/Chicago",
    }
    a = client.post("/api/imports", json={**meta, "source_hash": "A", "events": events}).json()
    assert not a["already_imported"] and a["diff"] is None
    same = client.post("/api/imports", json={**meta, "source_hash": "A", "events": events}).json()
    assert same["already_imported"] and same["import_id"] == a["import_id"]
    revised = [e for e in events if not e["start_date"].endswith("01-19")]
    b = client.post("/api/imports", json={**meta, "source_hash": "B", "events": revised}).json()
    assert (
        len(b["diff"]["removed"]) == 1
        and b["diff"]["added"] == []
        and not b["diff"]["identical_source"]
    )
    assert len(client.get("/api/imports").json()) == 2


def test_api_key_gate(calendar_pdf, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_key", "s3cret-demo-key")
    client = TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))
    assert client.get("/health").status_code == 200  # health stays open for the platform
    assert client.get("/api/providers").status_code == 401
    bad = client.get("/api/providers", headers={"x-api-key": "wrong"})
    assert bad.status_code == 401 and bad.json()["detail"]["code"] == "unauthorized"
    ok = client.get("/api/providers", headers={"x-api-key": "s3cret-demo-key"})
    assert ok.status_code == 200
    up = client.post(
        "/api/uploads/extract",
        files={"file": ("c.pdf", calendar_pdf)},
        data={"school_name": "S", "academic_year": "Y", "timezone": "UTC"},
    )
    assert up.status_code == 401  # uploads are gated too
