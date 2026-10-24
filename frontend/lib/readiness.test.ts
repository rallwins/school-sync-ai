import { describe, expect, it } from "vitest";
import { bulkAllDayEligible, confirmBlockers, readiness, summarize } from "./readiness";
import type { CalendarEvent } from "./types";

const base: CalendarEvent = {
  event_id_internal: "a",
  source_region: { page: 1, x0: 0, y0: 0, x1: 1, y1: 1, cell_label: "2025-09-01" },
  source_text: "Labor Day",
  event_title: "Labor Day",
  description: "",
  start_date: "2025-09-01",
  end_date: "2025-09-01",
  is_all_day: true,
  start_time: null,
  end_time: null,
  timezone: "America/Chicago",
  duration_kind: "all_day",
  category_id: "holiday",
  category_label: "Holiday",
  sampled_color: null,
  matched_legend_color: null,
  validation_status: "confirmed",
  warnings: [],
  user_confirmed: false,
  normalized_fingerprint: "f",
};

describe("readiness", () => {
  it("clean confirmed event is ready", () => {
    expect(readiness(base)).toBe("ready");
  });
  it("critical warning blocks until user confirms", () => {
    const e = { ...base, warnings: [{ code: "x", message: "m", critical: true }] };
    expect(readiness(e)).toBe("needs_attention");
    expect(readiness({ ...e, user_confirmed: true })).toBe("ready");
  });
  it("half day without time cannot be confirmed (no assumed noon)", () => {
    const e = { ...base, duration_kind: "half_day" as const, is_all_day: false };
    expect(confirmBlockers(e)).toContain("Enter the dismissal time (not assumed).");
    expect(readiness({ ...e, user_confirmed: true })).toBe("needs_attention");
  });
  it("untitled colour-only unknown event is blocked", () => {
    const e = { ...base, event_title: "(untitled - colour only)", duration_kind: "unknown" as const, validation_status: "ambiguous" as const };
    expect(confirmBlockers(e).length).toBe(2);
    expect(readiness(e)).toBe("needs_attention");
  });
  it("summarize counts", () => {
    const bad = { ...base, validation_status: "needs_review" as const };
    expect(summarize([base, bad])).toEqual({ total: 2, ready: 1, needsAttention: 1 });
  });
});

describe("bulkAllDayEligible", () => {
  const unknown = {
    ...base,
    duration_kind: "unknown" as const,
    is_all_day: false,
    validation_status: "needs_review" as const,
    warnings: [{ code: "duration_unknown", message: "m", critical: true }],
  };
  it("accepts a titled event whose only gap is duration", () => {
    expect(bulkAllDayEligible(unknown)).toBe(true);
  });
  it("rejects ambiguous, conflicting, untitled, grid-mismatch and already-confirmed events", () => {
    expect(bulkAllDayEligible({ ...unknown, validation_status: "ambiguous" })).toBe(false);
    const conflict = { ...unknown, warnings: [{ code: "legend_text_conflict", message: "m", critical: true }] };
    expect(bulkAllDayEligible(conflict)).toBe(false);
    expect(bulkAllDayEligible({ ...unknown, event_title: "(untitled - colour only)" })).toBe(false);
    const nogrid = { ...unknown, warnings: [...unknown.warnings, { code: "date_not_in_grid", message: "m", critical: true }] };
    expect(bulkAllDayEligible(nogrid)).toBe(false);
    expect(bulkAllDayEligible({ ...unknown, user_confirmed: true })).toBe(false);
  });
  it("rejects events that already have a duration", () => {
    expect(bulkAllDayEligible(base)).toBe(false);
    expect(bulkAllDayEligible({ ...base, duration_kind: "half_day" as const })).toBe(false);
  });
});
