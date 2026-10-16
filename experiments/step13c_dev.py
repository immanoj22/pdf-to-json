"""Step 13c development harness: the MathML stage's pass functions on the 13b bundles.

Runs ``book_core.mathml.cache`` passes (collect, isolated readings, votes, final table,
region records) on the Step 13b per-page bundles and the Step 13b final equation records,
reading formula readings from the per-image cache (``--live`` computes missing ones; without
it a missing reading counts as "no reading"), then scores every path against the verified
gold. Development only: the final records come from ``book_run``.

Usage: python step13c_dev.py --book statistics [--live] [--pages 1-100] [--out dev1]
"""

# ruff: noqa: E402
import argparse
import gzip
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13b_bundles as bundles
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS
from step13_boundaries import classify
from step13c_readings import keys_of

from book_core.cache_store import read_model
from book_core.equations.models import PageEquations
from book_core.evaluation.math_scoring import score, window
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.mathml import cache as stage
from book_core.mathml import images as imaging
from book_core.mathml import markup, shapes
from book_core.mathml.decide import compare
from book_core.mathml.recognition import PPFormulaNet, RecognitionCache
from book_core.mathml.settings import MathSettings
from book_core.mathml.symbols import TextSymbols

OUT = ROOT / "experiments/out/step13c/dev"
GOLD = ROOT / "backend/tests/gold_derived_math/statistics"


class CachedOnly:
    """A reading cache that never runs the model: a missing reading is empty."""

    def __init__(self, cache):
        self.cache, self.recognizer, self.missing = cache, cache.recognizer, 0

    def read(self, png):
        import hashlib

        from book_core.cache_store import read_json

        digest = hashlib.sha256(png).hexdigest()
        path = self.cache.root / self.cache.key() / digest[:2] / f"{digest}.json"
        if path.exists():
            return read_json(path)
        self.missing += 1
        return {"latex": None, "truncated": False}


class JsonlReader:
    """Dev only: readings of another recognizer by image digest (UniMERNet comparison)."""

    def __init__(self, path, recognizer):
        self.recognizer, self.missing, self.by_digest = recognizer, 0, {}
        for line in Path(path).read_text("utf-8").splitlines():
            row = json.loads(line)
            if row.get("path"):
                self.by_digest[Path(row["path"]).stem] = row["latex"]

    def read(self, png):
        import hashlib

        latex = self.by_digest.get(hashlib.sha256(png).hexdigest())
        self.missing += latex is None
        return {"latex": latex, "truncated": False}


class BundleBook:
    def __init__(self, book, key, numbers):
        self.book, self.key, self.numbers = book, key, numbers

    def pages(self):
        for number in self.numbers:
            yield bundles.load(self.book, number)["page"]

    def each(self):
        for number in self.numbers:
            equations = read_model(
                CACHE / "equations" / self.key / f"{number}.json",
                PageEquations,
                self.key,
            )
            if not equations.regions:
                yield (
                    SimpleNamespace(geometry=SimpleNamespace(page=number)),
                    None,
                    equations,
                    {},
                    None,
                )
                continue
            bundle = bundles.load(self.book, number)
            page = bundle["page"]
            native = bundle["native"]
            yield (
                page,
                native,
                equations,
                {o.id: o for o in native.objects},
                TextSymbols(page, native),
            )


def gold():
    with gzip.open(GOLD / "equations.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    with gzip.open(GOLD / "mathml.jsonl.gz", "rt", encoding="utf-8") as stream:
        mathml = {json.loads(line)["slot"]: json.loads(line)["mathml"] for line in stream}
    return rows, mathml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default="statistics")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--pages")
    parser.add_argument("--out", default="dev")
    parser.add_argument("--isolated", help="dev only: pickle {signature: LaTeX} of shapes")
    parser.add_argument("--readings", help="dev only: JSON lines of another recognizer")
    args = parser.parse_args()
    keys = keys_of(args.book)
    evidence = bundles.book_evidence(args.book)
    total = evidence["pages"]
    first, last = (1, total) if not args.pages else map(int, args.pages.split("-"))
    numbers = list(range(first, last + 1))
    book = BundleBook(args.book, keys["equations"], numbers)
    settings = MathSettings()
    cache = RecognitionCache(
        PPFormulaNet(device="auto", cache_dir=ROOT / ".cache/huggingface"),
        ROOT / ".cache/models",
    )
    reader = cache if args.live else CachedOnly(cache)
    if args.readings:
        reader = JsonlReader(args.readings, cache.recognizer)
    extractor = PyMuPDFExtractor("cpu")
    source = reference_path(BOOKS[args.book][0])
    started = time.perf_counter()
    book_size = evidence["book_size"]
    renderer = imaging.RegionImages(extractor, source, settings.recognition_dpi)
    readings, heights, rows, representative, _ = stage.collect(book, reader, renderer, book_size)
    units = shapes.unit_heights(heights)
    descents = shapes.descents(rows, units, book_size)
    if args.isolated:
        latex_of = pickle.loads(Path(args.isolated).read_bytes())
        isolated = {
            s: (*shapes.isolated_reading(latex_of[s]), latex_of[s])
            if s in latex_of
            else (None, None, None)
            for s in representative
        }
    else:
        # Shapes are always read by the stage recognizer (cached); --readings swaps only the
        # region readings (the image path and the context votes).
        shape_reader = CachedOnly(cache) if args.readings else reader
        isolated = stage.isolated_readings(representative, shape_reader)
    provisional = stage.provisional_table(isolated, units, descents)
    name = "pp_formulanet_l"
    votes = stage.context_votes(book, provisional, readings, name, book_size)
    table, labels = stage.final_table(isolated, votes, units, descents)
    records = {}
    regions_by_page = {}
    for _page, _native, equations, objects, text in book.each():
        regions_by_page[equations.page] = equations.regions
        for region in equations.regions:
            records[region.id] = stage.region_record(
                region,
                objects,
                text,
                table,
                labels,
                readings,
                name,
                settings,
                book_size,
            )
    elapsed = time.perf_counter() - started
    summary = {
        "pages": [first, last],
        "regions": len(records),
        "missing_readings": getattr(reader, "missing", 0),
        "seconds": round(elapsed, 1),
        "by_review": Counter(r.review_status for r in records.values()),
        "by_agreement": Counter(r.agreement for r in records.values()),
        "by_output": Counter(r.output for r in records.values()),
        "by_source_agreement": Counter(f"{r.source}/{r.agreement}" for r in records.values()),
        "shapes": {
            s: {
                "char": label.char,
                "isolated": label.isolated,
                "confidence": label.confidence,
                "by_position": label.by_position,
                "votes": label.votes,
                "flags": label.flags,
            }
            for s, label in labels.items()
        },
    }
    summary["records"] = [
        {
            "page": r.page,
            "id": r.equation_id[:12],
            "source": r.source,
            "agreement": r.agreement,
            "confidence": r.confidence,
            "review": r.review_status,
            "flags": r.flags,
            "readings": {x.path: x.latex for x in r.readings},
        }
        for r in records.values()
    ]
    if args.book == "statistics":
        summary["gold"] = evaluate(regions_by_page, records, numbers)
    target = OUT / f"{args.out}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "shapes"}, indent=1,
                     ensure_ascii=False)[:6000])  # fmt: skip


def evaluate(regions_by_page, records, numbers, extra=None):
    """Scores per level (strict / expression), path, presentation and review status.
    ``extra``: {region id: {path name: tree or None}} of additional readings."""
    rows, mathml = gold()
    located = defaultdict(list)
    for row in rows:
        if row["status"] == "located":
            located[row["page"]].append(row)
    table = defaultdict(lambda: defaultdict(list))
    examples, per_row = [], []
    for number in numbers:
        page_rows = located.get(number, [])
        all_objects = {o for r in page_rows for o in r["object_ids"]}
        for row in page_rows:
            if not row["verified"]:
                continue
            label, used = classify(row, regions_by_page.get(number, []), all_objects - set(
                row["object_ids"]))  # fmt: skip
            if not used or label in {"missed", "split", "partial"}:
                table["boundary_failure"]["count"].append(1)
                continue
            record = records[used[0].id]
            expected = markup.read(mathml[row["slot"]])
            # Strict: one complete region holding only this equation's evidence (a mixed
            # region also holds text-set parts the reference keeps as text).
            level = "strict" if label == "complete" and used[0].source != "mixed" else "expression"
            readings = {r.path: r for r in record.readings}
            candidates = {"chosen": record.mathml}
            for path in ("text", "drawn", "image"):
                if path in readings:
                    candidates[path] = readings[path].mathml
            for path, tree in ((extra or {}).get(record.equation_id) or {}).items():
                candidates[path] = tree
            trees = {}
            row_result = {"slot": row["slot"], "level": level, "presentation": row["presentation"]}
            for path, value in candidates.items():
                tree = markup.read(value) if isinstance(value, str) else value
                trees[path] = tree
                result = score(tree, expected) if level == "strict" else window(tree, expected)
                row_result[path] = result
                buckets = [
                    f"{level}/{path}/{row['presentation']}",
                    f"{level}/{path}/all",
                ]
                if path == "chosen":
                    buckets.append(f"{level}/chosen@{record.review_status}/all")
                for bucket in buckets:
                    table[bucket]["exact"].append(result["exact"])
                    table[bucket]["symbol_accuracy"].append(result["symbol_accuracy"])
                    if result["ted_share"] is not None:
                        table[bucket]["ted_share"].append(result["ted_share"])
                if path == "chosen" and not result["exact"] and len(examples) < 400:
                    examples.append(
                        {
                            "page": number,
                            "slot": row["slot"],
                            "level": level,
                            "gold": row["leaf_text"],
                            "chosen": record.latex,
                            "path": record.path,
                            "readings": {r.path: r.latex for r in record.readings},
                            "agreement": record.agreement,
                            "confidence": record.confidence,
                            "symbol_accuracy": result["symbol_accuracy"],
                        }
                    )
            pp, uni = trees.get("image"), trees.get("image_unimernet")
            row_result["models_agree"] = None if pp is None or uni is None else compare(pp, uni)[0]
            per_row.append(row_result)
    out = {}
    for bucket, metrics in sorted(table.items()):
        out[bucket] = {
            "n": len(next(iter(metrics.values()))),
            **{k: round(sum(map(float, v)) / len(v), 4) if v else None for k, v in metrics.items()},
        }
    out["examples"] = examples
    out["rows"] = per_row
    return out


if __name__ == "__main__":
    main()
