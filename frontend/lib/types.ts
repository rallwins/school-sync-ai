export type DurationKind = "all_day" | "half_day" | "timed" | "unknown";
export type ValidationStatus = "confirmed" | "inferred" | "ambiguous" | "needs_review";
export type RGB = [number, number, number];

export interface SourceRegion {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  cell_label: string | null;
}
export interface EventWarning {
  code: string;
  message: string;
  critical: boolean;
}
export interface CalendarEvent {
  event_id_internal: string;
  source_region: SourceRegion;
  source_text: string;
  event_title: string;
  description: string;
  start_date: string; // YYYY-MM-DD
  end_date: string; // inclusive
  is_all_day: boolean;
  start_time: string | null; // HH:MM:SS
  end_time: string | null;
  timezone: string;
  duration_kind: DurationKind;
  category_id: string | null;
  category_label: string | null;
  sampled_color: RGB | null;
  matched_legend_color: RGB | null;
  validation_status: ValidationStatus;
  warnings: EventWarning[];
  user_confirmed: boolean;
  normalized_fingerprint: string;
}
export interface LegendEntry {
  label: string;
  category_id: string;
  rgb: RGB;
  page: number;
}
export interface ExtractionResult {
  source_hash: string;
  school_name: string;
  school_name_source: string;
  legend: LegendEntry[];
  events: CalendarEvent[];
  warnings: string[];
  pages_processed: number[];
  pages_skipped: number[];
}
export interface ImportMeta {
  fileName: string;
  school: string;
  schoolSource?: string;
  academicYear: string;
  timezone: string;
  destination: "file" | "google" | "microsoft";
}
export interface EditRecord {
  eventId: string;
  field: string;
  from: string;
  to: string;
  at: string;
}

export interface ProviderInfo {
  id: string;
  label: string;
  available: boolean;
  reason: string | null;
}
export type PlanAction = "create" | "update" | "skip" | "conflict" | "propose_remove";
export interface PlanItem {
  action: PlanAction;
  stable_id: string;
  title: string;
  start_date: string;
  end_date: string;
  reason: string;
  matched_title: string | null;
}
export interface CategoryColor {
  category: string;
  color_id: string;
  color_name: string;
  hex: string;
}
export interface SyncPreview {
  category_colors?: CategoryColor[];
  items: PlanItem[];
  counts: Record<PlanAction, number>;
  plan_token: string;
}
export interface SyncResultItem {
  stable_id: string;
  title: string;
  status: string;
  detail: string;
  provider_event_id: string | null;
}
export interface SyncReport {
  batch_id: string;
  summary: Record<string, number>;
  results: SyncResultItem[];
}
export interface ImportDiff {
  added: string[];
  removed: string[];
  changed: string[];
  unchanged: string[];
  identical_source: boolean;
}
export interface ImportRecordResult {
  import_id: string;
  already_imported: boolean;
  diff: ImportDiff | null;
}

export interface Destination {
  provider: string; // "mock" | "google"
  calendarId: string;
  calendarName: string;
}
export interface CalendarOption {
  id: string;
  name: string;
}
