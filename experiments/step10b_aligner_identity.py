"""Step 10b: prove the current aligner behaves as the Step 5b aligner (owner instruction).

The alignment producer digest changed after Step 5b only through shared modules (ledger line
endings, the atomic-retry write in ``reference/cache.py``, extraction/model/objects changes of
Steps 6-7). This re-aligns book 3 (9 pages) with the current code, writes its derived gold to
a scratch directory with the same arguments as ``step5_gold.py`` (committed gold untouched),
and compares it byte by byte with the committed gold. Manifest fields that name code or
profile versions (the alignment producer digest and the whole profile-file digest) are
reported separately; every other byte must match. Logged in step5/holdout_runs.jsonl.

Usage: python step10b_aligner_identity.py --scratch <dir>
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from reference_paths import PROJECT_ROOT, reference_path
from step5_run import BOOKS, CACHE, DIALECTS, OUT

from book_core.caching import code_digest
from book_core.evaluation.derived_gold import write_derived_gold
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.reference.cache import align_cached
from book_core.reference.dialects import load_dialects

BOOK = "art_therapy_index"
GOLD = PROJECT_ROOT / "backend/tests/gold_derived" / BOOK
VERSION_FIELDS = ("alignment_producer_sha256", "dialect_profiles_sha256")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    spec = BOOKS[BOOK]
    pdf, xml = reference_path(spec["pdf"]), reference_path(spec["xml"])
    for path, key in ((pdf, "pdf_sha256"), (xml, "xml_sha256")):
        if source_digest(path) != spec[key]:
            raise SystemExit(f"{path}: SHA-256 differs from the approved reference pair")
    extractor = CachedExtractor(PyMuPDFExtractor("cpu"), CACHE / "native")
    dialects = load_dialects(DIALECTS)
    doc, pages, result = align_cached(
        xml, pdf, extractor, dialects, CACHE, object_extractor=PyMuPDFExtractor("cpu")
    )
    target = args.scratch / BOOK
    write_derived_gold(
        target, book=BOOK, split=spec["split"], notes=spec["notes"],
        pdf_sha256=source_digest(pdf), extractor=extractor.identity.model_dump(mode="json"),
        doc=doc, pages=pages, result=result, dialects_digest=dialects.digest,
        low_confidence_markers=True,
    )  # fmt: skip
    files = {}
    for path in sorted(GOLD.iterdir()):
        new = target / path.name
        same = new.exists() and new.read_bytes() == path.read_bytes()
        files[path.name] = {
            "committed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rerun_sha256": hashlib.sha256(new.read_bytes()).hexdigest() if new.exists() else None,
            "byte_identical": same,
        }
    old = json.loads((GOLD / "manifest.json").read_text("utf-8"))
    new = json.loads((target / "manifest.json").read_text("utf-8"))
    versions = {field: {"committed": old["provenance"][field], "rerun": new["provenance"][field]}
                for field in VERSION_FIELDS}  # fmt: skip
    for row in (old, new):
        for field in VERSION_FIELDS:
            row["provenance"][field] = None
    report = {
        "book": BOOK,
        "data_files_byte_identical": all(
            v["byte_identical"] for k, v in files.items() if k != "manifest.json"
        ),  # fmt: skip
        "manifest_identical_except_version_fields": old == new,
        "version_fields": versions,
        "files": files,
        "alignment_producer_sha256": code_digest("alignment"),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out = PROJECT_ROOT / "experiments/out/step10b"
    out.mkdir(parents=True, exist_ok=True)
    (out / "aligner_identity_book3.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    identical = (
        report["data_files_byte_identical"] and report["manifest_identical_except_version_fields"]
    )
    with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({
            "book": BOOK, "action": "aligner_identity_check",
            "reason": "aligner digest changed, behaviour proven identical"
            if identical else "aligner digest changed; behaviour NOT identical",
            "alignment_producer_sha256": report["alignment_producer_sha256"],
            "committed_alignment_producer_sha256": versions["alignment_producer_sha256"][
                "committed"],
            "data_files_byte_identical": report["data_files_byte_identical"],
            "evidence": "experiments/out/step10b/aligner_identity_book3.json",
            "time": report["time"],
        }) + "\n")  # fmt: skip
    print(json.dumps(report, indent=1))
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
