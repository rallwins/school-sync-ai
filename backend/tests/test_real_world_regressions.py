"""Regressions found by validating against a real school calendar (not committed). Each test
recreates the *structure* that broke, with synthetic content."""

import io

import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.extraction.pipeline import ImportContext, extract_events
from app.legend.parse import parse_legend
from app.pdf.layout import extract_layout

CTX = ImportContext("S", "Y", "UTC", "d")


def build(draw) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4), invariant=1)
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def date_cells_and_checkboxes(c):
    """Small coloured date cells (with numbers) and tiny checkboxes beside list text."""
    c.setFont("Helvetica", 7)
    for i in range(7):
        c.setFillColorRGB(0.6 + i * 0.02, 0.8, 0.85)
        c.rect(70 + i * 20, 400, 19, 17, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(75 + i * 20, 405, f"{i + 1:02d}")
    for k, (r, g, b) in enumerate([(0.9, 0.4, 0.04), (0.87, 0.62, 0.06), (0.5, 0.5, 0.9)]):
        c.setFillColorRGB(r, g, b)
        c.rect(500, 380 - k * 20, 6, 6, stroke=0, fill=1)  # EY/PY checkbox-sized
        c.setFillColorRGB(0, 0, 0)
        c.drawString(515, 380 - k * 20, f"Jun {12 + k} Parent Orientation")
    # blank padding cells right next to list text
    for k, (r, g, b) in enumerate([(1, 0.98, 0.9), (0.62, 0.82, 0.85), (1, 1, 1)]):
        c.setFillColorRGB(r, g, b)
        c.rect(200, 300 - k * 20, 19, 17, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(230, 303 - k * 20, f"May {5 + k}-23 Summer programme")


def test_date_cells_checkboxes_and_padding_are_not_a_legend():
    lay = extract_layout(build(date_cells_and_checkboxes), "h")
    assert parse_legend(lay) == []


def centred_wide_swatch_legend(c):
    """Wide swatches in a column, labels centred inside a neighbouring strip (starts far right)."""
    c.setFont("Helvetica", 9)
    rows = [("Student Days", (1, 0.98, 0.91)), ("Public Holidays", (0.62, 0.82, 0.85)),
            ("School Opening & Reopening Days", (0.87, 0.62, 0.06)), ("Important Days", (0.94, 0.61, 0.34))]  # fmt: skip
    for k, (label, rgb) in enumerate(rows):
        y = 200 - k * 17
        c.setFillColorRGB(*rgb)
        c.rect(583, y, 75, 17, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.rect(658, y, 138, 17, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        w = c.stringWidth(label, "Helvetica", 9)
        c.drawString(658 + (138 - w) / 2, y + 5, label)


def test_wide_swatches_with_centred_full_labels():
    legend = parse_legend(extract_layout(build(centred_wide_swatch_legend), "h"))
    assert [e.label for e in legend] == [
        "Student Days", "Public Holidays", "School Opening & Reopening Days", "Important Days"]  # fmt: skip


def two_month_page(c):
    c.setFont("Helvetica", 8)
    for top in (500, 300):
        for i, d in enumerate(["Mon", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            c.drawString(74 + i * 20, top, d)
    c.drawString(54, 450, "May")
    c.drawString(54, 470, "2025")


def test_multi_month_page_gets_an_accurate_message_not_a_wrong_extraction():
    res = extract_events(extract_layout(build(two_month_page), "h"), CTX)
    assert res.events == [] and res.pages_skipped == [1]
    assert any("month grids on one page" in w for w in res.warnings)


def test_abbreviated_weekdays_and_rotated_label_are_recognised():
    from app.grid_detection.grid import find_month_year

    lay = extract_layout(build(two_month_page), "h")
    assert find_month_year(lay.pages[0]) == (2025, 5)


@pytest.mark.parametrize("label", ["Jun 12 PY Parent Orientation", "01 02 03 04", "27"])
def test_label_filter_rejects_list_rows_and_bare_numbers(label):
    from app.legend.parse import _valid_label

    assert not _valid_label(label.split())
