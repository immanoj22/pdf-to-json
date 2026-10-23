"""Step 17: every measurement of the final runs in one JSON for the report (no runs here).

Per book, from the final run records and the published book folders:

- output: book JSON bytes, files, images, review crops, units, build time of the assembly
  stage and of the whole run, peak memory;
- schema validation (``jsonschema``) and the round trip JSON -> model -> JSON (identical);
- review list: items by severity and kind;
- the lossless check, the evaluators on the JSON and the clean-up counts (their own scripts'
  outputs, read back).

Usage: python step17_report_data.py [--out final]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.assembly import validate
from book_core.assembly.schema import Book, iter_units

OUT = ROOT / "experiments/out/step17"
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy",
         "statistics")  # fmt: skip


def read(path):
    return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else None


def book_row(book, out):
    record = read(OUT / out / "performance" / f"{book}.json")
    if record is None:
        return None
    run = record["run"]
    folder = Path(run["book_json"])
    text = (folder / "book.json").read_text("utf-8")
    data = json.loads(text)
    errors = validate.errors(data)
    model = Book.model_validate(data)
    again = validate.dumps(model.model_dump(mode="json", by_alias=True))
    files = [p for p in folder.rglob("*") if p.is_file()]
    stages = run["stages"]
    return {
        "pages": run["pages"],
        "book_json_folder": str(folder),
        "publication_rebuilt_from_archive": bool(record.get("assembly_refresh")),
        "book_json_bytes": len(text.encode("utf-8")),
        "folder_bytes": sum(p.stat().st_size for p in files),
        "files": len(files),
        "images": sum(1 for p in files if p.parent.name == "images"),
        "review_crops": sum(1 for p in files if p.parent.name == "review"),
        "units": sum(1 for _ in iter_units(model.content)),
        "schema_errors": len(errors),
        "round_trip_identical": again == text,
        "content_sha256": data["metadata"]["content_sha256"],
        "assembly_seconds": round(stages.get("assembly", {}).get("wall_seconds", 0), 1),
        "assembly_peak_rss_bytes": stages.get("assembly", {}).get("peak_rss_bytes"),
        "assembly_peak_tree_rss_bytes": record.get("assembly_refresh", {}).get(
            "peak_tree_rss_bytes", run.get("peak_tree_rss_bytes")),
        "total_seconds": round(run["total"]["wall_seconds"], 1),
        "peak_tree_rss_bytes": run.get("peak_tree_rss_bytes"),
        "review_counts": data["review"]["counts"] if data.get("review") else {},
        "review_items": len(data["review"]["items"]) if data.get("review") else 0,
        "suppressed_by_reason": _count(data.get("suppressed") or [], "reason"),
        "lossless": read(OUT / out / "lossless" / f"{book}.json"),
        "json_eval": read(OUT / "json_eval" / f"{book}.json"),
        "cleanup": read(OUT / "cleanup" / f"{book}.json"),
    }


def _count(rows, key):
    found = {}
    for row in rows:
        found[row[key]] = found.get(row[key], 0) + 1
    return dict(sorted(found.items()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    result = {book: book_row(book, args.out) for book in BOOKS}
    result["_styling"] = {
        book: read(OUT / "styling" / f"{book}.json") for book in BOOKS
    }
    result["_hand_check"] = {
        "round1": read(OUT / "styling" / "hand_check_round1_summary.json"),
        "round2": read(OUT / "styling" / "hand_check_summary.json"),
    }
    result["_ocr"] = {
        "page_flag": read(OUT / "ocr" / "page_flag.json"),
        "pp_calibration": read(OUT / "ocr" / "pp_calibration.json"),
        "real_scans": (read(OUT / "real_eval" / "summary.json") or {}).get("groups"),
    }
    (OUT / args.out / "report_data.json").write_text(json.dumps(result, indent=1, default=str)
                                                     + "\n", "utf-8", newline="\n")  # fmt: skip
    for book in BOOKS:
        row = result[book]
        if row:
            print(book, {k: row[k] for k in ("book_json_bytes", "units", "schema_errors",
                                             "round_trip_identical", "review_items",
                                             "assembly_seconds")})  # fmt: skip


if __name__ == "__main__":
    main()
