"""Inspect suppression/token-boundary evidence without changing inputs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.cache_store import read_json
from book_core.assembly.lossless import _records

run = json.loads((ROOT / "experiments/out/step17/final/performance/medical_anatomy.json")
                 .read_text("utf-8"))["run"]
data = json.loads((Path(run["book_json"]) / "book.json").read_text("utf-8"))
for item in data["suppressed"]:
    if item["text"] != "CHAPTER":
        continue
    payload = read_json(Path(run["output"]) / f"page_{item['page']:06d}.json.gz")
    store = payload["source"]["store"]
    print("suppressed", item)
    for node in data["content"]:
        for record in _records(node):
            if any(r["line"] == item["source_runs"][0]["line"]
                   for r in record.get("source_runs", [])):
                print("published", node["id"], record)
    for line in store["lines"]:
        if not any(s.startswith(item["source_runs"][0]["span"]) for s in line["span_ids"]):
            continue
        print("source line", line)
        for span in line["span_ids"]:
            print("span", span, repr(store["spans"][span]["raw_text"]))
        for line_id, spans in payload["line_spans"].items():
            if set(spans) & set(line["span_ids"]):
                print("layout line", line_id, spans)
                print("units", [u for u in payload["units"]["units"] if line_id in u["line_ids"]])
    break
