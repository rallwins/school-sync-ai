"use client";
import { readiness } from "@/lib/readiness";
import type { CalendarEvent } from "@/lib/types";
import { css } from "./LegendPanel";

function ymd(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

/** Pure date-string arithmetic in UTC: no local-timezone shifts of all-day dates. */
export function monthsSpanned(events: CalendarEvent[]): { y: number; m: number }[] {
  const set = new Set<string>();
  for (const e of events) {
    const d = new Date(e.start_date + "T00:00:00Z");
    const end = new Date(e.end_date + "T00:00:00Z");
    for (; d <= end; d.setUTCDate(d.getUTCDate() + 1)) set.add(`${d.getUTCFullYear()}-${d.getUTCMonth()}`);
  }
  return [...set]
    .map((s) => s.split("-").map(Number))
    .map(([y, m]) => ({ y, m }))
    .sort((a, b) => a.y - b.y || a.m - b.m);
}

export function MonthCalendar({
  events,
  selectedId,
  onSelect,
}: {
  events: CalendarEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (events.length === 0) return <p className="rounded border border-dashed border-line p-6 text-sm text-muted">No events match these filters.</p>;
  const byDay = new Map<string, CalendarEvent[]>();
  for (const e of events) {
    const d = new Date(e.start_date + "T00:00:00Z");
    const end = new Date(e.end_date + "T00:00:00Z");
    for (; d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      const k = ymd(d);
      byDay.set(k, [...(byDay.get(k) ?? []), e]);
    }
  }
  return (
    <div className="space-y-6">
      {monthsSpanned(events).map(({ y, m }) => {
        const first = new Date(Date.UTC(y, m, 1));
        const lead = first.getUTCDay(); // Sunday-first display
        const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
        const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
        while (cells.length % 7) cells.push(null);
        const title = first.toLocaleString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
        return (
          <section key={`${y}-${m}`} aria-label={title}>
            <h3 className="mb-1 font-medium">{title}</h3>
            <div role="grid" aria-label={title} className="grid grid-cols-7 gap-px rounded border border-line bg-line text-xs">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div role="columnheader" key={d} className="bg-surface p-1 text-center text-muted">{d}</div>
              ))}
              {cells.map((day, i) => {
                const evs = day ? (byDay.get(ymd(new Date(Date.UTC(y, m, day)))) ?? []) : [];
                return (
                  <div role="gridcell" key={i} className="min-h-16 bg-surface p-1">
                    {day && <div className="text-muted">{day}</div>}
                    {evs.map((e) => (
                      <button
                        key={e.event_id_internal}
                        onClick={() => onSelect(e.event_id_internal)}
                        aria-label={`${e.event_title}, ${e.start_date}`}
                        aria-pressed={e.event_id_internal === selectedId}
                        className={
                          "mt-0.5 block w-full truncate rounded px-1 text-left text-[11px] text-black " +
                          (e.event_id_internal === selectedId ? "ring-2 ring-accent " : "") +
                          (readiness(e) === "ready" ? "" : "border border-dashed border-warn")
                        }
                        style={{ background: e.sampled_color ? css(e.sampled_color) : "#e5e7eb" }}
                      >
                        {readiness(e) === "ready" ? "" : "⚠ "}
                        {e.event_title}
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
