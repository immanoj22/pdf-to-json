"""Step 11c experiments. The intake books are deliberately absent from the CLI."""

import argparse
import gc
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step11c_identity import BOOKS, OUT, digest  # noqa: E402


def model_digest(value):
    """Hash the exact JSON without a second full-size UTF-8 allocation."""
    serialized = value.model_dump_json()
    checksum = hashlib.sha256()
    for offset in range(0, len(serialized), 1024 * 1024):
        checksum.update(serialized[offset : offset + 1024 * 1024].encode("utf8"))
    return checksum.hexdigest()


def migrate(book, stages=None):
    from reference_paths import reference_path
    from step7_layouts import BOOKS as SOURCES
    from step7_layouts import CACHE
    from step8_run import vocabulary_for

    from book_core.cache_admin import cache_lock, register
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.layout.models import PageLayout
    from book_core.layout.pipeline import layout_fingerprint
    from book_core.objects.analysis import (
        atomic_write,
        cached_repetition,
        fingerprints,
        verified_read,
        write_analysis,
    )
    from book_core.objects.models import NativeObjectPage, ObjectAnalysis
    from book_core.reading_order.cache import order_fingerprint
    from book_core.reading_order.models import PageReadingOrder
    from book_core.run_context import source_session

    before = json.loads((OUT / "before" / f"{book}.json").read_text("utf8"))
    objects = json.loads((OUT / "before" / f"{book}_objects.json").read_text("utf8"))
    source = reference_path(SOURCES[book][0])
    report_path = OUT / "migration" / f"{book}.json"
    report = json.loads(report_path.read_text("utf8")) if report_path.exists() else {}
    with cache_lock(ROOT / ".cache"), source_session(source) as snapshot:
        if snapshot.digest != before["source_sha256"]:
            raise ValueError("Source differs from identity baseline")
        extractor = PyMuPDFExtractor("cpu")
        repetition = cached_repetition(source, extractor, CACHE)
        native, analysis = fingerprints(snapshot.digest, extractor, repetition)
        layout = layout_fingerprint(analysis, extractor.device.resolved)
        keys = {
            "native": native,
            "analysis": analysis,
            "layout": layout,
            "reading_order": order_fingerprint(layout, vocabulary_for(book)),
        }
        models = {
            "native": NativeObjectPage,
            "analysis": ObjectAnalysis,
            "layout": PageLayout,
            "reading_order": PageReadingOrder,
        }
        for stage, model in models.items():
            if stages is not None and stage not in stages:
                continue
            oldkey, newkey = before["keys"][stage], keys[stage]
            oldroot, newroot = CACHE / stage / oldkey, CACHE / stage / newkey
            paths = sorted(oldroot.glob("*.json"), key=lambda p: int(p.stem))
            if {p.stem for p in paths} != set(before["pages"]):
                raise ValueError(
                    f"Original {book}/{stage} baseline cache is incomplete or already pruned. "
                    "Do not replace the saved migration proof; run the current pipeline instead."
                )
            for path in paths:
                number = path.stem
                output = newroot / path.name
                expected = (
                    objects[number][stage]
                    if stage in {"native", "analysis"}
                    else before["pages"][number][stage]
                )
                if not output.exists():
                    value = verified_read(path, model, oldkey)
                    if stage == "analysis":
                        write_analysis(output, value, newkey, native)
                    else:
                        atomic_write(output, value, newkey)
                    del value
                    gc.collect()
                # Comparing the restored result with the frozen baseline proves the
                # migration directly; serializing the old model again adds no evidence.
                restored = verified_read(output, model, newkey)
                actual = (
                    model_digest(restored)
                    if stage in {"native", "analysis"}
                    else digest(restored.model_dump(mode="json"))
                )
                if actual != expected:
                    raise ValueError(f"Migration changed content: {book}/{stage}/{number}")
                del restored
                gc.collect()
                if int(number) % 50 == 0:
                    print(book, stage, number, flush=True)
            newpaths = list(newroot.glob("*.json"))
            register(
                ROOT / ".cache", snapshot.digest, stage, oldkey, paths, producer=f"legacy/{oldkey}"
            )
            register(
                ROOT / ".cache",
                snapshot.digest,
                stage,
                newkey,
                newpaths,
                producer=f"migrated/{newkey}",
            )
            report[stage] = {
                "pages_identical": len(paths),
                "old_key": oldkey,
                "new_key": newkey,
                "before_bytes": sum(p.stat().st_size for p in paths),
                "after_bytes": sum(p.stat().st_size for p in newpaths),
            }
            (OUT / "migration").mkdir(exist_ok=True)
            (OUT / "migration" / f"{book}.json").write_text(
                json.dumps(report, indent=2) + "\n", "utf8"
            )
            print(book, stage, "identical", len(paths), flush=True)


def run(book, workers):
    from reference_paths import reference_path
    from step7_layouts import BOOKS as SOURCES
    from step7_layouts import CACHE
    from step8_run import CACHE8, step6_artifact, vocabulary_for
    from step9_run import CACHE9
    from step10_run import CACHE10
    from step11_run import CACHE11

    from book_core.book_run import run_book

    before = json.loads((OUT / "before" / f"{book}.json").read_text("utf8"))
    artifact, _ = step6_artifact(before["source_sha256"])

    def progress(stage, completed, total):
        if completed % 50 == 0 or completed == total:
            print(book, stage, completed, total, flush=True)

    result = run_book(
        reference_path(SOURCES[book][0]),
        ROOT / ".cache/step11c/final_books",
        ROOT / ".cache",
        workers=workers,
        device="cpu",
        evidence=artifact,
        vocabulary=vocabulary_for(book),
        cache_dirs={
            "page": CACHE,
            "furniture": CACHE8,
            "metadata": CACHE8 / "metadata",
            "paragraphs": CACHE9,
            "structure": CACHE10,
            "lists": CACHE11,
        },
        progress=progress,
    )
    target = OUT / "performance"
    target.mkdir(exist_ok=True)
    (target / f"{book}_workers{workers}.json").write_text(
        json.dumps(result, indent=2) + "\n", "utf8"
    )
    print(book, result["total"], flush=True)


def metrics(book):
    import step11_run

    step11_run.OUT = OUT / "metrics"
    step11_run.HOLDOUT = {}
    sys.argv = [sys.argv[0], "--book", book]
    step11_run.main()


def compare_metrics():
    # These are operational identities, explicitly excluded from the semantic proof.
    excluded = {
        "seconds",
        "cache_hit",
        "cache_key_inputs",
        "paragraph_book_key",
        "lists_producer_sha256",
        "structure_producer_sha256",
        "paragraphs_producer_equals_step10b_freeze",
    }

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in excluded}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    comparison = {}
    for book in BOOKS:
        before = json.loads((OUT / "before" / f"{book}_metrics.json").read_text("utf8"))
        after = json.loads((OUT / "metrics" / book / "summary.json").read_text("utf8"))
        comparison[book] = {
            "identical": strip(before) == strip(after),
            "before_sha256": digest(strip(before)),
            "after_sha256": digest(strip(after)),
        }
    (OUT / "metrics_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", "utf8")
    print(comparison)
    if not all(r["identical"] for r in comparison.values()):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["migrate", "run", "metrics", "compare-metrics"])
    parser.add_argument("--book", choices=BOOKS)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--stages", nargs="+", choices=["native", "analysis", "layout", "reading_order"]
    )
    args = parser.parse_args()
    if args.action == "compare-metrics":
        compare_metrics()
    elif not args.book:
        parser.error("--book is required")
    elif args.action == "migrate":
        migrate(args.book, args.stages)
    elif args.action == "run":
        run(args.book, args.workers)
    else:
        metrics(args.book)


if __name__ == "__main__":
    main()
