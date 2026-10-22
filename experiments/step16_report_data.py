"""Aggregate every Step 16 measurement into one JSON for the report (no OCR runs here).

- synthetic benchmark: CER/WER per book x degradation x reader, with counts; readers are
  compared on the cases all of them read (common pages only);
- orientation: expected vs detected rotation;
- confidence calibration: threshold fitted on a seeded half of the pages, evaluated on the
  other half (word level); page threshold for ``must_check`` fitted the same way;
- time and memory per page and reader;
- producer equivalence: cases cached before the formatting-only producer change compared
  with the same cases re-read on the frozen producer;
- real scans: per language and reader, with the language-choice before/after.
"""

from __future__ import annotations

import glob
import gzip
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.ocr.evaluation import calibration_counts, fit_threshold

OUT = ROOT / "experiments/out/step16"
READERS = ("tesseract", "pp_ocrv5", "combined", "confidence_selection_experiment")


def load_cases():
    cases = []
    for path in sorted(glob.glob(str(OUT / "benchmark/cases/*/*.json.gz"))):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            record = json.load(stream)
        record["path"] = path
        cases.append(record)
    return cases


def case_id(record):
    i = record["identity"]
    return (i["book"], i["page"], i["degradation"])


def latest(cases, *, with_secondary):
    """One record per case: the frozen producer when present, else the earlier one."""
    producers = [r["identity"]["producer"] for r in cases]
    frozen = max(
        set(producers),
        key=lambda p: max(
            Path(r["path"]).stat().st_mtime
            for r in cases
            if r["identity"]["producer"] == p
        ),
    )
    chosen = {}
    for record in cases:
        if (record["identity"]["secondary"] is not None) != with_secondary:
            continue
        key = case_id(record)
        if key not in chosen or record["identity"]["producer"] == frozen:
            chosen[key] = record
    return chosen, frozen


def equivalence(cases, frozen):
    by_key = defaultdict(dict)
    for record in cases:
        if record["identity"]["secondary"] is None:
            by_key[case_id(record)][record["identity"]["producer"]] = record
    compared = identical = 0
    differing = []
    for key, versions in by_key.items():
        if frozen in versions and len(versions) > 1:
            new = versions[frozen]
            for producer, old in versions.items():
                if producer == frozen:
                    continue
                compared += 1
                same = (
                    old["readings"] == new["readings"]
                    and old["scores"] == new["scores"]
                )
                identical += same
                if not same:
                    differing.append(list(key))
    return {"compared": compared, "identical": identical, "differing": differing}


def add(total, part):
    for k in ("characters", "character_errors", "words", "word_errors"):
        total[k] = total.get(k, 0) + part[k]


def rates(total):
    return {
        **total,
        "cer": total["character_errors"] / total["characters"]
        if total.get("characters")
        else None,
        "wer": total["word_errors"] / total["words"] if total.get("words") else None,
    }


def synthetic(tess, pp):
    table = defaultdict(dict)
    for (book, _, degradation), record in tess.items():
        add(
            table[(book, degradation)].setdefault("tesseract", {}),
            record["scores"]["tesseract"]["geometry_aligned"],
        )
    per = {
        f"{b}|{d}": {r: rates(v) for r, v in readers.items()}
        for (b, d), readers in sorted(table.items())
    }
    overall = defaultdict(dict)
    for (_, degradation), readers in table.items():
        add(overall[degradation].setdefault("tesseract", {}), readers["tesseract"])
    common = defaultdict(dict)
    for key, record in pp.items():
        book, _, degradation = key
        for reader in READERS:
            if reader in record["scores"]:
                add(
                    common[f"{book}|{degradation}"].setdefault(reader, {}),
                    record["scores"][reader]["geometry_aligned"],
                )
    return {
        "per_book_degradation": per,
        "per_degradation": {
            d: {r: rates(v) for r, v in x.items()} for d, x in overall.items()
        },
        "readers_on_common_cases": {
            k: {r: rates(v) for r, v in x.items()} for k, x in sorted(common.items())
        },
        "cases": {"tesseract": len(tess), "two_readers": len(pp)},
    }


def orientation(tess):
    rows = defaultdict(lambda: {"cases": 0, "correct": 0, "wrong": []})
    for key, record in tess.items():
        row = rows[key[2]]
        row["cases"] += 1
        if record["orientation_expected"] == record["orientation_observed"]:
            row["correct"] += 1
        else:
            row["wrong"].append(
                [*key, record["orientation_expected"], record["orientation_observed"]]
            )
    return rows


def calibration(tess):
    pages = sorted({(b, p) for b, p, _ in tess})
    train = set(random.Random("1600:calibration").sample(pages, len(pages) // 2))
    split = {"train": [], "test": []}
    page_rows = {"train": [], "test": []}
    for (book, page, _), record in sorted(tess.items()):
        part = "train" if (book, page) in train else "test"
        observations = [
            (o["score"], o["wrong"])
            for o in record["scores"]["tesseract"]["observations"]
        ]
        split[part].extend(observations)
        reading = record["readings"]["tesseract"]
        scores = [w["confidence"] for w in reading["words"]]
        cer = record["scores"]["tesseract"]["geometry_aligned"]["cer"]
        if scores and cer is not None:
            page_rows[part].append((sum(scores) / len(scores), cer > 0.10))
    fitted = fit_threshold(split["train"])
    page_fit = fit_threshold(page_rows["train"])
    return {
        "split": "seeded half of the (book, page) pairs; all degradations of a page together",
        "word": {
            "threshold": fitted["threshold"],
            "training": fitted["training"],
            "held_out": calibration_counts(split["test"], fitted["threshold"]),
            "sample_sha256": fitted["sample_sha256"],
            "training_words": len(split["train"]),
        },
        "page": {
            "rule": "page needs checking when its CER > 10%",
            "threshold": page_fit["threshold"],
            "training": page_fit["training"],
            "held_out": calibration_counts(page_rows["test"], page_fit["threshold"]),
            "training_pages": len(page_rows["train"]),
        },
    }


def timing(tess, pp):
    rows = defaultdict(lambda: {"seconds": [], "rss": []})
    for source in (tess, pp):
        for record in source.values():
            for reader, value in record["timing"].items():
                rows[reader]["seconds"].append(value["wall_seconds"])
                rows[reader]["rss"].append(value["peak_process_tree_rss_bytes"])
    return {
        r: {
            "cases": len(v["seconds"]),
            "median_seconds": statistics.median(v["seconds"]),
            "max_seconds": max(v["seconds"]),
            "median_peak_rss_mb": statistics.median(v["rss"]) / 2**20,
            "max_peak_rss_mb": max(v["rss"]) / 2**20,
            "note": "measured while other jobs shared the CPU; upper bounds",
        }
        for r, v in rows.items()
    }


def real_scans():
    base = OUT / "real_eval"

    def read(name):
        path = base / name
        return json.loads(path.read_text("utf-8")) if path.exists() else []

    specific = [
        r
        for r in read("real_tesseract.json") + read("real_tesseract_chi2.json")
        if r.get("mode") == "specific" and "cer" in r
    ]
    pp = [r for r in read("real_pp_all.json") if "cer" in r]
    after = [r for r in read("real_tesseract_lingua2.json") if "cer" in r]
    before = [r for r in read("real_tesseract_lingua.json") if "cer" in r]
    common = {r["scan"] for r in pp} & {r["scan"] for r in specific}
    per = defaultdict(lambda: defaultdict(dict))
    for name, rows in (
        ("tesseract_specific_language", specific),
        ("pp_ocrv5", pp),
        ("tesseract_auto_after", after),
        ("tesseract_auto_before", before),
    ):
        for r in rows:
            add(
                per[r["language"] if "language" in r else r["scan"].split("_")[0]][
                    name
                ],
                r,
            )
    common_rows = defaultdict(lambda: defaultdict(dict))
    for name, rows in (("tesseract", specific), ("pp_ocrv5", pp)):
        for r in rows:
            if r["scan"] in common:
                add(common_rows[r["scan"].split("_")[0]][name], r)
    order_free = {}
    for r in pp:
        if "hypothesis" in r:
            ref = Counter(c for c in r["reference"] if not c.isspace())
            hyp = Counter(c for c in r["hypothesis"] if not c.isspace())
            hit = sum((ref & hyp).values())
            order_free[r["scan"]] = {
                "char_recall": hit / max(1, sum(ref.values())),
                "char_precision": hit / max(1, sum(hyp.values())),
            }
    return {
        "per_language": {
            k: {n: rates(v) for n, v in x.items()} for k, x in per.items()
        },
        "readers_on_common_scans": {
            k: {n: rates(v) for n, v in x.items()} for k, x in common_rows.items()
        },
        "pp_order_free": order_free,
        "pages": {"specific": specific, "pp": pp, "after": after, "before": before},
    }


def main():
    cases = load_cases()
    tess, frozen = latest(cases, with_secondary=False)
    pp, _ = latest(cases, with_secondary=True)
    result = {
        "frozen_producer": frozen,
        "equivalence": equivalence(cases, frozen),
        "synthetic": synthetic(tess, pp),
        "orientation": orientation(tess),
        "calibration": calibration(tess),
        "timing": timing(tess, pp),
        "real_scans": real_scans(),
    }
    (OUT / "report_data.json").write_text(
        json.dumps(result, indent=1, default=str), "utf-8"
    )
    print(
        json.dumps(
            {k: result[k] for k in ("equivalence", "calibration", "timing")},
            indent=1,
            default=str,
        )[:4000]
    )


if __name__ == "__main__":
    main()
