"""Step 14b parity check: the final archive's tables equal the development pipeline's.

Run after the final runs, with the development evidence rebuilt from the final caches
(``step14b_bundles``; ``step14b_common`` follows the Step 14b final capture). The dev
pipeline (``step14b_dev.pipeline``: analysis, records, title/note links, the TableFormer
uses) is compared page by page with the tables of the run's final archive: line sets, grid
shape, header rows, cells (position, spans, role, header references, content kinds), title
and notes (their lines), possible tables (line sets). Any difference is listed.

Usage: python step14b_parity.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b
import step14b_dev as dev

from book_core.cache_store import read_json


def _shape(table):
    """A comparable summary of one table record (dict from the archive or a model)."""
    t = table if isinstance(table, dict) else table.model_dump(mode="json")
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
    )  # fmt: skip


def check(book):
    titled, possible, *_ = dev.pipeline(book)
    run = common.read(c14b.FINAL / "performance" / f"{book}.json")["run"]
    root = Path(run["output"])
    differ = []
    pages = set(titled) | set(possible)
    for number in range(1, run["pages"] + 1):
        archived = read_json(root / f"page_{number:06d}.json.gz")["tables"]
        ours = sorted(_shape(t) for t in titled.get(number, []))
        theirs = sorted(_shape(t) for t in archived["tables"])
        maybe = sorted(tuple(sorted(t.line_ids)) for t in possible.get(number, []))
        archived_maybe = sorted(tuple(sorted(t["line_ids"])) for t in archived["possible_tables"])
        if number not in pages and (theirs or archived_maybe):
            differ.append({"page": number, "why": "archive has tables on a page without evidence"})
        elif ours != theirs or maybe != archived_maybe:
            differ.append({"page": number, "tables": [len(ours), len(theirs)],
                           "possible": [len(maybe), len(archived_maybe)]})  # fmt: skip
    common.write(c14b.OUT / "final" / "parity" / f"{book}.json",
                 {"pages_checked": run["pages"], "differ": differ})  # fmt: skip
    print(book, "pages", run["pages"], "differ", differ[:10], flush=True)
    return differ


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    bad = [d for b in ([args.book] if args.book else common.BOOK_ORDER) for d in check(b)]
    sys.exit(1 if bad else 0)
