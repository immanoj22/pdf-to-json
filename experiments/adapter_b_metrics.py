"""Adapter B: before -> after delivery metrics per book (index entries and page links, web
and e-mail links, boxes, prefaces, soft hyphens left, house-rule findings, order exceptions).

"before" is the Step 20 adapter gate (main checkout .cache/s20/adapter/<book>, the frontend
books from experiments/out/adapter_b/before); "after" is .cache/adapter_b/<tag>/<book>.

Usage: python adapter_b_metrics.py --tag final
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from adapter_b_run import FRONTEND, MAIN, STEP20  # noqa: E402
from lxml import etree  # noqa: E402

from book_adapters.compare.explain import links  # noqa: E402


def metrics(folder: Path) -> dict:
    root = next(p for p in folder.iterdir() if p.is_dir() and p.name != "report")
    main = next(p for p in root.glob("*.xml") if p.name != "page_info.xml")
    raw = main.read_text("utf-8")
    xml = etree.fromstring(raw.encode("utf-8"), etree.XMLParser(resolve_entities=False))
    index = xml.find(".//index")
    kinds = links(xml)
    report = json.loads((folder / "report/delivery_report.json").read_text("utf-8"))
    checks = report["checks"]
    return {
        "index_entries": len(index.findall(".//indexentry")) if index is not None else 0,
        "index_sub_entries": len(index.findall(".//secondaryie")) if index is not None else 0,
        "index_page_links": kinds.get("index page link", 0),
        "web_links": kinds.get("web", 0),
        "emails": kinds.get("email", 0) + kinds.get("mailto", 0),
        "object_links": sum(v for k, v in kinds.items() if k.startswith("object")),
        "citation_links": kinds.get("citation", 0),
        "sidebars": len(xml.findall(".//sidebar")),
        "prefaces": len(xml.findall("preface")),
        "chapters": len(xml.findall(".//chapter")),
        "soft_hyphens_left": raw.count("&#x00AD;"),
        "dtd_errors": checks["dtd"]["errors"],
        "house_findings": checks["house_rules"]["violations"],
        "lossless_missing_extra": [checks["lossless"]["missing"], checks["lossless"]["extra"]],
        "undeclared_out_of_order": checks["lossless"]["order"]["undeclared_out_of_order"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="final")
    args = parser.parse_args()
    out = {}
    for book in list(STEP20) + list(FRONTEND):
        before = (
            ROOT / ".cache/adapter_b/before" / book
            if book in FRONTEND
            else MAIN / ".cache/s20/adapter" / book
        )
        after = ROOT / ".cache/adapter_b" / args.tag / book
        out[book] = {"before": metrics(before), "after": metrics(after)}
        changed = {
            k: f"{v} -> {out[book]['after'][k]}"
            for k, v in out[book]["before"].items()
            if v != out[book]["after"][k]
        }
        print(book, changed)
    path = ROOT / "experiments/out/adapter_b" / args.tag / "metrics.json"
    path.write_text(json.dumps(out, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
