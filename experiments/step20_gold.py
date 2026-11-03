"""Step 20: derived gold (human_approved=false) for the ART book from Jaypee's delivered DocBook.

The reference is the delivery's complete book file (``9789372025262.xml``): it is well-formed
and holds every part, chapter and the index with the real part grouping. The per-chapter files
are standalone fragments; ``ch8.xml`` never closes its part, so the reader's ``close_open_end``
repair reads it. ``--cross-check`` reads every chapter file in book order and proves the
chapter set carries exactly the book file's words, so either source gives the same text.

Actions:
  units   align book file and PDF (cached), write backend/tests/gold_derived/art_lab/
  tables  table gold from the units, located on a Step 20 run's text cache
          (backend/tests/gold_derived_tables/art_lab/; needs ``--tag``)

Usage:
  python step20_gold.py units [--cross-check]
  python step20_gold.py tables --tag before
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path

BOOK = "art_lab"
BOOK_FILE = "9789372025262.xml"
CHAPTER_ORDER = ["front.xml", *(f"ch{i}.xml" for i in range(1, 18)), "index.xml"]
OUT = ROOT / "experiments/out/step20/gold"
CACHE = ROOT / ".cache/s20/gold"
NOTES = [
    (
        "ART book (Step 20 development, owner's real work); reference: Jaypee's delivered "
        "DocBook 4.2, the complete book file of the delivery"
    ),
    "page markers are anchors with ids page<label> (dialect docbook4-page-anchors)",
    "the per-chapter files carry the same words (cross-check); ch8.xml needs close_open_end",
]


def cross_check():
    from book_core.reference.xml_reader import load_tree

    delivery = reference_path("jaypee_art_delivery")
    words = lambda root: re.findall(r"\w+", " ".join(root.itertext()))
    book_root, book_repairs = load_tree((delivery / BOOK_FILE).read_bytes())
    chapter_words, repairs = [], {}
    for name in CHAPTER_ORDER:
        root, found = load_tree((delivery / "Chapters" / name).read_bytes())
        chapter_words += words(root)
        if found:
            repairs[name] = [{"kind": r.kind, "detail": r.detail} for r in found]
    result = {
        "book_file_repairs": [r.kind for r in book_repairs],
        "chapter_file_repairs": repairs,
        "book_file_words": len(words(book_root)),
        "chapter_set_words": len(chapter_words),
        "identical_word_sequence": words(book_root) == chapter_words,
    }
    write(OUT / "cross_check.json", result)
    print(json.dumps(result), flush=True)
    if not result["identical_word_sequence"]:
        raise SystemExit("chapter files and book file differ")


def units():
    from book_core.evaluation.derived_gold import write_derived_gold
    from book_core.evaluation.dialect_profiles import profile_digest
    from book_core.extraction.fingerprints import source_digest
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.reference.cache import align_cached
    from book_core.reference.dialects import load_dialects
    from book_core.settings import Settings

    pdf = reference_path("jaypee_art_pdf")
    xml = reference_path("jaypee_art_delivery") / BOOK_FILE
    extractor = PyMuPDFExtractor("cpu")
    dialects = load_dialects(Settings().reference_dialects)
    profiles = json.loads(Settings().reference_dialects.read_text("utf-8"))
    doc, pages, result = align_cached(
        xml, pdf, extractor, dialects, CACHE, object_extractor=PyMuPDFExtractor("cpu")
    )
    entry = next(d for d in profiles["dialects"] if d["name"] == doc.dialect.name)
    manifest = write_derived_gold(
        ROOT / "backend/tests/gold_derived" / BOOK, book=BOOK, split="development",
        notes=NOTES, pdf_sha256=source_digest(pdf),
        extractor=extractor.identity.model_dump(mode="json"), doc=doc, pages=pages,
        result=result, dialects_digest=dialects.digest,
        dialect_profile_digest=profile_digest(profiles, doc.dialect.name),
        marker_label=entry.get("page_marker_label"),
    )  # fmt: skip
    write(OUT / "units_manifest.json", manifest)
    print(doc.dialect.name, json.dumps(manifest.get("coverage", manifest.get("counts", {}))))


def tables(tag):
    """The Step 14a table-gold derivation, located on this run's retained native tokens."""
    import step14a_gold
    import step20_eval

    record = json.loads((step20_eval.OUT / tag / "performance" / f"{BOOK}.json").read_text("utf-8"))
    record["tag"] = tag
    step20_eval.point_helpers(record)
    delivery = reference_path("jaypee_art_delivery")
    step14a_gold.XML_KEYS[BOOK] = "jaypee_art_book_file"
    step14a_gold.reference_path = lambda key: (
        delivery / BOOK_FILE if key == "jaypee_art_book_file" else reference_path(key)
    )
    coverage = step14a_gold.derive(BOOK)
    write(OUT / "tables_coverage.json", coverage)
    print(json.dumps(coverage), flush=True)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["units", "tables"])
    parser.add_argument("--cross-check", action="store_true")
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.action == "units":
        if args.cross_check:
            cross_check()
        return units()
    if not args.tag:
        parser.error("tables needs --tag (a Step 20 run of the ART book)")
    return tables(args.tag)


if __name__ == "__main__":
    main()
