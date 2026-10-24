import type { ExtractionResult } from "./types";

// "same-origin" makes the browser call this site's own /api proxy (used on Vercel).
const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL;
export const API_URL =
  RAW_API_URL === "same-origin" ? "" : (RAW_API_URL ?? "http://localhost:8000");

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function extractCalendar(
  file: File,
  p: { school: string; academicYear: string; timezone: string; tolerance: number },
): Promise<ExtractionResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("school_name", p.school);
  fd.append("academic_year", p.academicYear);
  fd.append("timezone", p.timezone);
  fd.append("color_tolerance", String(p.tolerance));
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/uploads/extract`, { method: "POST", body: fd });
  } catch {
    throw new ApiError("network", `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let code = "error";
    let msg = `Request failed (${res.status}).`;
    try {
      const j = await res.json();
      const d = j.detail;
      if (d && typeof d === "object" && !Array.isArray(d)) {
        code = d.code ?? code;
        msg = d.message ?? msg;
      } else if (Array.isArray(d)) {
        msg = d.map((x: { msg?: string }) => x.msg).join("; ");
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(code, msg);
  }
  return (await res.json()) as ExtractionResult;
}

import type {
  CalendarEvent,
  ImportMeta,
  ImportRecordResult,
  ProviderInfo,
  SyncPreview,
  SyncReport,
} from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("network", `Cannot reach the API at ${API_URL}.`);
  }
  if (!res.ok) {
    let code = "error";
    let msg = `Request failed (${res.status}).`;
    try {
      const d = (await res.json()).detail;
      if (d && typeof d === "object" && !Array.isArray(d)) {
        code = d.code ?? code;
        msg = d.message ?? msg;
        if (Array.isArray(d.titles)) msg += ` (${d.titles.join(", ")})`;
      }
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(code, msg);
  }
  return (await res.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listProviders = () => call<ProviderInfo[]>("/api/providers");

export const recordImport = (meta: ImportMeta, hash: string, events: CalendarEvent[]) =>
  call<ImportRecordResult>(
    "/api/imports",
    post({
      source_hash: hash,
      school_name: meta.school,
      academic_year: meta.academicYear,
      timezone: meta.timezone,
      events,
    }),
  );

export async function downloadExport(
  kind: "ics" | "csv",
  events: CalendarEvent[],
  dayStart: string | null,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(
      `${API_URL}/api/export/${kind}`,
      post({ events, day_start: dayStart ? dayStart + ":00" : null }),
    );
  } catch {
    throw new ApiError("network", `Cannot reach the API at ${API_URL}.`);
  }
  if (!res.ok) {
    const d = (await res.json().catch(() => ({}))).detail ?? {};
    throw new ApiError(d.code ?? "error", d.message ?? `Export failed (${res.status}).`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `schoolsync.${kind}`;
  a.click();
  URL.revokeObjectURL(url);
}

interface SyncBody {
  provider: string;
  calendar_id: string;
  events: CalendarEvent[];
  day_start: string | null;
}
export const previewSync = (b: SyncBody) => call<SyncPreview>("/api/sync/preview", post(b));
export const executeSync = (b: SyncBody, planToken: string) =>
  call<SyncReport>("/api/sync/execute", post({ ...b, confirm: true, plan_token: planToken }));
export const rollbackBatch = (batchId: string) =>
  call<{ results: { status: string }[] }>(
    `/api/sync/rollback/${batchId}`,
    post({ confirm: true }),
  );
