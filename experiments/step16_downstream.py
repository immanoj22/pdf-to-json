"""Downstream effect of OCR: the same pages as native text and as a raster-only scan.

For each book, seeded sample pages (preferring pages with tables, lists, columns, index
or equations) are copied into a native subset PDF and rendered at 300 dpi into an
image-only PDF.  Both go through ``run_book`` with the production defaults; the scan run
gets an OcrInput from ``prepare_book`` (Tesseract only; PP-OCRv5 is measured separately).
The page payloads of the two runs are compared, never merged:

- reading order  : Kendall tau over words that occur once in both orders, plus the
                   word error rate of the main-stream word order;
- paragraphs     : boundary F1 (a native paragraph start matches an OCR start at the
                   aligned word position within one word);
- lists          : list-item units matched by text similarity;
- tables         : count, and structure-only TEDS of tables matched by overlap.
Page numbers appear only as the sample drawn from the benchmark manifest.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

OUT = ROOT / "experiments/out/step16/downstream"
WORK = ROOT / ".cache/step16/downstream"
FURNITURE = {
    "running_head",
    "running_foot",
    "folio",
    "production_mark",
    "artifact",
    "invisible",
}


def sample_pages(book, count):
    manifest = json.loads(
        (ROOT / "experiments/out/step16/benchmark/sample_manifest.json").read_text(
            "utf-8"
        )
    )
    rows = manifest["books"][book]["selected"]
    featured = [r for r in rows if r["features"]]
    plain = [r for r in rows if not r["features"]]
    chosen = (featured + plain)[:count]
    return sorted(r["page"] for r in chosen)


def build_pdfs(book, pages, directory):
    import pymupdf
    from reference_paths import reference_path
    from step16_benchmark import BOOKS

    directory.mkdir(parents=True, exist_ok=True)
    native_path, scan_path = directory / "native.pdf", directory / "scan.pdf"
    source = pymupdf.open(str(reference_path(BOOKS[book])))
    native = pymupdf.open()
    scan = pymupdf.open()
    for number in pages:
        native.insert_pdf(source, from_page=number - 1, to_page=number - 1)
        page = source[number - 1]
        pixmap = page.get_pixmap(dpi=300, alpha=False)
        target = scan.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, pixmap=pixmap)
    native.save(str(native_path), garbage=4, deflate=True)
    scan.save(str(scan_path), garbage=4, deflate=True)
    return native_path, scan_path


def ocr_settings(config):
    from book_core.ocr.settings import OcrJobSettings, OcrSettings

    return OcrJobSettings(
        device="cpu",
        ocr_languages=config["languages"],
        ocr=OcrSettings(
            executable=Path(config["tesseract_executable"]),
            tessdata=Path(config["tessdata"]),
            asset_manifest=ROOT
            / "experiments/out/step16/dependencies/tessdata_manifest.json",
            second_reader="off",
        ),
    )


def visual_checks(source, cache):
    """Two layout readers plus PP text detection decide that a raster page holds text."""
    from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.ocr.engines import PpOcrV5Engine
    from book_core.ocr.visual_checks import LearnedVisualTextChecks

    manifest = json.loads(
        (ROOT / "experiments/out/step16/dependencies/ppocr_manifest.json").read_text(
            "utf-8"
        )
    )
    spec = next(m for m in manifest["models"] if "server_det" in m["id"])
    text_detector = PpOcrV5Engine(ROOT / spec["local_directory"], spec["revision"], ())
    detectors = [
        kind(cache_dir=ROOT / ".cache/huggingface", local_files_only=True)
        for kind in (HeronDetector, PPDocLayoutV3Detector)
    ]
    return LearnedVisualTextChecks(
        source,
        PyMuPDFExtractor("cpu"),
        detectors,
        text_detector,
        cache / "detections",
        cache / "ocr_visual",
    )


def run(source, name, config, *, ocr):
    from book_core.book_run import run_book
    from book_core.ocr.engines import TesseractEngine
    from book_core.ocr.prepare import prepare_book

    cache = WORK / "cache"
    output = WORK / "final" / name
    kwargs = {}
    settings = None
    if ocr:
        settings = ocr_settings(config)
        primary = TesseractEngine(
            Path(config["tesseract_executable"]), Path(config["tessdata"])
        )
        kwargs["ocr_input"] = prepare_book(
            source, cache, settings, primary, visual_checks=visual_checks(source, cache)
        )
        kwargs["settings"] = settings
    result = run_book(
        source,
        output,
        cache,
        workers=1,
        device="cpu",
        model_cache_dir=ROOT / ".cache/huggingface",
        **kwargs,
    )
    return Path(result["output"]), result


def read_pages(root):
    pages = {}
    for path in sorted(Path(root).glob("page_*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            pages[int(path.name[5:11])] = json.load(stream)
    return pages


def page_model(payload):
    """Main-stream words in emitted order, paragraph start indices, list items, tables."""
    spans = payload["source"]["store"]["spans"]
    line_text = {
        line: "".join(spans[s]["raw_text"] for s in ids)
        for line, ids in payload["line_spans"].items()
    }
    removed = set(payload["table_view"]["removed"])
    units = [u for u in payload["units"]["units"] if u["id"] not in removed]
    unit_of = {lid: u for u in units for lid in u["line_ids"]}
    words, starts, items = [], [], []
    for stream in payload["units"]["order"]["streams"]:
        if stream["kind"] != "main":
            continue
        seen = set()
        for lid in stream["line_ids"]:
            unit = unit_of.get(lid)
            if unit is None or unit["kind"] in FURNITURE:
                continue
            if unit["id"] not in seen:
                seen.add(unit["id"])
                starts.append(len(words))
                if unit["kind"] == "list_item":
                    items.append(
                        " ".join(
                            " ".join(
                                line_text.get(x, "") for x in unit["line_ids"]
                            ).split()
                        )
                    )
            words.extend(line_text.get(lid, "").split())
    tables = payload["tables"]["tables"]
    return {"words": words, "starts": starts, "items": items, "tables": tables}


def align(native, other):
    """Map each native word index to the aligned index in the other sequence."""
    from rapidfuzz.distance import Levenshtein

    mapping = {}
    for op in Levenshtein.opcodes(native, other):
        span = op.src_end - op.src_start
        for offset in range(span):
            if op.tag == "equal":
                mapping[op.src_start + offset] = op.dest_start + offset
            elif op.tag == "replace":
                width = op.dest_end - op.dest_start
                mapping[op.src_start + offset] = op.dest_start + min(offset, width - 1)
            else:
                mapping[op.src_start + offset] = op.dest_start
    return mapping


def boundary_f1(native, other):
    if not native["starts"] and not other["starts"]:
        return None
    mapping = align(native["words"], other["words"])
    ours = set(other["starts"])
    matched = 0
    for start in native["starts"]:
        target = mapping.get(start)
        if target is not None and {target - 1, target, target + 1} & ours:
            matched += 1
    precision = matched / len(other["starts"]) if other["starts"] else 0.0
    recall = matched / len(native["starts"]) if native["starts"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "matched": matched,
        "native": len(native["starts"]),
        "ocr": len(other["starts"]),
        "f1": f1,
    }


def kendall(native, other):
    from collections import Counter

    a, b = Counter(native), Counter(other)
    common = [w for w in native if a[w] == 1 and b[w] == 1]
    if len(common) < 3:
        return None, len(common)
    position = {w: i for i, w in enumerate(other)}
    order = [position[w] for w in common]
    concordant = discordant = 0
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            if order[i] < order[j]:
                concordant += 1
            else:
                discordant += 1
    return (concordant - discordant) / (concordant + discordant), len(common)


def similar(a, b):
    from rapidfuzz import fuzz

    return fuzz.ratio(a, b) / 100


def list_match(native, other):
    unused = list(range(len(other["items"])))
    matched = 0
    for text in native["items"]:
        best = max(unused, key=lambda i: similar(text, other["items"][i]), default=None)
        if best is not None and similar(text, other["items"][best]) >= 0.8:
            matched += 1
            unused.remove(best)
    return {
        "native": len(native["items"]),
        "ocr": len(other["items"]),
        "matched": matched,
    }


def grid(table):
    return {
        "cells": [
            (
                c["row"],
                c["column"],
                c["row_span"],
                c["column_span"],
                c["header"],
                frozenset(),
            )
            for c in table["cells"]
        ]
    }


def overlap(a, b):
    w = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    h = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    return max(0, w) * max(0, h)


def table_match(native, other):
    from book_core.evaluation.table_scoring import teds

    scores, used = [], set()
    for table in native["tables"]:
        best = max(
            (i for i in range(len(other["tables"])) if i not in used),
            key=lambda i: overlap(table["bbox"], other["tables"][i]["bbox"]),
            default=None,
        )
        if (
            best is not None
            and overlap(table["bbox"], other["tables"][best]["bbox"]) > 0
        ):
            used.add(best)
            scores.append(teds(grid(table), grid(other["tables"][best])))
        else:
            scores.append(0.0)
    return {
        "native": len(native["tables"]),
        "ocr": len(other["tables"]),
        "teds": scores,
    }


def compare(native_pages, scan_pages, mapping):
    rows = {}
    for native_number, scan_number in mapping.items():
        n, s = (
            page_model(native_pages[native_number]),
            page_model(scan_pages[scan_number]),
        )
        tau, common = kendall(n["words"], s["words"])
        from book_core.ocr.evaluation import error_counts

        rows[native_number] = {
            "word_order": error_counts(" ".join(n["words"]), " ".join(s["words"])),
            "kendall_tau": tau,
            "kendall_words": common,
            "paragraph_boundaries": boundary_f1(n, s),
            "lists": list_match(n, s),
            "tables": table_match(n, s),
        }
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--book", action="append")
    parser.add_argument("--pages", type=int, default=8)
    parser.add_argument(
        "--work",
        type=Path,
        help="shorter working root (Windows 260-character path limit)",
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text("utf-8"))
    global WORK
    WORK = args.work or WORK
    from step16_benchmark import BOOKS

    OUT.mkdir(parents=True, exist_ok=True)
    for book in args.book or BOOKS:
        pages = sample_pages(book, args.pages)
        native_pdf, scan_pdf = build_pdfs(book, pages, WORK / book)
        cfg = {**config, "languages": config["book_languages"][book]}
        native_root, _ = run(native_pdf, f"{book}_native", cfg, ocr=False)
        scan_root, _ = run(scan_pdf, f"{book}_scan", cfg, ocr=True)
        native_pages, scan_pages = read_pages(native_root), read_pages(scan_root)
        mapping = {i + 1: i + 1 for i in range(len(pages))}
        rows = compare(native_pages, scan_pages, mapping)
        report = {
            "book": book,
            "source_pages": pages,
            "pages": rows,
            "native_output": str(native_root),
            "scan_output": str(scan_root),
        }
        (OUT / f"{book}.json").write_text(json.dumps(report, indent=1), "utf-8")
        print(book, "done", flush=True)


if __name__ == "__main__":
    main()
