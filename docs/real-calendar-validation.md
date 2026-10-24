# Validation against a real school calendar

Run 2026-10-24, **locally only** (the PDF is kept in the git-ignored `data/private/`, never
uploaded to the public demo, never committed). The document is a 9-page family calendar PDF:
cover, 7 month-pair pages, closing photo. It has a text layer and vector colouring.

## Result: 0 events extracted. The layout is not supported.

All 9 pages were skipped with a warning and nothing was written. That is the intended safe
failure, but it is a real failure: the product does not yet work on this calendar.

## What the real file looks like (and why it does not fit the current extractor)
| Real calendar | Extractor assumption |
|---|---|
| Two month grids per page | One grid per page |
| Date "cells" are small and drawn as **merged colour strips** (one rect spans several days) | Each cell is its own filled rect |
| Month label is **rotated** ("May" / "2025" stacked vertically) | Horizontal "Month YYYY" |
| Weekday header is abbreviated ("Mon Tu We Th Fr Sa Su") | Full or 3-letter names |
| Events are in a **separate list** to the right: `Jun 2-13  Professional Development...`, `Jun 27 | 28  ...` | Event text printed inside the date cell |
| Audience (EY / PY) shown as checkbox columns; public holidays in their own column | Not modelled |
| Legend only on the **last page**, wide swatches with centred labels | Legend on each page, small swatches |
| One colour ("Public Holidays") also tints every weekend and break day | Colour identifies the event |

## Bugs this found, now fixed (111 tests pass)
1. **False legend.** Date cells and 6x6 checkboxes were read as legend swatches, producing 40+
   nonsense legend entries whose labels were rows of list text. Swatches must now contain no text, be
   at least 8 pt, form an aligned group of 3+ distinct colours, and carry a short alphabetic label
   that does not look like a dated list row.
2. **Truncated legend labels** for centred labels ("Public" instead of "Public Holidays").
3. **Overflow-left labels** (a centred label wider than its strip) lost their first word.
4. Weekday abbreviations and rotated month labels are now recognised.
5. Multi-month pages now say so ("2 month grids on one page") instead of "no Month YYYY header".

After the fixes the legend is read correctly from this file: Student Days, Public Holidays,
School Opening & Reopening Days, Important Days, each with the right colour. Regression tests
recreate each broken structure with synthetic content (`tests/test_real_world_regressions.py`).

## What supporting this calendar would take (not built)
1. Locate date cells from the printed day numbers and sample colour under each, instead of
   relying on one rect per cell; handle two month blocks per page.
2. Parse the right-hand list: date, range (`Jun 2-13`) and pair (`Jun 27 | 28`) forms, with the
   year taken from the month block beside it, plus wrapped titles.
3. Take category from the grid colour via the document-wide (last-page) legend, but not treat
   "Public Holidays" tint as proof an event is a closure.
4. Policy for events with no duration (most rows are single-day activities with no time).
   Today these correctly come out `needs_review`; a bulk "treat as all-day" confirmation would be
   needed to make review practical.
5. Optional: EY/PY audience from the checkbox columns.

The public demo (Vercel + Lambda) has **not** been redeployed with these fixes.
