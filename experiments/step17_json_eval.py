"""Step 17 Part 7: the earlier evaluators run on the book JSON alone (plus the shared token
view of the source), compared with the Step 15/16 numbers.

Token view: every retained PDF token ``(page, ordinal)`` and its layout line, as all earlier
evaluators use it (``step14a_bundles.token_owners``: span store and layout lines only).

From the JSON:

- **owners**: each content text unit (paragraph, heading, item or entry, caption, footnote,
  divider; figure texts; table cell units) owns the tokens of the layout lines in its
  ``refs.lines``; a table cell's text fragments own their lines and span ranges (cell id,
  the Step 14b convention); suppressed and furniture tokens have no owner;
- **paragraphs** (``evaluation.paragraphs.paragraph_scores``): per page (column links
  joined) and chained (every link joined), as Step 15 (``step15_effect``);
- **lists** (``evaluation.lists``): items, definitions, index, bibliography, cross-page
  entries, with kinds, lists, levels, terms and links from the JSON;
- **reading order** (``evaluation.reading_order`` through the derived harness): the main
  flow is the page's top-level text units in JSON order; boxes, figures, tables, footnotes and
  credits are floats anchored after the main tokens read before them;
- **tables** (books with multi-page reference tables): the Step 15 joined-table TEDS from the
  JSON's table grids and their ``continues_from`` links.

Token ownership is also compared with the Step 16 final archive's (``step15_common``):
a token whose owner differs is counted with its cause (the unit types on both sides).

Usage: python step17_json_eval.py --book NAME --json PATH
"""

import argparse
import itertools
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.evaluation import table_scoring
from book_core.evaluation.paragraphs import paragraph_scores
from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.model.spans import ExtractedPage

import step14a_common as common
import step14b_common  # noqa: F401
import step14b_dev as tables_dev
import step15_common as c15
from step14a_bundles import token_owners

OUT = ROOT / "experiments/out/step17/json_eval"
CAPTURE = ROOT / "experiments/out/step16/final"
FLOAT_TYPES = {"box", "figure", "table", "footnote"}
KIND_OF = {"glossary_entry": "definition_entry"}


def walk(node, parent=None, list_node=None, top=None):
    """(node, parent node, enclosing list node, top-level node) depth first; nodes inside a
    table cell carry the cell and table ids (``_cell``, ``_table``)."""
    yield node, parent, list_node, top
    here = node if node.get("type") == "list" else list_node
    inherited = {k: node[k] for k in ("_cell", "_table") if k in node}
    for key in ("items", "children"):
        for child in node.get(key) or ():
            yield from walk({**child, **inherited}, node, here, top or node)
    for cell in node.get("cells") or ():
        for item in cell["content"]:
            yield from walk({**item, "_cell": cell["id"], "_table": node["id"]}, node, None,
                            top or node)  # fmt: skip
    for key in ("captions", "credits", "text"):
        value = node.get(key)
        if isinstance(value, list) and node.get("type") == "figure":
            for item in value:
                yield from walk(
                    {**item, "type": "figure_text"}, node, None, top or node
                )
    if node.get("type") == "table":
        for key in ("title", "notes"):
            value = node.get(key)
            for item in [value] if isinstance(value, dict) else value or []:
                yield from walk({**item, "type": "table_text", "_table_text": node["id"]}, node,
                                None, top or node)  # fmt: skip


def json_view(book_json):
    """Per page: {line prefix: owner}, {span prefix: [owner]} and unit records."""
    lines, spans, units = defaultdict(dict), defaultdict(lambda: defaultdict(list)), {}
    for top in book_json["content"]:
        for node, _, list_node, root in walk(top):
            kind = node.get("type")
            if kind in {"page_marker", "list", "box", "figure", "table", "equation"}:
                continue
            page = node["pages"][0] if "pages" in node else (root or top)["pages"][0]
            owner = node.get("id") or node.get("_cell")
            if kind == "text":
                owner = node["_cell"]
            units[owner] = {"type": kind, "page": page, "node": node, "list": list_node,
                            "top": root or top}  # fmt: skip
            for prefix in node["refs"]["lines"]:
                lines[page].setdefault(prefix, owner)
            for ref in node["refs"].get("spans", []):
                spans[page][ref["span"]].append(owner)
    return lines, spans, units


def owners_of(book, json_lines, json_spans, pages):
    """{(page, ordinal): owner} of the JSON, and the token view per page."""
    owner, views = {}, {}
    for number in range(1, pages + 1):
        page = common.text_page(book, number)
        layout = common.layout_page(book, number)
        tokens = token_owners(page, layout)
        views[number] = tokens
        for ordinal, (lid, span_ids) in enumerate(tokens):
            found = json_lines[number].get(lid[:16]) if lid else None
            if found is None:
                for sid in span_ids:
                    cand = json_spans[number].get(sid[:16])
                    if cand:
                        found = cand[0]
                        break
            if found is not None:
                owner[(number, ordinal)] = found
    return owner, views


def chains(book_json, kinds):
    """{unit: root} over continues links (``kinds``: page and/or column)."""
    parent = {}

    def root(x):
        while x in parent:
            x = parent[x]
        return x

    for top in book_json["content"]:
        for node, *_ in walk(top):
            link = node.get("continues_to")
            if link and link["kind"] in kinds and node.get("type") != "list":
                a, b = root(node["id"]), root(link["unit"])
                if a != b:
                    parent[b] = a
    return root


def paragraphs(book, owner, book_json):
    gold = common.derived_gold(book)
    per_page = chains(book_json, {"column"})
    chained = chains(book_json, {"column", "page"})
    return {
        "per_page": paragraph_scores(gold, {t: per_page(u) for t, u in owner.items()}),
        "chained": paragraph_scores(gold, {t: chained(u) for t, u in owner.items()}),
    }


def lists(book, owner, units, book_json, views):
    from book_core.evaluation.lists import (
        Ours,
        bibliography_scores,
        cross_page_scores,
        definition_scores,
        index_scores,
        list_item_scores,
    )

    gold = common.derived_gold(book)
    ours = Ours(unit_of=dict(owner))
    root = chains(book_json, {"page", "column"})
    for uid, unit in units.items():
        kind = unit["type"]
        ours.kind_of[uid] = KIND_OF.get(kind, kind)
        if unit["list"] is not None:
            ours.list_of[uid] = unit["list"]["list_id"]
            # Index entries can have different depths within a single flat list.
            ours.level_of[uid] = (unit["node"]["level"] if "level" in unit["node"]
                                 else unit["list"]["level"])
        ours.chain_of[uid] = root(uid)
        link = unit["node"].get("continues_to")
        if link:
            ours.links.append((uid, link["unit"]))
    # Terms: the item's tokens in order are its marker's then its text's.
    tokens_of = defaultdict(list)
    for key, uid in sorted(owner.items()):
        tokens_of[uid].append(key)
    for uid, unit in units.items():
        node = unit["node"]
        if not node.get("term"):
            continue
        text = node["content"]["text"]
        marker = node["marker"]["text"] if node.get("marker") else ""
        before = len(TOKEN_PATTERN.findall(marker))
        start, end = node["term"]
        first = before + len(TOKEN_PATTERN.findall(text[:start]))
        last = before + len(TOKEN_PATTERN.findall(text[:end]))
        ours.terms.update(tokens_of[uid][first:last])
    index_pages = [p for p, k in common.navigation(book).items() if k == "index"]
    return {
        "list_items": list_item_scores(gold, ours, index_pages),
        "definitions": definition_scores(gold, ours),
        "index": index_scores(gold, ours, index_pages),
        "bibliography": bibliography_scores(gold, ours),
        "cross_page_entries": cross_page_scores(gold, ours),
    }


def reading_order(book, owner, book_json, views):
    from book_core.evaluation.derived_harness import evaluate
    from book_core.evaluation.reading_order import PageOrder, ReadingOrderOutput

    gold = common.derived_gold(book)
    digests = {row["page"]: row["token_digest"] for row in gold.pages}
    by_page = defaultdict(list)
    for top in book_json["content"]:
        by_page[top["pages"][0]].append(top)
    pages, owners = {}, {}
    tokens_of = defaultdict(list)
    for key, uid in owner.items():
        tokens_of[uid].append(key[1])
    for number, tokens in views.items():
        main, streams, stream_of = [], {}, {}
        for top in by_page.get(number, []):
            members = [n.get("id") or n.get("_cell") for n, *_ in walk(top)]
            ordinals = sorted({o for m in members if m for o in tokens_of.get(m, [])})
            if not ordinals:
                continue
            is_float = top["type"] in FLOAT_TYPES or (
                top["type"] == "paragraph" and top.get("role") == "credit")  # fmt: skip
            if is_float:
                kind = {"box": top.get("box_kind", "sidebar"), "footnote": "note",
                        "paragraph": "credit"}.get(top["type"], top["type"])  # fmt: skip
                streams[top["id"]] = {"kind": kind, "tokens": ordinals,
                                      "anchor": len(main)}  # fmt: skip
                for o in ordinals:
                    stream_of[o] = top["id"]
            else:
                main.extend(ordinals)
                for o in ordinals:
                    stream_of[o] = "main"
        streams["main"] = {"kind": "main", "tokens": list(main), "anchor": None}
        pages[number] = PageOrder(main=main, streams=streams, stream_of=stream_of)
        owners[number] = [stream_of.get(i) for i in range(len(tokens))]
    output = ReadingOrderOutput("json", book, owners, digests, pages)
    detail = evaluate([gold], {book: output}, include_holdout=True)["books"][book]
    order = detail["reading_order"]
    return {
        "main_flow": order["main_flow"]["pairwise_agreement_pooled"],
        "kendall_tau": order["main_flow"]["kendall_tau_pooled"],
        "float_anchors": order["float_anchors"]["accuracy"],
        "within_floats": order["within_floats"]["pairwise_agreement"],
    }


def order_agreement(book, owner, book_json, archive_dir):
    """Pairwise agreement between the JSON's main-flow token order and the lists-stage main
    stream of the archive, over tokens in both (1.0: the JSON keeps the archive's order)."""
    from book_core.evaluation.reading_order import page_order
    from book_core.reading_order.models import PageReadingOrder

    rank_json = {}
    position = 0
    for top in book_json["content"]:
        if top["type"] in FLOAT_TYPES or (top["type"] == "paragraph"
                                           and top.get("role") == "credit"):  # fmt: skip
            continue
        rank_json[top["id"]] = position
        position += 1
    tokens_of = defaultdict(list)
    for key, uid in owner.items():
        tokens_of[uid].append(key)
    unit_rank = {}
    for top in book_json["content"]:
        if top["id"] not in rank_json:
            continue
        for node, *_ in walk(top):
            uid = node.get("id") or node.get("_cell")
            if uid:
                unit_rank[uid] = rank_json[top["id"]]
    agree = total = 0
    for number in sorted({p for p, _ in owner}):
        payload = read_json(archive_dir / f"page_{number:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        order = PageReadingOrder.model_validate(payload["units"]["order"])
        view, _ = page_order(page, common.layout_page(book, number), order)
        ranks = [unit_rank[owner[(number, t)]] for t in view.main
                 if (number, t) in owner and owner[(number, t)] in unit_rank]  # fmt: skip
        # Compare consecutive distinct units (adjacent pairs) for a linear-time measure.
        runs = [r for i, r in enumerate(ranks) if i == 0 or r != ranks[i - 1]]
        for a, b in itertools.pairwise(runs):
            total += 1
            agree += a < b
    return {"adjacent_main_unit_pairs": total, "in_json_order": agree,
            "agreement": round(agree / total, 6) if total else None}  # fmt: skip


def joined_tables(book, book_json, views, archive):
    """The Step 15 joined-table TEDS from the JSON's grids."""
    import step15_joined_tables as jt

    gold = [t for t in common.gold_tables(book) if t["located"] and len(t["pages"]) > 1
            and not t["problems"]]  # fmt: skip
    if not gold:
        return None
    full_lines, full_spans, texts = {}, {}, {}
    grids, following = {}, {}
    tables = []
    for top in book_json["content"]:
        for node, *_ in walk(top):
            if node.get("type") == "table":
                tables.append(node)
    for table in tables:
        number = table["pages"][0]
        if number not in full_lines:
            payload = read_json(archive / f"page_{number:06d}.json.gz")
            full_lines[number] = {lid[:16]: lid for lid in payload["line_spans"]}
            spans = payload["source"]["store"]["spans"]
            full_spans[number] = {sid[:16]: sid for sid in spans}
            texts[number] = {sid: s["raw_text"] for sid, s in spans.items()}
        cells = []
        for cell in table["cells"]:
            line_ids, span_refs = [], []
            for item, *_ in (x for top in cell["content"] for x in walk(top)):
                # A figure in a cell keeps its own embedded text (not cell text, as Step 15).
                if "refs" not in item or item.get("type") == "figure_text":
                    continue
                for prefix in item["refs"]["lines"]:
                    if prefix in full_lines[number]:
                        line_ids.append(full_lines[number][prefix])
                for ref in item["refs"].get("spans", []):
                    span_refs.append(
                        SimpleNamespace(
                            span_id=full_spans[number][ref["span"]],
                            start=ref["start"],
                            end=ref["end"],
                        )
                    )
            cells.append(
                SimpleNamespace(
                    id=cell["id"],
                    row=cell["row"],
                    column=cell["column"],
                    row_span=cell["row_span"],
                    column_span=cell["column_span"],
                    header=cell["role"] == "column_header",
                    role=cell["role"],
                    header_cell_ids=cell["headers"],
                    line_ids=line_ids,
                    span_refs=span_refs,
                )
            )
        record = SimpleNamespace(cells=cells, header_rows=table["header_rows"])
        grids[table["id"]] = tables_dev.record_grid(number, record, views[number],
                                                    texts[number], None)  # fmt: skip
        if table.get("continues_to"):
            following[table["id"]] = table["continues_to"]["unit"]
    starts = set(following) - set(following.values())
    chain_of, repeated = {}, {}
    for table in tables:
        if table.get("continuation"):
            repeated[table["id"]] = table["continuation"]["repeated_header_rows"]
    for start in starts:
        members, step = [start], start
        while step in following:
            step = following[step]
            members.append(step)
        for m in members:
            chain_of[m] = members
    rows = []
    for t in gold:
        reference = jt.gold_grid(t)
        tokens = {tok for cell in reference["cells"] for tok in cell[5]}
        votes = Counter()
        for tid, grid in grids.items():
            held = sum(len(tokens & cell[5]) for cell in grid["cells"])
            if held:
                votes[tuple(chain_of.get(tid, [tid]))] += held
        if not votes:
            rows.append({"table": t["table"], "teds": None})
            continue
        members = list(votes.most_common(1)[0][0])
        parts = [grids[m] for m in members]
        joined = jt.stacked(parts, [0] + [repeated.get(m, 0) for m in members[1:]])
        pages = {
            next(tb["pages"][0] for tb in tables if tb["id"] == m) for m in members
        }
        rows.append(
            {
                "table": t["table"],
                "whole": pages >= set(t["pages"]),
                "teds": round(table_scoring.teds(reference, joined), 4),
                "teds_full": round(
                    table_scoring.teds(reference, joined, content=True), 4
                ),
            }
        )
    scored = [r for r in rows if r["teds"] is not None]
    whole = [r for r in scored if r["whole"]]
    mean = lambda key, xs: round(sum(r[key] for r in xs) / len(xs), 4) if xs else None
    return {"reference_multi_page_tables": len(gold), "scored": len(scored),
            "teds_joined": mean("teds", scored), "teds_full_joined": mean("teds_full", scored),
            "teds_joined_whole_only": mean("teds", whole)}  # fmt: skip


def ownership_against_archive(book, owner, units):
    """Tokens whose JSON owner differs from the Step 16 archive's final-view owner (a table
    cell's tokens compare at table level, as the archive view names the table)."""
    views, _ = c15.book_view(book, str(CAPTURE))
    table_of = {
        uid: u["node"]["_table"] for uid, u in units.items() if u["node"].get("_table")
    }
    text_of = {uid: u["node"]["_table_text"] for uid, u in units.items()
               if u["node"].get("_table_text")}  # fmt: skip
    owner = {k: table_of.get(v, v) for k, v in owner.items()}
    diff, total = Counter(), 0
    examples = []
    for number, view in views.items():
        for ordinal, archived in view.owner.items():
            total += 1
            ours = owner.get((number, ordinal))
            if ours == archived[:16] or text_of.get(ours) == archived[:16]:
                continue  # a title or note inside a table region: the archive names the table
            cause = (
                view.kind.get(archived, "?"),
                "none" if ours is None else "other unit",
            )
            diff[cause] += 1
            if len(examples) < 20:
                examples.append([number, ordinal, archived[:16], ours])
        for key, ours in ((k, v) for k, v in owner.items() if k[0] == number):
            if key[1] not in view.owner:
                diff[("not owned in the archive", "owned in the JSON")] += 1
    return {"archive_owned_tokens": total, "differences": {f"{a} -> {b}": n
                                                           for (a, b), n in diff.items()},
            "examples": examples}  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--archive", help="final archive (default: Step 16 final)")
    args = parser.parse_args()
    book_json = json.loads(Path(args.json).read_text("utf-8"))
    run = common.read(CAPTURE / "performance" / f"{args.book}.json")["run"]
    archive = Path(args.archive or run["output"])
    lines, spans, units = json_view(book_json)
    owner, views = owners_of(args.book, lines, spans, run["pages"])
    result = {"book": args.book, "owned_tokens": len(owner),
              "ownership_vs_step16": ownership_against_archive(args.book, owner, units)}  # fmt: skip
    if args.book != common.MATH_BOOK:
        result["paragraphs"] = paragraphs(args.book, owner, book_json)
        result["lists"] = lists(args.book, owner, units, book_json, views)
        result["reading_order"] = reading_order(args.book, owner, book_json, views)
    result["main_flow_order_vs_archive"] = order_agreement(
        args.book, owner, book_json, archive
    )
    result["joined_tables"] = joined_tables(args.book, book_json, views, archive)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(json.dumps(result, indent=1, default=str) + "\n",
                                           "utf-8", newline="\n")  # fmt: skip
    summary = {
        k: v
        for k, v in result.items()
        if k in {"owned_tokens", "joined_tables", "main_flow_order_vs_archive"}
    }
    summary["ownership_differences"] = result["ownership_vs_step16"]["differences"]
    if "paragraphs" in result:
        summary["paragraphs"] = {k: (v["boundary_f1"], v["exact_unit_match"])
                                 for k, v in result["paragraphs"].items()}  # fmt: skip
        summary["reading_order"] = result["reading_order"]
    print(json.dumps(summary, default=str))


if __name__ == "__main__":
    main()
