"""Deterministic full-day / half-day / timed classification with explicit evidence rules.

Rules (see tests): explicit text beats colour; legend wording is supporting evidence; a
text-vs-legend contradiction is ambiguous; a half-day without a printed time stays
time-unknown (no assumed noon); nothing is silently turned into an all-day event.
"""

import re
from dataclasses import dataclass, field
from datetime import time

from app.schemas import DurationKind, EventWarning, ValidationStatus

HALF_RE = re.compile(
    r"\b(half[- ]?day|early\s+(?:dismissal|release|out)|minimum\s+day|noon\s+dismissal)\b",
    re.IGNORECASE,
)
ALLDAY_RE = re.compile(
    r"\b(no\s+school|no\s+students|school\s+closed|closed|closures?|holidays?|breaks?|"
    r"recess(?:es)?|days?\s+off)\b",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b\.?", re.IGNORECASE)
STRIP_RE = re.compile(r"\bno\s+school\b|\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\b\.?", re.IGNORECASE)


@dataclass
class Classification:
    kind: DurationKind
    status: ValidationStatus
    title: str
    start_time: time | None = None
    end_time: time | None = None
    warnings: list[EventWarning] = field(default_factory=list)


def kind_from_text(text: str) -> DurationKind | None:
    half, allday = bool(HALF_RE.search(text)), bool(ALLDAY_RE.search(text))
    if half and allday:
        return DurationKind.UNKNOWN  # contradictory inside the text itself
    if half:
        return DurationKind.HALF_DAY
    if allday:
        return DurationKind.ALL_DAY
    return None


def parse_time(text: str) -> time | None:
    m = TIME_RE.search(text)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if not (1 <= h <= 12 and 0 <= mi <= 59):
        return None
    return time((h % 12) + (12 if ap == "p" else 0), mi)


def clean_title(text: str) -> str:
    t = re.sub(r"\s+", " ", STRIP_RE.sub("", text)).strip(" -:,")
    return t or text.strip()


def classify(
    text: str,
    legend_label: str | None,
    *,
    color_present: bool,
    color_matched: bool,
    color_ambiguous: bool = False,
    legend_inferred_only: bool = False,
) -> Classification:
    w: list[EventWarning] = []
    text_kind = kind_from_text(text) if text else None
    legend_kind = kind_from_text(legend_label) if (legend_label and color_matched) else None
    t = parse_time(text) if text else None
    title = clean_title(text) if text else ""

    if color_ambiguous:
        w.append(
            EventWarning(
                code="legend_color_ambiguous",
                message="Cell colour is close to more than one legend entry.",
            )
        )

    if text_kind == DurationKind.UNKNOWN:
        w.append(
            EventWarning(
                code="text_contradiction",
                critical=True,
                message="Text mentions both half-day and full closure.",
            )
        )
        return Classification(DurationKind.UNKNOWN, ValidationStatus.AMBIGUOUS, title, warnings=w)

    if text_kind and legend_kind and text_kind != legend_kind:
        w.append(
            EventWarning(
                code="legend_text_conflict",
                critical=True,
                message=f"Text says {text_kind.value} but legend '{legend_label}' "
                f"says {legend_kind.value}.",
            )
        )
        return Classification(DurationKind.UNKNOWN, ValidationStatus.AMBIGUOUS, title, warnings=w)

    kind = text_kind or legend_kind
    from_legend_only = text_kind is None and legend_kind is not None
    explicit_text = text_kind is not None
    status = ValidationStatus.CONFIRMED
    if color_present and not color_matched:
        w.append(
            EventWarning(
                code="color_not_in_legend",
                critical=not explicit_text,
                message="Cell colour matches no legend entry.",
            )
        )
        status = ValidationStatus.INFERRED if explicit_text else ValidationStatus.AMBIGUOUS
    if color_ambiguous and status == ValidationStatus.CONFIRMED:
        status = ValidationStatus.NEEDS_REVIEW

    if legend_inferred_only and from_legend_only and status == ValidationStatus.CONFIRMED:
        # Duration comes from the legend wording alone (no explicit text): say so.
        status = ValidationStatus.INFERRED
        w.append(
            EventWarning(
                code="kind_from_colour_only",
                message=f"Duration inferred from legend colour '{legend_label}' only.",
            )
        )

    if kind == DurationKind.HALF_DAY:
        if t is None:
            w.append(
                EventWarning(
                    code="half_day_time_unknown",
                    critical=True,
                    message="Half day with no printed dismissal time; "
                    "supply it or a school schedule profile.",
                )
            )
            return Classification(kind, ValidationStatus.NEEDS_REVIEW, title, warnings=w)
        return Classification(kind, status, title, end_time=t, warnings=w)  # t is dismissal
    if kind == DurationKind.ALL_DAY:
        return Classification(kind, status, title, warnings=w)
    if t is not None:
        return Classification(DurationKind.TIMED, status, title, start_time=t, warnings=w)

    w.append(
        EventWarning(
            code="duration_unknown",
            critical=True,
            message="No explicit all-day, half-day or time evidence.",
        )
    )
    final = (
        ValidationStatus.AMBIGUOUS
        if status == ValidationStatus.AMBIGUOUS
        else (ValidationStatus.NEEDS_REVIEW)
    )
    return Classification(DurationKind.UNKNOWN, final, title, warnings=w)
