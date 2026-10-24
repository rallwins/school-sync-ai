"""Find legend swatches and the label printed beside them.

A swatch is a small filled rect that contains NO text (date cells contain day numbers) with a
short alphabetic label to its right. Candidates must form an aligned group of >= 3 distinct
colours (a real legend) and labels must not look like list rows ("Jun 12 ..."). These rules
exist because a real-world calendar's date cells and EY/PY checkboxes were once misread as a
legend.
"""

import re

from app.schemas import DocumentLayout, FillRect, LegendEntry, PageLayout, SourceRegion

SW_MIN_H, SW_MAX_H, SW_MIN_W, SW_MAX_W = 8.0, 24.0, 8.0, 90.0
LABEL_GAP = 60.0
WORD_GAP = 12.0  # max space between words of one label
MAX_LABEL_WORDS = 8
MIN_DISTINCT_COLOURS = 3
_DATE_LIKE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.IGNORECASE
)


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _has_text(page: PageLayout, f: FillRect) -> bool:
    return any(
        f.x0 <= (w.x0 + w.x1) / 2 <= f.x1 and f.y0 <= (w.y0 + w.y1) / 2 <= f.y1 for w in page.spans
    )


def _valid_label(words: list[str]) -> bool:
    if not words or len(words) > MAX_LABEL_WORDS:
        return False
    label = " ".join(words)
    if _DATE_LIKE.search(label):
        return False
    alpha = [w for w in words if sum(c.isalpha() for c in w) >= 3]
    numeric = [w for w in words if w.strip("|-").isdigit()]
    return bool(alpha) and len(numeric) <= 0.3 * len(words)


def _page_legend(page: PageLayout) -> list[LegendEntry]:
    cands = sorted(
        (
            f
            for f in page.fills
            if SW_MIN_H <= f.y1 - f.y0 <= SW_MAX_H
            and SW_MIN_W <= f.x1 - f.x0 <= SW_MAX_W
            and not _has_text(page, f)
        ),
        key=lambda f: (round(f.y0), f.x0),
    )
    found: list[tuple[FillRect, list[str], float]] = []
    for i, sw in enumerate(cands):
        cy = (sw.y0 + sw.y1) / 2
        nxt = [s.x0 for s in cands[i + 1 :] if abs((s.y0 + s.y1) / 2 - cy) < 4 and s.x0 > sw.x1]
        row = sorted(
            (
                w
                for w in page.spans
                if (w.x0 + w.x1) / 2 >= sw.x1 and abs((w.y0 + w.y1) / 2 - cy) < 6
                and (not nxt or w.x0 < min(nxt))
            ),
            key=lambda w: w.x0,
        )  # fmt: skip
        words = []
        if (
            row and row[0].x0 < sw.x1 + LABEL_GAP
        ):  # label may be centred, so only its START is bounded
            words = [row[0]]
            for w in row[1:]:
                if w.x0 - words[-1].x1 > WORD_GAP:
                    break
                words.append(w)
        texts = [w.text for w in words]
        if _valid_label(texts):
            found.append((sw, texts, words[-1].x1))

    # keep only aligned groups (same size, shared row or column) with enough distinct colours
    groups: dict[tuple[str, int, int, int], list[int]] = {}
    for idx, (sw, _, _) in enumerate(found):
        size = (round(sw.x1 - sw.x0), round(sw.y1 - sw.y0))
        groups.setdefault(("row", round(sw.y0), *size), []).append(idx)
        groups.setdefault(("col", round(sw.x0), *size), []).append(idx)
    keep: set[int] = set()
    for members in groups.values():
        if len({found[m][0].rgb for m in members}) >= MIN_DISTINCT_COLOURS:
            keep.update(members)

    out: list[LegendEntry] = []
    for idx in sorted(keep):
        sw, texts, x_end = found[idx]
        label = " ".join(texts)
        out.append(
            LegendEntry(
                label=label,
                category_id=_slug(label),
                rgb=sw.rgb,
                page=page.page,
                region=SourceRegion(page=page.page, x0=sw.x0, y0=sw.y0, x1=x_end, y1=sw.y1),
            )
        )
    return out


def parse_legend(layout: DocumentLayout) -> list[LegendEntry]:
    """Document-level legend: first occurrence of each (label, colour) wins."""
    seen: set[tuple[str, tuple[int, int, int]]] = set()
    result: list[LegendEntry] = []
    for page in layout.pages:
        for e in _page_legend(page):
            key = (e.label, e.rgb)
            if key not in seen:
                seen.add(key)
                result.append(e)
    return result
