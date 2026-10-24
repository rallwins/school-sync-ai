"""Month-grid detection for vector PDFs: header month/year, weekday columns, cell -> date.

Assumes each day cell is a filled rectangle (white or coloured). Grids drawn only with stroked
lines (and most scans) need the OpenCV path, which is not implemented yet.

Dates are computed from the month header + cell position, then cross-checked against the day
number printed in the cell. A mismatch is reported; the date is never shifted to fit.
"""

import calendar
import itertools
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.schemas import FillRect, PageLayout, TextSpan

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
WEEKDAYS = {
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
    "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
}  # fmt: skip


class GridError(ValueError):
    pass


@dataclass
class Cell:
    day: date
    in_month: bool
    rect: FillRect
    day_number_ok: bool
    text: str
    page: int
    warnings: list[str] = field(default_factory=list)


def _center(s: TextSpan | FillRect) -> tuple[float, float]:
    return ((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2)


def find_month_year(page: PageLayout) -> tuple[int, int]:
    words = sorted(page.spans, key=lambda w: (round(w.y0), w.x0))
    for a, b in itertools.pairwise(words):
        if (
            a.text.lower() in MONTHS
            and re.fullmatch(r"(19|20)\d\d", b.text)
            and abs(a.y0 - b.y0) < 3
        ):
            return int(b.text), MONTHS[a.text.lower()]
    # Rotated (vertical) label: month and year words share a column, stacked either way.
    for a in page.spans:
        if a.text.lower() not in MONTHS:
            continue
        for b in page.spans:
            if (
                re.fullmatch(r"(19|20)\d\d", b.text)
                and abs(a.x0 - b.x0) < 4
                and abs(a.y0 - b.y0) < 40
            ):
                return int(b.text), MONTHS[a.text.lower()]
    raise GridError("no 'Month YYYY' header found")


def weekday_header_runs(page: PageLayout) -> list[list[TextSpan]]:
    """Every row holding 7 consecutive weekday labels, top to bottom (one per month grid).

    Looking for a *run* of 7 consecutive names (Mon Tu We ...) rather than counting labels per
    row ignores stray words such as 'Sat' or 'Th' that appear in ordinary text.
    """
    cands = sorted(
        (w for w in page.spans if w.text.lower().rstrip(".") in WEEKDAYS),
        key=lambda w: (w.y0, w.x0),
    )
    rows: list[list[TextSpan]] = []
    for w in cands:
        for r in rows:
            if abs(r[0].y0 - w.y0) < 3:
                r.append(w)
                break
        else:
            rows.append([w])
    runs: list[list[TextSpan]] = []
    for r in rows:
        r.sort(key=lambda w: w.x0)
        for k in range(len(r) - 6):
            win = r[k : k + 7]
            idx = [WEEKDAYS[w.text.lower().rstrip(".")] for w in win]
            if all((a + 1) % 7 == b for a, b in itertools.pairwise(idx)) and all(
                b.x0 - a.x1 < 200 for a, b in itertools.pairwise(win)
            ):
                runs.append(win)
                break
    return sorted(runs, key=lambda run: run[0].y0)


def _weekday_columns(page: PageLayout) -> list[tuple[float, int]]:
    """Return [(x_center, weekday_index)] for the header row, left to right."""
    runs = weekday_header_runs(page)
    if len(runs) > 1:
        raise GridError(f"{len(runs)} month grids on one page; multi-month pages are not supported")
    if not runs:
        raise GridError("weekday header row not found")
    return [(_center(w)[0], WEEKDAYS[w.text.lower().rstrip(".")]) for w in runs[0]]


def _cell_rects(page: PageLayout, header_bottom: float) -> list[FillRect]:
    cands = [f for f in page.fills if f.y0 >= header_bottom - 1 and (f.x1 - f.x0) > 30]
    if not cands:
        raise GridError("no cell-sized filled rectangles found")
    modal = Counter((round(f.x1 - f.x0), round(f.y1 - f.y0)) for f in cands).most_common(1)[0][0]
    return [
        f
        for f in cands
        if abs((f.x1 - f.x0) - modal[0]) <= 1.5 and abs((f.y1 - f.y0) - modal[1]) <= 1.5
    ]


def detect_cells(page: PageLayout) -> tuple[int, int, list[Cell]]:
    year, month = find_month_year(page)
    cols = _weekday_columns(page)
    week_start = cols[0][1]
    header_bottom = max(w.y1 for w in page.spans if w.text.lower().rstrip(".") in WEEKDAYS)
    rects = _cell_rects(page, header_bottom)

    row_keys = sorted({round(r.y0) for r in rects})
    weeks = calendar.Calendar(firstweekday=week_start).monthdatescalendar(year, month)
    if len(row_keys) != len(weeks):
        raise GridError(
            f"found {len(row_keys)} grid rows but {year}-{month:02d} needs {len(weeks)}"
        )

    cells: list[Cell] = []
    for r in rects:
        cx = _center(r)[0]
        col = min(range(7), key=lambda i: abs(cols[i][0] - cx))
        row = row_keys.index(round(r.y0))
        d = weeks[row][col]
        inside = [
            w for w in page.spans if r.x0 <= _center(w)[0] <= r.x1 and r.y0 <= _center(w)[1] <= r.y1
        ]
        nums = sorted(
            (w for w in inside if re.fullmatch(r"\d{1,2}", w.text)), key=lambda w: (w.y0, w.x0)
        )
        printed = int(nums[0].text) if nums else None
        ok = printed == d.day
        rest = [w for w in inside if not (nums and w is nums[0])]
        rest.sort(key=lambda w: (round(w.y0 / 2), w.x0))
        text = " ".join(w.text for w in rest)
        c = Cell(d, d.month == month and d.year == year, r, ok, text, page.page)
        if not ok:
            c.warnings.append(
                f"grid_misaligned: position implies {d.isoformat()} but cell prints {printed}"
            )
        cells.append(c)
    cells.sort(key=lambda c: c.day)
    return year, month, cells
