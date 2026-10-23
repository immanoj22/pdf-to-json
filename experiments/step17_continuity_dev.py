"""Step 17 Part 0: the continuity stage on the Step 16 final capture, with the two measured
changes switched on separately and together.

Inputs are rebuilt from the Step 16 final archives exactly as ``step15_dev`` does, plus the
page's display equation units (``continuity.cache.PageInput.equations``). Variants:

- ``base``: no equations given, kept Step 9 joins unchanged (must equal the Step 16 record);
- ``equations``: display equation units are floats at their anchors;
- ``column``: kept Step 9 page joins whose second part does not begin its column dropped;
- ``both``.

Each variant's chains are compared with the Step 16 final record: joins removed and added,
by kind, with the text at both sides of the break (``dev/<variant>/<book>.json``).

Usage: python step17_continuity_dev.py [--book NAME] [--variant base]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.continuity import cache as continuity
from book_core.continuity.cache import PageInput, link_book
from book_core.continuity.models import BookContinuity
from book_core.equations.models import EquationUnit
from book_core.model.common import Provenance

import step14a_common as common
import step14b_common  # noqa: F401 - cache keys of the latest final capture
import step15_dev as dev

CAPTURE = ROOT / "experiments/out/step16/final"
OUT = ROOT / "experiments/out/step17/continuity"
VARIANTS = {"base": (False, False), "equations": (True, False), "column": (False, True),
            "both": (True, True), "floats": ("floats", False)}  # fmt: skip


def inputs(book, with_equations):
    pages, headings, lists, paragraphs, total = dev.inputs_of(book, str(CAPTURE))
    root = Path(dev.c15.capture_run(str(CAPTURE))(book)["output"])

    def with_units():
        for number, item in enumerate(pages(), start=1):
            if not with_equations:
                yield item
                continue
            payload = read_json(root / f"page_{number:06d}.json.gz")
            units = tuple(
                EquationUnit.model_validate(u) for u in payload["equations"]["units"]
            )
            if with_equations == "floats":
                units += anchored_floats(payload, item.order)
            yield PageInput(**{**item.__dict__, "equations": units})

    return with_units, headings, lists, paragraphs, total, root


def anchored_floats(payload, order):
    """Development variant: final figures and float streams at their main-flow anchors,
    shaped like equation units (``id``, ``anchor``)."""
    from types import SimpleNamespace

    main = order.main
    found = []
    for figure in payload["figures"]["figures"]:
        a = figure["anchor"]
        found.append(SimpleNamespace(id=figure["id"], anchor=SimpleNamespace(
            stream_id=a["stream_id"], after_line_id=a["after_line_id"],
            position=a["position"], order=a["order"])))  # fmt: skip
    for stream in order.streams:
        if stream.anchor is None or stream.kind == "figure":
            continue
        a = stream.anchor
        found.append(SimpleNamespace(id=stream.id, anchor=SimpleNamespace(
            stream_id=main.id, after_line_id=a.after_line_id, position=a.position,
            order=a.order)))  # fmt: skip
    return tuple(found)


def joins(record):
    return {(b["from_id"], b["to_id"]): {**b, "chain_kind": c["kind"]}
            for c in record["chains"] for b in c["breaks"]}  # fmt: skip


_TEXTS = {}


def side_text(root, page, line_id):
    cache = _TEXTS
    if page not in cache:
        payload = read_json(root / f"page_{page:06d}.json.gz")
        spans = payload["source"]["store"]["spans"]
        cache.clear()
        cache[page] = {line: "".join(spans[s]["raw_text"] for s in ids)
                       for line, ids in payload["line_spans"].items()}  # fmt: skip
    return cache[page].get(line_id)


def run(book, variant):
    started = time.perf_counter()
    with_equations, column = VARIANTS[variant]
    continuity.KEPT_JOINS_BEGIN_COLUMN = column
    pages, headings, lists, paragraphs, total, root = inputs(book, with_equations)
    found = link_book(
        pages, headings, lists, paragraphs, dev.vocabulary(book), total, dev.DIGEST
    )
    record = BookContinuity(
        source_sha256=dev.DIGEST,
        pages=total,
        version="dev",
        provenance=Provenance(method="derived"),
        **found,
    )
    after = joins(record.model_dump(mode="json"))
    before = joins(read_json(root / "book.json.gz")["continuity"])
    rows = {}
    for name, keys, source in (("removed", before.keys() - after.keys(), before),
                               ("added", after.keys() - before.keys(), after)):  # fmt: skip
        rows[name] = []
        for key in sorted(keys, key=lambda k: (source[k]["from_page"], k)):
            b = source[key]
            rows[name].append({
                "kind": b["kind"], "chain_kind": b["chain_kind"], "source": b["source"],
                "from_page": b["from_page"], "to_page": b["to_page"],
                "from_id": b["from_id"], "to_id": b["to_id"],
                "a": side_text(root, b["from_page"], b["from_line_id"]),
                "b": side_text(root, b["to_page"], b["to_line_id"]),
                "reasons": b["reasons"], "skipped_ids": b["skipped_ids"],
            })  # fmt: skip
    result = {"book": book, "variant": variant, "joins_before": len(before),
              "joins_after": len(after), "counts": record.counts,
              "dropped_links": [d for d in record.dropped_links
                                if "begin its column" in d.get("reason", "")],
              **rows, "seconds": round(time.perf_counter() - started, 1)}  # fmt: skip
    path = OUT / variant / f"{book}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8",
                    newline="\n")  # fmt: skip
    print(book, variant, len(before), "->", len(after), "removed", len(rows["removed"]),
          "added", len(rows["added"]), result["seconds"], "s", flush=True)  # fmt: skip


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--variant", choices=VARIANTS, action="append")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        for variant in args.variant or list(VARIANTS):
            run(name, variant)
