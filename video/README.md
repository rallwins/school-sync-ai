# Demo video

**Status: recorded** (silent screen capture with on-screen captions; no voice narration).

- File: `video/schoolsync-demo.webm` (~154 s, ~14.5 MB, 1280x720)
- Source: a real, unedited run of the UI by `frontend/e2e/record-demo.mjs` against local servers
  on a fresh data directory, using only the synthetic fixture. Per-scene timestamps are in
  `video/timeline.json`. `video/sample-export.ics` is the ICS that run downloaded.
- Not shown: Google/Outlook sync (not verified against real services), scanned PDFs, the real
  school calendar (private; see `docs/real-calendar-validation.md`).
- I checked two captured frames by eye; I have not watched the whole video.

## Re-record
```powershell
# backend on :8000 with a FRESH SCHOOLSYNC_DATA_DIR, frontend built and started on :3000
cd frontend
node e2e/record-demo.mjs
```

## Scenes (actual offsets)
0:00 upload synthetic PDF, 0:11 legend mapping, 0:22 unlisted colour flagged, 0:38 half day
with no time blocked, 0:54 colour-only cell resolved by a person, 1:08 calendar view, 1:21 ICS
download, 1:35 sync preview, 1:46 report, 1:54 re-sync skips all 8, 2:04 same PDF re-imported and
recognised, 2:20 closing card with what is and is not proven.
