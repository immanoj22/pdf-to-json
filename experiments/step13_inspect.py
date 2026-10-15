"""Step 13a: list the equation regions of a development run with their source text.

Text is resolved from the span store for review only (never written back).

Usage: python step13_inspect.py --book immigrant_children [--run step12] [--key KEY]
                                [--source text] [--pages 1-50] [--out file.json]
"""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step13_equations import DEV, OUT, stage_inputs

from book_core.equations.cache import load_page


def region_text(store, region):
    return "".join(store.spans[r.span_id].raw_text[r.start : r.end] for r in region.span_refs)


def rows(book, run, key, source=None, pages=None):
    inputs = stage_inputs(book, run)
    key = key or json.loads((OUT / "equations_dev" / f"{book}.json").read_text("utf-8"))["key"]
    for page in inputs["pages"]():
        number = page.geometry.page
        if pages and not pages[0] <= number <= pages[1]:
            continue
        record = load_page(DEV, key, number)
        for region in record.regions:
            if source and region.source != source:
                continue
            yield {
                "page": number,
                "id": region.id[:12],
                "text": region_text(page.store, region),
                "source": region.source,
                "presentation": region.presentation,
                "rules": region.rules,
                "host": region.host.unit_kind,
                "models": [
                    m
                    for m, v in (
                        ("heron", region.model_support.heron),
                        ("pp", region.model_support.pp_doclayoutv3),
                    )
                    if v
                ],
                "bbox": [round(v, 1) for v in region.bbox.model_dump().values()],
                "objects": len(region.object_ids),
            }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="step12")
    parser.add_argument("--key")
    parser.add_argument("--source")
    parser.add_argument("--pages")
    parser.add_argument("--out")
    args = parser.parse_args()
    span = tuple(int(v) for v in args.pages.split("-")) if args.pages else None
    found = list(rows(args.book, args.run, args.key, args.source, span))
    if args.out:
        Path(args.out).write_text(json.dumps(found, indent=1, ensure_ascii=False), "utf-8")
    for row in found:
        print(
            ascii(
                (
                    row["page"],
                    row["text"],
                    row["presentation"],
                    row["rules"],
                    row["host"],
                    row["models"],
                )
            )
        )
    print(len(found), "regions")
