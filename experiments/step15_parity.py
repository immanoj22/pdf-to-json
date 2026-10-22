"""Step 15 parity check: the final archives equal the development path, page by page.

- **Continuity**: ``link_book`` on inputs rebuilt from the Step 15 final archive
  (``step15_dev.inputs_of``) gives exactly the archive's continuity record: chains (kind,
  members, every break's lines, kind, source, skipped items and pages, repeated header
  rows, marks, join hyphen choice), candidates and dropped links.
- **Tables** (``--tables``): the Step 14b development pipeline (analysis, records, titles
  and notes, the TableFormer uses) plus the Step 15 steps (``records.title_checks``,
  ``captions.title_pieces``), on development evidence rebuilt from the Step 15 final caches
  (``step14b_bundles`` into ``.cache/step15/pages``), gives the archive's tables: lines,
  grid, cells, titles and notes, continuation marks, absorbed figures, review status.

Usage: python step15_parity.py [--book NAME] [--tables]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b
import step15_common as c15

FINAL = ROOT / "experiments/out/step15/final"


def _chain(chain):
    return (
        chain["kind"], tuple(chain["members"]),
        tuple((b["kind"], b["from_line_id"], b["to_line_id"], b["source"],
               tuple(b["skipped_ids"]), tuple(b["skipped_pages"]), b["repeated_header_rows"],
               tuple(m["position"] for m in b["marks"]), b["page_label"],
               ((b["join"] or {}).get("hyphen") or {}).get("choice"))
              for b in chain["breaks"]),
    )  # fmt: skip


def continuity(book):
    import step15_dev as dev

    from book_core.cache_store import read_json
    from book_core.continuity.cache import link_book

    run = common.read(FINAL / "performance" / f"{book}.json")["run"]
    archive = read_json(Path(run["output"]) / "book.json.gz")["continuity"]
    pages, headings, lists, paragraphs, total = dev.inputs_of(book, str(FINAL))
    found = link_book(pages, headings, lists, paragraphs, dev.vocabulary(book), total,
                      archive["source_sha256"])  # fmt: skip
    ours = sorted(_chain(c.model_dump(mode="json")) for c in found["chains"])
    theirs = sorted(_chain(c) for c in archive["chains"])
    differ = {
        "chains_only_dev": len(set(ours) - set(theirs)),
        "chains_only_archive": len(set(theirs) - set(ours)),
        "candidates": [len(found["candidates"]), len(archive["candidates"])],
        "dropped": [len(found["dropped_links"]), len(archive["dropped_links"])],
    }
    same = (ours == theirs and differ["candidates"][0] == differ["candidates"][1]
            and differ["dropped"][0] == differ["dropped"][1])  # fmt: skip
    return {"chains": len(theirs), "identical": same, **differ}


def _shape(t):
    t = t if isinstance(t, dict) else t.model_dump(mode="json")
    cells = {c["id"]: (c["row"], c["column"]) for c in t["cells"]}
    return (
        tuple(sorted(t["line_ids"])), len(t["rows"]), len(t["columns"]), t["header_rows"],
        tuple(sorted(
            (c["row"], c["column"], c["row_span"], c["column_span"], c["role"],
             tuple(sorted(cells[h] for h in c["header_cell_ids"])),
             tuple(i["kind"] for i in c["content"]))
            for c in t["cells"]
        )),
        tuple(t["title"]["line_ids"]) if t["title"] else None,
        tuple(tuple(n["line_ids"]) for n in t["notes"]),
        tuple(sorted(t["absorbed_figure_ids"])),
        bool(t["continues_to"]), bool(t["continues_from"]), t.get("review_status"),
    )  # fmt: skip


def tables(book):
    c14b.FINAL = FINAL
    c14b.PAGES = ROOT / ".cache/step15/pages"
    c14b._keys.cache_clear()
    c14b.navigation.cache_clear()
    import step14b_bundles
    import step14b_dev as dev

    from book_core.cache_store import read_json
    from book_core.tables import captions, opinion, records
    from book_core.tables.page import analyze
    from book_core.tables.view import unit_view

    step14b_bundles.build(book)
    pages, possible, cands, claims, contents, pieces = {}, {}, {}, {}, {}, {}
    for number, pg in c14b.pages(book):
        ev, built = pg["evidence"], pg["built"]
        accepted, refused = analyze(ev)
        found, maybe, _, _ = records.records(accepted, refused, ev, built.order, dev.DIGEST,
                                             number)  # fmt: skip
        pages[number], possible[number] = found, maybe
        cands[number] = captions.candidates(ev, found, unit_view(built.units, found)[0])
        claims[number] = captions.figure_claims(ev, found)
        pieces[number] = captions.piece_candidates(ev, found)
        contents[number] = ev.content
    linked, _ = records.link(pages, contents)
    linked, _ = captions.link(linked, cands, claims, dev.figure_labels(book))
    linked, _ = records.title_checks(linked)
    linked, _, _ = captions.title_pieces(linked, pieces)
    for number in sorted(linked):
        readings = dev.reader(book)(number, linked[number])
        out = []
        for table in linked[number]:
            update, _ = opinion.apply(table, *readings[table.id])
            out.append((captions._validated(table, update) if update else table).with_status())
        linked[number] = out
    run = common.read(FINAL / "performance" / f"{book}.json")["run"]
    root = Path(run["output"])
    differ = []
    for number in range(1, run["pages"] + 1):
        archived = read_json(root / f"page_{number:06d}.json.gz")["tables"]
        ours = sorted(_shape(t) for t in linked.get(number, []))
        theirs = sorted(_shape(t) for t in archived["tables"])
        maybe = sorted(tuple(sorted(t.line_ids)) for t in possible.get(number, []))
        theirs_maybe = sorted(tuple(sorted(t["line_ids"])) for t in archived["possible_tables"])
        if ours != theirs or maybe != theirs_maybe:
            differ.append({"page": number, "tables": [len(ours), len(theirs)]})
    return {"pages_checked": run["pages"], "differ": differ}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--tables", action="store_true")
    args = parser.parse_args()
    bad = Counter()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        row = {"continuity": continuity(name)}
        bad["continuity"] += not row["continuity"]["identical"]
        if args.tables:
            row["tables"] = tables(name)
            bad["tables"] += bool(row["tables"]["differ"])
        common.write(c15.OUT / "final" / "parity" / f"{name}.json", row)
        print(name, row["continuity"], row.get("tables", {}).get("differ", [])[:5], flush=True)
    sys.exit(1 if sum(bad.values()) else 0)
