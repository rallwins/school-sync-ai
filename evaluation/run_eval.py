"""Evaluate extraction against labelled synthetic fixtures.  Run from repo root:

    backend/.venv/Scripts/python evaluation/run_eval.py

Caveat printed with results: fixtures and extractor were written by the same author, so these
numbers are an optimistic regression baseline, not a measure of real-world accuracy.
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.extraction.pipeline import ImportContext, extract_events  # noqa: E402
from app.pdf.layout import extract_layout  # noqa: E402

SYN = ROOT / "data" / "synthetic"
# Truth lists the Jan-1 continuation separately because it sits on another page.


def evaluate(pdf: Path, truth_path: Path) -> dict:
    truth = json.loads(truth_path.read_text())
    layout = extract_layout(pdf.read_bytes(), "eval")
    res = extract_events(
        layout, ImportContext(truth["school"], truth["academic_year"], truth["timezone"], "eval")
    )
    labels = {k: v["label"] for k, v in truth["legend"].items()}
    got = {(e.start_date, e.end_date): e for e in res.events}
    want = {(date.fromisoformat(t["start"]), date.fromisoformat(t["end"])): t for t in truth["events"]}
    tp = set(got) & set(want)
    n = len(tp) or 1
    cat_ok = sum(
        1 for k in tp if got[k].category_label == (labels.get(want[k]["category"]) if want[k]["category"] else None)
    )
    kind_ok = sum(1 for k in tp if got[k].duration_kind.value == want[k]["duration_kind"])
    status_ok = sum(1 for k in tp if got[k].validation_status.value == want[k]["status"])
    evid = sum(
        1 for e in res.events if e.source_region.cell_label and e.source_region.x1 > e.source_region.x0
    )
    review = sum(1 for e in res.events if e.validation_status.value != "confirmed")
    return {
        "dataset": {"pdfs": 1, "pages": layout.page_count, "labelled_events": len(want)},
        "precision": len(tp) / len(got) if got else 0.0,
        "recall": len(tp) / len(want),
        "category_accuracy": cat_ok / n,
        "duration_kind_accuracy": kind_ok / n,
        "status_accuracy": status_ok / n,
        "source_evidence_completeness": evid / len(res.events) if res.events else 0.0,
        "ambiguous_or_review_rate": review / len(res.events) if res.events else 0.0,
        "extraneous": sorted(str(k) for k in set(got) - set(want)),
        "missed": sorted(str(k) for k in set(want) - set(got)),
        "duplicate_create_rate_on_reimport": "0 creates on re-import in backend/tests/test_sync.py (mock provider)",
    }


FIXTURES = [
    ("maple_grove_2025_26", "Sunday-first, vector fills"),
    ("riverbend_2027_28", "Monday-first, leap year, drifted colours, conflict, timed event"),
    ("cedar_hill_2025_26", "List-style: 2 months/page, side event list, merged colour strips, legend on last page"),
]

if __name__ == "__main__":
    per = {}
    for name, desc in FIXTURES:
        per[name] = {"description": desc, **evaluate(SYN / f"{name}.pdf", SYN / f"{name}.truth.json")}
    total_events = sum(v["dataset"]["labelled_events"] for v in per.values())
    out = {"fixtures": per, "dataset_total": {"pdfs": len(per), "labelled_events": total_events}}
    (ROOT / "evaluation" / "results.json").write_text(json.dumps(out, indent=2))
    for name, v in per.items():
        print(f"{name}: P={v['precision']:.2f} R={v['recall']:.2f} cat={v['category_accuracy']:.2f} "
              f"kind={v['duration_kind_accuracy']:.2f} status={v['status_accuracy']:.2f} "
              f"evidence={v['source_evidence_completeness']:.2f} review_rate={v['ambiguous_or_review_rate']:.2f} "
              f"extra={v['extraneous']} missed={v['missed']}")
    print(f"\nTotal: {len(per)} synthetic PDFs, {total_events} labelled events.")
    print("NOTE: fixtures are synthetic and authored alongside the extractor; real calendars will differ.")

