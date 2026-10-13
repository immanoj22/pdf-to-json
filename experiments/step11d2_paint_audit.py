"""Compare actual cached visibility decisions with the independent render diagnosis."""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11c_identity import BOOKS
from step11d2_hidden import write
from step11d2_run import read

from book_core.cache_store import read_model
from book_core.paint.cache import paint_fingerprint
from book_core.paint.models import PagePaintEvidence

OUT = ROOT / "experiments/out/step11d2"


def audit(book, partial=False):
    baseline = read(OUT / f"before/{book}.json")
    diagnosis = read(OUT / f"hidden/{book}_validated.json")
    key = paint_fingerprint(baseline["keys"]["analysis"], "cpu")
    pages, totals, missing = {}, Counter(), []
    expected = {
        page["page"]: {
            row["span_id"]
            for row in page["candidates"]
            if row["render_test"].get("no_pixel_change")
        }
        for page in diagnosis["pages"]
    }
    for number in baseline["pages"]:
        path = ROOT / ".cache/step7/paint" / key / f"{number}.json"
        if not path.exists():
            missing.append(int(number))
            continue
        result = read_model(path, PagePaintEvidence, key)
        assert result.source_sha256 == baseline["source_sha256"] and result.page == int(number)
        confirmed = {s.span_id for s in result.spans if s.decision != "review"}
        diagnosed = expected.get(int(number), set())
        counts = Counter(s.decision for s in result.spans)
        totals.update(counts)
        pages[number] = {
            "counts": dict(counts),
            "confirmed_span_ids": sorted(confirmed),
            "diagnostic_only": sorted(diagnosed - confirmed),
            "runtime_only": sorted(confirmed - diagnosed),
            "diagnostics": result.diagnostics,
        }
    if not partial:
        assert not missing, missing
    result = {
        "complete": not missing,
        "source_sha256": baseline["source_sha256"],
        "paint_key": key,
        "missing_pages": missing,
        "totals": dict(totals),
        "pages": pages,
    }
    write(OUT / f"hidden/paint_audit_{book}{'_partial' if partial else ''}.json", result)
    print(book, "pages", len(pages), "complete", not missing, dict(totals))
    print(
        "diagnostic/runtime differences",
        sum(len(r["diagnostic_only"]) for r in pages.values()),
        sum(len(r["runtime_only"]) for r in pages.values()),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    audit(args.book, args.partial)
