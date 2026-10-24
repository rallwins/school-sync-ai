"""OAuth 2.0 (authorization code + PKCE) for Google, plus token vault and log redaction.

- state: random, single-use, 10-minute TTL, stored server-side with its PKCE verifier (CSRF).
- tokens: Fernet-encrypted before they reach the database; never logged (see redact()).
- scopes: least privilege. calendar.events lets us create/update events in calendars the user
  picks; calendar.calendarlist.readonly lets us list calendars. No full-calendar access.
"""

import base64
import hashlib
import json
import logging
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.imports.store import Store
from app.providers.base import ProviderError, ProviderNotConfigured

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    # lets the app create its own secondary calendar (and only manage calendars it created)
    "https://www.googleapis.com/auth/calendar.app.created",
]

_SECRET_PATTERNS = [
    re.compile(r"ya29\.[\w\-.]+"),  # Google access tokens
    re.compile(r"1//[\w\-]+"),  # Google refresh tokens
    re.compile(r"(?i)bearer\s+[\w\-.~+/=]+"),
    re.compile(
        r"(?i)((?:access_token|refresh_token|client_secret|code|code_verifier)[\"'=:\s]+)[^\s&\"',}]+"
    ),
]


def redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", out)
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


_installed = False


def install_log_redaction() -> None:
    """Redact secrets from every log record, whichever logger/handler emits it.

    Redacts the message template and any string arguments IN PLACE and keeps the argument
    tuple's shape: uvicorn's access formatter unpacks exactly five args, so collapsing them into
    a pre-formatted message (an earlier version did) broke every request log line.
    """
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return record

    logging.setLogRecordFactory(factory)
    _installed = True


class OAuthError(ProviderError):
    pass


class TokenVault:
    def __init__(self, store: Store, key: str | None) -> None:
        self.store = store
        self._fernet = Fernet(key.encode()) if key else None

    @property
    def usable(self) -> bool:
        return self._fernet is not None

    def save(self, provider: str, tokens: dict[str, object]) -> None:
        if self._fernet is None:
            raise ProviderNotConfigured(
                "TOKEN_ENCRYPTION_KEY is not set; refusing to store tokens."
            )
        blob = self._fernet.encrypt(json.dumps(tokens).encode()).decode()
        self.store.save_token_blob(provider, blob)

    def load(self, provider: str) -> dict[str, object] | None:
        blob = self.store.load_token_blob(provider)
        if blob is None or self._fernet is None:
            return None
        try:
            return json.loads(self._fernet.decrypt(blob.encode()))  # type: ignore[no-any-return]
        except InvalidToken:
            return None


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


class GoogleOAuth:
    def __init__(self, settings: Settings, http: httpx.Client, store: Store, vault: TokenVault):
        self.s, self.http, self.store, self.vault = settings, http, store, vault

    @property
    def configured(self) -> bool:
        return bool(self.s.google_client_id and self.s.google_client_secret and self.vault.usable)

    @property
    def connected(self) -> bool:
        return self.vault.load("google") is not None

    def disconnect(self) -> None:
        """Forget the stored tokens. (Revoking at Google is left to the user's account page.)"""
        self.store.delete_token_blob("google")
        self.store.audit("oauth.disconnected", "google")

    def start(self) -> str:
        if not self.configured:
            raise ProviderNotConfigured(
                "Google OAuth credentials or encryption key not configured."
            )
        state = secrets.token_urlsafe(32)
        verifier, challenge = pkce_pair()
        self.store.create_oauth_state(state, verifier)
        return (
            AUTH_URL
            + "?"
            + urlencode(
                {
                    "client_id": self.s.google_client_id,
                    "redirect_uri": self.s.google_redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(SCOPES),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "access_type": "offline",
                    "prompt": "consent",
                }
            )
        )

    def callback(self, code: str, state: str) -> None:
        if not self.configured:
            raise ProviderNotConfigured("Google OAuth not configured.")
        verifier = self.store.consume_oauth_state(state)
        if verifier is None:
            raise OAuthError("Invalid, expired or reused OAuth state.")
        self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.s.google_redirect_uri,
                "code_verifier": verifier,
            }
        )
        self.store.audit("oauth.connected", "google")

    def _token_request(self, form: dict[str, str], keep_refresh: str | None = None) -> None:
        body = {**form, "client_id": self.s.google_client_id or "",
                "client_secret": self.s.google_client_secret or ""}  # fmt: skip
        try:
            r = self.http.post(TOKEN_URL, data=body, timeout=10)
        except httpx.HTTPError as e:
            raise OAuthError("Token endpoint unreachable.") from e
        if r.status_code != 200:
            raise OAuthError(f"Token exchange failed (HTTP {r.status_code}).")  # body not echoed
        data = r.json()
        self.vault.save(
            "google",
            {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", keep_refresh),
                "expires_at": time.time() + int(data.get("expires_in", 3600)),
            },
        )

    def access_token(self) -> str:
        t = self.vault.load("google")
        if t is None:
            raise ProviderNotConfigured("Google is not connected.")
        if float(t["expires_at"]) - 60 > time.time():  # type: ignore[arg-type]
            return str(t["access_token"])
        refresh = t.get("refresh_token")
        if not refresh:
            raise OAuthError("Access token expired and no refresh token; reconnect Google.")
        self._token_request({"grant_type": "refresh_token", "refresh_token": str(refresh)},
                            keep_refresh=str(refresh))  # fmt: skip
        return str((self.vault.load("google") or {})["access_token"])
