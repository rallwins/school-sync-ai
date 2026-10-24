"""Event identity.

- fingerprint: hash of the *current* user-visible content (recomputed server-side, since users
  edit events after extraction). Changes when title/dates/duration/times change.
- stable_id: identity of an event slot across re-imports and revised PDFs. Derived from school,
  academic year and anchor start date, deliberately NOT from the PDF hash. Limitation: if a
  revised PDF moves an event to another date it appears as one removal plus one addition.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from difflib import SequenceMatcher

from app.schemas import CalendarEvent


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


def compute_fingerprint(ev: CalendarEvent) -> str:
    key = "|".join(
        [
            norm_title(ev.event_title),
            ev.start_date.isoformat(),
            ev.end_date.isoformat(),
            ev.duration_kind.value,
            str(ev.start_time),
            str(ev.end_time),
            ev.timezone,
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def sync_fingerprint(ev: CalendarEvent) -> str:
    """What we compare against the destination: the content fingerprint PLUS the colour we would
    apply, so changing the colour mapping updates our own events instead of being skipped."""
    from app.providers.colors import google_color_for

    c = google_color_for(ev.matched_legend_color)
    return hashlib.sha256(
        f"{compute_fingerprint(ev)}|{c.color_id if c else ''}".encode()
    ).hexdigest()[:32]


def stable_ids(events: Iterable[CalendarEvent]) -> dict[str, str]:
    """Map event_id_internal -> stable_id (collisions on the same start date get a suffix)."""
    seen: Counter[str] = Counter()
    out: dict[str, str] = {}
    for e in sorted(events, key=lambda x: (x.start_date, x.end_date, norm_title(x.event_title))):
        base = hashlib.sha256(
            f"{e.school_name.strip().lower()}|{e.academic_year.strip()}|{e.start_date}".encode()
        ).hexdigest()[:24]
        n = seen[base]
        seen[base] += 1
        out[e.event_id_internal] = base if n == 0 else f"{base}-{n}"
    return out


def title_similarity(a: str, b: str) -> float:
    """max(character ratio, fuzzy token containment of the shorter title in the longer one).

    Containment catches 'Labor Day' vs 'Labour Day - No School'. It only ever feeds the
    *conflict* path (human review), so a false positive costs a click, not a wrong write.
    """
    na, nb = norm_title(a), norm_title(b)
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = na.split(), nb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) < 2:
        return ratio
    hits = sum(1 for t in short if any(SequenceMatcher(None, t, u).ratio() >= 0.8 for u in long_))
    return max(ratio, hits / len(short))
