# Runbook

**Run locally:** see README ("Run locally"). Backend `:8000`, frontend `:3000`.

**Kill switch:** set `SCHOOLSYNC_SYNC_ENABLED=false` and restart. All sync/rollback endpoints return
503 `sync_disabled`; file export keeps working. On Lambda:
`aws lambda update-function-configuration --function-name schoolsync-backend --environment ...`
(this replaces the whole variable set, so include the key and upload cap too), or redeploy the stack.

**Demo is slow on first request:** Lambda cold start measured at ~20 s. Retry once; the Vercel proxy
waits up to 55 s.

**409 `plan_changed` on confirm:** the destination or events changed, or the request hit a
different Lambda instance. Preview again, then confirm.

**Provider shows "not connected":** complete the Google OAuth flow
(`GET /api/oauth/google/start` returns the URL). Setup: `docs/google-oauth-setup.md`.

**Roll back a sync:** `POST /api/sync/rollback/{batch_id}` with `{"confirm": true}` (UI: "Roll back
this batch"). Deletes only events mapped to that batch that still carry our owner property.

**Redeploy / teardown / cost:** `infra/aws/README.md`.
