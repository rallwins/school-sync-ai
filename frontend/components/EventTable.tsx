"use client";
import { durationLabel, formatRange, readiness } from "@/lib/readiness";
import type { CalendarEvent } from "@/lib/types";
import { Swatch } from "./LegendPanel";

const STATUS_TEXT: Record<string, string> = {
  confirmed: "Confirmed",
  inferred: "Inferred",
  ambiguous: "Ambiguous",
  needs_review: "Needs review",
};

export function EventTable({
  events,
  selectedId,
  onSelect,
}: {
  events: CalendarEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (events.length === 0)
    return <p className="rounded border border-dashed border-line p-6 text-sm text-muted">No events match these filters.</p>;
  return (
    <div className="overflow-x-auto rounded border border-line bg-surface">
      <table className="w-full text-sm">
        <caption className="sr-only">Extracted events</caption>
        <thead className="text-left text-muted">
          <tr>
            {["Title", "Date", "Duration", "Category", "Source", "Status", "Warnings"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {events.map((e) => {
            const sel = e.event_id_internal === selectedId;
            const ready = readiness(e) === "ready";
            return (
              <tr
                key={e.event_id_internal}
                aria-selected={sel}
                className={"border-t border-line " + (sel ? "bg-accent/10" : "")}
              >
                <td className="px-3 py-2">
                  <button className="text-left font-medium text-accent underline" onClick={() => onSelect(e.event_id_internal)}>
                    {e.event_title}
                  </button>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">{formatRange(e)}</td>
                <td className="px-3 py-2">{durationLabel(e)}</td>
                <td className="px-3 py-2">
                  <Swatch rgb={e.sampled_color} label={e.sampled_color ? "Cell colour" : "No colour"} />{" "}
                  {e.category_label ?? <span className="text-muted">none</span>}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">p.{e.source_region.page}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {STATUS_TEXT[e.validation_status]}
                  {e.user_confirmed && " · you confirmed"}
                  <span className={ready ? "ml-2 text-ok" : "ml-2 text-warn"}>
                    {ready ? "✓ ready" : "⚠ needs attention"}
                  </span>
                </td>
                <td className="px-3 py-2">{e.warnings.length || "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
