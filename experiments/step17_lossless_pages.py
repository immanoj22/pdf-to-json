"""Locate per-page differences between the published JSON and the archive ledger view."""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly.lossless import compare
from book_core.cache_store import read_json
from book_core.ledger.tokenization import token_counter


def main(book):
    record = ROOT / f"experiments/out/step17/final/performance/{book}.json"
    run = json.loads(record.read_text("utf-8"))["run"]
    data = json.loads((Path(run["book_json"]) / "book.json").read_text("utf-8"))
    failures = []
    for page in data["pages"]:
        number = page["index"]
        part = {"content": [u for u in data["content"] if number in u["pages"]],
                "furniture": [u for u in data["furniture"] if u["page"] == number],
                "suppressed": [u for u in data["suppressed"] if u["page"] == number]}
        payload = read_json(Path(run["output"]) / f"page_{number:06d}.json.gz")
        source = payload["source"]
        box = source["geometry"]["content_bbox"]
        retained = Counter()
        for line in source["store"]["lines"]:
            b = line["bbox"]
            if not (box["x0"] <= (b["x0"] + b["x1"]) / 2 <= box["x1"] and
                    box["y0"] <= (b["y0"] + b["y1"]) / 2 <= box["y1"]):
                continue
            retained.update(token_counter("".join(source["store"]["spans"][s]["raw_text"]
                                                  for s in line["span_ids"])))
        result = compare(part, retained)
        if result["missing"] or result["extra"]:
            row = {"page": number, **result}
            failures.append(row)
            print(row, flush=True)
    target = ROOT / f"experiments/out/step17/final/lossless/{book}_pages.json"
    target.write_text(json.dumps(failures, indent=1) + "\n", "utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1])
