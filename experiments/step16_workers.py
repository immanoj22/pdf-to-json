"""Determinism on the OCR path, two checks on one scanned book.

(a) 1 vs 2 workers: ``run_book`` with 2 workers on the downstream run's scan, in the same
    cache (the same OCR records), into a separate output; the final archive must equal the
    1-worker downstream archive byte for byte.
(b) OCR repeatability: the OCR page records recomputed in a fresh cache (``.cache/step16/
    workers2``, made by the first version of this check) must hold the same words: text,
    boxes and confidences. Their IDs differ by design: the OCR fingerprint covers the
    eligibility evidence, which names its file inside the cache.
"""

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step16_downstream as down

BOOK = sys.argv[1] if len(sys.argv) > 1 else "immigrant_children"
FRESH = ROOT / ".cache/step16/workers2/cache"
GZIP_MAGIC = bytes((0x1F, 0x8B))


def digests(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    }


def ocr_words(cache):
    """{(source, page): [(text, bbox, confidence)]} of every OCR page record in a cache."""
    pages = {}
    for path in sorted((Path(cache) / "ocr").glob("*/*.json")):
        raw = path.read_bytes()
        record = json.loads(gzip.decompress(raw) if raw[:2] == GZIP_MAGIC else raw)
        payload = record.get("payload", record)
        if isinstance(payload, str):
            payload = json.loads(payload)
        if "words" not in payload:
            continue
        page = payload["page"]
        spans = page["store"]["spans"]
        key = (page["source_sha256"], page["geometry"]["page"])
        pages[key] = [
            (
                spans[w["span_id"]]["raw_text"],
                json.dumps(spans[w["span_id"]]["bbox"], sort_keys=True),
                w["confidence"],
            )
            for w in payload["words"]
        ]
    return pages


if __name__ == "__main__":
    from book_core.book_run import run_book
    from book_core.ocr.engines import TesseractEngine
    from book_core.ocr.prepare import prepare_book

    config = json.loads(
        (ROOT / "experiments/out/step16/benchmark/config_tess.json").read_text()
    )
    config["languages"] = config["book_languages"][BOOK]
    one = json.loads((down.OUT / f"{BOOK}.json").read_text())["scan_output"]
    scan = down.WORK / BOOK / "scan.pdf"
    cache = down.WORK / "cache"
    settings = down.ocr_settings(config)
    primary = TesseractEngine(
        Path(config["tesseract_executable"]), Path(config["tessdata"])
    )
    inputs = prepare_book(
        scan, cache, settings, primary, visual_checks=down.visual_checks(scan, cache)
    )
    result = run_book(
        scan,
        ROOT / ".cache/step16/workers2/final_same_cache",
        cache,
        workers=2,
        device="cpu",
        model_cache_dir=ROOT / ".cache/huggingface",
        settings=settings,
        ocr_input=inputs,
    )
    a, b = digests(one), digests(result["output"])
    first, again = ocr_words(cache), ocr_words(FRESH)
    common = sorted(set(first) & set(again))
    out = {
        "book": BOOK,
        "workers": {
            "one_worker": one,
            "two_workers": result["output"],
            "files": [len(a), len(b)],
            "byte_identical": a == b,
            "differing": sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k)),
        },
        "ocr_repeatability": {
            "pages_compared": len(common),
            "identical_pages": sum(first[p] == again[p] for p in common),
            "words": sum(len(first[p]) for p in common),
            "differing_pages": [list(p) for p in common if first[p] != again[p]],
        },
    }
    (down.OUT / f"workers_{BOOK}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out)[:600])
