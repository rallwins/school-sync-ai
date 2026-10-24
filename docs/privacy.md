# Privacy

- **Use synthetic data on any shared deployment.** The live demo has one shared key, no user
  accounts and no isolation between visitors. Do not upload real school documents to it.
- PDFs are validated and parsed in memory; the app does not write the uploaded file to disk.
- Extracted events (titles, dates, source text) are stored in SQLite for import history and the
  provider manifest. On Lambda this lives in `/tmp` and disappears when the instance recycles.
  Locally it persists in `SCHOOLSYNC_DATA_DIR` until you delete it; there is **no retention
  job yet** (planned: configurable retention in Settings).
- The browser keeps the current session (events, edits) in `sessionStorage`, cleared when the tab
  closes. No analytics or third-party scripts are loaded.
- OAuth tokens are encrypted before storage and are never returned by the API or logged. The demo
  has Google OAuth unconfigured, so no tokens exist there.
- Logs: Lambda logs go to CloudWatch with 14-day retention. Request bodies are not logged by the app.
