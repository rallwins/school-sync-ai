"""Google adapter + OAuth against a MOCKED transport. Nothing here talks to Google."""

import json
import logging
import time
from datetime import date
from datetime import time as dtime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.deduplication.reconcile import plan_sync
from app.imports.executor import execute_plan
from app.imports.store import Store
from app.providers.base import (
    BATCH_PROP,
    OWNER_PROP,
    NotOwned,
    ProviderError,
    ProviderEvent,
    ProviderNotConfigured,
    RateLimited,
    TransientError,
)
from app.providers.google import GoogleCalendarProvider, from_google, to_google
from app.providers.mock import MockProvider
from app.providers.oauth import GoogleOAuth, OAuthError, RedactingFilter, TokenVault, redact
from tests.test_m3_helpers import ready_events

KEY = Fernet.generate_key().decode()


def settings(**kw) -> Settings:
    return Settings(google_client_id="cid", google_client_secret="csecret",
                    token_encryption_key=KEY, **kw)  # fmt: skip


def provider(handler, ready=True) -> GoogleCalendarProvider:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GoogleCalendarProvider(http, lambda: "ya29.fake-access-token", lambda: ready)


# ---------------- payload mapping ----------------
def test_all_day_payload_uses_dates_and_exclusive_end():
    ev = ProviderEvent("", "Winter Break", date(2025, 12, 22), date(2025, 12, 31), True,
                       private_props={OWNER_PROP: "abc"})  # fmt: skip
    b = to_google(ev)
    assert b["start"] == {"date": "2025-12-22"} and b["end"] == {"date": "2026-01-01"}
    assert b["extendedProperties"]["private"][OWNER_PROP] == "abc"


def test_timed_payload_carries_timezone_and_no_invented_end():
    ev = ProviderEvent("", "Conf", date(2028, 3, 14), date(2028, 3, 14), False, dtime(16, 0), None,
                       "America/New_York")  # fmt: skip
    b = to_google(ev)
    assert b["start"] == {"dateTime": "2028-03-14T16:00:00", "timeZone": "America/New_York"}
    assert b["end"] == b["start"]  # zero-length, not a guessed duration
    assert from_google({"id": "1", **b}).end_time is None


def test_roundtrip_all_day():
    ev = ProviderEvent("", "X", date(2025, 9, 1), date(2025, 9, 3), True)
    back = from_google({"id": "9", **to_google(ev)})
    assert (back.start_date, back.end_date, back.all_day) == (
        date(2025, 9, 1),
        date(2025, 9, 3),
        True,
    )


# ---------------- API behaviour ----------------
def test_pagination_follows_every_page_and_sends_bearer():
    seen = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        tok = req.url.params.get("pageToken")
        item = lambda i: {
            "id": f"e{i}",
            "summary": f"E{i}",
            "start": {"date": "2025-09-01"},
            "end": {"date": "2025-09-02"},
        }
        if tok is None:
            return httpx.Response(200, json={"items": [item(1), item(2)], "nextPageToken": "p2"})
        return httpx.Response(200, json={"items": [item(3)]})

    evs = provider(h).list_events("cal@x", date(2025, 9, 1), date(2025, 9, 30))
    assert [e.id for e in evs] == ["e1", "e2", "e3"] and len(seen) == 2
    assert seen[0].headers["authorization"] == "Bearer ya29.fake-access-token"
    assert seen[0].url.params["singleEvents"] == "true"


def test_find_by_owner_id_uses_private_extended_property_filter():
    def h(req):
        assert req.url.params["privateExtendedProperty"] == f"{OWNER_PROP}=sid1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "g1",
                        "summary": "T",
                        "start": {"date": "2025-09-01"},
                        "end": {"date": "2025-09-02"},
                    }
                ]
            },
        )

    assert provider(h).find_by_owner_id("c", "sid1").id == "g1"


@pytest.mark.parametrize(
    "resp,exc",
    [
        (httpx.Response(429, headers={"Retry-After": "7"}), RateLimited),
        (
            httpx.Response(403, text='{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}'),
            RateLimited,
        ),
        (httpx.Response(503), TransientError),
        (httpx.Response(400), ProviderError),
        (httpx.Response(401), ProviderError),
    ],
)
def test_error_mapping(resp, exc):
    with pytest.raises(exc) as e:
        provider(lambda r: resp).list_calendars()
    if isinstance(e.value, RateLimited) and resp.status_code == 429:
        assert e.value.retry_after == 7.0


def test_timeout_is_transient():
    def h(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(TransientError):
        provider(h).list_calendars()


def test_update_and_delete_refuse_unowned_events_without_writing():
    calls = []

    def h(req):
        calls.append(req.method)
        return httpx.Response(
            200,
            json={
                "id": "u1",
                "summary": "Dentist",
                "start": {"date": "2025-09-01"},
                "end": {"date": "2025-09-02"},
            },
        )  # no extendedProperties

    p = provider(h)
    ev = ProviderEvent("", "Hijack", date(2025, 9, 1), date(2025, 9, 1), True)
    with pytest.raises(NotOwned):
        p.update_event("c", "u1", ev)
    with pytest.raises(NotOwned):
        p.delete_event("c", "u1")
    assert calls == ["GET", "GET"]  # never PUT / DELETE


def test_not_connected_provider_refuses():
    with pytest.raises(ProviderNotConfigured):
        provider(lambda r: httpx.Response(200), ready=False).list_calendars()


def test_executor_creates_in_google_idempotently_with_lost_response(calendar_pdf):
    """End-to-end through the real planner/executor with a fake Google that loses one response."""
    store = Store(":memory:")
    db: dict[str, dict] = {}
    state = {"n": 0}

    def h(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "GET" and "privateExtendedProperty" in req.url.params:
            sid = req.url.params["privateExtendedProperty"].split("=", 1)[1]
            return httpx.Response(
                200,
                json={
                    "items": [
                        e
                        for e in db.values()
                        if e["extendedProperties"]["private"][OWNER_PROP] == sid
                    ]
                },
            )
        if req.method == "GET" and path.endswith("/events"):
            return httpx.Response(200, json={"items": list(db.values())})
        if req.method == "POST":
            state["n"] += 1
            body = json.loads(req.content)
            gid = f"g{state['n']}"
            db[gid] = {"id": gid, **body}
            if state["n"] == 1:
                raise httpx.ReadTimeout("response lost")  # created server-side, client sees timeout
            return httpx.Response(200, json=db[gid])
        return httpx.Response(404)

    p = provider(h)
    events = ready_events(calendar_pdf)[:3]
    items = plan_sync(events, {}, p.list_events("c", date(2025, 1, 1), date(2026, 12, 31)))
    rep = execute_plan(items, events, p, "c", store, sleep=lambda s: None)
    assert len(db) == 3 and rep.count("failed") == 0  # no duplicate despite the lost response
    assert all(e["extendedProperties"]["private"][BATCH_PROP] for e in db.values())
    again = plan_sync(
        events,
        store.manifest("google", "c"),
        p.list_events("c", date(2025, 1, 1), date(2026, 12, 31)),
    )
    assert all(i.action == "skip" for i in again)


# ---------------- OAuth ----------------
def make_oauth(handler=None, **kw):
    store = Store(":memory:")
    http = httpx.Client(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(500))))
    s = settings(**kw)
    return GoogleOAuth(s, http, store, TokenVault(store, s.token_encryption_key)), store


def token_ok(req):
    return httpx.Response(
        200,
        json={"access_token": "ya29.NEWTOKEN", "refresh_token": "1//REFRESH", "expires_in": 3600},
    )


def test_start_builds_pkce_url_with_least_privilege_scopes():
    oauth, store = make_oauth()
    q = parse_qs(urlparse(oauth.start()).query)
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    scopes = q["scope"][0].split()
    assert scopes == [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    ]
    assert store.consume_oauth_state(q["state"][0]) is not None


def test_state_must_match_and_is_single_use():
    oauth, _ = make_oauth(token_ok)
    state = parse_qs(urlparse(oauth.start()).query)["state"][0]
    with pytest.raises(OAuthError):
        oauth.callback("code", "forged-state")
    oauth.callback("code", state)
    assert oauth.connected
    with pytest.raises(OAuthError):
        oauth.callback("code", state)  # replay


def test_expired_state_rejected():
    from datetime import UTC, datetime, timedelta

    oauth, store = make_oauth(token_ok)
    store.create_oauth_state("old", "v", now=datetime.now(UTC) - timedelta(minutes=30))
    with pytest.raises(OAuthError):
        oauth.callback("code", "old")


def test_code_exchange_sends_verifier_and_tokens_are_encrypted_at_rest():
    sent = {}

    def h(req):
        sent.update({k: v[0] for k, v in parse_qs(req.content.decode()).items()})
        return token_ok(req)

    oauth, store = make_oauth(h)
    oauth.callback("the-code", parse_qs(urlparse(oauth.start()).query)["state"][0])
    assert sent["grant_type"] == "authorization_code" and sent["code_verifier"]
    raw = store.load_token_blob("google")
    assert raw and "NEWTOKEN" not in raw and "REFRESH" not in raw  # ciphertext only
    assert oauth.access_token() == "ya29.NEWTOKEN"


def test_expired_access_token_is_refreshed_keeping_refresh_token():
    oauth, _ = make_oauth(
        lambda r: httpx.Response(200, json={"access_token": "ya29.SECOND", "expires_in": 3600})
    )
    oauth.vault.save(
        "google",
        {"access_token": "old", "refresh_token": "1//KEEP", "expires_at": time.time() - 10},
    )
    assert oauth.access_token() == "ya29.SECOND"
    assert oauth.vault.load("google")["refresh_token"] == "1//KEEP"


def test_failed_exchange_does_not_echo_provider_body():
    oauth, _ = make_oauth(lambda r: httpx.Response(400, text="invalid_grant code=SECRETCODE"))
    with pytest.raises(OAuthError) as e:
        oauth.callback("c", parse_qs(urlparse(oauth.start()).query)["state"][0])
    assert "SECRETCODE" not in str(e.value)


def test_vault_refuses_without_encryption_key():
    store = Store(":memory:")
    with pytest.raises(ProviderNotConfigured):
        TokenVault(store, None).save("google", {"access_token": "x"})


def test_missing_credentials_means_not_configured():
    store = Store(":memory:")
    oauth = GoogleOAuth(Settings(), httpx.Client(), store, TokenVault(store, None))
    assert not oauth.configured
    with pytest.raises(ProviderNotConfigured):
        oauth.start()


def test_redaction_of_tokens_in_text_and_logs(caplog):
    txt = (
        "Authorization: Bearer ya29.abcDEF-123 refresh_token=1//0gXYZ code=4/0AQ client_secret=shh"
    )
    out = redact(txt)
    for secret in ("ya29.abcDEF-123", "1//0gXYZ", "4/0AQ", "shh"):
        assert secret not in out
    logger = logging.getLogger("t")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t"):
        logger.info("got token ya29.LEAKME and access_token=abc123")
    assert "LEAKME" not in caplog.text and "abc123" not in caplog.text


# ---------------- HTTP surface ----------------
def _configured_client(handler=token_ok):
    """App wired with Google credentials and a mocked Google transport."""
    import app.api.main as m

    store = Store(":memory:")
    s = settings()
    orig = m.get_settings
    m.get_settings = lambda: s  # type: ignore[assignment]
    try:
        client = TestClient(
            create_app(store, {}, httpx.Client(transport=httpx.MockTransport(handler))),
            follow_redirects=False,
        )
    finally:
        m.get_settings = orig
    return client, store


def test_api_oauth_unconfigured():
    c = TestClient(create_app(Store(":memory:"), {}), follow_redirects=False)
    assert c.get("/api/oauth/google/start").status_code == 503
    r = c.get("/api/oauth/google/callback", params={"code": "c", "state": "s"})
    assert r.status_code == 302 and "google=error" in r.headers["location"]
    assert "reason=not_configured" in r.headers["location"]
    assert c.get("/api/providers/google/calendars").status_code == 503


def test_oauth_flow_redirects_back_to_app_without_leaking_anything():
    client, _ = _configured_client()
    url = client.get("/api/oauth/google/start").json()["auth_url"]
    assert url.startswith("https://accounts.google.com/")
    bad = client.get("/api/oauth/google/callback", params={"code": "c", "state": "forged"})
    assert bad.status_code == 302 and "reason=oauth_failed" in bad.headers["location"]
    state = parse_qs(urlparse(url).query)["state"][0]
    ok = client.get("/api/oauth/google/callback", params={"code": "SECRETCODE", "state": state})
    assert ok.status_code == 302
    loc = ok.headers["location"]
    assert loc.startswith("http://localhost:3000/connect?") and "google=connected" in loc
    for secret in ("SECRETCODE", "NEWTOKEN", "REFRESH", state):
        assert secret not in loc
    prov = {p["id"]: p for p in client.get("/api/providers").json()}
    assert prov["google"]["available"] is True


def test_user_cancelling_at_google_is_reported_as_denied():
    client, _ = _configured_client()
    r = client.get("/api/oauth/google/callback", params={"error": "access_denied"})
    assert r.status_code == 302 and "reason=denied" in r.headers["location"]


def test_disconnect_forgets_tokens_and_provider_becomes_unavailable():
    client, store = _configured_client()
    state = parse_qs(urlparse(client.get("/api/oauth/google/start").json()["auth_url"]).query)[
        "state"
    ][0]
    client.get("/api/oauth/google/callback", params={"code": "c", "state": state})
    assert store.load_token_blob("google") is not None
    assert client.post("/api/oauth/google/disconnect").json() == {"connected": False}
    assert store.load_token_blob("google") is None
    prov = {p["id"]: p for p in client.get("/api/providers").json()}
    assert prov["google"]["available"] is False and prov["google"]["reason"] == "not connected"
    assert client.get("/api/providers/google/calendars").status_code == 409


def test_calendar_listing_for_connected_google_and_for_demo():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/token"):
            return token_ok(req)
        assert req.headers["authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": "work@x", "summary": "Work"},
                    {"id": "test@x", "summary": "SchoolSync TEST"},
                ]
            },
        )

    client, _ = _configured_client(handler)
    state = parse_qs(urlparse(client.get("/api/oauth/google/start").json()["auth_url"]).query)[
        "state"
    ][0]
    client.get("/api/oauth/google/callback", params={"code": "c", "state": state})
    assert client.get("/api/providers/google/calendars").json() == [
        {"id": "work@x", "name": "Work"},
        {"id": "test@x", "name": "SchoolSync TEST"},
    ]
    demo = TestClient(create_app(Store(":memory:"), {"mock": MockProvider()}))
    assert demo.get("/api/providers/mock/calendars").json()[0]["id"] == "demo"


def test_global_log_redaction_covers_any_logger(caplog):
    from app.providers.oauth import install_log_redaction

    install_log_redaction()
    with caplog.at_level(logging.INFO):
        logging.getLogger("some.other.module").warning("calling with Bearer ya29.GLOBALLEAK")
    assert "GLOBALLEAK" not in caplog.text and "[REDACTED]" in caplog.text
