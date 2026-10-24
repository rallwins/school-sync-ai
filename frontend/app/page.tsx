"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, extractCalendar, recordImport } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { ImportMeta } from "@/lib/types";

const MAX_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? "10");
const MAX_BYTES = MAX_MB * 1024 * 1024;

export default function ImportPage() {
  const router = useRouter();
  const { load, setImportRec, meta, result, clear } = useStore();
  const [zones, setZones] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      setZones(Intl.supportedValuesOf("timeZone"));
    } catch {
      setZones(["America/Chicago", "America/New_York", "America/Los_Angeles", "UTC"]);
    }
  }, []);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const file = f.get("file") as File | null;
    if (!file || file.size === 0) return setError("Choose a PDF file.");
    if (file.size > MAX_BYTES) return setError(`File is larger than ${MAX_MB} MB.`);
    if (!file.name.toLowerCase().endsWith(".pdf")) return setError("File must be a .pdf.");
    const m: ImportMeta = {
      fileName: file.name,
      school: String(f.get("school")).trim(),
      academicYear: String(f.get("year")).trim(),
      timezone: String(f.get("tz")).trim(),
      destination: "file",
    };
    setBusy(true);
    try {
      const res = await extractCalendar(file, {
        school: m.school,
        academicYear: m.academicYear,
        timezone: m.timezone,
        tolerance: Number(f.get("tolerance")),
      });
      load(m, res);
      // Record once, at upload time, so a re-upload of the same PDF is recognised.
      setImportRec(await recordImport(m, res.source_hash, res.events).catch(() => null));
      router.push("/review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error.");
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-1 w-full rounded border border-line bg-surface px-3 py-2";
  return (
    <div className="grid gap-8 md:grid-cols-[minmax(0,32rem)_1fr]">
      <section aria-labelledby="h-upload">
        <h1 id="h-upload" className="text-xl font-semibold">
          Import a school calendar
        </h1>
        <p className="mt-1 text-sm text-muted">
          Use a synthetic or non-sensitive PDF on shared deployments. Nothing is sent to a calendar
          provider from this page.
        </p>
        <form onSubmit={onSubmit} className="mt-4 space-y-4" aria-busy={busy}>
          <label className="block text-sm">
            Calendar PDF
            <input name="file" type="file" accept="application/pdf,.pdf" required className={input} />
          </label>
          <label className="block text-sm">
            School name
            <input name="school" required maxLength={200} defaultValue="Maple Grove Academy" className={input} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm">
              Academic year
              <input name="year" required maxLength={20} defaultValue="2025-2026" className={input} />
            </label>
            <label className="block text-sm">
              Timezone
              <input name="tz" required list="zones" defaultValue="America/Chicago" className={input} />
              <datalist id="zones">
                {zones.map((z) => (
                  <option key={z} value={z} />
                ))}
              </datalist>
            </label>
          </div>
          <fieldset className="text-sm">
            <legend className="mb-1">Destination</legend>
            <label className="mr-4">
              <input type="radio" name="dest" defaultChecked /> File export (ICS / CSV)
            </label>
            <label className="mr-4 text-muted">
              <input type="radio" name="dest" disabled /> Google (not configured)
            </label>
            <label className="text-muted">
              <input type="radio" name="dest" disabled /> Microsoft (not configured)
            </label>
          </fieldset>
          <details className="text-sm">
            <summary className="cursor-pointer">Advanced</summary>
            <label className="mt-2 block">
              Colour match tolerance (CIE76 ΔE, 1–40)
              <input name="tolerance" type="number" min={1} max={40} step={0.5} defaultValue={12} className={input} />
            </label>
          </details>
          <button
            disabled={busy}
            className="rounded bg-accent px-4 py-2 font-medium text-white disabled:opacity-60 dark:text-black"
          >
            {busy ? "Analysing PDF…" : "Upload and analyse"}
          </button>
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        </form>
      </section>

      <section aria-labelledby="h-hist">
        <h2 id="h-hist" className="text-lg font-semibold">
          Current session
        </h2>
        {result && meta ? (
          <div className="mt-3 rounded border border-line bg-surface p-4 text-sm">
            <p className="font-medium">{meta.fileName}</p>
            <p className="text-muted">
              {meta.school} · {meta.academicYear} · {meta.timezone}
            </p>
            <p className="mt-2">
              {result.events.length} events from {result.pages_processed.length} page(s)
              {result.pages_skipped.length > 0 && `, ${result.pages_skipped.length} skipped`}.
            </p>
            <div className="mt-3 flex gap-3">
              <a className="text-accent underline" href="/review">
                Continue review
              </a>
              <button className="text-muted underline" onClick={clear}>
                Discard
              </button>
            </div>
          </div>
        ) : (
          <p className="mt-3 rounded border border-dashed border-line p-6 text-sm text-muted">
            No import yet. Import history is kept only for this browser tab until persistence is added
            in Milestone 3.
          </p>
        )}
      </section>
    </div>
  );
}
