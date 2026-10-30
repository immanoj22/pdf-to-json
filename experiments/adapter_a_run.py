"""Adapter A: run the Jaypee profile (and the test profile) on the published books, compare
with the real Jaypee deliveries, and write summaries to experiments/out/adapter_a/.

Inputs are read-only copies of published book folders (manifest-verified) in
.cache/adapter_inputs/<name>; deliveries go to .cache/adapter_a/<name>/ (git-ignored).
One worker, books one after another.

  python experiments/adapter_a_run.py [name ...]
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402

from book_adapters.compare import compare_deliveries  # noqa: E402
from book_adapters.engine.run import run_book  # noqa: E402

INPUTS = ROOT / ".cache" / "adapter_inputs"
WORK = ROOT / ".cache" / "adapter_a"
OUT = ROOT / "experiments" / "out" / "adapter_a"
BOOKS = {
    "art_9789372025262": {
        "settings": "books/9789372025262.yaml",
        "reference": ("jaypee_art_delivery", None),
    },
    "medical_anatomy": {"settings": None, "reference": ("medical_xml", "parent")},
    "art_therapy_index": {"settings": None},
    "immigrant_children": {"settings": None},
    "statistics": {"settings": None},
    "iap_mec": {"settings": None},
    "trichology": {"settings": None},
}


def summary(report: dict) -> dict:
    checks = report["checks"]
    lossless = checks["lossless"]
    house = checks["house_rules"]
    return {
        "seconds": report["seconds"],
        "profile": report["profile"]["ref"],
        "profile_resolved_sha256": report["profile"]["resolved_sha256"],
        "dtd_files": checks["dtd"]["files"],
        "dtd_errors": checks["dtd"]["errors"],
        "dtd_first_errors": {k: v["first"][:2] for k, v in checks["dtd"]["by_file"].items()},
        "house_violations": house["violations"],
        "house_failed": {
            k: {"n": v["violations"], "item": v["item"], "examples": v["examples"][:3]}
            for k, v in house["checks"].items()
            if v["violations"]
        },
        "lossless": {
            "tokens": lossless["coverage"]["tokens"],
            "missing": lossless["missing"],
            "extra": lossless["extra"],
            "omitted": lossless["coverage"]["omitted_by_reason"],
            "written_as": lossless["coverage"]["written_as"],
            "undeclared_out_of_order": lossless["order"]["undeclared_out_of_order"],
            "declared_moves": lossless["order"]["declared_moves"],
            "xml_matches_ledger": lossless["output"]["matches_ledger"],
        },
        "review_counts": report["review_counts"],
        "warnings": report["warnings"],
        "alt_text": {k: v for k, v in report["alt_text"].items() if k != "units"},
        "divisions": len(report["delivery"]["divisions"]),
        "images": report["delivery"]["images"],
        "big_images": report["delivery"]["big_images"],
    }


def tree_sha(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(folder)).encode())
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def main(names: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    if (OUT / "runs.json").exists():
        results = json.loads((OUT / "runs.json").read_text("utf-8"))
    for name in names or list(BOOKS):
        spec = BOOKS[name]
        settings = ROOT / spec["settings"] if spec.get("settings") else None
        started = time.perf_counter()
        # Published books carry no alt text yet: the explicit override is used and recorded.
        report = run_book(
            INPUTS / name,
            WORK / name,
            settings,
            None if settings else "jaypee_v3",
            allow_alt_text_placeholders=True,
        )
        row = summary(report)
        row["delivery_sha256"] = tree_sha(Path(report["root"]))
        ref = spec.get("reference")
        if ref:
            key, mode = ref
            path = reference_path(key)
            folder = path.parent if mode == "parent" else path
            cmp = compare_deliveries(Path(report["root"]), folder)
            (OUT / f"compare_{name}.json").write_text(
                json.dumps(cmp, indent=1, ensure_ascii=False) + "\n", "utf-8"
            )
            row["compare"] = {
                "biggest": cmp["biggest_differences"][:12],
                "page_info_equal": cmp["page_info"]["equal"],
                "files": {k: v for k, v in cmp["files"].items() if k != "common"},
            }
        row["wall_seconds"] = round(time.perf_counter() - started, 1)
        results[name] = row
        print(
            name,
            json.dumps({k: row[k] for k in ("dtd_errors", "house_violations", "seconds")}),
            row["lossless"]["missing"],
            row["lossless"]["extra"],
            flush=True,
        )
        (OUT / "runs.json").write_text(
            json.dumps(results, indent=1, ensure_ascii=False) + "\n", "utf-8"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
