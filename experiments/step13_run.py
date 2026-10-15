"""Step 13a runs: books 1-4 through the Step 11d/12 driver, and the math development book.

Books 1-4 reuse the Step 11d continuation driver (run, proof, compare, details) with layout-
model figure evidence on (``not_both``), exactly as the Step 12 final run. ``freeze`` copies
the Step 12 final capture into ``experiments/out/step13/before`` once.

The math book (``statistics``) has no earlier stage registry: it runs ``run_book`` directly
(whole-book evidence and vocabulary computed by the runner itself, as in production) into
the same development caches, and ``proof`` checks I1-I7 and line ownership on every page.

Usage:
  python step13_run.py freeze
  python step13_run.py run --book statistics --out before
  python step13_run.py proof --book statistics --out before
  python step13_run.py run --book spanish_us_history --out final
  python step13_run.py compare --out final
"""

# ruff: noqa: E402
import argparse
import gc
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11d2_run as driver
import step12_run
from reference_paths import reference_path
from step7_layouts import CACHE
from step8_run import CACHE8
from step9_run import CACHE9
from step10_run import CACHE10
from step11_run import CACHE11
from step13_books import BOOKS, MATH_BOOK

FROZEN = ROOT / "experiments/out/step12/final"
OUT = ROOT / "experiments/out/step13"
BEFORE = OUT / "before"
CACHE_DIRS = {
    "page": CACHE,
    "furniture": CACHE8,
    "metadata": CACHE8 / "metadata",
    "paragraphs": CACHE9,
    "structure": CACHE10,
    "lists": CACHE11,
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="\n")


def freeze():
    if (BEFORE / "spanish_us_history.json").exists():
        raise SystemExit("The Step 13 baseline is already frozen")
    for book in driver.identity.BOOKS:
        for suffix in ("", "_objects", "_full_gates"):
            target = BEFORE / f"{book}{suffix}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(FROZEN / f"after/{book}{suffix}.json", target)
        shutil.copytree(FROZEN / f"metrics/{book}", BEFORE / f"metrics/{book}")


def capacity():
    """The owner's disk rule (Step 10b decision): stop when the full four-book cache estimate
    (1,412 pages x 12 MiB, as in Step 11c) exceeds free space minus 5 GB. The Step 11d driver
    kept a stricter 10 GB margin; every upstream cache already exists in Step 13."""
    free = shutil.disk_usage(ROOT).free
    estimate = 1412 * 12 * 1024 * 1024
    if estimate > free - 5_000_000_000:
        raise ValueError("Insufficient free disk: estimate exceeds free space minus 5 GB")
    return {"free_bytes": free, "estimate_bytes": estimate, "remaining_bytes": free - estimate}


def figure_settings():
    from book_core.figures.settings import FigureSettings

    return FigureSettings(model_evidence="on", model_disagreement="not_both")


def run_math_book(out):
    """The math book through the full runner, one worker, CPU, model evidence on."""
    from book_core.book_run import run_book
    from book_core.caching import SCOPES, code_digest

    target = OUT / out
    free = shutil.disk_usage(ROOT).free
    estimate = 871 * 12 * 1024 * 1024
    if free - estimate < 10_000_000_000:
        raise SystemExit("Insufficient free disk for the math book estimate")

    def progress(stage, completed, total):
        if completed % 25 == 0 or completed == total:
            print(MATH_BOOK, stage, completed, total, flush=True)

    result = run_book(
        reference_path(BOOKS[MATH_BOOK][0]),
        ROOT / ".cache/step13/final_books" / out,
        ROOT / ".cache",
        workers=1,
        device="cpu",
        cache_dirs={**CACHE_DIRS, "detections": ROOT / ".cache/models"},
        progress=progress,
        figure_settings=figure_settings(),
        model_cache_dir=ROOT / ".cache/huggingface",
    )
    write(
        target / f"performance/{MATH_BOOK}.json",
        {
            "disk_before": {"free_bytes": free, "estimate_bytes": estimate},
            "producers": {scope: code_digest(scope) for scope in SCOPES},
            "run": result,
        },
    )
    assert result["source_hashes"] == 1
    print(MATH_BOOK, "run complete", result["output"], flush=True)


def proof_math_book(out):
    """I1-I7 and exact line ownership on every page, from the run's caches."""
    from book_core.extraction.fingerprints import stable_id
    from book_core.layout.invariants import check
    from book_core.layout.models import PageLayout
    from book_core.lists.keys import book_fingerprint
    from book_core.lists.models import PageLists
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import ObjectAnalysis

    target = OUT / out
    keys = json.loads((target / f"performance/{MATH_BOOK}.json").read_text("utf-8"))["run"][
        "cache_keys"
    ]
    list_key = book_fingerprint(keys["lists"]) if isinstance(keys["lists"], dict) else None
    gates, ownership = {}, {}
    pages = json.loads((target / f"performance/{MATH_BOOK}.json").read_text("utf-8"))["run"][
        "pages"
    ]
    for number in range(1, pages + 1):
        analysis = verified_read(
            CACHE / "analysis" / keys["analysis"] / f"{number}.json",
            ObjectAnalysis,
            keys["analysis"],
        )
        layout = verified_read(
            CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
        )
        key = list_key or keys["lists"]
        units = verified_read(
            CACHE11 / "lists/page" / key / f"{number}.json",
            PageLists,
            stable_id(key, "page", int(number)),
        )
        assigned = [lid for unit in units.units for lid in unit.line_ids]
        ordered = [lid for stream in units.order.streams for lid in stream.line_ids]
        expected = {line.id for line in layout.lines}
        gates[str(number)] = check(layout, analysis)
        ownership[str(number)] = {
            "lines": len(expected),
            "units_once": len(assigned) == len(set(assigned)) and set(assigned) == expected,
            "ordered_once": len(ordered) == len(set(ordered)) and set(ordered) == expected,
        }
        del analysis, layout, units
        gc.collect()
        if number % 50 == 0:
            print(MATH_BOOK, "proof", number, flush=True)
    totals = {
        name: sum(len(r[name]) for r in gates.values())
        for name in ("I1", "I2", "I3", "I4", "I5", "I6", "I7")
    }
    write(
        target / f"after/{MATH_BOOK}_full_gates.json",
        {"invariants": gates, "invariant_totals": totals, "ownership": ownership},
    )
    print(totals, all(v["units_once"] and v["ordered_once"] for v in ownership.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run", "proof", "compare", "details"])
    parser.add_argument("--book", choices=BOOKS)
    parser.add_argument("--out", default="run")
    args = parser.parse_args()
    if args.action == "freeze":
        return freeze()
    if args.book == MATH_BOOK:
        if args.action == "run":
            return run_math_book(args.out)
        if args.action == "proof":
            return proof_math_book(args.out)
        parser.error("compare/details apply to books 1-4")
    step12_run.use_model_evidence("not_both")
    driver.capacity = capacity
    driver.BASE, driver.OUT, driver.VARIANT = BEFORE, OUT / args.out, "step13"
    if args.action == "compare":
        return driver.compare(args.book)
    if args.action == "details":
        return driver.details(args.book)
    if not args.book:
        parser.error("--book is required")
    if args.action == "run":
        return driver.run(args.book)
    return driver.proof(args.book)


if __name__ == "__main__":
    main()
