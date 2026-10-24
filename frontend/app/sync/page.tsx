"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  downloadExport,
  executeSync,
  listProviders,
  previewSync,
  rollbackBatch,
} from "@/lib/api";
import { readiness, summarize } from "@/lib/readiness";
import { useStore } from "@/lib/store";
import type { ProviderInfo, SyncPreview, SyncReport } from "@/lib/types";

const ACTION_TEXT: Record<string, string> = {
  create: "Create",
  update: "Update",
  skip: "Skip",
  conflict: "Conflict",
  propose_remove: "Removal proposed",
};

export default function SyncPage() {
  const { result, events, meta, legendConfirmed, hydrated, importRec, destination } = useStore();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [dayStart, setDayStart] = useState("");
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [rolled, setRolled] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  if (!hydrated) return <p>Loading…</p>;
  if (!result || !meta)
    return (
      <p className="rounded border border-dashed border-line p-6 text-sm">
        Nothing to export. <Link className="text-accent underline" href="/">Import a PDF</Link> first.
      </p>
    );

  const s = summarize(events);
  const ready = events.filter((e) => readiness(e) === "ready");
  const blocked = events.filter((e) => readiness(e) !== "ready");
  const canAct = legendConfirmed && ready.length > 0;
  const demo = providers.find((p) => p.id === "mock");
  // No explicit choice -> the harmless in-memory demo calendar. A real calendar is never a default.
  const dest =
    destination ??
    (demo?.available ? { provider: "mock", calendarId: "demo", calendarName: "Demo calendar (in-memory)" } : null);
  const destProvider = providers.find((p) => p.id === dest?.provider);
  const isReal = !!dest && dest.provider !== "mock";
  const destLabel = dest ? `${isReal ? "your REAL Google calendar" : "the demo calendar"} “${dest.calendarName}”` : "";
  const body = () => ({ provider: dest?.provider ?? "mock", calendar_id: dest?.calendarId ?? "demo", events, day_start: dayStart || null });

  async function run<T>(fn: () => Promise<T>, done: (v: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Unexpected error.");
    } finally {
      setBusy(false);
    }
  }

  const btn = "rounded border border-line px-3 py-1.5 disabled:opacity-50";
  const primary = "rounded bg-accent px-3 py-1.5 font-medium text-white disabled:opacity-50 dark:text-black";

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-xl font-semibold">Export &amp; sync</h1>

      <dl className="grid grid-cols-3 gap-3 text-sm">
        {(
          [["Events", s.total], ["Ready", s.ready], ["Need attention", s.needsAttention]] as const
        ).map(([k, v]) => (
          <div key={k} className="rounded border border-line bg-surface p-3">
            <dt className="text-muted">{k}</dt>
            <dd className="text-2xl font-semibold">{v}</dd>
          </div>
        ))}
      </dl>

      {importRec && (
        <section aria-labelledby="h-imp" className="rounded border border-line bg-surface p-4 text-sm">
          <h2 id="h-imp" className="font-semibold">Import history check</h2>
          {importRec.already_imported ? (
            <p role="status" className="mt-1">This exact PDF was imported before. No new import record was created.</p>
          ) : importRec.diff ? (
            <div role="status" className="mt-1">
              <p>Compared with the previous import of this school and year:</p>
              <ul className="list-disc pl-5">
                <li>{importRec.diff.added.length} added, {importRec.diff.removed.length} removed (proposed only), {importRec.diff.changed.length} changed, {importRec.diff.unchanged.length} unchanged</li>
                {importRec.diff.changed.map((c) => <li key={c}>Changed: {c}</li>)}
                {importRec.diff.removed.map((c) => <li key={c}>No longer in source: {c}</li>)}
              </ul>
            </div>
          ) : (
            <p className="mt-1 text-muted">First import for this school and year.</p>
          )}
        </section>
      )}

      {!legendConfirmed && (
        <p role="status" className="text-sm text-warn">
          Confirm the legend mapping first. <Link className="underline" href="/review">Go to review</Link>.
        </p>
      )}
      {blocked.length > 0 && (
        <div role="status" className="rounded border border-warn p-3 text-sm">
          <p className="font-medium">{blocked.length} event(s) will be left out until resolved:</p>
          <ul className="list-disc pl-5">
            {blocked.map((e) => <li key={e.event_id_internal}>{e.start_date} · {e.event_title}</li>)}
          </ul>
        </div>
      )}
      <p role="alert" className="text-sm text-danger">{error}</p>

      <section aria-labelledby="h-file" className="rounded border border-line bg-surface p-4 text-sm">
        <h2 id="h-file" className="font-semibold">Download a file</h2>
        <label className="mt-2 block">
          School day start time (optional, your own value)
          <input type="time" value={dayStart} onChange={(e) => setDayStart(e.target.value)}
            className="ml-2 rounded border border-line bg-surface px-2 py-1" />
        </label>
        <p className="mt-1 text-xs text-muted">
          Without it, half days export as all-day events with the dismissal time in the title. With it,
          they become timed events and the description says the start came from you.
        </p>
        <div className="mt-3 flex gap-2">
          <button disabled={!canAct || busy} className={btn}
            onClick={() => run(() => downloadExport("ics", ready, dayStart || null), () => undefined)}>
            Download ICS ({ready.length})
          </button>
          <button disabled={!canAct || busy} className={btn}
            onClick={() => run(() => downloadExport("csv", ready, dayStart || null), () => undefined)}>
            Download CSV ({ready.length})
          </button>
        </div>
        <details className="mt-3 text-xs text-muted">
          <summary className="cursor-pointer">How to import the file</summary>
          <ul className="mt-1 list-disc pl-5">
            <li>Google Calendar: Settings → Import &amp; export → Import (ICS).</li>
            <li>Outlook: File → Open &amp; Export → Import/Export, or Add calendar → Upload from file.</li>
            <li>Importing the same file twice may create duplicates in some clients; ICS UIDs help
              clients that honour them. The connected sync path below checks for duplicates itself.</li>
            <li>These instructions and the file formats have been checked with parser tests only, not
              imported into real Google or Outlook calendars.</li>
          </ul>
        </details>
      </section>

      <section aria-labelledby="h-sync" className="rounded border border-line bg-surface p-4 text-sm">
        <h2 id="h-sync" className="font-semibold">Sync to a calendar</h2>
        <ul className="mt-2 space-y-1">
          {providers.filter((p) => p.id !== "file").map((p) => (
            <li key={p.id} className={p.available ? "" : "text-muted"}>
              {p.label}: {p.available ? "available" : `unavailable (${p.reason})`}
            </li>
          ))}
        </ul>
        <p className="mt-2">
          Destination:{" "}
          <strong>{dest ? dest.calendarName : "none selected"}</strong>
          {isReal && <span className="text-warn"> (writes to a real Google Calendar after you confirm)</span>}{" "}
          <Link className="text-accent underline" href="/connect">Change</Link>
        </p>
        <p className="mt-1 text-xs text-muted">
          The demo calendar is in memory and resets when the server restarts. Microsoft is not implemented.
        </p>

        {(() => {
          const unmet: { text: string; href: string; link: string }[] = [];
          if (!legendConfirmed) unmet.push({ text: "Legend mapping is not confirmed.", href: "/review", link: "Confirm it on Review" });
          if (ready.length === 0) unmet.push({ text: "No events are ready yet.", href: "/review", link: "Resolve or bulk-confirm events on Review" });
          if (!dest) unmet.push({ text: "No destination chosen.", href: "/connect", link: "Choose one on Connect" });
          else if (!destProvider?.available)
            unmet.push({ text: `${dest.provider === "google" ? "Google" : "The destination"} is unavailable (${destProvider?.reason ?? "unknown"}).`, href: "/connect", link: "Fix it on Connect" });
          return unmet.length === 0 ? (
            <p role="status" className="mt-3 text-ok">✓ Ready to preview: {ready.length} event(s) ready, destination {dest?.calendarName}.</p>
          ) : (
            <div role="status" className="mt-3 rounded border border-warn p-3">
              <p className="font-medium">Before you can preview a sync:</p>
              <ul className="mt-1 list-disc pl-5">
                {unmet.map((u) => (
                  <li key={u.text}>{u.text} <Link className="text-accent underline" href={u.href}>{u.link}</Link></li>
                ))}
              </ul>
            </div>
          );
        })()}

        <div className="mt-3 flex gap-2">
          <button disabled={!canAct || !dest || !destProvider?.available || busy} className={btn}
            onClick={() => run(() => previewSync(body()), (p) => { setPreview(p); setReport(null); setConfirmed(false); setRolled(null); })}>
            Preview sync to {dest ? dest.calendarName : "a calendar"}
          </button>
        </div>

        {preview && (
          <div className="mt-4 space-y-3">
            <p role="status" className="font-medium">
              {Object.entries(preview.counts).filter(([, n]) => n > 0)
                .map(([k, n]) => `${n} ${ACTION_TEXT[k].toLowerCase()}`).join(" · ") || "Nothing to do"}
            </p>
            <table className="w-full text-left">
              <caption className="sr-only">Sync plan</caption>
              <thead className="text-muted"><tr><th scope="col">Action</th><th scope="col">Event</th><th scope="col">Why</th></tr></thead>
              <tbody>
                {preview.items.map((i) => (
                  <tr key={i.stable_id + i.action} className="border-t border-line align-top">
                    <td className="py-1 pr-2 whitespace-nowrap">{ACTION_TEXT[i.action]}</td>
                    <td className="pr-2">{i.start_date !== "0001-01-01" && i.start_date + " · "}{i.title}</td>
                    <td className="text-muted">{i.reason}{i.matched_title && ` (matches “${i.matched_title}”)`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!report && (
              <>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  I confirm: apply {preview.counts.create} create and {preview.counts.update} update
                  action(s) to {destLabel}. Conflicts and removals are not applied.
                </label>
                <button disabled={!confirmed || busy} className={primary}
                  onClick={() => run(() => executeSync(body(), preview.plan_token), setReport)}>
                  Confirm and sync
                </button>
              </>
            )}
          </div>
        )}

        {report && (
          <div className="mt-4 space-y-2" aria-labelledby="h-rep">
            <h3 id="h-rep" className="font-medium">Import report</h3>
            <p role="status">
              {Object.entries(report.summary).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(" · ")}
            </p>
            <ul className="list-disc pl-5">
              {report.results.filter((r) => r.status !== "skipped").map((r) => (
                <li key={r.stable_id + r.status}>{r.title}: {r.status}{r.detail && ` (${r.detail})`}{r.provider_event_id && ` [${r.provider_event_id}]`}</li>
              ))}
            </ul>
            <button disabled={busy || rolled !== null} className={btn}
              onClick={() => { if (window.confirm(`Remove only the events created in this batch from ${destLabel}?`))
                run(() => rollbackBatch(report.batch_id), (r) => setRolled(`${r.results.filter((x) => x.status === "deleted").length} event(s) removed`)); }}>
              Roll back this batch
            </button>
            {rolled && <p role="status">{rolled}.</p>}
          </div>
        )}
      </section>
    </div>
  );
}
