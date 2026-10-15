"""Step 13a: derive provisional math gold for the math development book (human_approved=false).

Reads the CNXML collection with the math-only dialect profile, aligns its text (equations as
slots) to the retained PDF tokens with the unchanged reference aligner, and locates each
equation between its aligned neighbours: native drawn objects and unaligned PDF tokens in
the gap. Native pages come from the run's extraction cache (the Extractor).

Writes backend/tests/gold_derived_math/statistics/ (manifest, equations, MathML, page digests)
and experiments/out/step13/gold/ (coverage report, examples).

Usage: python step13_gold.py [--run before]
"""

# ruff: noqa: E402
import argparse
import gzip
import hashlib
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS, CNXML, MATH_BOOK

from book_core.cache_store import read_model
from book_core.caching import code_digest
from book_core.evaluation import math_gold
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage
from book_core.reference.aligner import AlignerConfig, AlignmentResult, align
from book_core.reference.pdf_tokens import page_tokens

GOLD = ROOT / "backend/tests/gold_derived_math" / MATH_BOOK
OUT = ROOT / "experiments/out/step13/gold"
WORK = ROOT / ".cache/step13/gold"


def write_gz_jsonl(path, rows):
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    path.write_bytes(buffer.getvalue())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="\n")


def main(run, native_key=None):
    started = time.perf_counter()
    if native_key is None:
        record = json.loads(
            (ROOT / f"experiments/out/step13/{run}/performance/{MATH_BOOK}.json").read_text("utf-8")
        )["run"]
        native_key = record["cache_keys"]["native"]
    total = len(list((CACHE / "text" / native_key).glob("*.json")))
    pdf = reference_path(BOOKS[MATH_BOOK][0])
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    profile = math_gold.profile_data()
    reference = math_gold.read_math_reference(reference_path(CNXML[MATH_BOOK]), profile)
    pages, geometry = [], {}
    for number in range(1, total + 1):
        page = read_model(CACHE / "text" / native_key / f"{number}.json", ExtractedPage, native_key)
        if page.source_sha256 != pdf_sha:
            raise SystemExit("Cached text belongs to another source")
        pages.append(page_tokens(page))
        native = verified_read(
            CACHE / "native" / native_key / f"{number}.json", NativeObjectPage, native_key
        )
        boxes, token_lines, line_boxes, size = math_gold.token_geometry(page)
        objects = [
            math_gold.PageObjectBox(o.id, o.kind, o.bbox, math_gold.object_shape(o))
            for o in native.objects
            if o.kind in {"drawing", "image"} and o.bbox is not None
        ]
        item = math_gold.PageGeometry(number, boxes, token_lines, line_boxes, size, objects)
        if len(boxes) != len(pages[-1].tokens):
            raise SystemExit(f"Token geometry mismatch on page {number}")
        math_gold.place_objects(item)
        geometry[number] = item
        if number % 100 == 0:
            print("pages", number, flush=True)
    config = AlignerConfig()
    cached = WORK / f"alignment_{reference.document.sha256[:16]}_{native_key[:16]}.json.gz"
    if cached.exists():
        result = AlignmentResult.from_payload(json.loads(gzip.decompress(cached.read_bytes())))
    else:
        result = align(reference.document, pages, config)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(gzip.compress(json.dumps(result.to_payload()).encode(), mtime=0))
    print("aligned", round(time.perf_counter() - started), flush=True)
    gold = math_gold.locate(reference, result, geometry)
    coverage = math_gold.coverage(gold)
    aligned = sum(1 for p in result.xml_page if p >= 0)
    coverage["reference_tokens"] = len(result.xml_page)
    coverage["reference_tokens_aligned"] = aligned
    coverage["reference_token_alignment"] = round(aligned / max(1, len(result.xml_page)), 4)
    GOLD.mkdir(parents=True, exist_ok=True)
    rows = math_gold.gold_rows(gold)
    write_gz_jsonl(GOLD / "equations.jsonl.gz", rows)
    write_gz_jsonl(
        GOLD / "mathml.jsonl.gz",
        [{"slot": s, "mathml": reference.mathml[s]} for s in sorted(reference.mathml)],
    )
    write_json(
        GOLD / "pages.json",
        {
            "pages": [
                {"page": p.page, "tokens": len(p.tokens), "token_digest": p.digest} for p in pages
            ]
        },
    )
    files = {
        name: hashlib.sha256((GOLD / name).read_bytes()).hexdigest()
        for name in ("equations.jsonl.gz", "mathml.jsonl.gz", "pages.json")
    }
    collection = sorted((reference_path(CNXML[MATH_BOOK]) / "collections").glob("*.xml"))[0]
    manifest = {
        "book": MATH_BOOK,
        "split": "development",
        "notes": [
            "Step 13 math development book: OpenStax Statistics (CC BY 4.0)",
            "math gold only: the CNXML reference is never a heading/paragraph/list style model",
            "equations are located between aligned reference neighbours; vector glyphs and "
            "unaligned PDF tokens in that gap form the region",
        ],
        "human_approved": False,
        "status": "provisional derived math gold; the reference is evidence, not truth",
        "version": math_gold.MATH_GOLD_VERSION,
        "provenance": {
            "pdf_sha256": pdf_sha,
            "reference_sha256": reference.document.sha256,
            "reference_collection_sha256": hashlib.sha256(collection.read_bytes()).hexdigest(),
            "reference_module_sha256": reference.sources,
            "reference_repository": "https://github.com/openstax/osbooks-statistics",
            "reference_commit": "7dea80ae2800386d470b11f6528962f9c4992d15",
            "math_dialect_profile_sha256": reference.profile_sha256,
            "native_key": native_key,
            "aligner_version": result.version,
            "aligner_config": result.config,
            "math_gold_producer_sha256": hashlib.sha256(
                (ROOT / "backend/src/book_core/evaluation/math_gold.py").read_bytes()
            ).hexdigest(),
            "alignment_producer_sha256": code_digest("alignment"),
            "token_reference": "[page, ordinal] over retained native tokens; verify with "
            "pages.json token_digest",
        },
        "counts": coverage,
        "files": files,
    }
    write_json(GOLD / "manifest.json", manifest)
    write_json(OUT / "coverage.json", coverage)
    print(json.dumps(coverage, indent=1))
    print("seconds", round(time.perf_counter() - started))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="before")
    parser.add_argument("--native-key", help="read caches before the run's record exists")
    arguments = parser.parse_args()
    main(arguments.run, arguments.native_key)
