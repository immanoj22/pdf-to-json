"""Step 9 Part 0, owner decision 3: evidence-based fix of book 2 derived-gold markers 146/147.

Evidence written to experiments/out/step9/gold_fix/: page renders (top strip with the folio, and full page)
of PDF pages 156-159, the alignment detail of the bibliography entries around the page breaks,
the printed folio and PDF page-label metadata of those pages, and the marker records before
and after. The fix moves only markers "146" and "147", keeps human_approved = false, updates
the manifest file digests and notes, and appends a before/after record to the Step 5 hold-out
log. Refuses to run twice. Usage: python step9_gold_fix.py
"""

import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402

GOLD = ROOT / "backend/tests/gold_derived/immigrant_children"
OUT = ROOT / "experiments/out/step9/gold_fix"
LOG = ROOT / "experiments/out/step5/holdout_runs.jsonl"
FIX = {"146": 157, "147": 158}  # label -> evidenced physical page
PAGES = (156, 157, 158, 159)
NOTE = (
    "Step 9 logged marker fix: reference page breaks 146 and 147 sit one run of bibliography "
    "entries late; markers moved to the pages that print folios 146 and 147 "
    "(evidence: experiments/out/step9/gold_fix)"
)


def main():
    import pymupdf

    from book_core.evaluation.derived_harness import DerivedGold

    markers_path = GOLD / "page_markers.json"
    manifest_path = GOLD / "manifest.json"
    markers = json.loads(markers_path.read_text("utf-8"))
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if NOTE in manifest["notes"]:
        raise SystemExit("Fix already applied")
    OUT.mkdir(parents=True, exist_ok=True)

    # Evidence 1: renders (full page and the folio strip at the bottom).
    source = reference_path("small_pdf")
    with pymupdf.open(source) as pdf:
        for number in PAGES:
            page = pdf[number - 1]
            page.get_pixmap(dpi=60).save(OUT / f"page_{number}.png")
            rect = page.rect  # this book prints folios in the running head at the top
            top = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + 0.12 * rect.height)
            page.get_pixmap(dpi=110, clip=top).save(OUT / f"top_strip_{number}.png")
        labels = {
            number: pdf[number - 1].get_label() if hasattr(pdf[number - 1], "get_label") else None
            for number in PAGES
        }

    # Evidence 2: alignment of the bibliography entries around the breaks.
    units = [
        json.loads(line)
        for line in gzip.decompress((GOLD / "units.jsonl.gz").read_bytes()).decode().splitlines()
    ]
    entries = [
        {
            "path": u["path"],
            "kind": u["kind"],
            "pdf_runs": u["pdf"],
            "confidence": u["confidence"],
        }
        for u in units
        if "/chapter[7]/section[12]/bibliolist[1]/bibliomixed[" in u["path"]
    ]
    furniture = json.loads(
        (ROOT / "experiments/out/step9/furniture/immigrant_children/page_markers.json").read_text(
            "utf-8"
        )
    )
    printed = {
        m["page"]: {"label": m["label"], "source": m["source"], "metadata": m["metadata_label"]}
        for m in furniture
        if m["page"] in PAGES
    }
    before = [m for m in markers if m["label"] in FIX]
    after_markers = []
    for marker in markers:
        if marker["label"] in FIX:
            marker = {**marker, "pdf_page": FIX[marker["label"]]}
        after_markers.append(marker)
    after = [m for m in after_markers if m["label"] in FIX]
    evidence = {
        "pdf_page_labels_metadata": labels,
        "step8_page_markers": printed,
        "bibliography_entries": entries,
        "markers_before": before,
        "markers_after": after,
        "reading": [
            "PDF pages 157 and 158 print folios 146 and 147; PDF page-label metadata agrees",
            "bibliography entries 1-15 lie on PDF page 157 and 16-30 on page 158",
            "the reference places page break 146 after entry 15 and 147 after entry 30, so "
            "the text following each break lies mostly on the next PDF page, and the derived "
            "placement (page holding most of the following segment) lands one page late",
        ],
    }
    (OUT / "evidence.json").write_text(
        json.dumps(evidence, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )

    # Apply: same serialisation as derived_gold.write_derived_gold.
    data = (json.dumps(after_markers, ensure_ascii=False, indent=1) + "\n").encode()
    markers_path.write_bytes(data)
    manifest["notes"] = [*manifest["notes"], NOTE]
    manifest["files"]["page_markers.json"] = hashlib.sha256(data).hexdigest()
    manifest_path.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    )
    gold = DerivedGold.load(GOLD)  # verifies digests and human_approved = false
    assert all(m["pdf_page"] == FIX[m["label"]] for m in gold.markers if m["label"] in FIX)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "book": "immigrant_children",
                    "action": "derived_gold_marker_fix",
                    "owner_decision": "Step 8 decision 3 (Step 9 Part 0)",
                    "before": [{k: m[k] for k in ("label", "pdf_page")} for m in before],
                    "after": [{k: m[k] for k in ("label", "pdf_page")} for m in after],
                    "evidence": "experiments/out/step9/gold_fix/evidence.json",
                    "human_approved": False,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
            + "\n"
        )
    print(json.dumps({"before": before, "after": after}, indent=1))


if __name__ == "__main__":
    main()
