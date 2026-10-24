"""PyMuPDF text + vector-fill extraction. Coordinates are PDF points, origin top-left."""

import pymupdf

from app.schemas import DocumentLayout, FillRect, PageLayout, TextSpan

MIN_TEXT_CHARS_FOR_TEXT_PDF = 20


def _rgb255(c: tuple[float, ...] | None) -> tuple[int, int, int] | None:
    if c is None or len(c) != 3:
        return None
    return (round(c[0] * 255), round(c[1] * 255), round(c[2] * 255))


def extract_layout(data: bytes, source_hash: str) -> DocumentLayout:
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages: list[PageLayout] = []
    warnings: list[str] = []
    try:
        for i, page in enumerate(doc, start=1):
            spans = [
                TextSpan(text=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3])
                for w in page.get_text("words")
            ]
            fills: list[FillRect] = []
            for d in page.get_drawings():
                rgb = _rgb255(d.get("fill"))
                if rgb is None:
                    continue
                r = d["rect"]
                if r.width < 2 or r.height < 2:
                    continue
                fills.append(FillRect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1, rgb=rgb))
            has_text = sum(len(s.text) for s in spans) >= MIN_TEXT_CHARS_FOR_TEXT_PDF
            if not has_text:
                warnings.append(f"page {i}: no usable text layer; OCR required (milestone 3)")
            pages.append(
                PageLayout(
                    page=i,
                    width=page.rect.width,
                    height=page.rect.height,
                    has_text_layer=has_text,
                    spans=spans,
                    fills=fills,
                )
            )
    finally:
        doc.close()
    return DocumentLayout(
        source_hash=source_hash, page_count=len(pages), pages=pages, warnings=warnings
    )
