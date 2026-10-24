"""Generate deterministic synthetic school-calendar PDFs plus ground truth.

All content is fictional ("Maple Grove Academy"). Run:  python data/synthetic/generate_fixtures.py
Outputs: data/synthetic/maple_grove_2025_26.pdf and maple_grove_2025_26.truth.json

The legend is printed on every page. One date (2025-10-31) is deliberately filled with a colour
that is NOT in the legend and carries no text: the pipeline must flag it, not invent an event.
"""
import calendar
import json
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent
PAGE_W, PAGE_H = landscape(letter)

LEGEND = {
    "holiday": ("Holiday / No School", (0.957, 0.714, 0.714)),
    "half_day": ("Half Day (Early Dismissal)", (1.0, 0.878, 0.541)),
    "pd_day": ("Teacher Work Day - No Students", (0.718, 0.843, 0.957)),
    "break": ("School Break", (0.804, 0.910, 0.753)),
}
UNLISTED = (0.878, 0.765, 0.941)  # purple, deliberately absent from the legend

# (year, month) -> {day: (category | None for unlisted, label text lines)}
MONTHS: dict[tuple[int, int], dict[int, tuple[str | None, list[str]]]] = {
    (2025, 9): {
        1: ("holiday", ["Labor Day", "No School"]),
        26: ("half_day", ["Early Dismissal", "12:30 PM"]),
    },
    (2025, 10): {
        13: ("pd_day", ["Teacher", "Work Day"]),
        17: ("half_day", ["Half Day"]),  # no dismissal time given
        31: (None, []),  # unlisted colour, no text
    },
    (2025, 12): {d: ("break", ["Winter Break"] if d == 22 else []) for d in range(22, 32)},
    (2026, 1): {
        1: ("break", ["Winter Break"]),
        19: ("holiday", ["MLK Day", "No School"]),
    },
}

TRUTH_EVENTS = [
    {"title": "Labor Day", "start": "2025-09-01", "end": "2025-09-01", "category": "holiday",
     "duration_kind": "all_day", "page": 1, "status": "confirmed"},
    {"title": "Early Dismissal", "start": "2025-09-26", "end": "2025-09-26",
     "category": "half_day", "duration_kind": "half_day", "end_time": "12:30", "page": 1,
     "status": "confirmed"},
    {"title": "Teacher Work Day", "start": "2025-10-13", "end": "2025-10-13",
     "category": "pd_day", "duration_kind": "all_day", "page": 2, "status": "confirmed"},
    {"title": "Half Day", "start": "2025-10-17", "end": "2025-10-17", "category": "half_day",
     "duration_kind": "half_day", "end_time": None, "page": 2, "status": "needs_review"},
    {"title": None, "start": "2025-10-31", "end": "2025-10-31", "category": None,
     "duration_kind": "unknown", "page": 2, "status": "ambiguous"},
    {"title": "Winter Break", "start": "2025-12-22", "end": "2025-12-31", "category": "break",
     "duration_kind": "all_day", "page": 3, "status": "confirmed"},
    {"title": "Winter Break", "start": "2026-01-01", "end": "2026-01-01", "category": "break",
     "duration_kind": "all_day", "page": 4, "status": "confirmed",
     "note": "continuation of the Dec 22-31 block; merge into 2025-12-22..2026-01-01 in review"},
    {"title": "MLK Day", "start": "2026-01-19", "end": "2026-01-19", "category": "holiday",
     "duration_kind": "all_day", "page": 4, "status": "confirmed"},
]

X0, TOP, CW, CH, HDR = 36.0, 96.0, 100.0, 62.0, 18.0
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def draw_page(c: canvas.Canvas, year: int, month: int) -> None:
    c.setFont("Helvetica-Bold", 20)
    c.drawString(X0, PAGE_H - 40, f"Maple Grove Academy - {calendar.month_name[month]} {year}")
    c.setFont("Helvetica", 9)
    c.drawString(X0, PAGE_H - 56, "Academic Year 2025-2026 (synthetic demo calendar)")
    # legend
    lx = X0
    for key, (label, rgb) in LEGEND.items():
        c.setFillColorRGB(*rgb)
        c.rect(lx, PAGE_H - 78, 12, 12, stroke=1, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        c.drawString(lx + 16, PAGE_H - 75, label)
        lx += 16 + c.stringWidth(label, "Helvetica", 8) + 18
    # weekday header
    for i, d in enumerate(DAYS):
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(X0 + i * CW + CW / 2, PAGE_H - TOP - 12, d)
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
    marks = MONTHS[(year, month)]
    for r, week in enumerate(weeks):
        for col, d in enumerate(week):
            x = X0 + col * CW
            y = PAGE_H - TOP - HDR - (r + 1) * CH
            in_month = d.month == month
            if in_month and d.day in marks:
                cat, _ = marks[d.day]
                c.setFillColorRGB(*(LEGEND[cat][1] if cat else UNLISTED))
            else:
                c.setFillColorRGB(1, 1, 1)
            c.setStrokeColorRGB(0.4, 0.4, 0.4)
            c.rect(x, y, CW, CH, stroke=1, fill=1)
            c.setFillColorRGB(0, 0, 0) if in_month else c.setFillColorRGB(0.65, 0.65, 0.65)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 4, y + CH - 12, str(d.day))
            if in_month and d.day in marks:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 7.5)
                for k, line in enumerate(marks[d.day][1]):
                    c.drawString(x + 4, y + CH - 26 - k * 9, line)
    c.showPage()


def main() -> None:
    pdf_path = OUT / "maple_grove_2025_26.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=landscape(letter), invariant=1)
    c.setTitle("Maple Grove Academy 2025-26 (synthetic)")
    for ym in MONTHS:
        draw_page(c, *ym)
    c.save()
    truth = {
        "school": "Maple Grove Academy",
        "academic_year": "2025-2026",
        "timezone": "America/Chicago",
        "week_starts_on": "sunday",
        "legend": {k: {"label": v[0], "rgb255": [round(x * 255) for x in v[1]]}
                   for k, v in LEGEND.items()},
        "events": TRUTH_EVENTS,
    }
    (OUT / "maple_grove_2025_26.truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote {pdf_path}")


if __name__ == "__main__":
    main()
