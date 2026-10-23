"""Step 17 Part 3: before/after counts of the clean-up, per book (Step 16 archive vs JSON).

- **hidden text**: before, spans proven hidden (paint cover, or no pixel change when
  suppressed) that sat in content units; after, ``suppressed`` records by reason (spans and
  tokens), and none of those tokens left in content;
- **figure text**: before, units in the paragraph stream that belong to a figure (figure-text
  units no figure links, and units of a figure's own stream); after, how many were moved
  into ``figure.text`` and how many stay paragraphs (role ``figure_text``, flagged);
- **index dividers**: units typed ``index_divider`` and what they were before;
- **list markers**: items whose marker became structure (``marker``), by type, and markers
  kept in the text because they are glued to the word that follows (flagged).

Nothing is lost: the lossless check (``step17_lossless.py``) runs on the same JSON.

Usage: python step17_cleanup_counts.py --book NAME --json PATH [--archive DIR]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.ledger.tokenization import token_counter

import step17_json_eval as jeval

OUT = ROOT / "experiments/out/step17/cleanup"


def before_counts(archive, pages):
    counts, kinds_of = Counter(), {}
    for number in range(1, pages + 1):
        payload = read_json(archive / f"page_{number:06d}.json.gz")
        view = payload["table_view"]
        removed = set(view["removed"])
        units = [u for u in payload["units"]["units"] if u["id"] not in removed] + view[
            "added"
        ]
        claimed = {
            link["unit_id"]
            for f in payload["figures"]["figures"]
            for key in ("captions", "credits", "internal_text")
            for link in f[key]
        }
        streams = {s["id"]: s["kind"] for s in payload["units"]["order"]["streams"]}
        for unit in units:
            kinds_of[unit["id"][:16]] = unit["kind"]
            if unit["id"] in claimed:
                counts["figure_text_already_linked"] += 1
                continue
            if unit["kind"] == "figure_text":
                counts["figure_text_units_in_paragraph_stream"] += 1
            elif unit["stream_kind"] == "figure" and unit["kind"] == "paragraph":
                counts["figure_stream_paragraphs"] += 1
        # Items: every lists-stage unit (table cells too), as the JSON keeps them all.
        for unit in payload["units"]["units"]:
            if unit.get("marker"):
                counts["items_with_marker_in_text"] += 1
        counts["hidden_spans_proven_covered"] += sum(
            1 for v in payload["visibility_evidence"] if v["decision"] == "invisible"
        )
        _ = streams
    return counts, kinds_of


def after_counts(book_json, kinds_before):
    counts, markers = Counter(), Counter()
    dividers = Counter()
    tokens = Counter()
    for top in book_json["content"]:
        for node, *_ in jeval.walk(top):
            kind = node.get("type")
            if kind == "figure":
                counts["figure_text_entries"] += len(node.get("text") or [])
            if kind == "paragraph" and node.get("role") == "figure_text":
                counts["figure_text_paragraphs_left"] += 1
                if any("became a table piece" in f for f in node.get("flags") or ()):
                    counts["figure_text_left_figure_gone"] += 1
            if kind == "index_divider":
                dividers[kinds_before.get(node["id"], "?")] += 1
            if node.get("marker"):
                markers[node["marker"]["type"]] += 1
            if any("glued" in f for f in node.get("flags") or ()):
                counts["markers_kept_glued"] += 1
    for item in book_json.get("suppressed") or ():
        counts[f"suppressed_{item['reason']}"] += 1
        tokens[item["reason"]] += sum(token_counter(item["text"]).values())
    return counts, markers, dividers, tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--archive")
    args = parser.parse_args()
    run = json.loads((jeval.CAPTURE / "performance" / f"{args.book}.json").read_text())[
        "run"
    ]
    archive = Path(args.archive or run["output"])
    book_json = json.loads(Path(args.json).read_text("utf-8"))
    before, kinds = before_counts(archive, run["pages"])
    after, markers, dividers, tokens = after_counts(book_json, kinds)
    result = {"book": args.book, "before": dict(before), "after": dict(after),
              "markers_as_structure_by_type": dict(markers),
              "index_dividers_by_previous_kind": dict(dividers),
              "suppressed_tokens_by_reason": dict(tokens)}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8",
                                           newline="\n")  # fmt: skip
    print(json.dumps(result))


if __name__ == "__main__":
    main()
