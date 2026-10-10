"""Step 5 Parts 3-4: write provisional derived gold, score the ingestion stage, draw samples.

Uses the cached alignment (same key as step5_run.py). Hold-out books need --holdout; each
hold-out use is appended to experiments/out/step5/holdout_runs.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from reference_paths import PROJECT_ROOT, reference_path
from step5_run import BOOKS, CACHE, DIALECTS, OUT

from book_core.caching import code_digest
from book_core.evaluation.derived_gold import write_derived_gold
from book_core.evaluation.derived_harness import DerivedGold, evaluate, ingestion_output
from book_core.evaluation.dialect_profiles import profile_digest
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.reference.cache import align_cached
from book_core.reference.dialects import load_dialects

GOLD = PROJECT_ROOT / "backend/tests/gold_derived"
COLORS = {  # BGR
    "heading": (40, 40, 220),
    "paragraph": (60, 160, 60),
    "list_item": (200, 120, 0),
    "table_cell": (160, 0, 160),
    "caption": (0, 160, 200),
    "image_description": (0, 200, 255),
    "index_entry": (200, 120, 0),
    "definition_term": (120, 80, 0),
    "definition_description": (160, 120, 40),
    "bibliography_entry": (90, 90, 160),
    "other": (128, 128, 128),
    "unaligned": (40, 40, 40),
}


def load(book: str):
    spec = BOOKS[book]
    pdf, xml = reference_path(spec["pdf"]), reference_path(spec["xml"])
    extractor = CachedExtractor(PyMuPDFExtractor("cpu"), CACHE / "native")
    dialects = load_dialects(DIALECTS)
    doc, pages, result = align_cached(
        xml, pdf, extractor, dialects, CACHE, object_extractor=PyMuPDFExtractor("cpu")
    )
    return spec, pdf, extractor, doc, pages, result, dialects


def line_rows(doc, pages, result, extracted, page_number):
    """One row per retained line: majority aligned element, kind, method and confidence."""
    index = result.pages.index(page_number)
    page = pages[index]
    store_lines = {line.id: line for line in extracted.store.lines}
    rows = []
    for line in page.lines:
        tokens = [t for t in page.tokens if t.line == line.ordinal]
        linked = [result.pdf_xml[index][t.ordinal] for t in tokens]
        aligned = [x for x in linked if x >= 0]
        units = Counter(doc.units[x] for x in aligned)
        unit = units.most_common(1)[0][0] if units else None
        causes = Counter(result.pdf_cause[index][t.ordinal] for t in tokens if t.ordinal >= 0)
        causes.pop("", None)
        rows.append(
            {
                "line": line.ordinal,
                "bbox": store_lines[line.id].bbox,
                "text": " ".join(t.value for t in tokens),
                "aligned": f"{len(aligned)}/{len(tokens)}",
                "kind": doc.dialect.element_kind(unit, doc.elements)
                if unit is not None
                else "unaligned",
                "path": doc.elements[unit].path if unit is not None else "",
                "methods": dict(Counter(result.xml_method[x] for x in aligned)),
                "confidence": round(
                    sum(result.xml_confidence[x] for x in aligned) / len(aligned), 3
                )
                if aligned
                else 0.0,
                "causes": dict(causes),
            }
        )
    return rows


def overlay(pdf: Path, page_number: int, rows, target: Path):
    raster = PyMuPDFExtractor("cpu").render_page(pdf, page_number, dpi=110)
    image = cv2.imdecode(np.frombuffer(raster.png, np.uint8), cv2.IMREAD_COLOR)
    scale = raster.width / raster.page_width
    shade = image.copy()
    for row in rows:
        box = row["bbox"]
        p0 = (int(box.x0 * scale), int(box.y0 * scale))
        p1 = (int(box.x1 * scale), int(box.y1 * scale))
        color = COLORS.get(row["kind"], COLORS["other"])
        cv2.rectangle(shade, p0, p1, color, -1)
        cv2.rectangle(image, p0, p1, color, 1)
    image = cv2.addWeighted(shade, 0.28, image, 0.72, 0)
    legend = [k for k in COLORS if any(r["kind"] == k for r in rows)]
    for n, kind in enumerate(legend):
        y = 16 + 18 * n
        cv2.rectangle(image, (6, y - 11), (20, y + 2), COLORS[kind], -1)
        cv2.putText(image, kind, (26, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.imwrite(str(target), image)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=sorted(BOOKS), required=True)
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--sample-pages", type=int, nargs="*", default=[])
    parser.add_argument("--reason", default="derived gold + harness")
    args = parser.parse_args(argv)
    spec, pdf, extractor, doc, pages, result, dialects = load(args.book)
    if spec["split"] == "holdout" and not args.holdout:
        parser.error(f"{args.book} is a hold-out book; pass --holdout")
    profiles = json.loads(Path(DIALECTS).read_text("utf-8"))
    entry = next(d for d in profiles["dialects"] if d["name"] == doc.dialect.name)
    manifest = write_derived_gold(
        GOLD / args.book,
        book=args.book,
        split=spec["split"],
        notes=spec["notes"],
        pdf_sha256=source_digest(pdf),
        extractor=extractor.identity.model_dump(mode="json"),
        doc=doc,
        pages=pages,
        result=result,
        dialects_digest=dialects.digest,
        low_confidence_markers=args.book == "art_therapy_index",
        dialect_profile_digest=profile_digest(profiles, doc.dialect.name),
        marker_label=entry.get("page_marker_label"),
    )
    extracted = list(extractor.extract_pages(pdf))
    gold = DerivedGold.load(GOLD / args.book)
    report = evaluate(
        [gold],
        {args.book: ingestion_output(args.book, extracted)},
        include_holdout=spec["split"] == "holdout",
    )
    out = OUT / args.book
    out.mkdir(parents=True, exist_ok=True)
    (out / "harness_ingestion.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    (out / "gold_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", "utf-8")
    by_number = {page.geometry.page: page for page in extracted}
    for number in args.sample_pages:
        rows = line_rows(doc, pages, result, by_number[number], number)
        overlay(pdf, number, rows, out / f"sample_p{number}.png")
        printable = [{k: v for k, v in row.items() if k != "bbox"} for row in rows]
        (out / f"sample_p{number}.json").write_text(
            json.dumps(printable, ensure_ascii=False, indent=1) + "\n", "utf-8"
        )
    if spec["split"] == "holdout":
        with (OUT / "holdout_runs.jsonl").open("a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "book": args.book,
                        "action": "derived gold + harness",
                        "reason": args.reason,
                        "alignment_producer_sha256": code_digest("alignment"),
                    }
                )
                + "\n"
            )
    print(json.dumps(report["books"][args.book], indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
