"""sRGB -> CIE Lab (D65) and CIE76 Delta E. Legend matching uses a tolerance, never exact RGB."""

import math
from collections.abc import Iterable

from app.schemas import LegendEntry, LegendMatch

RGB = tuple[int, int, int]
DEFAULT_TOLERANCE = 12.0  # CIE76 dE; configurable per import (Settings page)
AMBIGUITY_MARGIN = 3.0  # runner-up within this dE of the best => mapping is ambiguous


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_lin(v) for v in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: RGB, b: RGB) -> float:
    return math.dist(rgb_to_lab(a), rgb_to_lab(b))


def is_blank(rgb: RGB) -> bool:
    """White / near-white background, i.e. 'no colour coding'."""
    return delta_e(rgb, (255, 255, 255)) < 4.0


def match_color(
    rgb: RGB, legend: Iterable[LegendEntry], tolerance: float = DEFAULT_TOLERANCE
) -> LegendMatch:
    scored = sorted(((delta_e(rgb, e.rgb), e) for e in legend), key=lambda t: t[0])
    if not scored or scored[0][0] > tolerance:
        best = scored[0][0] if scored else None
        return LegendMatch(entry=None, delta_e=best, ambiguous=False)
    best_de, best_entry = scored[0]
    ambiguous = (
        len(scored) > 1
        and scored[1][0] <= tolerance
        and (scored[1][0] - best_de < AMBIGUITY_MARGIN)
    )
    return LegendMatch(entry=best_entry, delta_e=best_de, ambiguous=ambiguous)
