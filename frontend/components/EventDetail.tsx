"use client";
import { confirmBlockers, formatTime, readiness } from "@/lib/readiness";
import { useStore } from "@/lib/store";
import type { CalendarEvent, DurationKind } from "@/lib/types";
import { Swatch } from "./LegendPanel";

export function EventDetail({ event }: { event: CalendarEvent }) {
  const { editEvent, confirmEvent, edits } = useStore();
  const id = event.event_id_internal;
  const blockers = confirmBlockers(event);
  const r = event.source_region;
  const input = "mt-1 w-full rounded border border-line bg-surface px-2 py-1";
  const history = edits.filter((x) => x.eventId === id);

  function setKind(k: DurationKind) {
    editEvent(id, {
      duration_kind: k,
      is_all_day: k === "all_day",
      start_time: k === "timed" ? event.start_time : null,
      end_time: k === "all_day" ? null : event.end_time,
    });
  }
  const t = (v: string) => (v ? v + ":00" : null);

  return (
    <aside aria-labelledby="h-detail" className="space-y-4 rounded border border-line bg-surface p-4 text-sm">
      <h2 id="h-detail" className="text-base font-semibold">Event detail</h2>

      <div>
        <h3 className="font-medium text-muted">Source evidence</h3>
        <p>Page {r.page}, cell {r.cell_label}</p>
        <p className="text-xs text-muted">
          region ({Math.round(r.x0)}, {Math.round(r.y0)})–({Math.round(r.x1)}, {Math.round(r.y1)}) pt
        </p>
        <p>Printed text: <q>{event.source_text || "none"}</q></p>
        <p>
          <Swatch rgb={event.sampled_color} label="Sampled cell colour" /> sampled
          {" → "}
          <Swatch rgb={event.matched_legend_color} label="Matched legend colour" />{" "}
          {event.category_label ?? "no legend match"}
        </p>
      </div>

      {event.warnings.length > 0 && (
        <ul className="space-y-1" aria-label="Warnings">
          {event.warnings.map((w) => (
            <li key={w.code} className={w.critical ? "text-danger" : "text-warn"}>
              {w.critical ? "Critical: " : "Note: "}
              {w.message}
            </li>
          ))}
        </ul>
      )}

      <form className="space-y-3" onSubmit={(e) => e.preventDefault()}>
        <label className="block">
          Title
          <input className={input} value={event.event_title.toLowerCase().includes("untitled") ? "" : event.event_title}
            placeholder="Enter a title" onChange={(e) => editEvent(id, { event_title: e.target.value })} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label>Start date
            <input type="date" className={input} value={event.start_date}
              onChange={(e) => e.target.value && editEvent(id, { start_date: e.target.value })} />
          </label>
          <label>End date (inclusive)
            <input type="date" className={input} value={event.end_date}
              onChange={(e) => e.target.value && editEvent(id, { end_date: e.target.value })} />
          </label>
        </div>
        <label className="block">Duration
          <select className={input} value={event.duration_kind} onChange={(e) => setKind(e.target.value as DurationKind)}>
            <option value="unknown">Unknown: choose one</option>
            <option value="all_day">All day</option>
            <option value="half_day">Half day</option>
            <option value="timed">Timed</option>
          </select>
        </label>
        {event.duration_kind === "half_day" && (
          <label className="block">Dismissal time
            <input type="time" className={input} value={formatTime(event.end_time)}
              onChange={(e) => editEvent(id, { end_time: t(e.target.value) })} />
          </label>
        )}
        {event.duration_kind === "timed" && (
          <div className="grid grid-cols-2 gap-3">
            <label>Start time
              <input type="time" className={input} value={formatTime(event.start_time)}
                onChange={(e) => editEvent(id, { start_time: t(e.target.value) })} />
            </label>
            <label>End time (optional)
              <input type="time" className={input} value={formatTime(event.end_time)}
                onChange={(e) => editEvent(id, { end_time: t(e.target.value) })} />
            </label>
          </div>
        )}
        <p className="text-xs text-muted">Timezone: {event.timezone}</p>

        {readiness(event) === "ready" && event.user_confirmed ? (
          <p role="status" className="text-ok">✓ You confirmed this event.</p>
        ) : (
          <>
            {blockers.length > 0 && (
              <ul role="status" className="list-disc pl-5 text-warn">
                {blockers.map((b) => <li key={b}>{b}</li>)}
              </ul>
            )}
            <button type="button" disabled={blockers.length > 0} onClick={() => confirmEvent(id)}
              className="rounded bg-accent px-3 py-1.5 font-medium text-white disabled:opacity-50 dark:text-black">
              Confirm this event
            </button>
          </>
        )}
      </form>

      {history.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted">Edit history ({history.length})</summary>
          <ul className="mt-1 space-y-0.5 text-xs">
            {history.map((h, i) => (
              <li key={i}>{h.at.slice(11, 19)} · {h.field}: “{h.from}” → “{h.to}”</li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-muted">Source page crop preview is not implemented yet.</p>
    </aside>
  );
}
