"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { EventDetail } from "@/components/EventDetail";
import { EventTable } from "@/components/EventTable";
import { LegendPanel } from "@/components/LegendPanel";
import { MonthCalendar } from "@/components/MonthCalendar";
import { bulkAllDayEligible, readiness, summarize } from "@/lib/readiness";
import { useStore } from "@/lib/store";

export default function ReviewPage() {
  const { result, events, hydrated, meta, bulkAllDay } = useStore();
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "calendar">("table");
  const [cat, setCat] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      events.filter(
        (e) =>
          (!cat || (cat === "__none" ? !e.category_id : e.category_id === cat)) &&
          (!kind || e.duration_kind === kind) &&
          (!status || e.validation_status === status) &&
          (!attentionOnly || readiness(e) !== "ready") &&
          (!q || (e.event_title + " " + e.source_text).toLowerCase().includes(q.toLowerCase())),
      ),
    [events, cat, kind, status, q, attentionOnly],
  );

  if (!hydrated) return <p>Loading…</p>;
  if (!result)
    return (
      <p className="rounded border border-dashed border-line p-6 text-sm">
        Nothing to review. <Link className="text-accent underline" href="/">Import a PDF</Link> first.
      </p>
    );

  const s = summarize(events);
  const sel = events.find((e) => e.event_id_internal === selected) ?? null;
  const sel_ = "rounded border border-line bg-surface px-2 py-1 text-sm";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Review events</h1>
          <p className="text-sm text-muted">{meta?.fileName} · {meta?.school} · {meta?.academicYear}</p>
          {meta?.schoolSource && (
            <p className="text-xs text-muted">School name {meta.schoolSource}. If it is wrong, import again and type the name.</p>
          )}
        </div>
        <p role="status" className="text-sm">
          {s.total} events · <span className="text-ok">{s.ready} ready</span> ·{" "}
          <span className="text-warn">{s.needsAttention} need attention</span>
        </p>
      </header>

      {(result.pages_skipped.length > 0 || result.warnings.length > 0) && (
        <div role="alert" className="rounded border border-warn p-3 text-sm">
          {result.pages_skipped.length > 0 && <p>Pages not processed: {result.pages_skipped.join(", ")}.</p>}
          <ul className="list-disc pl-5">{result.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      {events.filter(bulkAllDayEligible).length > 0 && (
        <section aria-labelledby="h-bulk" className="rounded border border-line bg-surface p-4 text-sm">
          <h2 id="h-bulk" className="font-semibold">No stated duration</h2>
          <p className="mt-1 text-muted">
            {events.filter(bulkAllDayEligible).length} event(s) have a title and date but no time or
            all-day/half-day wording. You can treat them all as all-day events. This is your decision,
            not something the app assumes; each event keeps an edit-history entry. Ambiguous or
            conflicting events are not included.
          </p>
          <button
            className="mt-2 rounded bg-accent px-3 py-1.5 font-medium text-white dark:text-black"
            onClick={() => {
              const n = events.filter(bulkAllDayEligible).length;
              if (!window.confirm(`Mark ${n} event(s) as all-day and confirm them?`)) return;
              setBulkMsg(`${bulkAllDay()} event(s) marked all-day by you.`);
            }}
          >
            Treat {events.filter(bulkAllDayEligible).length} as all-day…
          </button>
        </section>
      )}
      {bulkMsg && <p role="status" className="text-sm text-ok">{bulkMsg}</p>}

      <LegendPanel />

      <div className="flex flex-wrap items-center gap-2" role="search" aria-label="Filter events">
        <input aria-label="Search events" placeholder="Search…" className={sel_} value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Category" className={sel_} value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">All categories</option>
          {result.legend.map((l) => <option key={l.category_id} value={l.category_id}>{l.label}</option>)}
          <option value="__none">No category</option>
        </select>
        <select aria-label="Duration" className={sel_} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All durations</option>
          <option value="all_day">All day</option>
          <option value="half_day">Half day</option>
          <option value="timed">Timed</option>
          <option value="unknown">Unknown</option>
        </select>
        <select aria-label="Status" className={sel_} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="inferred">Inferred</option>
          <option value="ambiguous">Ambiguous</option>
          <option value="needs_review">Needs review</option>
        </select>
        <label className="text-sm">
          <input type="checkbox" checked={attentionOnly} onChange={(e) => setAttentionOnly(e.target.checked)} /> Needs attention only
        </label>
        <div className="ml-auto flex gap-1" role="group" aria-label="View">
          {(["table", "calendar"] as const).map((v) => (
            <button key={v} aria-pressed={view === v} onClick={() => setView(v)}
              className={"rounded border border-line px-3 py-1 text-sm " + (view === v ? "bg-accent text-white dark:text-black" : "bg-surface")}>
              {v === "table" ? "Table" : "Calendar"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          {view === "table" ? (
            <EventTable events={filtered} selectedId={selected} onSelect={setSelected} />
          ) : (
            <MonthCalendar events={filtered} selectedId={selected} onSelect={setSelected} />
          )}
        </div>
        {sel ? (
          <EventDetail key={sel.event_id_internal} event={sel} />
        ) : (
          <p className="rounded border border-dashed border-line p-4 text-sm text-muted">
            Select an event to see its source evidence, warnings and edit options.
          </p>
        )}
      </div>

      <div className="flex justify-end">
        <Link href="/sync" className="rounded bg-accent px-4 py-2 font-medium text-white dark:text-black">
          Continue to export →
        </Link>
      </div>
    </div>
  );
}
