"""Third synthetic fixture: LIST-STYLE family calendar (structure modelled on a real calendar that
the extractor could not read, with entirely fictional content, "Cedar Hill School").

Structure: two month grids per page; rotated month labels; abbreviated weekday header; day cells
drawn as merged colour strips with day numbers on top; events in a separate list to the right
(`DATE | IMPORTANT DATES`) in forms like `Sep 8-12`, `Sep 18 | 19`; a PUBLIC HOLIDAYS column whose
titles wrap; legend only on the last page (wide swatches, centred labels); a notes box whose
`Jun 16-Oct 31` text must NOT become an event; a text-only cover page.

Run: python data/synthetic/generate_fixture_c.py
"""

import calendar
import json
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent
W, H = landscape(A4)  # 842 x 595

CREAM, TEAL, GOLD, ORANGE = (255, 249, 233), (158, 209, 216), (222, 159, 16), (240, 156, 86)
LEGEND = [("Student Days", CREAM), ("Public Holidays", TEAL),
          ("School Opening & Reopening Days", GOLD), ("Important Days", ORANGE)]  # fmt: skip

COL_X0, COL_PITCH, ROW_PITCH = 74.0, 20.5, 17.0
DAYS = ["Mon", "Tu", "We", "Th", "Fr", "Sa", "Su"]

# (year, month): special day colours
SPECIAL = {
    (2025, 9): {1: TEAL, 5: TEAL, **{d: ORANGE for d in (8, 9, 10, 11, 12, 18, 19, 26)}},
    (2025, 10): {2: TEAL, 6: GOLD, 20: TEAL, 21: TEAL, **{d: ORANGE for d in range(27, 32)}},
    (2025, 12): {22: GOLD, 25: TEAL},
    (2026, 1): {5: GOLD, 26: TEAL},
}
# list rows: (date text, title, column)  column: "E" events, "H" public holidays
ROWS = {
    (2025, 9): [("Sep 8-12", "Book Fair", "E"), ("Sep 18 | 19", "Parent Workshops", "E"),
                ("Sep 26", "Open House 4:30 PM", "E"), ("Sep 1", "Founders Day", "H"),
                ("Sep 5", "Teachers Day", "H")],
    (2025, 10): [("Oct 6", "School Reopens", "E"), ("Oct 27-31", "Field Trip", "E"),
                 ("Oct 2", "Gandhi Jayanti", "H"), ("Oct 20-21", "Diwali Festival of Lights|Holiday", "H")],
    (2025, 12): [("Dec 22", "School Closes for Learners", "E"), ("Dec 25", "Christmas", "H")],
    (2026, 1): [("Jan 5", "School Reopens for Learners", "E"), ("Jan 26", "Republic Day", "H")],
}  # fmt: skip
PAGES = [[(2025, 9), (2025, 10)], [(2025, 12), (2026, 1)]]

TRUTH = [  # title, start, end, duration_kind, status, category label, page
    ("Book Fair", "2025-09-08", "2025-09-12", "unknown", "needs_review", "Important Days", 2),
    ("Parent Workshops", "2025-09-18", "2025-09-19", "unknown", "needs_review", "Important Days", 2),
    ("Open House", "2025-09-26", "2025-09-26", "timed", "confirmed", "Important Days", 2),
    ("Founders Day", "2025-09-01", "2025-09-01", "all_day", "inferred", "Public Holidays", 2),
    ("Teachers Day", "2025-09-05", "2025-09-05", "all_day", "inferred", "Public Holidays", 2),
    ("School Reopens", "2025-10-06", "2025-10-06", "unknown", "needs_review",
     "School Opening & Reopening Days", 2),
    ("Field Trip", "2025-10-27", "2025-10-31", "unknown", "needs_review", "Important Days", 2),
    ("Gandhi Jayanti", "2025-10-02", "2025-10-02", "all_day", "inferred", "Public Holidays", 2),
    ("Diwali Festival of Lights Holiday", "2025-10-20", "2025-10-21", "all_day", "confirmed",
     "Public Holidays", 2),
    ("School Closes for Learners", "2025-12-22", "2025-12-22", "unknown", "needs_review",
     "School Opening & Reopening Days", 3),
    ("Christmas", "2025-12-25", "2025-12-25", "all_day", "inferred", "Public Holidays", 3),
    ("School Reopens for Learners", "2026-01-05", "2026-01-05", "unknown", "needs_review",
     "School Opening & Reopening Days", 3),
    ("Republic Day", "2026-01-26", "2026-01-26", "all_day", "inferred", "Public Holidays", 3),
]  # fmt: skip


def rgb(c):
    return tuple(v / 255 for v in c)


def y(top):  # top-based y to reportlab y
    return H - top


def draw_block(c, hdr_top, year, month):
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 0)
    for i, d in enumerate(DAYS):
        c.drawString(COL_X0 + i * COL_PITCH, y(hdr_top + 8), d)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    sp = SPECIAL[(year, month)]
    for r, week in enumerate(weeks):
        top = hdr_top + 12 + r * ROW_PITCH
        c.setFillColorRGB(1, 1, 1)
        c.rect(71, y(top + 17), 584, 17, stroke=0, fill=1)  # white row background
        runs: list[tuple[int, int, tuple]] = []  # merged colour strips
        for col, d in enumerate(week):
            if d.month != month:
                continue
            colour = TEAL if col >= 5 else sp.get(d.day, CREAM)
            if runs and runs[-1][1] == col - 1 and runs[-1][2] == colour:
                runs[-1] = (runs[-1][0], col, colour)
            else:
                runs.append((col, col, colour))
        for a, b, colour in runs:
            c.setFillColorRGB(*rgb(colour))
            c.rect(COL_X0 - 5 + a * COL_PITCH, y(top + 17), (b - a + 1) * COL_PITCH, 17, stroke=0, fill=1)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        for col, d in enumerate(week):
            if d.month == month:
                c.drawString(COL_X0 + col * COL_PITCH + (2 if d.day < 10 else 0), y(top + 12), f"{d.day:02d}")
    # rotated "Month YYYY" label, reading bottom-to-top
    c.saveState()
    c.translate(66, y(hdr_top + 12 + len(weeks) * ROW_PITCH))
    c.rotate(90)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(0, 0, f"{calendar.month_name[month]} {year}")
    c.restoreState()
    # list rows
    c.setFont("Helvetica", 8)
    ey = hdr_top + 8
    hy = hdr_top + 8
    for text, title, col in ROWS[(year, month)]:
        if col == "E":
            c.drawString(229, y(ey), text)
            c.drawString(300, y(ey), title)
            ey += 17
        else:
            c.drawString(614, y(hy), text)
            parts = title.split("|")
            for k, part in enumerate(parts):
                c.drawString(659, y(hy + k * 9), part)
            hy += 17 if len(parts) == 1 else 26


def draw_page(c, months, last):
    c.setFont("Helvetica-Bold", 9)
    c.drawString(323, y(122), "ACADEMIC YEAR 2025-2026 | FAMILY CALENDAR")
    c.setFont("Helvetica-Bold", 8)
    c.drawString(229, y(147), "DATE")
    c.drawString(390, y(147), "IMPORTANT DATES")
    c.drawString(588, y(147), "EY")
    c.drawString(601, y(147), "PY")
    c.drawString(659, y(147), "PUBLIC HOLIDAYS")
    for i, (yr, mo) in enumerate(months):
        draw_block(c, 160 + i * 150, yr, mo)
    if last:
        c.setFillColorRGB(*rgb((235, 229, 219)))
        c.rect(583, y(442), 212, 34, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(635, y(402), "Academic Year (2 Semesters)")
        c.setFont("Helvetica", 8)
        c.drawString(666, y(419), "Jun 16-Oct 31")
        c.drawString(667, y(435), "Nov 1-Apr 23")
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(112, y(407), "Note: Some holidays may be declared by the authorities at short notice.")
        for k, (label, colour) in enumerate(LEGEND):
            top = 466 + k * 17
            c.setFillColorRGB(*rgb(colour))
            c.rect(583, y(top + 17), 75, 17, stroke=0, fill=1)
            c.setFillColorRGB(1, 1, 1)
            c.rect(658, y(top + 17), 138, 17, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 8)
            c.drawString(658 + (138 - c.stringWidth(label, "Helvetica", 8)) / 2, y(top + 12), label)
    c.showPage()


def main():
    pdf = OUT / "cedar_hill_2025_26.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(A4), invariant=1)
    c.setTitle("Cedar Hill School 2025-26 (synthetic)")
    c.setFont("Helvetica-Bold", 28)
    c.drawString(80, y(250), "Annual Calendar 2025 - 2026")
    c.setFont("Helvetica", 16)
    c.drawString(80, y(300), "Cedar Hill School")
    c.showPage()  # page 1: cover
    for i, months in enumerate(PAGES):
        draw_page(c, months, last=(i == len(PAGES) - 1))
    c.save()
    events = [
        {"title": t, "start": s, "end": e, "duration_kind": k, "status": st, "category": cat, "page": p}
        for t, s, e, k, st, cat, p in TRUTH
    ]
    truth = {"school": "Cedar Hill School", "academic_year": "2025-2026", "timezone": "Asia/Kolkata",
             "layout": "list-style, two months per page", "events": events,
             "legend": {lab: {"label": lab, "rgb255": list(col)} for lab, col in LEGEND}}  # fmt: skip
    (OUT / "cedar_hill_2025_26.truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote {pdf}")


if __name__ == "__main__":
    main()
    assert date(2025, 9, 1).weekday() == 0
