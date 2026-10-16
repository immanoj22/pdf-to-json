"""Step 13c evaluation: final Statistics MathML records against the 1,254 verified gold.

Scores the archived records (chosen MathML and every path's reading) at expression level and
strict, per path, inline vs display and per review status (``step13c_dev.evaluate``), adds
UniMERNet as a separate image reading (side-environment readings matched by image digest,
``step13c_unimernet.py``), and summarises books 1-4 equation records, stage time and memory
from the final performance records.

The "with UniMERNet" system (UniMERNet as the image path instead of PP-FormulaNet-L) is the
development harness re-run with UniMERNet readings (``step13c_dev.py --readings ...``); its
gold table is merged here when present.

Usage: python step13c_evaluate.py --out final
"""

# ruff: noqa: E402
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13c_dev import evaluate

from book_core.cache_store import read_json
from book_core.equations.models import PageEquations
from book_core.mathml.latex import from_latex
from book_core.mathml.models import EquationMath

OUT = ROOT / "experiments/out/step13c"
BOOKS = (
    "spanish_us_history",
    "immigrant_children",
    "art_therapy_index",
    "medical_anatomy",
)


def archive_records(run):
    output = Path(run["output"])
    regions_by_page, records = {}, {}
    for number in range(1, run["pages"] + 1):
        payload = read_json(output / f"page_{number:06d}.json.gz")
        regions_by_page[number] = PageEquations.model_validate(payload["equations"]).regions
        for item in payload["mathml"]["equations"]:
            record = EquationMath.model_validate(item)
            records[record.equation_id] = record
    return regions_by_page, records


def unimernet_trees(book):
    mapping = OUT / f"unimernet/{book}_regions.json"
    readings = OUT / f"unimernet/{book}.jsonl"
    if not mapping.exists() or not readings.exists():
        return None
    by_digest = {
        json.loads(line)["image_sha256"]: json.loads(line)["latex"]
        for line in readings.read_text("utf-8").splitlines()
    }
    regions = json.loads(mapping.read_text("utf-8"))
    out = {}
    for region_id, digest in regions.items():
        latex = by_digest.get(digest)
        out[region_id] = {"image_unimernet": from_latex(latex) if latex else None}
    return out


def model_comparison(rows):
    """PP-FormulaNet-L vs UniMERNet on the gold equations both read: accuracy per model,
    their agreement rate, and each model's accuracy when they agree and disagree."""

    def mean(values):
        values = list(values)
        return round(sum(values) / len(values), 4) if values else None

    out = {}
    for level in ("strict", "expression", "all"):
        chosen = [r for r in rows if level == "all" or r["level"] == level]
        both = [r for r in chosen if r.get("models_agree") is not None]
        part = {"gold_equations": len(chosen), "read_by_both": len(both)}
        for path, name in (("image", "pp_formulanet_l"), ("image_unimernet", "unimernet")):
            read = [r for r in chosen if path in r and r[path]["ted"] is not None]
            part[name] = {
                "read": len(read),
                "exact": mean(r[path]["exact"] for r in read),
                "symbol_accuracy": mean(r[path]["symbol_accuracy"] for r in read),
                "exact_on_both": mean(r[path]["exact"] for r in both),
            }
        agree = [r for r in both if r["models_agree"]]
        disagree = [r for r in both if not r["models_agree"]]
        part["agreement_rate"] = mean(r["models_agree"] for r in both)
        part["when_agree"] = {
            "n": len(agree),
            "exact": mean(r["image"]["exact"] for r in agree),
            "symbol_accuracy": mean(r["image"]["symbol_accuracy"] for r in agree),
        }
        part["when_disagree"] = {
            "n": len(disagree),
            "pp_exact": mean(r["image"]["exact"] for r in disagree),
            "unimernet_exact": mean(r["image_unimernet"]["exact"] for r in disagree),
            "either_exact": mean(
                r["image"]["exact"] or r["image_unimernet"]["exact"] for r in disagree
            ),
        }
        out[level] = part
    return out


def summary(records):
    return {
        "records": len(records),
        "by_source": dict(Counter(r.source for r in records)),
        "by_path": dict(Counter(r.path or "none" for r in records)),
        "by_agreement": dict(Counter(r.agreement for r in records)),
        "by_review": dict(Counter(r.review_status for r in records)),
        "by_output": dict(Counter(r.output for r in records)),
        "fallback_images": sum(r.fallback_image is not None for r in records),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    target = OUT / args.out
    run = json.loads((target / "performance/statistics.json").read_text("utf-8"))["run"]
    regions_by_page, records = archive_records(run)
    extra = unimernet_trees("statistics")
    result = {
        "statistics": {
            **summary(list(records.values())),
            "gold": evaluate(regions_by_page, records, range(1, run["pages"] + 1), extra),
        }
    }
    result["statistics"]["image_models"] = model_comparison(
        result["statistics"]["gold"].pop("rows")
    )
    dev = OUT / "dev/with_unimernet.json"
    if dev.exists():
        result["statistics"]["system_with_unimernet"] = {
            k: v for k, v in json.loads(dev.read_text("utf-8"))["gold"].items() if k != "examples"
        }
    for book in BOOKS:
        path = target / f"performance/{book}.json"
        if not path.exists():
            continue
        book_run = json.loads(path.read_text("utf-8"))["run"]
        _, book_records = archive_records(book_run)
        rows = sorted(book_records.values(), key=lambda r: (r.page, r.equation_id))
        result[book] = {
            **summary(rows),
            "records_list": [
                {
                    "page": r.page,
                    "source": r.source,
                    "latex": r.latex,
                    "readings": {x.path: x.latex for x in r.readings},
                    "agreement": r.agreement,
                    "confidence": r.confidence,
                    "review": r.review_status,
                    "output": r.output,
                    "flags": r.flags,
                }
                for r in rows
            ],
        }
    timing = {}
    for book in (*BOOKS, "statistics"):
        path = target / f"performance/{book}.json"
        if path.exists():
            book_run = json.loads(path.read_text("utf-8"))["run"]
            stage = book_run["stages"].get("mathml", {})
            timing[book] = {
                "mathml_seconds": stage.get("seconds") or stage.get("wall_seconds"),
                "mathml_peak_rss_bytes": stage.get("peak_rss_bytes"),
                "total_seconds": book_run["total"].get("seconds")
                or book_run["total"].get("wall_seconds"),
                "peak_tree_rss_bytes": book_run.get("peak_tree_rss_bytes"),
            }
    result["timing"] = timing
    (target / "evaluation.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    stats = result["statistics"]
    print(json.dumps({k: v for k, v in stats.items() if k != "gold"}, indent=1))
    for bucket, value in stats["gold"].items():
        if bucket != "examples":
            print(bucket, value)


if __name__ == "__main__":
    main()
