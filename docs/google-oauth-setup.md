# Google Calendar setup (NOT yet verified against real Google)

The adapter and the Connect page are tested against mocked HTTP and a mocked browser network only;
they have **never** been run against real Google. Use a **test Google account and a throwaway
calendar** for the first run. The app never connects or writes without your explicit confirmation.

1. Google Cloud console -> create a project -> enable "Google Calendar API".
2. OAuth consent screen: External, add yourself as a test user.
3. Credentials -> OAuth client ID -> Web application. Authorised redirect URI:
   `http://localhost:8000/api/oauth/google/callback`
4. Generate an encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
5. Put these in `backend/.env` (never commit it; the backend reads `.env` from its own folder):
   ```
   SCHOOLSYNC_GOOGLE_CLIENT_ID=...
   SCHOOLSYNC_GOOGLE_CLIENT_SECRET=...
   SCHOOLSYNC_TOKEN_ENCRYPTION_KEY=<key from step 4>
   ```
6. Restart the backend and the frontend (`SCHOOLSYNC_FRONTEND_URL` defaults to http://localhost:3000).
7. In the app open **Connect**, press **Connect Google**, approve, then pick the calendar to write to
   (use a throwaway test calendar). Sync then targets exactly that calendar, shows a REAL-calendar
   warning, and still needs your plan confirmation. **Disconnect** forgets the stored tokens.

Scopes requested (least privilege, never the full `calendar` scope):
- `calendar.events`: create/update events (only events this app owns are ever changed or deleted)
- `calendar.calendarlist.readonly`: list your calendars so you can pick one
- `calendar.app.created`: create a NEW secondary calendar named after the school, and manage only
  calendars this app created

If you connected before `calendar.app.created` was added, press **Reconnect** on the Connect page
once; Google asks for the extra permission. Creating a calendar needs an explicit confirmation and
the app refuses to create a second calendar with the same name (it offers to use the existing one).

Colours: each legend category is mapped to one of Google's darker event colours by hue
(for example teal to Peacock, gold to Banana, orange to Tangerine, cream/grey to Graphite) and the
mapping is shown on the sync preview. Changing the mapping updates only events this app created.
Google is intentionally NOT enabled on the public demo (shared key, no user accounts): run it locally.

