CREATE TABLE IF NOT EXISTS oauth_states (
  state       TEXT PRIMARY KEY,
  verifier    TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  used        INTEGER NOT NULL DEFAULT 0
);

-- Token blobs are Fernet-encrypted by the application; the database never sees plaintext.
CREATE TABLE IF NOT EXISTS oauth_tokens (
  provider    TEXT PRIMARY KEY,
  blob        TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
