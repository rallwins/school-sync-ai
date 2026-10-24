"""Best-effort school-name detection from a PDF's text layer.

A school name is almost always a short title ending in School / Academy / Institute / College...
(or "University of X"). Only the first two pages and the last page are searched, lines containing
digits are ignored (list rows such as "Jan 5 School Reopens"), and the keyword must END the name,
so event text like "School Closes for Learners" is never mistaken for a name.

Limits, stated plainly: a logo drawn as an image is invisible to this (only text is read), and
letter-spaced text ("C O N T I N U U M S C H O O L") has no word boundaries, so only a trailing
keyword can be split off. The result is a suggestion the user can edit.
"""

import re
from dataclasses import dataclass

from app.schemas import DocumentLayout, PageLayout, TextSpan

KEYWORDS = (
    "school", "academy", "institute", "college", "elementary", "primary", "secondary",
    "montessori", "vidyalaya", "kindergarten", "preschool", "university", "gymnasium",
)  # fmt: skip
_KW = "|".join(KEYWORDS)
_ENDS_WITH_KW = re.compile(rf"\b({_KW})$", re.IGNORECASE)
_STARTS_UNIVERSITY = re.compile(r"^university of\b", re.IGNORECASE)
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_MONTH_YEAR_TAIL = re.compile(
    rf"\s*[-–|:,]?\s*(?:{_MONTHS})[a-z]*\.?\s+(?:19|20)\d\d\s*$", re.IGNORECASE
)
_EDGE_SEPS = " -–|:,.·"
MAX_WORDS, MIN_LEN, MAX_LEN = 8, 4, 70
LETTER_RUN_MIN = 4


@dataclass(frozen=True)
class SchoolNameGuess:
    name: str
    page: int
    letter_spaced: bool

    @property
    def where(self) -> str:
        how = "letter-spaced text, check the spelling" if self.letter_spaced else "title text"
        return f"{how} on page {self.page}"


def collapse_letter_spaced(tokens: list[str]) -> tuple[list[str], bool]:
    """Join runs of >= 4 single letters ("C O N T I N U U M") into one word. If the joined run
    ends in a school keyword, split that keyword off ("CONTINUUM SCHOOL")."""
    out: list[str] = []
    changed = False
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and len(tokens[j]) == 1 and tokens[j].isalpha():
            j += 1
        if j - i >= LETTER_RUN_MIN:
            run = "".join(tokens[i:j])
            for kw in sorted(KEYWORDS, key=len, reverse=True):
                if run.lower().endswith(kw) and len(run) > len(kw):
                    out += [run[: -len(kw)], run[-len(kw) :]]
                    break
            else:
                out.append(run)
            changed = True
            i = j
        else:
            out.append(tokens[i])
            i += 1
    return out, changed


def _lines(page: PageLayout) -> list[list[TextSpan]]:
    rows: list[list[TextSpan]] = []
    for w in sorted(page.spans, key=lambda s: (s.y0, s.x0)):
        if rows and abs(rows[-1][0].y0 - w.y0) < 4:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda s: s.x0) for r in rows]


def _tidy(words: list[str]) -> str:
    text = " ".join(words)
    if text.upper() == text:  # ALL CAPS -> Title Case ("MARY'S" -> "Mary's")
        text = " ".join(w.capitalize() for w in text.split())
    return text


def _dedupe_repeats(tokens: list[str]) -> list[str]:
    """Some PDFs draw text twice ("An An SSVM SSVM"): drop immediate repeats of whole words."""
    return [t for k, t in enumerate(tokens) if k == 0 or t != tokens[k - 1]]


def _candidate(tokens: list[str]) -> tuple[str, bool] | None:
    tokens, spaced = collapse_letter_spaced(tokens)
    text = _MONTH_YEAR_TAIL.sub("", " ".join(_dedupe_repeats(tokens))).strip(_EDGE_SEPS)
    if any(c.isdigit() for c in text) or not (MIN_LEN <= len(text) <= MAX_LEN):
        return None
    words = text.split()
    if not words or len(words) > MAX_WORDS or "calendar" in text.lower():
        return None
    if not (_ENDS_WITH_KW.search(text) or _STARTS_UNIVERSITY.match(text)):
        return None
    if len(words) < 2:  # "School" alone is not a name
        return None
    return _tidy(words), spaced


def detect_school_name(layout: DocumentLayout) -> SchoolNameGuess | None:
    pages = [p for p in layout.pages if p.page <= 2 or p.page == layout.page_count]
    best: tuple[tuple[int, int, float], SchoolNameGuess] | None = None
    for p in pages:
        for line in _lines(p):
            cand = _candidate([w.text for w in line])
            if cand is None:
                continue
            name, spaced = cand
            height = max(w.y1 - w.y0 for w in line)
            # earlier page first, plain text before letter-spaced, then larger type
            key = (p.page, int(spaced), -height)
            if best is None or key < best[0]:
                best = (key, SchoolNameGuess(name, p.page, spaced))
    return best[1] if best else None
