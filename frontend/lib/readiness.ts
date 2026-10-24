import type { CalendarEvent } from "./types";

export const UNTITLED_MARK = "untitled";

export function isPlaceholderTitle(title: string): boolean {
  return title.toLowerCase().includes(UNTITLED_MARK) || title.trim() === "";
}

/** Reasons a user cannot yet confirm this event (empty = can confirm). */
export function confirmBlockers(e: CalendarEvent): string[] {
  const out: string[] = [];
  if (isPlaceholderTitle(e.event_title)) out.push("Give the event a real title.");
  if (e.duration_kind === "unknown") out.push("Choose all-day, half-day or timed.");
  if (e.duration_kind === "half_day" && !e.end_time)
    out.push("Enter the dismissal time (not assumed).");
  if (e.duration_kind === "timed" && !e.start_time) out.push("Enter the start time.");
  if (e.end_date < e.start_date) out.push("End date is before start date.");
  return out;
}

export type Readiness = "ready" | "needs_attention";

/** An event may be synced only if it is user-confirmed, or clean with no critical warning. */
export function readiness(e: CalendarEvent): Readiness {
  if (e.user_confirmed && confirmBlockers(e).length === 0) return "ready";
  const clean =
    (e.validation_status === "confirmed" || e.validation_status === "inferred") &&
    !e.warnings.some((w) => w.critical) &&
    confirmBlockers(e).length === 0;
  return clean ? "ready" : "needs_attention";
}

export function summarize(events: CalendarEvent[]) {
  const ready = events.filter((e) => readiness(e) === "ready").length;
  return { total: events.length, ready, needsAttention: events.length - ready };
}

export function formatRange(e: CalendarEvent): string {
  return e.start_date === e.end_date ? e.start_date : `${e.start_date} → ${e.end_date}`;
}

export function formatTime(t: string | null): string {
  return t ? t.slice(0, 5) : "";
}

export function durationLabel(e: CalendarEvent): string {
  switch (e.duration_kind) {
    case "all_day":
      return "All day";
    case "half_day":
      return e.end_time ? `Half day, dismissal ${formatTime(e.end_time)}` : "Half day, time unknown";
    case "timed":
      return `Timed ${formatTime(e.start_time)}${e.end_time ? "–" + formatTime(e.end_time) : ""}`;
    default:
      return "Unknown";
  }
}

/**
 * Events a person may bulk-mark as all-day: the ONLY thing missing is a stated duration.
 * Excluded on purpose: ambiguous events, contradictions, untitled colour-only cells, and
 * dates not found in their month grid. Those need individual attention.
 */
export function bulkAllDayEligible(e: CalendarEvent): boolean {
  return (
    e.duration_kind === "unknown" &&
    !e.user_confirmed &&
    !isPlaceholderTitle(e.event_title) &&
    e.validation_status !== "ambiguous" &&
    e.warnings.every((w) => !w.critical || w.code === "duration_unknown")
  );
}
