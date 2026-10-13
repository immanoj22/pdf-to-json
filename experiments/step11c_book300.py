"""Prepare an explicit development excerpt and measure the full implemented pipeline."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

BASE = ROOT / ".cache/step11c/book300"
OUT = ROOT / "experiments/out/step11c/book300"


def prepare(pages):
    import pymupdf
    from reference_paths import reference_path

    from book_core.extraction.fingerprints import source_digest

    first, last = map(int, pages.split("-"))
    source = reference_path("spanish_pdf")
    BASE.mkdir(parents=True, exist_ok=True)
    target = BASE / "excerpt.pdf"
    if target.exists():
        raise ValueError("Benchmark excerpt already exists; do not replace its identity")
    with pymupdf.open(source) as original, pymupdf.open() as excerpt:
        if not 1 <= first <= last <= len(original):
            raise ValueError("Invalid explicit page range")
        excerpt.insert_pdf(original, from_page=first - 1, to_page=last - 1)
        excerpt.save(target, garbage=4, deflate=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.json").write_text(
        json.dumps(
            {
                "label": "standalone development-book-1 excerpt, no accuracy scoring",
                "pages": last - first + 1,
                "physical_source_range": [first, last],
                "original_sha256": source_digest(source),
                "excerpt_sha256": source_digest(target),
            },
            indent=2,
        )
        + "\n",
        "utf8",
    )


def run(mode, workers):
    from book_core.book_run import run_book

    def progress(stage, completed, total):
        if completed % 10 == 0 or completed == total:
            print(mode, workers, stage, completed, total, flush=True)

    result = run_book(
        BASE / "excerpt.pdf",
        BASE / f"final_{mode}_{workers}",
        BASE / f"cache_{mode}_{workers}",
        mode=mode,
        workers=workers,
        device="auto",
        progress=progress,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{mode}_workers{workers}.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
    print(result["total"], flush=True)


def compare():
    outputs = {}
    for result_path in OUT.glob("*_workers*.json"):
        result = json.loads(result_path.read_text("utf8"))
        path = Path(result["output"])
        outputs[result_path.stem] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
        }
    identical = len(outputs) >= 2 and all(
        v == next(iter(outputs.values())) for v in outputs.values()
    )
    (OUT / "identity.json").write_text(
        json.dumps({"identical": identical, "runs": sorted(outputs)}, indent=2) + "\n", "utf8"
    )
    print("identical", identical, flush=True)
    if not identical:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "compare"])
    parser.add_argument("--pages")
    parser.add_argument("--mode", choices=["development", "production"], default="development")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.pages:
            parser.error("prepare requires an explicit --pages range")
        prepare(args.pages)
    elif args.action == "run":
        run(args.mode, args.workers)
    else:
        compare()


if __name__ == "__main__":
    main()
