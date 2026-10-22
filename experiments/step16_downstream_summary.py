"""Totals of the downstream comparison per book (scan vs native of the same pages)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step16/downstream"


def main():
    summary = {}
    for book in (
        "spanish_us_history",
        "immigrant_children",
        "medical_anatomy",
        "statistics",
    ):
        path = OUT / f"{book}.json"
        if not path.exists():
            continue
        report = json.loads(path.read_text("utf-8"))
        t = {"pages": len(report["pages"]), "words": 0, "word_errors": 0, "tau": [],
             "b_matched": 0, "b_native": 0, "b_ocr": 0, "l_native": 0, "l_ocr": 0,
             "l_matched": 0, "t_native": 0, "t_ocr": 0, "teds": [], "empty_ocr_pages": 0}  # fmt: skip
        for row in report["pages"].values():
            order = row["word_order"]
            t["words"] += order["words"]
            t["word_errors"] += order["word_errors"]
            if row["kendall_tau"] is not None:
                t["tau"].append(row["kendall_tau"])
            b = row["paragraph_boundaries"]
            if b:
                t["b_matched"] += b["matched"]
                t["b_native"] += b["native"]
                t["b_ocr"] += b["ocr"]
                t["empty_ocr_pages"] += b["ocr"] == 0
            for k in ("native", "ocr", "matched"):
                t["l_" + k] += row["lists"][k]
            t["t_native"] += row["tables"]["native"]
            t["t_ocr"] += row["tables"]["ocr"]
            t["teds"] += row["tables"]["teds"]
        precision = t["b_matched"] / t["b_ocr"] if t["b_ocr"] else 0.0
        recall = t["b_matched"] / t["b_native"] if t["b_native"] else 0.0
        t["paragraph_f1"] = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        t["paragraph_precision"], t["paragraph_recall"] = precision, recall
        t["order_wer"] = t["word_errors"] / t["words"] if t["words"] else None
        t["median_tau"] = sorted(t["tau"])[len(t["tau"]) // 2] if t["tau"] else None
        t["source_pages"] = report["source_pages"]
        summary[book] = t
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), "utf-8")
    for book, t in summary.items():
        print(book, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in t.items()
                     if k not in ("tau", "teds", "source_pages")})  # fmt: skip


if __name__ == "__main__":
    main()
