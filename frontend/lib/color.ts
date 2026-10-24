import type { RGB } from "./types";

/** A darker shade of a PDF colour for text-on-colour chips. Keeps hue, lowers lightness. */
export function darken(c: RGB, factor = 0.55): RGB {
  return [Math.round(c[0] * factor), Math.round(c[1] * factor), Math.round(c[2] * factor)];
}

/** Relative luminance (WCAG) of an sRGB colour, 0..1. */
export function luminance(c: RGB): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
}

/** Contrast ratio between two colours (WCAG), 1..21. */
export function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Chip background for white text: the PDF colour darkened just until the contrast ratio reaches
 * `minContrast` (WCAG AA = 4.5). Pale colours (cream) need a stronger darkening than saturated ones.
 */
export function chipColor(c: RGB, minContrast = 4.5): RGB {
  let factor = 0.6;
  let out = darken(c, factor);
  while (contrast(out, [255, 255, 255]) < minContrast && factor > 0.05) {
    factor -= 0.05;
    out = darken(c, factor);
  }
  return out;
}
