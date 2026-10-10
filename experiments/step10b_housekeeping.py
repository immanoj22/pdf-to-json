"""Step 10b disk check before the book 4 run (owner instruction).

1. Delete superseded cache entries only, by the Step 9 rules (``step9_housekeeping``: keys
   recomputed with the real key functions for the approved books) plus Step 10 structure
   entries whose producer digest is superseded. Never: current keys, gold, outputs.
2. Estimate book 4's cache need from its page count and book 1's per-page cache sizes (the
   current-key directories of book 1 in every per-page cache, plus book-level caches), with a
   margin.
3. Stop (exit 2) when the estimate exceeds free space minus the reserve (5 GB).

Usage: python step10b_housekeeping.py [--apply] --pages 314
"""

import argparse
import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

import step9_housekeeping as step9  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "experiments/out/step10b"
RESERVE = 5 * 10**9
MARGIN = 1.25
BOOK1_PAGES = 758


def size(path):
    return step9.size(path) if Path(path).exists() else 0


def structure_superseded():
    from book_core.structure.keys import evidence_code_digest, structure_code_digest

    evidence_now, structure_now = evidence_code_digest(), structure_code_digest()
    rows = []
    for path in sorted((CACHE / "step10/structure/evidence").glob("*.json.gz")):
        body = gzip.decompress(path.read_bytes()).split(b"\n", 1)[1]
        current = json.loads(body)["cache_key_inputs"].get("evidence_producer_sha256")
        rows.append((current != evidence_now, path, "structure evidence"))
    for path in sorted((CACHE / "step10/structure/book").glob("*.json")):
        payload = json.loads(json.loads(path.read_text("utf-8"))["payload"])
        current = payload["cache_key_inputs"].get("structure_producer_sha256")
        rows.append((current != structure_now, path, "structure decision"))
    return rows


def book1_per_page():
    """Bytes per page of book 1's current entries in each per-page cache, and book-level."""
    keys, _ = step9.book_keys()
    from step8_run import vocabulary_for

    from book_core.extraction.fingerprints import source_digest
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition, fingerprints

    source = step9.reference_path("spanish_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE / "step7")
    inputs = PageInputs(source, extractor, repetition, CACHE / "step7",
                        vocabulary_for("spanish_us_history"))  # fmt: skip
    native, analysis = fingerprints(source_digest(source), extractor, repetition)
    own = {"native": native, "analysis": analysis, "layout": inputs.layout_key,
           "reading_order": inputs.order_key}  # fmt: skip
    per_page = {f"step7/{name}": size(CACHE / "step7" / name / key) / BOOK1_PAGES
                for name, key in own.items()}  # fmt: skip
    furniture = [
        d for d in (CACHE / "step8/furniture/page").iterdir() if d.name in keys["furniture"]
    ]
    per_page["step8/furniture/page"] = max((size(d) for d in furniture), default=0) / BOOK1_PAGES
    # Step 9 paragraphs, Step 10 evidence, Step 5/6 native: the largest book entry is book 1.
    for name in ("step9/paragraphs", "step6/native", "step5/native"):
        entries = [p for p in (CACHE / name).iterdir()] if (CACHE / name).exists() else []
        per_page[name] = max((size(p) for p in entries), default=0) / BOOK1_PAGES
    evidence = list((CACHE / "step10/structure/evidence").glob("*.json.gz"))
    per_page["step10/evidence"] = max((size(p) for p in evidence), default=0) / BOOK1_PAGES
    return per_page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pages", type=int, required=True, help="book 4 page count")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    step9.OUT = OUT  # the Step 9 rules, reported under Step 10b
    sys.argv = [sys.argv[0], *(["--apply"] if args.apply else [])]
    step9.main()
    structure = structure_superseded()
    freed = sum(size(p) for stale, p, _ in structure if stale)
    if args.apply:
        for stale, path, _ in structure:
            if stale:
                path.unlink()
    per_page = book1_per_page()
    estimate = args.pages * sum(per_page.values()) * MARGIN
    free = shutil.disk_usage(ROOT).free
    report = {
        "applied": args.apply,
        "structure_superseded": [{"path": p.relative_to(ROOT).as_posix(), "kind": k,
                                  "bytes": size(p) if not args.apply else None}
                                 for stale, p, k in structure if stale],  # fmt: skip
        "structure_bytes_freed": freed if args.apply else 0,
        "book1_bytes_per_page": {k: round(v) for k, v in per_page.items()},
        "book4_pages": args.pages,
        "margin": MARGIN,
        "book4_estimate_bytes": round(estimate),
        "free_bytes": free,
        "reserve_bytes": RESERVE,
        "fits": estimate <= free - RESERVE,
        "step9_rules_report": (OUT / ("housekeeping.json" if args.apply
                                      else "housekeeping_plan.json")).relative_to(ROOT).as_posix(),
    }  # fmt: skip
    name = "disk_check.json" if args.apply else "disk_check_plan.json"
    (OUT / name).write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "structure_superseded"}, indent=1))
    if not report["fits"]:
        print(f"STOP: estimate {estimate / 1e9:.1f} GB > free {free / 1e9:.1f} GB - 5 GB")
        sys.exit(2)


if __name__ == "__main__":
    main()
