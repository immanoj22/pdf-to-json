"""Step 17 development: assemble a final archive into the book JSON (no stage cache).

Reads a final capture's archive (default: Step 16 final), the run's native object cache
(span baselines, drawings), and the source PDF (link annotations, render proofs of hidden
text). Writes ``experiments/out/step17/dev/<label>/<book>.json`` (validated) with timing.

Usage: python step17_assemble_dev.py --book art_therapy_index [--label try1] [--capture DIR]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly.assemble import assemble
from book_core.assembly.cache import read_native_evidence
from book_core.assembly.hidden import candidates, render_proofs
from book_core.assembly.links import PyMuPDFLinkExtractor
from book_core.assembly.profile import load_profile

import step14a_common as common
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS

OUT = ROOT / "experiments/out/step17/dev"


def providers(book, run):
    source = reference_path(BOOKS[book][0])
    key = run["cache_keys"]["native"]
    links = PyMuPDFLinkExtractor("cpu")

    def native(number):
        return read_native_evidence(CACHE, key, number)

    def evidence(number, page):
        proofs = render_proofs(source, page, candidates(page.store))
        proofs.pop("_unproven", None)
        found = links.extract_links(source, number)
        marks = links.extract_marks(source, number, page.store, found)
        return {"links": found, "marks": marks, "not_rendered": proofs}

    return native, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="try")
    parser.add_argument("--capture", default=str(ROOT / "experiments/out/step16/final"))
    args = parser.parse_args()
    run = json.loads(
        (Path(args.capture) / "performance" / f"{args.book}.json").read_text()
    )["run"]
    native, evidence = providers(args.book, run)
    started = time.perf_counter()

    def progress(stage, n, total):
        if n % 100 == 0 or n == total:
            print(stage, n, total, round(time.perf_counter() - started), flush=True)

    book, ctx = assemble(Path(run["output"]), native_page=native, evidence_page=evidence,
                         profile=load_profile(),
                         converter={"name": "book_core", "version": "dev", "producer": "0" * 64},
                         settings_sha256="0" * 64, progress=progress)  # fmt: skip
    data = book.model_dump(mode="json", by_alias=True)
    path = OUT / args.label / f"{args.book}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=None,
                               separators=(",", ":")), "utf-8", newline="\n")  # fmt: skip
    counts = {k: v for k, v in ctx.counts.items() if not k.startswith("segment:")}
    print(
        args.book,
        "seconds",
        round(time.perf_counter() - started),
        "bytes",
        path.stat().st_size,
        json.dumps(counts),
        json.dumps(data["review"]["counts"]) if data.get("review") else "",
    )


if __name__ == "__main__":
    main()
