"""Step 11 Part 0: prove the page-anchor reader filter leaves books 1-4 derived gold unchanged.

The logged reader change (docs/decisions.md, Step 11): an element of a dialect's page-marker
names is a page marker only when its id matches the dialect's ``page_marker_label`` pattern.
For each approved book this re-aligns with the current code (a real re-run: the alignment key
binds the producer digest), writes derived gold to a scratch directory with the same arguments
as ``step5_gold.py`` (committed gold untouched) and compares it byte by byte with the committed
gold. Manifest fields naming code or profile versions are reported separately; every other
byte must match. It also counts page-marker elements the filter rejects. Book 4 is the
hold-out: only byte identity is compared, nothing is inspected. Logged in
step5/holdout_runs.jsonl.

Committed gold that carries a logged, owner-approved fix (book 2 markers 146/147, Step 9) is
compared after the same fix is applied to the re-derived gold (``step9_gold_fix.FIX``/``NOTE``,
same serialisation). ``--books`` re-runs some books and merges them into the report.

Usage: python step11_reader_identity.py --scratch <dir> [--books <book> ...]
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from book_core.caching import code_digest
from book_core.evaluation.derived_gold import write_derived_gold
from book_core.evaluation.dialect_profiles import profile_digest
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.reference.cache import align_cached
from book_core.reference.dialects import load_dialects
from book_core.reference.xml_reader import load_tree, local_name

from reference_paths import PROJECT_ROOT, reference_path
from step5_run import BOOKS, CACHE, DIALECTS, OUT
from step9_gold_fix import FIX, NOTE

GOLD = PROJECT_ROOT / "backend/tests/gold_derived"
VERSION_FIELDS = ("alignment_producer_sha256", "dialect_profiles_sha256")
ORDER = (
    "spanish_us_history",
    "immigrant_children",
    "art_therapy_index",
    "medical_anatomy",
)


def marker_elements(xml, dialect):
    """Elements in the file named as the dialect's page markers."""
    root, _ = load_tree(xml.read_bytes())
    named = sum(
        1 for node in root.iter()
        if isinstance(node.tag, str) and local_name(node.tag) in dialect.page_marker_elements
    )  # fmt: skip
    return named


def check(book, scratch, extractor, dialects, profiles):
    spec = BOOKS[book]
    pdf, xml = reference_path(spec["pdf"]), reference_path(spec["xml"])
    for path, key in ((pdf, "pdf_sha256"), (xml, "xml_sha256")):
        if source_digest(path) != spec[key]:
            raise SystemExit(
                f"{path}: SHA-256 differs from the approved reference pair"
            )
    doc, pages, result = align_cached(
        xml, pdf, extractor, dialects, CACHE, object_extractor=PyMuPDFExtractor("cpu")
    )
    gold = GOLD / book
    old = json.loads((gold / "manifest.json").read_text("utf-8"))
    entry = next(d for d in profiles["dialects"] if d["name"] == doc.dialect.name)
    per_dialect = "dialect_profile_sha256" in old["provenance"]
    target = scratch / book
    write_derived_gold(
        target, book=book, split=spec["split"], notes=spec["notes"],
        pdf_sha256=source_digest(pdf), extractor=extractor.identity.model_dump(mode="json"),
        doc=doc, pages=pages, result=result, dialects_digest=dialects.digest,
        low_confidence_markers=book == "art_therapy_index",
        dialect_profile_digest=profile_digest(profiles, doc.dialect.name) if per_dialect else None,
        marker_label=entry.get("page_marker_label"),
    )  # fmt: skip
    reapplied = None
    if (
        NOTE in old["notes"]
    ):  # the logged Step 9 marker fix, applied as step9_gold_fix does
        markers = json.loads((target / "page_markers.json").read_text("utf-8"))
        markers = [{**m, "pdf_page": FIX[m["label"]]} if m["label"] in FIX else m
                   for m in markers]  # fmt: skip
        data = (json.dumps(markers, ensure_ascii=False, indent=1) + "\n").encode()
        (target / "page_markers.json").write_bytes(data)
        manifest = json.loads((target / "manifest.json").read_text("utf-8"))
        manifest["notes"] = [*manifest["notes"], NOTE]
        manifest["files"]["page_markers.json"] = hashlib.sha256(data).hexdigest()
        (target / "manifest.json").write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        )
        reapplied = "Step 9 logged marker fix (146 -> p157, 147 -> p158)"
    files = {}
    for path in sorted(gold.iterdir()):
        new = target / path.name
        files[path.name] = {
            "committed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rerun_sha256": hashlib.sha256(new.read_bytes()).hexdigest()
            if new.exists()
            else None,
            "byte_identical": new.exists() and new.read_bytes() == path.read_bytes(),
        }
    new = json.loads((target / "manifest.json").read_text("utf-8"))
    versions = {
        field: {
            "committed": old["provenance"][field],
            "rerun": new["provenance"][field],
        }
        for field in VERSION_FIELDS
    }
    for row in (old, new):
        for field in VERSION_FIELDS:
            row["provenance"][field] = None
    named = marker_elements(xml, doc.dialect)
    return {
        "book": book,
        "split": spec["split"],
        "dialect": doc.dialect.name,
        "logged_fix_reapplied": reapplied,
        "page_marker_named_elements": named,
        "page_markers_read": len(doc.markers),
        "rejected_by_page_pattern": named - len(doc.markers)
        if doc.dialect.page_marker_label
        else 0,
        "data_files_byte_identical": all(
            v["byte_identical"] for k, v in files.items() if k != "manifest.json"
        ),
        "manifest_identical_except_version_fields": old == new,
        "version_fields": versions,
        "files": files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--books", nargs="*", choices=ORDER, default=list(ORDER))
    args = parser.parse_args()
    out = PROJECT_ROOT / "experiments/out/step11"
    previous = {}
    if (out / "reader_identity.json").exists():
        previous = {
            b["book"]: b
            for b in json.loads((out / "reader_identity.json").read_text("utf-8"))[
                "books"
            ]
        }
    extractor = PyMuPDFExtractor(
        "cpu"
    )  # same identity as the cached extractor; no new cache
    dialects = load_dialects(DIALECTS)
    profiles = json.loads(Path(DIALECTS).read_text("utf-8"))
    books = []
    for book in ORDER:
        if book not in args.books:
            if book in previous:
                books.append(previous[book])
            continue
        started = time.perf_counter()
        row = check(book, args.scratch, extractor, dialects, profiles)
        row["seconds"] = round(time.perf_counter() - started, 1)
        books.append(row)
        print(book, row["data_files_byte_identical"],
              row["manifest_identical_except_version_fields"], flush=True)  # fmt: skip
    identical = all(
        b["data_files_byte_identical"] and b["manifest_identical_except_version_fields"]
        for b in books
    )  # fmt: skip
    report = {
        "change": "page markers from page-marker elements only when the id matches the "
        "dialect's page pattern (reference/xml_reader.py, reference/dialects.py)",
        "all_identical_except_version_fields": identical,
        "alignment_producer_sha256": code_digest("alignment"),
        "books": books,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "reader_identity.json").write_text(
        json.dumps(report, indent=1) + "\n", "utf-8"
    )
    with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as log:
        for row in books:
            if row["book"] not in args.books:
                continue
            log.write(json.dumps({
                "book": row["book"], "action": "aligner_identity_check",
                "reason": "Step 11 reader change (page-anchor id filter): derived gold proven "
                "identical" if row["data_files_byte_identical"]
                and row["manifest_identical_except_version_fields"]
                else "Step 11 reader change: derived gold NOT identical",
                "alignment_producer_sha256": report["alignment_producer_sha256"],
                "data_files_byte_identical": row["data_files_byte_identical"],
                "evidence": "experiments/out/step11/reader_identity.json",
                "time": report["time"],
            }) + "\n")  # fmt: skip
    print(json.dumps({k: v for k, v in report.items() if k != "books"}, indent=1))
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
