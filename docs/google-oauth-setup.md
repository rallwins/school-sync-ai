# Google Calendar setup (NOT yet verified against real Google)

The adapter is tested against mocked HTTP only. Use a **test Google account and a throwaway
calendar** for the first run. The app never connects or writes without your explicit confirmation.

1. Google Cloud console -> create a project -> enable "Google Calendar API".
2. OAuth consent screen: External, add yourself as a test user.
3. Credentials -> OAuth client ID -> Web application. Authorised redirect URI:
   `http://localhost:8000/api/oauth/google/callback`
4. Generate an encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
5. Put these in `.env` (never commit it):
   ```
   SCHOOLSYNC_GOOGLE_CLIENT_ID=...
   SCHOOLSYNC_GOOGLE_CLIENT_SECRET=...
   SCHOOLSYNC_TOKEN_ENCRYPTION_KEY=<key from step 4>
   ```
6. Restart the backend, open `GET /api/oauth/google/start`, follow `auth_url`, approve.
7. `GET /api/providers/google/calendars` lists writable calendars.

Scopes requested: `calendar.events` and `calendar.calendarlist.readonly` only.
The frontend does not yet have a Google connection or calendar-picker page; sync to Google through
the UI is therefore not wired (the API path exists).
