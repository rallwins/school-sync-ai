"""Canonical typed models. All-day events are date-based (never midnight timestamps)."""

from __future__ import annotations

from datetime import date, time
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DurationKind(StrEnum):
    ALL_DAY = "all_day"
    HALF_DAY = "half_day"
    TIMED = "timed"
    UNKNOWN = "unknown"


class ValidationStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"
    NEEDS_REVIEW = "needs_review"


class SourceRegion(BaseModel):
    """Location of evidence on a page, in PDF points (origin top-left)."""

    page: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float
    cell_label: str | None = None


class EventWarning(BaseModel):
    code: str
    message: str
    critical: bool = False


class CalendarEvent(BaseModel):
    event_id_internal: str
    source_document_id: str
    source_hash: str
    school_name: str
    academic_year: str
    source_region: SourceRegion
    source_text: str
    event_title: str
    description: str = ""
    start_date: date
    end_date: date  # inclusive; ICS export converts to exclusive DTEND
    is_all_day: bool
    start_time: time | None = None
    end_time: time | None = None
    timezone: str
    duration_kind: DurationKind
    category_id: str | None = None
    category_label: str | None = None
    sampled_color: tuple[int, int, int] | None = None
    matched_legend_color: tuple[int, int, int] | None = None
    extraction_method: str
    validation_status: ValidationStatus
    warnings: list[EventWarning] = Field(default_factory=list)
    user_confirmed: bool = False
    normalized_fingerprint: str = ""
    provider: str | None = None
    provider_event_id: str | None = None
    import_batch_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> CalendarEvent:
        if self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        if self.is_all_day and (self.start_time or self.end_time):
            raise ValueError("all-day event must not carry times")
        if self.duration_kind == DurationKind.TIMED and not self.start_time:
            raise ValueError("timed event requires start_time")
        return self


class LegendEntry(BaseModel):
    label: str
    category_id: str
    rgb: tuple[int, int, int]
    page: int
    region: SourceRegion


class LegendMatch(BaseModel):
    entry: LegendEntry | None
    delta_e: float | None
    ambiguous: bool = False


class ExtractionResult(BaseModel):
    source_hash: str
    legend: list[LegendEntry]
    events: list[CalendarEvent]
    warnings: list[str] = Field(default_factory=list)
    pages_processed: list[int] = Field(default_factory=list)
    pages_skipped: list[int] = Field(default_factory=list)


# ---- PDF layout (Milestone 1 output) -------------------------------------------------------


class TextSpan(BaseModel):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


class FillRect(BaseModel):
    """A vector-filled rectangle (cell background or legend swatch)."""

    x0: float
    y0: float
    x1: float
    y1: float
    rgb: tuple[int, int, int]


class PageLayout(BaseModel):
    page: int
    width: float
    height: float
    has_text_layer: bool
    spans: list[TextSpan]
    fills: list[FillRect]


class DocumentLayout(BaseModel):
    source_hash: str
    page_count: int
    pages: list[PageLayout]
    warnings: list[str] = Field(default_factory=list)
