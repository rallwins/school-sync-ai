"""SQLite persistence for imports, the provider event mapping (manifest) and an audit trail.

Plain sqlite3 + portable SQL so a PostgreSQL implementation can replace it behind this class.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import CalendarEvent

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


@dataclass
class ManifestRecord:
    stable_id: str
    provider: str
    calendar_id: str
    provider_event_id: str
    fingerprint: str
    batch_id: str


@dataclass
class ImportRow:
    id: str
    created_at: str
    source_hash: str
    school: str
    academic_year: str
    timezone: str
    events: list[CalendarEvent]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        for f in sorted(MIGRATIONS.glob("*.sql")):
            self.db.executescript(f.read_text())

    # ---- imports ----
    def save_import(
        self, source_hash: str, school: str, year: str, tz: str, events: list[CalendarEvent]
    ) -> ImportRow:
        iid = uuid.uuid4().hex[:16]
        ts = _now()
        self.db.execute(
            "INSERT INTO imports VALUES (?,?,?,?,?,?,?)",
            (iid, ts, source_hash, school, year, tz,
             json.dumps([e.model_dump(mode="json") for e in events])),
        )  # fmt: skip
        self.db.commit()
        self.audit("import.saved", f"{iid} events={len(events)}")
        return ImportRow(iid, ts, source_hash, school, year, tz, events)

    def _row(self, r: sqlite3.Row) -> ImportRow:
        return ImportRow(
            r["id"], r["created_at"], r["source_hash"], r["school"], r["academic_yr"],
            r["timezone"], [CalendarEvent.model_validate(x) for x in json.loads(r["events_json"])],
        )  # fmt: skip

    def list_imports(self) -> list[ImportRow]:
        rows = self.db.execute("SELECT * FROM imports ORDER BY created_at DESC, rowid DESC")
        return [self._row(r) for r in rows]

    def previous_import(self, school: str, year: str) -> ImportRow | None:
        r = self.db.execute(
            "SELECT * FROM imports WHERE school=? AND academic_yr=? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (school, year),
        ).fetchone()
        return self._row(r) if r else None

    # ---- manifest ----
    def manifest(self, provider: str, calendar_id: str) -> dict[str, ManifestRecord]:
        rows = self.db.execute(
            "SELECT * FROM provider_map WHERE provider=? AND calendar_id=? AND rolled_back=0",
            (provider, calendar_id),
        )
        return {
            r["stable_id"]: ManifestRecord(
                r["stable_id"], r["provider"], r["calendar_id"], r["provider_event_id"],
                r["fingerprint"], r["batch_id"],
            )
            for r in rows
        }  # fmt: skip

    def upsert_mapping(self, m: ManifestRecord) -> None:
        self.db.execute(
            "INSERT INTO provider_map VALUES (?,?,?,?,?,?,?,0) "
            "ON CONFLICT(stable_id, provider, calendar_id) DO UPDATE SET "
            "provider_event_id=excluded.provider_event_id, fingerprint=excluded.fingerprint, "
            "batch_id=excluded.batch_id, synced_at=excluded.synced_at, rolled_back=0",
            (m.stable_id, m.provider, m.calendar_id, m.provider_event_id, m.fingerprint,
             m.batch_id, _now()),
        )  # fmt: skip
        self.db.commit()

    def batch_mappings(self, batch_id: str) -> list[ManifestRecord]:
        rows = self.db.execute(
            "SELECT * FROM provider_map WHERE batch_id=? AND rolled_back=0", (batch_id,)
        )
        return [
            ManifestRecord(r["stable_id"], r["provider"], r["calendar_id"],
                           r["provider_event_id"], r["fingerprint"], r["batch_id"])
            for r in rows
        ]  # fmt: skip

    def mark_rolled_back(self, m: ManifestRecord) -> None:
        self.db.execute(
            "UPDATE provider_map SET rolled_back=1 WHERE stable_id=? AND provider=? AND calendar_id=?",
            (m.stable_id, m.provider, m.calendar_id),
        )
        self.db.commit()

    # ---- OAuth state + encrypted token blobs ----
    def create_oauth_state(self, state: str, verifier: str, now: datetime | None = None) -> None:
        ts = (now or datetime.now(UTC)).isoformat()
        self.db.execute("INSERT INTO oauth_states VALUES (?,?,?,0)", (state, verifier, ts))
        self.db.commit()

    def consume_oauth_state(
        self, state: str, ttl_seconds: int = 600, now: datetime | None = None
    ) -> str | None:
        """Return the PKCE verifier once; None if unknown, expired or already used."""
        r = self.db.execute("SELECT * FROM oauth_states WHERE state=?", (state,)).fetchone()
        if r is None or r["used"]:
            return None
        self.db.execute("UPDATE oauth_states SET used=1 WHERE state=?", (state,))
        self.db.commit()
        age = (now or datetime.now(UTC)) - datetime.fromisoformat(r["created_at"])
        return None if age.total_seconds() > ttl_seconds else str(r["verifier"])

    def save_token_blob(self, provider: str, blob: str) -> None:
        self.db.execute(
            "INSERT INTO oauth_tokens VALUES (?,?,?) ON CONFLICT(provider) DO UPDATE SET "
            "blob=excluded.blob, updated_at=excluded.updated_at",
            (provider, blob, _now()),
        )
        self.db.commit()

    def load_token_blob(self, provider: str) -> str | None:
        r = self.db.execute(
            "SELECT blob FROM oauth_tokens WHERE provider=?", (provider,)
        ).fetchone()
        return str(r["blob"]) if r else None

    def delete_token_blob(self, provider: str) -> None:
        self.db.execute("DELETE FROM oauth_tokens WHERE provider=?", (provider,))
        self.db.commit()

    def audit(self, action: str, detail: str) -> None:
        self.db.execute("INSERT INTO audit VALUES (?,?,?)", (_now(), action, detail))
        self.db.commit()
