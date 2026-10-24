import { describe, expect, it } from "vitest";
import { chipColor, contrast, darken } from "./color";
import type { RGB } from "./types";

// the legend colours of a real school calendar
const LEGEND: Record<string, RGB> = {
  "Student Days": [255, 249, 233],
  "Public Holidays": [158, 209, 216],
  "School Opening": [222, 159, 16],
  "Important Days": [240, 156, 86],
};

describe("darker chips", () => {
  it("every legend colour gets readable white text once darkened", () => {
    for (const c of Object.values(LEGEND)) {
      expect(contrast(chipColor(c), [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("is darker than the original and keeps channels in range", () => {
    for (const c of Object.values(LEGEND)) {
      const d = chipColor(c);
      expect(d.every((v, i) => v < c[i] && v >= 0)).toBe(true);
    }
    expect(darken([100, 100, 100], 0.5)).toEqual([50, 50, 50]);
  });
  it("the original pastel colours are NOT readable with white text (why we darken)", () => {
    expect(contrast(LEGEND["Public Holidays"], [255, 255, 255])).toBeLessThan(2);
  });
});
