# SchoolSync AI

Extract events from school calendar PDFs (including colour-coded legends and half-days),
review them, and export to ICS/CSV or sync to Google Calendar / Microsoft Outlook.

**Status: Milestone 3 of 5 complete (extraction, review UI, duplicate-safe export and demo sync).
A synthetic-data demo is live at https://schoolsync-ai.vercel.app (Vercel frontend, AWS Lambda
backend; see [infra/aws/README.md](infra/aws/README.md)). No real Google/Outlook calendar has ever been touched.**

| Capability | State |
|---|---|
| Upload validation (size, type, pages, malformed, encrypted) | Implemented, tested |
| Vector-PDF grid/date detection, legend parsing, CIE76 colour matching | Implemented; tested on 3 synthetic PDFs (cell-text and list-style layouts) and 1 real calendar |
| Full-day / half-day / timed rules (no assumed times) | Implemented, tested |
| Review UI: legend, table, month calendar, filters, edit + confirm, history | Implemented, 1 Playwright e2e |
| ICS export (date-valued all-day, exclusive DTEND, TZID, stable UIDs) | Implemented, parser-tested only |
| CSV export (formula-injection safe) | Implemented, tested; not imported into real clients |
| Duplicate layers A/B/C, re-import idempotence, revised-PDF diff | Implemented, tested against the mock provider |
| Sync preview, plan-token-bound confirmation, retries, partial success, rollback | Implemented, tested against the **in-memory mock provider only** |
| Kill switch (`SCHOOLSYNC_SYNC_ENABLED=false`) | Implemented, tested |
| SQLite import history + provider manifest | Implemented, tested |
| Google Calendar / Microsoft Graph adapters and OAuth | **Not implemented** (stubs report "not configured") |
| OCR / scanned PDFs | Not implemented (flagged and skipped; Tesseract not installed) |
| Stroked-line grids, icon/pattern legends | Not implemented |
| Source-page crop preview, settings page, provider connection page | Not implemented |
| Real school calendar (list-style, 2 months/page) | **113 events extracted from a real 9-page calendar** (row count matches the source page by page; sample of dates/titles checked by eye; file is private). 80 have no stated duration; bulk "treat as all-day" is an explicit user action. See [docs/real-calendar-validation.md](docs/real-calendar-validation.md) |
| Backend Docker image | Built and smoke-tested locally (health, extract, import) |
| `docker-compose.yml`, CI workflow | Written, never run |
| Deployment: Vercel + Lambda Function URL (CloudFormation) | Deployed; full e2e flow passed against the live URL |
| PPTX deck (`presentation/`), demo video (`video/`, silent + captions), ADRs 1-5, threat model, diagrams | Written; deck not visually reviewed, Mermaid not rendered |
| Google adapter + OAuth (PKCE, encrypted tokens) | Implemented, **mocked-HTTP tests only** |

## Verified results (this machine)

- Backend: 124 pytest tests pass; ruff and strict mypy clean.
- Frontend: `tsc` clean, 8 Vitest tests, production build, and 2 Playwright tests in Chromium against
  the live backend: upload, resolve a time-less half day and a colour-only ambiguous event, confirm
  legend, download ICS, preview 8 creates, explicit confirm, report, second preview shows 8 skips.
- Evaluation (`evaluation/run_eval.py`): precision/recall 1.0 on **3 synthetic PDFs, 26 labelled events** (Sunday-first; Monday-first with leap
  year, drifted colours and a text/legend conflict; list-style with two months per page). Same author,
  so this is a regression baseline, not real-world accuracy. The only real calendar tried is the one above.

## Design decisions worth knowing

- Half day with a printed time but no known start exports as an **all-day** event with the dismissal
  time in the title, unless you supply a school start time (then it is timed, and says so).
- Identity across revised PDFs is school + academic year + start date. A date change shows as one
  removal plus one addition. Removals are only ever proposed.
- Events the app did not create are never updated or deleted; look-alikes become conflicts.
- Importing an ICS file twice can still duplicate in some calendar clients.

## Run locally

```powershell
# terminal 1
cd backend; .venv\Scripts\python -m uvicorn app.api.main:app --port 8000
# terminal 2
cd frontend; npm install; npm run build; npx next start -p 3000
# terminal 3 (optional e2e)
cd frontend; npx playwright install chromium; npx playwright test
```

## Local setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy app
.venv\Scripts\python -m uvicorn app.api.main:app --reload   # http://localhost:8000/docs
```

Regenerate the synthetic fixture: `python data/synthetic/generate_fixtures.py`
(all data is fictional, "Maple Grove Academy"). Never commit real school PDFs; `.gitignore`
blocks `*.pdf` except under `data/synthetic/` and `evaluation/fixtures/`.

## Docs
- [Architecture](docs/architecture.md), [C4 diagram source](docs/diagrams/c4-container.mmd)
- [Security policy](SECURITY.md), [Contributing](CONTRIBUTING.md)
