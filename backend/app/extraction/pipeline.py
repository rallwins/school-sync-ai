"""Vector-PDF extraction: layout -> legend + grid -> cells -> classified, merged events."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.color_mapping.lab import DEFAULT_TOLERANCE, is_blank, match_color
from app.deduplication.identity import compute_fingerprint
from app.grid_detection.grid import Cell, GridError, detect_cells
from app.legend.parse import parse_legend
from app.schemas import (
    CalendarEvent,
    DocumentLayout,
    DurationKind,
    EventWarning,
    ExtractionResult,
    LegendEntry,
    SourceRegion,
    ValidationStatus,
)
from app.validation.classify import classify

UNTITLED = "(untitled - colour only)"


@dataclass
class ImportContext:
    school_name: str
    academic_year: str
    timezone: str
    source_document_id: str
    color_tolerance: float = DEFAULT_TOLERANCE


def _build(
    cells: list[Cell],
    legend: list[LegendEntry],
    ctx: ImportContext,
    source_hash: str,
) -> CalendarEvent:
    first, last = cells[0], cells[-1]
    r = first.rect
    rgb = r.rgb
    colored = not is_blank(rgb)
    m = match_color(rgb, legend, ctx.color_tolerance) if colored else None
    matched = m is not None and m.entry is not None
    legend_label = m.entry.label if matched and m is not None and m.entry else None
    text = first.text.strip()

    if not text and not matched:
        c = classify("", None, color_present=colored, color_matched=False)
        title = UNTITLED
    elif not text:
        c = classify(
            "",
            legend_label,
            color_present=True,
            color_matched=True,
            color_ambiguous=bool(m and m.ambiguous),
        )
        c.title = UNTITLED
        c.warnings.append(
            EventWarning(
                code="no_text_evidence",
                critical=True,
                message="Coloured cell has no printed text; title unknown.",
            )
        )
        c.status = ValidationStatus.NEEDS_REVIEW
        title = UNTITLED
    else:
        c = classify(
            text,
            legend_label,
            color_present=colored,
            color_matched=matched,
            color_ambiguous=bool(m and m.ambiguous),
        )
        title = c.title

    region = SourceRegion(
        page=first.page,
        x0=r.x0,
        y0=r.y0,
        x1=last.rect.x1,
        y1=last.rect.y1,
        cell_label=first.day.isoformat(),
    )
    ev = CalendarEvent(
        event_id_internal=hashlib.sha256(
            f"{source_hash}|{first.page}|{first.day.isoformat()}".encode()
        ).hexdigest()[:24],
        source_document_id=ctx.source_document_id,
        source_hash=source_hash,
        school_name=ctx.school_name,
        academic_year=ctx.academic_year,
        source_region=region,
        source_text=text,
        event_title=title,
        start_date=first.day,
        end_date=last.day,
        is_all_day=c.kind == DurationKind.ALL_DAY,
        start_time=c.start_time,
        end_time=c.end_time,
        timezone=ctx.timezone,
        duration_kind=c.kind,
        category_id=m.entry.category_id if matched and m and m.entry else None,
        category_label=legend_label,
        sampled_color=rgb if colored else None,
        matched_legend_color=m.entry.rgb if matched and m and m.entry else None,
        extraction_method="vector_pdf_deterministic",
        validation_status=c.status,
        warnings=c.warnings,
    )
    ev.normalized_fingerprint = compute_fingerprint(ev)
    return ev


def _same_block(prev: Cell, cur: Cell) -> bool:
    """cur continues prev's event: next day, same colour, and cur adds no text of its own
    (or repeats prev's text exactly)."""
    if cur.day - prev.day != timedelta(days=1) or cur.rect.rgb != prev.rect.rgb:
        return False
    return cur.text.strip() == "" or cur.text.strip().lower() == prev.text.strip().lower()


def extract_events(layout: DocumentLayout, ctx: ImportContext) -> ExtractionResult:
    ZoneInfo(ctx.timezone)  # raises on an invalid timezone before any event is built
    legend = parse_legend(layout)
    warnings: list[str] = list(layout.warnings)
    if not legend:
        warnings.append("No legend detected: colours cannot be mapped; manual mapping required.")
    events: list[CalendarEvent] = []
    done: list[int] = []
    skipped: list[int] = []

    for page in layout.pages:
        if not page.has_text_layer:
            skipped.append(page.page)
            continue
        try:
            _, _, cells = detect_cells(page)
        except GridError as e:
            warnings.append(f"page {page.page}: {e}")
            skipped.append(page.page)
            continue
        done.append(page.page)
        candidates: list[Cell] = []
        for c in cells:
            if c.warnings:
                warnings.extend(f"page {c.page} {c.day}: {w}" for w in c.warnings)
                continue  # never guess a date for a misaligned cell
            if not c.in_month:
                continue
            if c.text.strip() or not is_blank(c.rect.rgb):
                candidates.append(c)
        blocks: list[list[Cell]] = []
        for c in candidates:
            if blocks and _same_block(blocks[-1][-1], c):
                blocks[-1].append(c)
            else:
                blocks.append([c])
        events.extend(_build(b, legend, ctx, layout.source_hash) for b in blocks)

    return ExtractionResult(
        source_hash=layout.source_hash,
        legend=legend,
        events=events,
        warnings=warnings,
        pages_processed=done,
        pages_skipped=skipped,
    )
