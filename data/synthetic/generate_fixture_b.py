"""Second synthetic fixture, deliberately different from fixture A to test generalisation:
Monday-first weeks, a leap-year February, different legend wording, cell fills that DRIFT from
the legend swatch colours (simulating print/scan variation), an untinted timed event, and a
cell whose text contradicts its legend colour.

All content is fictional ("Riverbend Elementary"). Run: python data/synthetic/generate_fixture_b.py
"""

import calendar
import json
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent
PAGE_W, PAGE_H = landscape(letter)

LEGEND = {  # key: (label, swatch rgb 0-255, drift applied to cell fills)
    "early": ("Early Release Day", (250, 200, 200), (8, -6, 5)),
    "closed": ("Closed - No Classes", (255, 235, 160), (-7, -8, 6)),
    "recess": ("Vacation / Recess", (190, 215, 250), (6, 5, -8)),
}
MONTHS = {
    (2028, 2): {29: ("closed", ["Leap Day", "School Closed"])},
    (2028, 3): {
        10: ("early", ["Early Release", "1:15 PM"]),
        14: (None, ["Parent", "Conferences", "4:00 PM"]),  # timed, no colour
        21: ("closed", ["Early Release"]),  # text contradicts legend colour
        **{d: ("recess", ["Spring Recess"] if d == 27 else []) for d in range(27, 32)},
    },
}
TRUTH_EVENTS = [
    {"title": "Leap Day", "start": "2028-02-29", "end": "2028-02-29", "category": "closed",
     "duration_kind": "all_day", "status": "confirmed"},
    {"title": "Early Release", "start": "2028-03-10", "end": "2028-03-10", "category": "early",
     "duration_kind": "half_day", "end_time": "13:15", "status": "confirmed"},
    {"title": "Parent Conferences", "start": "2028-03-14", "end": "2028-03-14", "category": None,
     "duration_kind": "timed", "start_time": "16:00", "status": "confirmed"},
    {"title": "Early Release", "start": "2028-03-21", "end": "2028-03-21", "category": "closed",
     "duration_kind": "unknown", "status": "ambiguous",
     "note": "text says early release, legend colour says closed: must be flagged"},
    {"title": "Spring Recess", "start": "2028-03-27", "end": "2028-03-31", "category": "recess",
     "duration_kind": "all_day", "status": "confirmed"},
]
X0, TOP, CW, CH, HDR = 36.0, 96.0, 100.0, 62.0, 18.0
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _rgb(c):
    return tuple(max(0, min(255, v)) / 255 for v in c)


def draw_page(c, year, month):
    c.setFont("Helvetica-Bold", 20)
    c.drawString(X0, PAGE_H - 40, f"Riverbend Elementary {calendar.month_name[month]} {year}")
    c.setFont("Helvetica", 9)
    c.drawString(X0, PAGE_H - 56, "School Year 2027-2028 (synthetic demo calendar)")
    lx = X0
    for _, (label, rgb, _) in LEGEND.items():
        c.setFillColorRGB(*_rgb(rgb))
        c.rect(lx, PAGE_H - 78, 12, 12, stroke=1, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        c.drawString(lx + 16, PAGE_H - 75, label)
        lx += 16 + c.stringWidth(label, "Helvetica", 8) + 18
    for i, d in enumerate(DAYS):
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(X0 + i * CW + CW / 2, PAGE_H - TOP - 12, d)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    marks = MONTHS[(year, month)]
    for r, week in enumerate(weeks):
        for col, d in enumerate(week):
            x, y = X0 + col * CW, PAGE_H - TOP - HDR - (r + 1) * CH
            in_month = d.month == month
            fill = (1, 1, 1)
            if in_month and d.day in marks and marks[d.day][0]:
                _, base, drift = LEGEND[marks[d.day][0]]
                fill = _rgb(tuple(b + dd for b, dd in zip(base, drift, strict=True)))
            c.setFillColorRGB(*fill)
            c.setStrokeColorRGB(0.4, 0.4, 0.4)
            c.rect(x, y, CW, CH, stroke=1, fill=1)
            c.setFillColorRGB(*((0, 0, 0) if in_month else (0.65, 0.65, 0.65)))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 4, y + CH - 12, str(d.day))
            if in_month and d.day in marks:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 7.5)
                for k, line in enumerate(marks[d.day][1]):
                    c.drawString(x + 4, y + CH - 26 - k * 9, line)
    c.showPage()


def main():
    pdf = OUT / "riverbend_2027_28.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(letter), invariant=1)
    c.setTitle("Riverbend Elementary 2027-28 (synthetic)")
    for ym in MONTHS:
        draw_page(c, *ym)
    c.save()
    truth = {
        "school": "Riverbend Elementary", "academic_year": "2027-2028",
        "timezone": "America/New_York", "week_starts_on": "monday",
        "legend": {k: {"label": v[0], "rgb255": list(v[1])} for k, v in LEGEND.items()},
        "events": TRUTH_EVENTS,
    }  # fmt: skip
    (OUT / "riverbend_2027_28.truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote {pdf}")


if __name__ == "__main__":
    main()
