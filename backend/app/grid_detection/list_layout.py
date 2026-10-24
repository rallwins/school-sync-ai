"""List-style family calendars: month grids carry only colour, events live in a side list.

Structure handled (modelled on a real calendar that the cell-text extractor could not read):
- several month grids per page, each with a (possibly rotated) "Month YYYY" label and a
  weekday header, possibly abbreviated;
- day cells drawn as merged colour strips, so cells are located from the PRINTED DAY NUMBERS and
  the colour is sampled under each number;
- a `DATE | IMPORTANT DATES` list to the right with rows like `Sep 8-12 ...` or `Sep 18 | 19 ...`,
  and a separate PUBLIC HOLIDAYS column; wrapped titles continue on the next line;
- the legend lives elsewhere (usually the last page) and is matched by the caller.

Safety: a weekday that disagrees with a day number is reported and skipped, never shifted; a
list row whose date has no printed day number in its month grid is flagged for review; text
that merely looks like a date range ("Jun 16-Oct 31") is not a row.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date

from app.grid_detection.grid import MONTHS, WEEKDAYS, GridError, weekday_header_runs
from app.schemas import PageLayout, TextSpan

RGB = tuple[int, int, int]
_MONTH_ABBR = {m[:3].lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTH_ABBR["sept"] = 9
_DAY = re.compile(r"^(\d{1,2})(?:[-–](\d{1,2}))?$")
CONTINUATION_MAX_DY = 13.0  # a wrapped line sits closer than one row pitch (~17 pt)
MAX_MONTH_DISTANCE = 2  # a row's month must be within this many months of its grid's month


def parse_date_prefix(tokens: list[str]) -> tuple[int, int, int, list[str]] | None:
    """`Sep 8-12 ...` / `Jun 27 | 28 ...` -> (month, first_day, last_day, remaining tokens)."""
    if len(tokens) < 2:
        return None
    mo = _MONTH_ABBR.get(tokens[0].rstrip(".").lower())
    m = _DAY.match(tokens[1])
    if mo is None or m is None:
        return None
    d1 = int(m.group(1))
    d2 = int(m.group(2)) if m.group(2) else d1
    rest = tokens[2:]
    if not m.group(2) and len(rest) >= 2 and rest[0] == "|" and rest[1].isdigit():
        d2, rest = int(rest[1]), rest[2:]
    most = calendar.monthrange(2000, mo)[1]  # leap-year upper bound; exact check needs the year
    if not (1 <= d1 <= d2 <= most):
        return None
    return mo, d1, d2, rest


@dataclass
class ListRow:
    start: date
    end: date
    title: str
    raw_text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    column: str  # "events" | "holidays"
    in_grid: bool  # the start date has a printed day number in its month grid


@dataclass
class ListPage:
    rows: list[ListRow] = field(default_factory=list)
    cell_colors: dict[date, RGB | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    audience_columns: bool = False


def looks_like_list_layout(page: PageLayout) -> bool:
    words = {s.text for s in page.spans}
    return "DATE" in words and "DATES" in words and bool(weekday_header_runs(page))


def _center(s: TextSpan) -> tuple[float, float]:
    return ((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2)


def _colour_at(page: PageLayout, x: float, y: float) -> RGB | None:
    """Colour of the LAST-drawn fill containing the point (later fills paint over earlier)."""
    hit: RGB | None = None
    for f in page.fills:
        if f.x0 <= x <= f.x1 and f.y0 <= y <= f.y1:
            hit = f.rgb
    return hit


def _block_month_year(
    page: PageLayout, run: list[TextSpan], lo: float, hi: float
) -> tuple[int, int] | None:
    left = [s for s in page.spans if s.x1 <= run[0].x0 + 1 and lo <= s.y0 < hi]
    for a in left:
        if a.text.lower() not in MONTHS:
            continue
        for b in left:  # rotated label: year stacked above or below the month in one column
            if (
                re.fullmatch(r"(19|20)\d\d", b.text)
                and abs(a.x0 - b.x0) < 4
                and abs(a.y0 - b.y0) < 40
            ):
                return int(b.text), MONTHS[a.text.lower()]
        for b in left:  # horizontal label
            if re.fullmatch(r"(19|20)\d\d", b.text) and abs(a.y0 - b.y0) < 3 and b.x0 > a.x0:
                return int(b.text), MONTHS[a.text.lower()]
    return None


def _first(page: PageLayout, text: str, near_y: float | None = None) -> TextSpan | None:
    """First span with this text; if near_y is given it must sit on that header line, because
    list rows can contain the same words ('EY', 'PY', ...)."""
    return next(
        (s for s in page.spans if s.text == text and (near_y is None or abs(s.y0 - near_y) < 6)),
        None,
    )


def _has_checkbox_fills(page: PageLayout, x_lo: float, x_hi: float) -> bool:
    return any(
        4 <= f.x1 - f.x0 <= 9 and 4 <= f.y1 - f.y0 <= 9 and x_lo <= f.x0 <= x_hi for f in page.fills
    )


def _lines(words: list[TextSpan]) -> list[list[TextSpan]]:
    out: list[list[TextSpan]] = []
    for w in sorted(words, key=lambda s: (s.y0, s.x0)):
        if out and abs(out[-1][0].y0 - w.y0) < 5:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda s: s.x0) for line in out]


def _resolve_year(block: tuple[int, int], mo: int) -> int | None:
    by, bm = block
    best = min((by - 1, by, by + 1), key=lambda y: abs((y * 12 + mo) - (by * 12 + bm)))
    return best if abs((best * 12 + mo) - (by * 12 + bm)) <= MAX_MONTH_DISTANCE else None


_Cur = tuple[int, int, int, list[str], list[TextSpan]]


def _finish(
    cur: _Cur | None,
    column: str,
    block: tuple[int, int],
    grid_days: set[date],
    page_no: int,
    out: ListPage,
) -> None:
    if cur is None:
        return
    mo, d1, d2, title_tokens, ws = cur
    y = _resolve_year(block, mo)
    if y is None:
        out.warnings.append(
            f"page {page_no}: row dated month {mo} is far from its grid "
            f"({block[0]}-{block[1]:02d}); skipped"
        )
        return
    if calendar.monthrange(y, mo)[1] < d2:
        return
    start, end = date(y, mo, d1), date(y, mo, d2)
    title = re.sub(r"\s+", " ", " ".join(title_tokens)).strip(" |-")
    if not title:
        return
    out.rows.append(
        ListRow(
            start, end, title, " ".join(w.text for w in ws), page_no,
            min(w.x0 for w in ws), min(w.y0 for w in ws),
            max(w.x1 for w in ws), max(w.y1 for w in ws),
            column, start in grid_days,
        )
    )  # fmt: skip


def detect_list_page(page: PageLayout) -> ListPage:
    runs = weekday_header_runs(page)
    if not runs:
        raise GridError("no calendar grid found")
    out = ListPage()
    date_h = _first(page, "DATE")
    ref = date_h.y0 if date_h else None
    ey_h, pub_h = _first(page, "EY", ref), _first(page, "PUBLIC", ref)

    for i, run in enumerate(runs):
        lo = run[0].y0 - 2
        hi = runs[i + 1][0].y0 - 2 if i + 1 < len(runs) else page.height
        block = _block_month_year(page, run, lo, hi)
        if block is None:
            out.warnings.append(
                f"page {page.page}: month grid at y={run[0].y0:.0f} has no month label"
            )
            continue
        year, month = block
        days_in_month = calendar.monthrange(year, month)[1]
        gx0, gx1 = run[0].x0 - 12, run[-1].x1 + 12
        centers = [(_center(w)[0], WEEKDAYS[w.text.lower().rstrip(".")]) for w in run]
        hdr_bottom = max(w.y1 for w in run)

        # --- day cells from printed day numbers
        grid_days: set[date] = set()
        for w in page.spans:
            cx, cy = _center(w)
            if not (re.fullmatch(r"\d{1,2}", w.text) and gx0 <= cx <= gx1 and hdr_bottom < cy < hi):
                continue
            n = int(w.text)
            if not 1 <= n <= days_in_month:
                continue
            d = date(year, month, n)
            _, wd = min(centers, key=lambda c: abs(c[0] - cx))
            if wd != d.weekday():
                out.warnings.append(
                    f"page {page.page}: {d.isoformat()} sits in a {calendar.day_name[wd]} column; skipped"
                )
                continue
            grid_days.add(d)
            out.cell_colors.setdefault(d, _colour_at(page, cx, cy))

        # --- list columns for this block
        ev_x0 = (date_h.x0 - 4) if date_h else gx1 + 4
        # Title area ends where the audience checkboxes begin; when the header has no EY/PY
        # text, stop just before the holidays column (checkboxes are fills, never text).
        ev_x1 = (ey_h.x0 - 4) if ey_h else ((pub_h.x0 - 65) if pub_h else page.width)
        out.audience_columns = (
            out.audience_columns
            or ey_h is not None
            or _has_checkbox_fills(page, ev_x1 - 80, ev_x1 + 10)
        )
        regions = [("events", ev_x0, ev_x1)]
        if pub_h is not None:
            regions.append(("holidays", pub_h.x0 - 60, page.width))
        for column, x0, x1 in regions:
            words = [
                w for w in page.spans
                if x0 <= _center(w)[0] < x1 and lo + 3 <= _center(w)[1] < hi
            ]  # fmt: skip
            cur: tuple[int, int, int, list[str], list[TextSpan]] | None = None
            prev_y: float | None = None

            for line in _lines(words):
                parsed = parse_date_prefix([w.text for w in line])
                if parsed is not None:
                    _finish(cur, column, (year, month), grid_days, page.page, out)
                    mo, d1, d2, rest = parsed
                    cur = (mo, d1, d2, rest, list(line))
                elif (
                    cur is not None
                    and prev_y is not None
                    and line[0].y0 - prev_y < CONTINUATION_MAX_DY
                ):
                    cur = (
                        cur[0],
                        cur[1],
                        cur[2],
                        cur[3] + [w.text for w in line],
                        cur[4] + list(line),
                    )
                else:
                    _finish(cur, column, (year, month), grid_days, page.page, out)
                    cur = None
                prev_y = line[0].y0
            _finish(cur, column, (year, month), grid_days, page.page, out)
    return out
