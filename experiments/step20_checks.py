"""Step 20 machine checks on a run's publication (any book; the only measures for books
without a reference): the checks of the owner's reviews.

* Interleaving, against the PDF's own text order (independent of the layout code): a visual
  line is *joined across* when its spans come from native lines that are not consecutive in
  the page's native line order (blank native lines skipped). A paragraph-like node is
  *interleaved* when one of its lines is joined across; a body page is interleaved when one of
  its paragraph-like nodes is. Body text share = characters of interleaved nodes / characters
  of all paragraph-like nodes on body pages.
* Line adjacency: consecutive lines of one node on one page whose native ranks follow on
  (next first rank = previous last rank + 1).
* Heading census: headings by role and level; paragraphs typed display_title or
  heading_candidate.
* Zone map: runs of pages per zone.
* TOC entries: entries with text, with a target page, with target units.

Usage: python step20_checks.py --book iap_mec --tag before
"""

import argparse
import json
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20"
TEXT_NODES = {"paragraph", "list_item", "caption", "footnote", "definition_entry", "heading"}


def nodes(book_json):
    """Every node in book order, nested ones included."""
    pending = list(reversed(book_json["content"]))
    while pending:
        node = pending.pop()
        yield node
        for key in ("children", "items", "content"):
            value = node.get(key)
            if isinstance(value, list):
                pending.extend(reversed([v for v in value if isinstance(v, dict) and "type" in v]))


def page_lines(archive, number):
    """{line id prefix: sorted native ranks} for one archive page."""
    from book_core.cache_store import read_json

    data = read_json(archive / f"page_{number:06d}.json.gz")
    store = data["source"]["store"]
    rank, position = {}, 0
    for line in store["lines"]:
        texts = [store["spans"][sid]["raw_text"] for sid in line["span_ids"]]
        if not "".join(texts).strip():
            continue
        for sid in line["span_ids"]:
            rank[sid] = position
        position += 1
    return {
        lid[:16]: sorted({rank[sid] for sid in spans if sid in rank})
        for lid, spans in data["line_spans"].items()
    }


def check(book, tag):
    record = json.loads((OUT / tag / "performance" / f"{book}.json").read_text("utf-8"))
    book_json = json.loads((Path(record["run"]["book_json"]) / "book.json").read_text("utf-8"))
    archive = Path(record["run"]["output"])
    zone = {p["index"]: p["zone"] for p in book_json["pages"]}
    ranks = {}
    for number in zone:
        for lid, found in page_lines(archive, number).items():
            ranks[lid] = (number, found)
    joined = {lid for lid, (_, r) in ranks.items() if any(b - a > 1 for a, b in pairwise(r))}
    body_pages, interleaved_pages = set(), Counter()
    chars, interleaved_chars, pairs, adjacent = 0, 0, 0, 0
    census, examples = Counter(), []
    for node in nodes(book_json):
        kind, role = node["type"], node.get("role")
        if kind == "heading":
            census[f"heading {role} level {node.get('level')}"] += 1
        elif role in {"display_title", "heading_candidate"}:
            census[f"paragraph {role}"] += 1
        lines = [lid for lid in node.get("refs", {}).get("lines", []) if lid in ranks]
        if kind not in TEXT_NODES or kind == "heading" or not lines:
            continue
        pages = {ranks[lid][0] for lid in lines}
        if not any(zone[p] == "body" for p in pages):
            continue
        size = len((node.get("content") or {}).get("text") or "")
        chars += size
        body_pages.update(p for p in pages if zone[p] == "body")
        crossing = [lid for lid in lines if lid in joined]
        if crossing:
            interleaved_chars += size
            for p in {ranks[lid][0] for lid in crossing}:
                interleaved_pages[p] += 1
            if len(examples) < 40:
                examples.append({"node": node["id"], "page": ranks[crossing[0]][0],
                                 "text": (node.get("content") or {}).get("text", "")[:120]})  # fmt: skip
        for a, b in pairwise(lines):
            (pa, ra), (pb, rb) = ranks[a], ranks[b]
            if pa == pb and ra and rb:
                pairs += 1
                adjacent += rb[0] == ra[-1] + 1
    runs = []
    for number in sorted(zone):
        if runs and runs[-1][0] == zone[number] and runs[-1][2] == number - 1:
            runs[-1][2] = number
        else:
            runs.append([zone[number], number, number])
    toc = book_json["navigation"]["toc"]
    result = {
        "book": book,
        "tag": tag,
        "interleaving": {
            "lines": len(ranks),
            "lines_joined_across": len(joined),
            "body_pages_with_text": len(body_pages),
            "body_pages_interleaved": len(interleaved_pages),
            "body_text_chars": chars,
            "interleaved_chars": interleaved_chars,
            "interleaved_share": round(interleaved_chars / chars, 4) if chars else None,
            "interleaved_pages": sorted(interleaved_pages),
            "examples": examples,
        },
        "line_adjacency": {
            "pairs": pairs,
            "adjacent": adjacent,
            "share": round(adjacent / pairs, 4) if pairs else None,
        },
        "heading_census": dict(sorted(census.items())),
        "zones": {"pages": dict(Counter(zone.values())), "runs": runs},
        "toc": {
            "entries": len(toc),
            "with_text": sum(1 for e in toc if e.get("text")),
            "with_entry_unit": sum(1 for e in toc if e.get("entry")),
            "flagged": sum(1 for e in toc if e.get("flags")),
            "with_target_page": sum(1 for e in toc if e.get("target_page")),
            "with_target_units": sum(1 for e in toc if e.get("target_units")),
        },
    }
    target = OUT / tag / "checks" / f"{book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8")
    brief = {k: v for k, v in result["interleaving"].items() if k not in {"examples", "interleaved_pages"}}  # fmt: skip
    print(book, json.dumps(brief), json.dumps(result["line_adjacency"]), json.dumps(result["toc"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    check(args.book, args.tag)


if __name__ == "__main__":
    main()
