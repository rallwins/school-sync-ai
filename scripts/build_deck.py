"""Build presentation/SchoolSync-AI.pptx (editable). Run: python scripts/build_deck.py

Numbers on the evaluation slide are read from evaluation/results.json, not typed in.
A rough text-fit check fails the build if a text box would overflow (no renderer is available
on the dev machine, so the deck has NOT been visually reviewed).
"""

import json
import math
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
INK, MUTED, ACCENT, WARN = RGBColor(0x1B, 0x1F, 0x24), RGBColor(0x5B, 0x65, 0x73), RGBColor(0x1F, 0x5F, 0xBF), RGBColor(0x8A, 0x5A, 0x00)
LIGHT = RGBColor(0xEE, 0xF2, 0xF8)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def fit_check(texts: list[str], size: int, width_in: float, height_in: float, what: str) -> None:
    chars_per_line = max(1, int(width_in * 72 / (size * 0.52)))
    lines = sum(max(1, math.ceil(len(t) / chars_per_line)) for t in texts)
    need = lines * size * 1.3 / 72 + 0.1 * len(texts)
    if need > height_in:
        raise SystemExit(f"text overflow risk in {what}: needs {need:.1f}in, has {height_in:.1f}in")


def text(slide, x, y, w, h, items, size=18, color=INK, bold=False, bullet=True, align=None, what=""):
    fit_check(items, size, w - 0.3, h, what or items[0][:30])
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, t in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("• " + t) if bullet else t
        p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
        p.space_after = Pt(6)
        if align:
            p.alignment = align
    return tb


def slide(title, subtitle=None):
    s = prs.slides.add_slide(BLANK)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = ACCENT; bar.line.fill.background()
    text(s, 0.6, 0.35, 12.1, 0.8, [title], size=32, bold=True, bullet=False, what=title)
    if subtitle:
        text(s, 0.6, 1.1, 12.1, 0.5, [subtitle], size=16, color=MUTED, bullet=False, what=subtitle)
    return s


def box(s, x, y, w, h, label, fill=LIGHT, size=14, color=INK):
    fit_check([label], size, w - 0.3, h, label)
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = ACCENT
    tf = sh.text_frame; tf.word_wrap = True
    tf.text = label
    for p in tf.paragraphs:
        p.font.size, p.font.color.rgb, p.alignment = Pt(size), color, PP_ALIGN.CENTER
    return sh


def arrow(s, x1, y1, x2, y2):
    c = s.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = MUTED
    c.line.width = Pt(1.5)


# 1 Problem ---------------------------------------------------------------------------------
s = slide("SchoolSync AI", "Turn a school calendar PDF into reviewed, duplicate-safe calendar events")
text(s, 0.6, 1.9, 12.1, 4.8, [
    "Parents re-type school calendars by hand: dates, half days and closures, every year.",
    "PDFs encode meaning in colour and layout: a legend says which colour means 'half day'.",
    "A wrong date or an invented time on your calendar is worse than no event.",
    "Goal: extract with evidence, flag what is uncertain, and never write without confirmation.",
], size=22, what="s1")

# 2 Workflow --------------------------------------------------------------------------------
s = slide("Product workflow")
steps = ["Upload PDF", "Detect grid, legend, colours", "Review + resolve uncertainty", "Duplicate check", "Preview plan", "Confirm, export or sync"]
for i, t in enumerate(steps):
    x = 0.5 + i * 2.1
    box(s, x, 2.6, 1.85, 1.3, t, size=14)
    if i < len(steps) - 1:
        arrow(s, x + 1.85, 3.25, x + 2.1, 3.25)
text(s, 0.6, 4.6, 12.1, 2.2, [
    "Every event keeps its source page, cell and printed text.",
    "Ambiguous events cannot be exported or synced until a person resolves them.",
    "ICS/CSV download works with no account; sync needs explicit confirmation of the exact plan.",
], size=20, what="s2")

# 3 Architecture ----------------------------------------------------------------------------
s = slide("Architecture (as built)", "Modular monolith; demo hosted on Vercel + AWS Lambda")
box(s, 0.6, 2.2, 2.4, 1.2, "Browser UI\nNext.js, TypeScript")
box(s, 3.6, 2.2, 2.4, 1.2, "Vercel /api proxy\nadds API key server-side")
box(s, 6.6, 2.2, 2.9, 1.2, "FastAPI on Lambda\n(container image)")
box(s, 10.1, 2.2, 2.6, 1.2, "SQLite\nimports + manifest")
box(s, 6.6, 4.1, 2.9, 1.0, "PDF: PyMuPDF, grid, legend, colour")
box(s, 10.1, 4.1, 2.6, 1.0, "Providers: file, mock, Google*")
for a, b in [(3.0, 3.6), (6.0, 6.6), (9.5, 10.1)]:
    arrow(s, a, 2.8, b, 2.8)
arrow(s, 8.0, 3.4, 8.0, 4.1)
arrow(s, 9.5, 3.2, 10.4, 4.1)
text(s, 0.6, 5.6, 12.1, 1.5, [
    "*Google adapter is tested against mocked HTTP only; Microsoft is not implemented.",
    "No LLM is used. Dates, identity, duplicates and sync are deterministic code.",
], size=16, color=MUTED, what="s3")

# 4 Grid / legend / colour -----------------------------------------------------------------
s = slide("Reading the grid, legend and colours")
text(s, 0.6, 1.5, 6.2, 5.4, [
    "Find 'Month YYYY' and 7 weekday labels; compute each cell's date from position.",
    "Cross-check against the day number printed in the cell. Mismatch = reported, never shifted.",
    "Legend: small square swatches plus the label printed beside them.",
    "Match cell colour to legend with CIE76 Delta E and a tolerance, not exact RGB.",
    "Nothing is hard-coded: 'red = holiday' is never assumed.",
], size=18, what="s4a")
box(s, 7.2, 1.7, 5.4, 0.9, "Unlisted colour, no text", fill=RGBColor(0xFF, 0xF1, 0xD6))
text(s, 7.2, 2.65, 5.4, 0.8, ["-> ambiguous, untitled placeholder, needs a person"], size=15, color=WARN, bullet=False, what="s4b")
box(s, 7.2, 3.5, 5.4, 0.9, "Text says 'Early Release', legend colour says 'Closed'", fill=RGBColor(0xFF, 0xF1, 0xD6))
text(s, 7.2, 4.45, 5.4, 0.8, ["-> conflict flagged, not resolved silently"], size=15, color=WARN, bullet=False, what="s4c")
text(s, 7.2, 5.4, 5.4, 1.2, ["Not handled: scanned pages (flagged, skipped), stroked-line grids, icon/pattern legends."], size=15, color=MUTED, bullet=False, what="s4d")

# 5 Half day --------------------------------------------------------------------------------
s = slide("Full day, half day and uncertainty")
text(s, 0.6, 1.5, 12.1, 5.4, [
    "Explicit text wins: 'Half Day', 'Early Dismissal/Release', 'No School', 'Closed', 'Recess'.",
    "A printed time is kept (dismissal time for half days; start time for timed events).",
    "Half day with no printed time stays time-unknown and blocks export. No assumed noon.",
    "Only the user can supply a school start time; it is then labelled user-supplied.",
    "Without it, a half day exports as an all-day event with the dismissal time in the title.",
    "Uncertainty is shown per event (status + reasons), not as one confidence number.",
], size=20, what="s5")

# 6 Duplicates ------------------------------------------------------------------------------
s = slide("Duplicate-safe sync and provider adapters")
text(s, 0.6, 1.5, 6.4, 5.4, [
    "Stable id = school + year + start date; survives a revised PDF.",
    "Layer A: ours (owner property / manifest). B: identical, not ours: skip. C: look-alike: conflict.",
    "Only events we created are ever updated or deleted. Removals are proposed, not executed.",
    "Retries re-check the owner id first, so a lost response cannot create a twin.",
    "Confirmation is bound to the previewed plan; changes since then are rejected (409).",
], size=17, what="s6a")
box(s, 7.5, 1.8, 5.0, 0.8, "CalendarProvider protocol", fill=ACCENT, color=RGBColor(255, 255, 255))
for i, (t, st) in enumerate([("File export (ICS/CSV)", "tested"), ("Mock calendar", "tested"), ("Google Calendar", "mocked HTTP only"), ("Microsoft Graph", "not implemented")]):
    box(s, 7.5, 2.9 + i * 0.95, 5.0, 0.8, f"{t}: {st}", size=14)

# 7 Security --------------------------------------------------------------------------------
s = slide("Security, privacy and OAuth boundaries")
text(s, 0.6, 1.5, 12.1, 5.4, [
    "Uploads are untrusted: magic bytes, size and page caps, full parse, encrypted PDFs rejected.",
    "Public demo: API key required, held only on the Vercel server; synthetic data only.",
    "OAuth: single-use state, PKCE S256, least-privilege scopes; tokens Fernet-encrypted; never logged.",
    "Server re-checks readiness; CSV cells are protected against formula injection.",
    "Known gaps: no user accounts or isolation; no retention job; Gitleaks CI never run; PyMuPDF is native code.",
], size=19, what="s7")

# 8 Evaluation ------------------------------------------------------------------------------
res = json.loads((ROOT / "evaluation" / "results.json").read_text())
s = slide("Evaluation: actual results", f"{res['dataset_total']['pdfs']} synthetic PDFs, {res['dataset_total']['labelled_events']} labelled events")
rows = [["Metric"] + list(res["fixtures"].keys())]
for label, key in [("Precision", "precision"), ("Recall", "recall"), ("Category accuracy", "category_accuracy"),
                   ("Full/half/timed accuracy", "duration_kind_accuracy"), ("Status accuracy", "status_accuracy"),
                   ("Source evidence complete", "source_evidence_completeness"), ("Needs-review rate", "ambiguous_or_review_rate")]:
    rows.append([label] + [f"{v[key]:.2f}" for v in res["fixtures"].values()])
tbl = s.shapes.add_table(len(rows), len(rows[0]), Inches(0.6), Inches(1.8), Inches(7.4), Inches(3.6)).table
for r, row in enumerate(rows):
    for c, val in enumerate(row):
        cell = tbl.cell(r, c); cell.text = val
        cell.text_frame.paragraphs[0].font.size = Pt(13)
text(s, 8.4, 1.8, 4.5, 4.9, [
    "Backend: 104 pytest tests. Frontend: 5 unit tests + 1 browser e2e (also run against the live deployment).",
    "Caveat: fixtures share an author and drawing code: a baseline, not real-world accuracy. On a REAL school calendar (list-style, 2 months/page) the extractor found 0 events; see docs.",
    "Duplicate-create rate on re-import: 0 in tests against the mock provider.",
], size=15, what="s8")

# 9 AWS -------------------------------------------------------------------------------------
s = slide("AWS deployment mapping and cost controls")
text(s, 0.6, 1.5, 6.3, 5.4, [
    "Deployed: Vercel frontend -> Lambda container (Function URL) -> in-memory/ephemeral SQLite.",
    "CloudFormation: ECR, Lambda, logs-only IAM role, 14-day logs, $5 budget alert.",
    "Account is Paid plan with $0 credits, so Lambda's always-free tier was chosen over EC2/App Runner/ALB.",
    "Cost: not measured; expected pennies. Budget email alerts but cannot stop spend.",
    "Measured: ~20 s cold start on first request.",
], size=16, what="s9a")
text(s, 7.2, 1.5, 5.6, 5.4, [
    "Production shape (documented, not built):",
    "ECS Fargate + ALB + RDS/Aurora + Secrets Manager + IAM task roles + CloudWatch.",
    "Needed first: user accounts, durable storage, a real secret store, retention.",
], size=16, bullet=False, what="s9b")

# 10 Trade-offs -----------------------------------------------------------------------------
s = slide("Trade-offs, limitations and roadmap")
text(s, 0.6, 1.5, 6.0, 5.4, [
    "Trade-offs: deterministic rules (reproducible, narrower) over an LLM; blocking uncertain events over guessing.",
    "Limitations: tested layouts only (real list-style calendar unsupported); no OCR; Google unverified; Microsoft missing; no accounts.",
], size=17, what="s10a")
text(s, 7.0, 1.5, 5.8, 5.4, [
    "Roadmap:",
    "OCR + OpenCV grid detection for scans.",
    "Real Google test-calendar run; Microsoft Graph adapter.",
    "Source-page crop preview, settings page, retention.",
    "Support list-style, multi-month real calendars; evaluate on consented real ones.",
], size=17, bullet=False, what="s10b")

out = ROOT / "presentation" / "SchoolSync-AI.pptx"
out.parent.mkdir(exist_ok=True)
prs.save(out)
print(f"wrote {out} ({len(prs.slides)} slides)")
