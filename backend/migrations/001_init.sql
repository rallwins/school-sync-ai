-- Portable SQL (SQLite now; types/constraints chosen to port to PostgreSQL).
CREATE TABLE IF NOT EXISTS imports (
  id           TEXT PRIMARY KEY,
  created_at   TEXT NOT NULL,
  source_hash  TEXT NOT NULL,
  school       TEXT NOT NULL,
  academic_yr  TEXT NOT NULL,
  timezone     TEXT NOT NULL,
  events_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_imports_school ON imports (school, academic_yr, created_at);

CREATE TABLE IF NOT EXISTS provider_map (
  stable_id         TEXT NOT NULL,
  provider          TEXT NOT NULL,
  calendar_id       TEXT NOT NULL,
  provider_event_id TEXT NOT NULL,
  fingerprint       TEXT NOT NULL,
  batch_id          TEXT NOT NULL,
  synced_at         TEXT NOT NULL,
  rolled_back       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (stable_id, provider, calendar_id)
);

CREATE TABLE IF NOT EXISTS audit (
  ts      TEXT NOT NULL,
  action  TEXT NOT NULL,
  detail  TEXT NOT NULL
);
