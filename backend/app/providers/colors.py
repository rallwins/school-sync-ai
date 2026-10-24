"""Map a PDF legend colour to one of Google Calendar's event colours.

PDF legends use pale pastels; Google's event palette is deliberately much darker and more
saturated, which is what we want on a calendar. Matching is by HUE (CIE Lab angle), not by
lightness, so a pale teal swatch maps to a strong cyan-blue rather than to a washed-out colour.
Near-neutral swatches (cream, white, grey) map to Graphite. The mapping is deterministic, shown
to the user before sync, and never decides anything about dates, durations or identity.

Hex values are Google Calendar's current web palette for each colorId.
"""

import math
from dataclasses import dataclass

from app.color_mapping.lab import rgb_to_lab

NEUTRAL_CHROMA = 12.0  # below this a colour is treated as grey/cream


@dataclass(frozen=True)
class GoogleColor:
    color_id: str
    name: str
    hex: str


PALETTE = (
    GoogleColor("11", "Tomato", "#d50000"),
    GoogleColor("4", "Flamingo", "#e67c73"),
    GoogleColor("6", "Tangerine", "#f4511e"),
    GoogleColor("5", "Banana", "#f6bf26"),
    GoogleColor("10", "Basil", "#0b8043"),
    GoogleColor("2", "Sage", "#33b679"),
    GoogleColor("7", "Peacock", "#039be5"),
    GoogleColor("9", "Blueberry", "#3f51b5"),
    GoogleColor("1", "Lavender", "#7986cb"),
    GoogleColor("3", "Grape", "#8e24aa"),
)
GRAPHITE = GoogleColor("8", "Graphite", "#616161")
BY_ID = {c.color_id: c for c in (*PALETTE, GRAPHITE)}


def _rgb(hex_: str) -> tuple[int, int, int]:
    return (int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16))


def _hue_chroma(rgb: tuple[int, int, int]) -> tuple[float, float]:
    _, a, b = rgb_to_lab(rgb)
    return (math.degrees(math.atan2(b, a)) % 360, math.hypot(a, b))


_HUES = {c.color_id: _hue_chroma(_rgb(c.hex))[0] for c in PALETTE}


def google_color_for(rgb: tuple[int, int, int] | None) -> GoogleColor | None:
    """None means 'leave the calendar's default colour' (no colour evidence)."""
    if rgb is None:
        return None
    hue, chroma = _hue_chroma(rgb)
    if chroma < NEUTRAL_CHROMA:
        return GRAPHITE

    def gap(c: GoogleColor) -> float:
        d = abs(hue - _HUES[c.color_id])
        return min(d, 360 - d)

    return min(PALETTE, key=gap)
