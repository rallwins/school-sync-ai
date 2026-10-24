"use client";
import { useStore } from "@/lib/store";
import type { RGB } from "@/lib/types";

export const css = (c: RGB) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
const hex = (c: RGB) => "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");

export function Swatch({ rgb, label }: { rgb: RGB | null; label: string }) {
  return (
    <span
      role="img"
      aria-label={label}
      className="inline-block h-4 w-4 shrink-0 rounded-sm border border-line align-middle"
      style={rgb ? { background: css(rgb) } : { background: "transparent", borderStyle: "dashed" }}
    />
  );
}

export function LegendPanel() {
  const { result, events, legendConfirmed, setLegendConfirmed } = useStore();
  if (!result) return null;
  const counts = new Map<string, number>();
  for (const e of events) if (e.category_id) counts.set(e.category_id, (counts.get(e.category_id) ?? 0) + 1);
  const unmatched = events.filter((e) => e.sampled_color && !e.matched_legend_color);

  return (
    <section aria-labelledby="h-legend" className="rounded border border-line bg-surface p-4">
      <h2 id="h-legend" className="font-semibold">
        Legend mapping
      </h2>
      {result.legend.length === 0 ? (
        <p role="alert" className="mt-2 text-sm text-danger">
          No legend was detected. Colours cannot be mapped automatically; classification relies on
          printed text only.
        </p>
      ) : (
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Detected legend entries</caption>
          <thead className="text-left text-muted">
            <tr>
              <th scope="col" className="py-1 pr-2">Colour</th>
              <th scope="col" className="pr-2">Legend label (as printed)</th>
              <th scope="col" className="pr-2">Value</th>
              <th scope="col">Events</th>
            </tr>
          </thead>
          <tbody>
            {result.legend.map((l) => (
              <tr key={l.label + l.rgb.join()} className="border-t border-line">
                <td className="py-1 pr-2"><Swatch rgb={l.rgb} label={`Swatch ${hex(l.rgb)}`} /></td>
                <td className="pr-2">{l.label}</td>
                <td className="pr-2 font-mono text-xs">{hex(l.rgb)}</td>
                <td>{counts.get(l.category_id) ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {unmatched.length > 0 && (
        <p className="mt-3 text-sm text-warn" role="status">
          {unmatched.length} event(s) use a colour that matches no legend entry:{" "}
          {unmatched.map((e) => e.start_date).join(", ")}. They are marked for review, not guessed.
        </p>
      )}
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={legendConfirmed}
          onChange={(e) => setLegendConfirmed(e.target.checked)}
        />
        I have checked that this legend mapping is correct.
      </label>
    </section>
  );
}
