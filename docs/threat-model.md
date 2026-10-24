# Threat model

Scope: the app as built, including the Vercel + Lambda demo. Status column is honest: "tested"
means an automated test exists; "design only" means no test.

| # | Threat | Mitigation | Status |
|---|---|---|---|
| 1 | Malicious/oversized/malformed PDF | Magic bytes, size cap, full parse, page cap, encrypted PDFs rejected; read capped at limit+1 | tested |
| 2 | PDF parser exploit (memory corruption) | PyMuPDF is native code; run in a container/Lambda sandbox; keep dependency pinned and audited in CI | design only |
| 3 | Unauthorised use of the public demo | `X-API-Key` required on `/api/*`; key only on the Vercel server side | tested (backend gate), live smoke-tested |
| 4 | Abuse/cost via the public demo | Lambda concurrency quota 10, 4 MB upload cap, $5 budget alert (email only, does not stop spend) | partly design only |
| 5 | Writing to or altering unrelated calendar events | Owner property required for update/delete, enforced in planner and adapter; conflicts never executed | tested |
| 6 | Accidental sync | Confirmation bound to the previewed plan token; kill switch `SCHOOLSYNC_SYNC_ENABLED=false` | tested |
| 7 | OAuth CSRF / code injection | Random single-use 10-min state, PKCE S256, redirect URI fixed in config | tested (mocked Google) |
| 8 | Token theft at rest | Fernet-encrypted blobs; refuses to store without a key | tested; key management is design only |
| 9 | Token leakage in logs/errors | `redact()` + log filter; provider error bodies are not echoed | tested (global log-record factory installed at app start) |
| 10 | CSV formula injection | Cells starting with `= + - @ tab CR` are prefixed with `'` | tested |
| 11 | Client trusting itself (skipping review) | Server recomputes readiness on export and sync | tested |
| 12 | Secrets in the repo | `.env`, `.deploy/`, `.vercel/` ignored; `.env.example` placeholders; Gitleaks job in CI (never run) | partly tested |
| 13 | Cross-user data exposure | The app has **no user accounts**; imports and manifest are global per instance. Not safe for real multi-user use | known gap |
| 14 | Stored PDFs/personal data | PDFs are processed in memory and not stored; extracted events are stored in SQLite | design only |

Trust boundaries: Browser -> Vercel (HTTPS) -> Lambda Function URL (HTTPS, key) -> app -> provider
APIs (HTTPS, OAuth bearer). Diagram: `docs/diagrams/trust-boundaries.mmd`.
