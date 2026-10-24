# Validation against a real school calendar

Run 2026-10-24, **locally only**. The PDF stays in the git-ignored `data/private/`; it was never
uploaded to the public demo and is not in this repository. It is a 9-page family calendar:
cover, 7 pages of month pairs (May 2025 to Jun 2026), closing photo. Text layer plus vector colour.

## Outcome
| | First run | After this work |
|---|---|---|
| Events extracted | **0** (all pages skipped) | **113** |
| Legend | 40+ nonsense entries | 4 correct entries with correct colours |

### How the 113 was checked
I counted the dated rows in the source document page by page (both the "Important Dates" list and
the "Public Holidays" column) and compared with the extractor's per-page output:

| Page | 2 | 3 | 4 | 5 | 6 | 7 | 8 | Total |
|---|---|---|---|---|---|---|---|---|
| Source rows | 11 | 24 | 18 | 14 | 19 | 22 | 5 | 113 |
| Extracted | 11 | 24 | 18 | 14 | 19 | 22 | 5 | 113 |

Ranges (`Jun 2-13`), pairs (`Jun 27 | 28`), wrapped holiday titles and the Dec 2025 / Jan 2026
boundary came out right in the samples I compared. **Limits of this check:** counts match and I
compared a sample of dates and titles by eye; I did not diff all 113 rows field by field, and there
is no automated test against this file (it is private). Synthetic fixture C covers the same structure.

### What the app does with them
- 33 are all-day (30 inferred from the "Public Holidays" legend colour, with a visible
  "inferred from colour only" warning; a few from explicit text such as "Holiday" or "Fall Break").
- 80 have **no stated duration** (assemblies, trips, workshops) and are `needs_review`. They can be
  bulk-marked all-day by the user in one explicit, confirmed action; ambiguous or conflicting events
  are excluded from that action.
- 1 is `ambiguous`: one date is painted pure orange (255,153,0), which matches no legend colour
  (nearest is dE 18, tolerance 12), so it is flagged rather than guessed.
- Audience (EY / PY) is **not read**; the app says so. Several titles keep a trailing `| EY & PY`.
- The "Public Holidays" tint also colours weekends and breaks, so an event on a Saturday is
  "inferred all-day" because of the weekend colour. Treat colour-only inferences accordingly.

## Bugs this validation found and fixed
1. Date cells and 6x6 checkboxes were read as legend swatches (40+ bogus entries).
2. Centred legend labels were truncated ("Public"), and labels overflowing leftwards lost a word.
3. Plural wording ("Public **Holidays**") did not match the all-day keyword rules.
4. A stray "EY"/"PY" word inside a row was taken for the column header, clipping titles and dropping
   an entire page of events.
5. A row whose date sat 4 pt below its first title line was split in two, leaving the title "Day".
6. Weekday header detection counted labels per row, so a stray "Sa"/"Th" broke a page; it now
   looks for a run of 7 consecutive weekday names.
7. Rotated month labels, abbreviated weekdays and several month grids per page are now supported.

## Still not handled
Scanned/image-only pages, grids drawn only with stroked lines, icon or pattern legends, audience
columns, and any layout that differs materially from the two structures tested (cell-text
calendars and this list style).

## Reproducing
`python data/synthetic/generate_fixture_c.py` builds a fictional calendar with the same structure;
`backend/tests/test_list_layout.py` asserts the results. To run your own file locally:
put it under `data/private/` (ignored by git) and use the upload form against a local server.
