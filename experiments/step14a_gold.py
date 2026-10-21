"""Step 14a Task 1: derive table gold (human_approved=false) for books 1-4 and Statistics.

Books 1-4: the reference XML grid (rows, spans, header rows, titles, notes) located through
the committed derived gold units (each unit's table cell path and its PDF token runs).
Statistics: the CNXML collection (math-only reader, which keeps attributes) located through
the cached Step 13a reference alignment. Per page, a table's box is the union of its
located token boxes (a lower bound: empty cells and rules are not tokens).

Writes backend/tests/gold_derived_tables/<book>/ (manifest, tables.jsonl.gz) and
experiments/out/step14a/gold/coverage.json.

Usage: python step14a_gold.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from reference_paths import reference_path
from step13_books import CNXML, MATH_BOOK

from book_core.evaluation import math_gold, table_gold
from book_core.reference.aligner import AlignmentResult
from book_core.reference.xml_reader import load_tree

GOLD = ROOT / "backend/tests/gold_derived_tables"
DERIVED = ROOT / "backend/tests/gold_derived"
XML_KEYS = {
    "spanish_us_history": "spanish_xml",
    "immigrant_children": "immigrant_xml",
    "art_therapy_index": "art_index_xml",
    "medical_anatomy": "medical_xml",
}


def write_gz_jsonl(path, rows):
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())


def boxes(book, rows):
    """Per page: the union box of each table's located tokens (cells, title, notes apart)."""
    pages = sorted({p for r in rows for p in r["pages"]})
    geometry = {}
    for number in pages:
        token_boxes, _, _, _ = math_gold.token_geometry(common.text_page(book, number))
        geometry[number] = token_boxes
    for row in rows:
        row["boxes"] = {}
        parts = {
            "cells": [ref for c in row["cells"] for ref in c["tokens"]],
            "title": row["title"]["tokens"],
            "notes": row["notes"]["tokens"],
        }
        for part, refs in parts.items():
            for page, ordinal in refs:
                found = geometry[page]
                if ordinal >= len(found):
                    raise SystemExit(f"{book}: token {page}/{ordinal} beyond the page")
                b = found[ordinal]
                key = str(page)
                box = row["boxes"].setdefault(key, {}).get(part)
                row["boxes"][key][part] = (
                    [b.x0, b.y0, b.x1, b.y1]
                    if box is None
                    else [
                        min(box[0], b.x0),
                        min(box[1], b.y0),
                        max(box[2], b.x1),
                        max(box[3], b.y1),
                    ]
                )


def derive(book):
    if book == MATH_BOOK:
        profile = math_gold.profile_data()
        reference = math_gold.read_math_reference(reference_path(CNXML[book]), profile)
        native_key = common.keys(book)["native"]
        cached = sorted(
            (ROOT / ".cache/step13/gold").glob(
                f"alignment_{reference.document.sha256[:16]}_{native_key[:16]}.json.gz"
            )
        )
        if not cached:
            raise SystemExit("The Step 13a alignment cache is missing")
        alignment = AlignmentResult.from_payload(
            json.loads(gzip.decompress(cached[0].read_bytes()))
        )
        dialect = reference.document.dialect.name
        vocab = table_gold.vocabulary(dialect)
        tables = table_gold.read_tables(table_gold.element_tree(reference.document.elements), vocab)
        table_gold.attach_alignment(tables, reference.document, alignment, reference.slots)
        reference_sha = reference.document.sha256
        provenance = {
            "reference_repository": "https://github.com/openstax/osbooks-statistics",
            "reference_commit": "7dea80ae2800386d470b11f6528962f9c4992d15",
            "alignment": cached[0].name,
            "aligner_version": alignment.version,
            "math_dialect_profile_sha256": reference.profile_sha256,
        }
        pdf_sha = hashlib.sha256(common.source(book).read_bytes()).hexdigest()
    else:
        manifest = json.loads((DERIVED / book / "manifest.json").read_text("utf-8"))
        dialect = manifest["provenance"]["dialect"]
        data = reference_path(XML_KEYS[book]).read_bytes()
        root, repairs = load_tree(data)
        vocab = table_gold.vocabulary(dialect)
        tables = table_gold.read_tables(table_gold.xml_tree(root), vocab)
        with gzip.open(DERIVED / book / "units.jsonl.gz", "rt", encoding="utf-8") as stream:
            units = [json.loads(line) for line in stream]
        table_gold.attach_units(tables, units)
        reference_sha = hashlib.sha256(data).hexdigest()
        if reference_sha != manifest["provenance"]["xml_sha256"]:
            raise SystemExit(f"{book}: reference XML differs from the derived gold's")
        pdf_sha = manifest["provenance"]["pdf_sha256"]
        provenance = {
            "derived_gold_manifest_sha256": hashlib.sha256(
                (DERIVED / book / "manifest.json").read_bytes()
            ).hexdigest(),
            "derived_gold_units_sha256": hashlib.sha256(
                (DERIVED / book / "units.jsonl.gz").read_bytes()
            ).hexdigest(),
            "in_memory_repairs": [r.kind for r in repairs],
        }
    rows = table_gold.gold_rows(tables)
    boxes(book, rows)
    target = GOLD / book
    write_gz_jsonl(target / "tables.jsonl.gz", rows)
    coverage = table_gold.coverage(rows)
    manifest = {
        "book": book,
        "notes": [
            "table gold derived from the reference XML grid and located through aligned "
            "reference tokens; token references are [page, ordinal] over retained native "
            "tokens (verify with the derived gold pages.json token digests)",
            "boxes are unions of located token boxes (empty cells and rules are not tokens)",
        ],
        "human_approved": False,
        "status": "provisional derived table gold; the reference is evidence, not truth",
        "version": table_gold.TABLE_GOLD_VERSION,
        "provenance": {
            "pdf_sha256": pdf_sha,
            "reference_sha256": reference_sha,
            "dialect": dialect,
            "table_profile_sha256": hashlib.sha256(table_gold.PROFILE.read_bytes()).hexdigest(),
            "table_gold_producer_sha256": hashlib.sha256(
                (ROOT / "backend/src/book_core/evaluation/table_gold.py").read_bytes()
            ).hexdigest(),
            "native_key": common.keys(book)["native"],
            **provenance,
        },
        "counts": coverage,
        "files": {
            "tables.jsonl.gz": hashlib.sha256((target / "tables.jsonl.gz").read_bytes()).hexdigest()
        },
    }
    common.write(target / "manifest.json", manifest)
    return coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    out = common.OUT / "gold/coverage.json"
    result = common.read(out) if out.exists() else {}
    for book in [args.book] if args.book else common.BOOK_ORDER:
        result[book] = derive(book)
        print(book, json.dumps(result[book]), flush=True)
    common.write(out, result)


if __name__ == "__main__":
    main()
