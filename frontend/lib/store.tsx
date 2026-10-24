"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { bulkAllDayEligible, confirmBlockers } from "./readiness";
import type {
  CalendarEvent,
  EditRecord,
  ExtractionResult,
  ImportMeta,
  ImportRecordResult,
} from "./types";

interface State {
  meta: ImportMeta | null;
  result: ExtractionResult | null;
  events: CalendarEvent[];
  edits: EditRecord[];
  legendConfirmed: boolean;
  importRec: ImportRecordResult | null;
}
const EMPTY: State = {
  meta: null,
  result: null,
  events: [],
  edits: [],
  legendConfirmed: false,
  importRec: null,
};
const KEY = "schoolsync.session.v1";

interface Ctx extends State {
  hydrated: boolean;
  load: (meta: ImportMeta, result: ExtractionResult) => void;
  editEvent: (id: string, patch: Partial<CalendarEvent>) => void;
  confirmEvent: (id: string) => void;
  bulkAllDay: () => number;
  setLegendConfirmed: (v: boolean) => void;
  setImportRec: (r: ImportRecordResult | null) => void;
  clear: () => void;
}
const StoreCtx = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>(EMPTY);
  const [hydrated, setHydrated] = useState(false);

  // sessionStorage is a per-tab convenience only; it may be unavailable or empty.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) setState(JSON.parse(raw) as State);
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* ignore */
    }
  }, [state, hydrated]);

  const load = useCallback((meta: ImportMeta, result: ExtractionResult) => {
    setState({ ...EMPTY, meta, result, events: result.events });
  }, []);

  const editEvent = useCallback((id: string, patch: Partial<CalendarEvent>) => {
    setState((s) => {
      const cur = s.events.find((e) => e.event_id_internal === id);
      if (!cur) return s;
      const now = new Date().toISOString();
      const rec: EditRecord[] = (Object.keys(patch) as (keyof CalendarEvent)[])
        .filter((k) => JSON.stringify(cur[k]) !== JSON.stringify(patch[k]))
        .map((k) => ({
          eventId: id,
          field: k,
          from: String(cur[k] ?? ""),
          to: String(patch[k] ?? ""),
          at: now,
        }));
      // Any edit revokes a prior confirmation: the user must re-confirm what they changed.
      const next = { ...cur, ...patch, user_confirmed: false };
      return {
        ...s,
        events: s.events.map((e) => (e.event_id_internal === id ? next : e)),
        edits: [...s.edits, ...rec],
      };
    });
  }, []);

  const confirmEvent = useCallback((id: string) => {
    setState((s) => ({
      ...s,
      events: s.events.map((e) =>
        e.event_id_internal === id && confirmBlockers(e).length === 0
          ? { ...e, user_confirmed: true }
          : e,
      ),
      edits: [
        ...s.edits,
        { eventId: id, field: "user_confirmed", from: "false", to: "true", at: new Date().toISOString() },
      ],
    }));
  }, []);

  // Explicit, user-triggered: marks every eligible unknown-duration event all-day AND confirmed,
  // writing one history record per event. Returns how many were changed.
  const bulkAllDay = useCallback(() => {
    let n = 0;
    setState((s) => {
      const now = new Date().toISOString();
      const rec: EditRecord[] = [];
      const events = s.events.map((e) => {
        if (!bulkAllDayEligible(e)) return e;
        n += 1;
        rec.push({ eventId: e.event_id_internal, field: "bulk_all_day", from: "unknown", to: "all_day", at: now });
        return { ...e, duration_kind: "all_day" as const, is_all_day: true, start_time: null, end_time: null, user_confirmed: true };
      });
      return n === 0 ? s : { ...s, events, edits: [...s.edits, ...rec] };
    });
    return n;
  }, []);

  const setLegendConfirmed = useCallback(
    (v: boolean) => setState((s) => ({ ...s, legendConfirmed: v })),
    [],
  );
  const setImportRec = useCallback(
    (r: ImportRecordResult | null) => setState((s) => ({ ...s, importRec: r })),
    [],
  );
  const clear = useCallback(() => setState(EMPTY), []);

  const value = useMemo<Ctx>(
    () => ({ ...state, hydrated, load, editEvent, confirmEvent, bulkAllDay, setLegendConfirmed, setImportRec, clear }),
    [state, hydrated, load, editEvent, confirmEvent, bulkAllDay, setLegendConfirmed, setImportRec, clear],
  );
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}

export function useStore(): Ctx {
  const c = useContext(StoreCtx);
  if (!c) throw new Error("useStore outside StoreProvider");
  return c;
}
