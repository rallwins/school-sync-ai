"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ApiError, createCalendar, listCalendars, listProviders, oauthDisconnect, oauthStart } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { CalendarOption, ProviderInfo } from "@/lib/types";

const REASONS: Record<string, string> = {
  denied: "You cancelled at Google, so nothing was connected.",
  oauth_failed: "Google sign-in could not be completed (the link may have expired). Try again.",
  bad_request: "The sign-in response was incomplete. Try again.",
  not_configured: "Google credentials are not configured on this server.",
};

function ConnectInner() {
  const params = useSearchParams();
  const { destination, setDestination, meta } = useStore();
  const [calName, setCalName] = useState("");
  const [existing, setExisting] = useState<CalendarOption | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [calendars, setCalendars] = useState<CalendarOption[]>([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const p = await listProviders();
      setProviders(p);
      if (p.find((x) => x.id === "google")?.available) {
        setCalendars(await listCalendars("google"));
      } else {
        setCalendars([]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the API.");
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  // prefill the new calendar's name with the school name (editable)
  useEffect(() => {
    if (meta?.school) setCalName((cur) => cur || meta.school);
  }, [meta?.school]);

  const google = providers.find((p) => p.id === "google");
  const demo = providers.find((p) => p.id === "mock");
  const status = params.get("google");

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Unexpected error.");
    } finally {
      setBusy(false);
    }
  }

  const btn = "rounded border border-line px-3 py-1.5 disabled:opacity-50";
  const primary = "rounded bg-accent px-3 py-1.5 font-medium text-white disabled:opacity-50 dark:text-black";

  return (
    <div className="max-w-2xl space-y-5">
      <h1 className="text-xl font-semibold">Connect a destination</h1>
      <p className="text-sm text-muted">
        Connecting does not change any calendar. Nothing is written until you preview a plan and
        confirm it on the Export &amp; sync page. You can always download an ICS/CSV file instead.
      </p>

      {status === "connected" && (
        <p role="status" className="rounded border border-ok p-3 text-sm text-ok">Google connected. Choose a calendar below.</p>
      )}
      {status === "error" && (
        <p role="alert" className="rounded border border-danger p-3 text-sm text-danger">
          {REASONS[params.get("reason") ?? ""] ?? "Google connection failed."}
        </p>
      )}
      <p role="alert" className="text-sm text-danger">{error}</p>

      <section aria-labelledby="h-google" className="rounded border border-line bg-surface p-4 text-sm">
        <h2 id="h-google" className="font-semibold">Google Calendar</h2>
        {!google && <p className="mt-2 text-muted">Loading…</p>}

        {google && !google.available && google.reason === "not configured" && (
          <p className="mt-2 text-muted">
            Not configured on this server. Google sign-in only works on a server you run yourself with your own
            OAuth credentials (see <code>docs/google-oauth-setup.md</code>). It is deliberately disabled on the
            public demo, which has no user accounts.
          </p>
        )}

        {google && !google.available && google.reason === "not connected" && (
          <div className="mt-2 space-y-2">
            <p>
              Asks Google for two permissions only: create/edit events, and list your calendars. It will not read
              your other events, and it never deletes or edits events it did not create.
            </p>
            <button
              className={primary}
              disabled={busy}
              onClick={() => act(async () => { window.location.href = (await oauthStart()).auth_url; })}
            >
              Connect Google
            </button>
            <p className="text-xs text-muted">Use a test Google account or a throwaway calendar for the first run.</p>
          </div>
        )}

        {google?.available && (
          <div className="mt-2 space-y-3">
            <p className="text-ok">Connected.</p>
            <label className="block">
              Calendar to write to
              <select
                className="mt-1 w-full rounded border border-line bg-surface px-2 py-1"
                value={pick}
                onChange={(e) => setPick(e.target.value)}
              >
                <option value="">Choose a calendar…</option>
                {calendars.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <div className="flex gap-2">
              <button
                className={primary}
                disabled={!pick}
                onClick={() => {
                  const c = calendars.find((x) => x.id === pick);
                  if (c) setDestination({ provider: "google", calendarId: c.id, calendarName: c.name });
                }}
              >
                Use this calendar
              </button>
              <button
                className={btn}
                disabled={busy}
                onClick={() => act(async () => { window.location.href = (await oauthStart()).auth_url; })}
              >
                Reconnect
              </button>
              <button
                className={btn}
                disabled={busy}
                onClick={() => act(async () => {
                  await oauthDisconnect();
                  if (destination?.provider === "google") setDestination(null);
                  setPick("");
                  await refresh();
                })}
              >
                Disconnect
              </button>
            </div>
            <p className="text-xs text-muted">
              Disconnect forgets the stored tokens here. To revoke access completely, remove the app in your
              Google Account security settings.
            </p>
          </div>
        )}
      </section>

      {google?.available && (
        <section aria-labelledby="h-create" className="rounded border border-line bg-surface p-4 text-sm">
          <h2 id="h-create" className="font-semibold">Create a calendar for this school</h2>
          <p className="mt-1 text-muted">
            Makes a new, separate Google calendar so these events never mix with your own. Nothing is created until you confirm.
          </p>
          <label className="mt-2 block">
            Calendar name
            <input
              className="mt-1 w-full rounded border border-line bg-surface px-2 py-1"
              value={calName}
              maxLength={100}
              onChange={(e) => { setCalName(e.target.value); setExisting(null); }}
              placeholder="Import a PDF first to prefill the school name"
            />
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              className={primary}
              disabled={busy || calName.trim() === ""}
              onClick={() => act(async () => {
                const name = calName.trim();
                if (!window.confirm(`Create a new Google calendar named \u201c${name}\u201d in your account?`)) return;
                try {
                  const c = await createCalendar("google", name, meta?.timezone ?? "Asia/Kolkata");
                  setDestination({ provider: "google", calendarId: c.id, calendarName: c.name });
                  setCreated(`Created \u201c${c.name}\u201d and selected it as the destination.`);
                  setExisting(null);
                  await refresh();
                } catch (e) {
                  if (e instanceof ApiError && e.code === "calendar_exists" && e.extra?.calendar) setExisting(e.extra.calendar);
                  throw e;
                }
              })}
            >
              Create calendar…
            </button>
            {existing && (
              <button
                className={btn}
                onClick={() => {
                  setDestination({ provider: "google", calendarId: existing.id, calendarName: existing.name });
                  setCreated(`Using the existing calendar \u201c${existing.name}\u201d.`);
                  setError(null);
                }}
              >
                Use the existing \u201c{existing.name}\u201d
              </button>
            )}
          </div>
          {created && <p role="status" className="mt-2 text-ok">{created}</p>}
          <p className="mt-2 text-xs text-muted">
            If creation is refused, press Reconnect above once: creating calendars needs one extra Google permission
            (it only lets this app manage calendars it created itself).
          </p>
        </section>
      )}

      <section aria-labelledby="h-demo" className="rounded border border-line bg-surface p-4 text-sm">
        <h2 id="h-demo" className="font-semibold">Demo calendar</h2>
        <p className="mt-1 text-muted">In memory on the server; nothing leaves it. Good for trying the flow.</p>
        <button
          className={`${btn} mt-2`}
          disabled={!demo?.available}
          onClick={() => setDestination({ provider: "mock", calendarId: "demo", calendarName: "Demo calendar (in-memory)" })}
        >
          Use the demo calendar
        </button>
      </section>

      <section aria-labelledby="h-dest" className="rounded border border-line bg-surface p-4 text-sm">
        <h2 id="h-dest" className="font-semibold">Current destination</h2>
        <p role="status" className="mt-1">
          {destination
            ? `${destination.provider === "google" ? "Google" : "Demo"}: ${destination.calendarName}`
            : "None chosen (sync will offer the demo calendar)."}
        </p>
        <div className="mt-2 flex gap-3">
          <Link className="text-accent underline" href="/sync">Go to Export &amp; sync</Link>
          {destination && (
            <button className="text-muted underline" onClick={() => setDestination(null)}>Clear</button>
          )}
        </div>
      </section>
    </div>
  );
}

export default function ConnectPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <ConnectInner />
    </Suspense>
  );
}
