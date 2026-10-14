"""Step 12 four-book runs: the full pipeline (figures included), identities, metrics, gates.

Reuses the Step 11d continuation driver (run, proof, compare, details) with Step 12 paths.
``freeze`` copies the frozen HEAD capture (Step 11d continuation, combined run) into
``experiments/out/step12/before`` once; the run writes ``experiments/out/step12/run``.

Usage:
  python step12_run.py freeze
  python step12_run.py run --book spanish_us_history
  python step12_run.py proof --book spanish_us_history --fresh
  python step12_run.py compare [--book ...]
  python step12_run.py details --book spanish_us_history
  (``--out final`` writes experiments/out/step12/final instead of run)
"""

# ruff: noqa: E402
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11d2_run as driver

FROZEN = ROOT / "experiments/out/step11d2/combined"
BEFORE = ROOT / "experiments/out/step12/before"
RUN = ROOT / "experiments/out/step12/run"
BOOKS = driver.identity.BOOKS


def freeze():
    if BEFORE.exists():
        raise SystemExit("The Step 12 baseline is already frozen")
    BEFORE.mkdir(parents=True)
    for book in BOOKS:
        for suffix in ("", "_objects", "_full_gates"):
            shutil.copyfile(FROZEN / f"after/{book}{suffix}.json", BEFORE / f"{book}{suffix}.json")
        shutil.copytree(FROZEN / f"metrics/{book}", BEFORE / f"metrics/{book}")


def use_model_evidence(rule):
    """Run books with layout-model figure evidence from the Step 12 detection cache."""
    from book_core.figures.settings import FigureSettings

    original = driver.run_book

    def run_book(*args, **kwargs):
        kwargs["cache_dirs"] = {**kwargs["cache_dirs"], "detections": ROOT / ".cache/models"}
        return original(
            *args,
            **kwargs,
            figure_settings=FigureSettings(model_evidence="on", model_disagreement=rule),
            model_cache_dir=ROOT / ".cache/huggingface",
        )

    driver.run_book = run_book


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run", "proof", "compare", "details"])
    parser.add_argument("--book", choices=BOOKS)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--out", default="run", help="output directory under step12/")
    parser.add_argument(
        "--evidence",
        choices=["neither", "not_both", "heron", "pp"],
        help="layout-model figure evidence on, with this disagreement rule (cached detections)",
    )
    args = parser.parse_args()
    if args.action == "freeze":
        return freeze()
    run = RUN.parent / args.out
    if args.evidence:
        use_model_evidence(args.evidence)
    driver.BASE, driver.OUT, driver.VARIANT = BEFORE, run, "step12"
    if args.action == "compare":
        return driver.compare(args.book)
    if args.action == "details":
        return driver.details(args.book)
    if not args.book:
        parser.error("--book is required")
    if args.action == "run":
        return driver.run(args.book)
    return driver.proof(args.book, fresh=args.fresh)


if __name__ == "__main__":
    main()
