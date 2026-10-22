"""Step 15 source, ledger and final-archive gates: the Step 14b gates on the Step 15 runs.

As ``step14b_source_gates`` (30 sample pages 0 missing / 0 extra, book 1 ledger 495,751,
archive manifests and images, every line owned once by the final unit view and the
text-owning tables, titles and notes), with the Step 15 changes:

- the archive's units carry the continuity stage's links, so the identity check against
  the lists-stage pages first restores the lists-stage links (the archive's own record of
  them, ``lists.page_links``); everything else of the units must be identical;
- continuity: every unit's ``continues_from`` / ``continues_to`` (units and table-view
  parts) equals the continuity record's links; every break of the page names members of
  the final view (or text-owning tables) and their last / first lines; a column break stays
  on its page; table breaks name the tables' continuation marks consistently.
"""

# ruff: noqa: E402
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_source_gates as gates
import step14b_source_gates as gates14b

from book_core.cache_store import read_json
from book_core.continuity.models import BookContinuity
from book_core.lists.models import PageLists

gates.RUN = ROOT / "experiments/out/step15/final"
gates.BASELINE = ROOT / "experiments/out/step15/before"
_tables_14b = gates14b.check_tables
LISTS_LINKS = {}  # source sha -> {page: ({from unit: to unit}, {to unit: from unit})}
RECORDS = {}  # source sha -> BookContinuity


def _load(book):
    run = gates.read(gates.RUN / f"performance/{book}.json")["run"]
    archive = read_json(Path(run["output"]) / "book.json.gz")
    sha = archive["source_sha256"]
    links = {}
    for link in archive["lists"]["page_links"]:
        links.setdefault(link["from_page"], ({}, {}))[0][link["from_unit_id"]] = link["to_unit_id"]
        links.setdefault(link["to_page"], ({}, {}))[1][link["to_unit_id"]] = link["from_unit_id"]
    LISTS_LINKS[sha] = links
    RECORDS[sha] = BookContinuity.model_validate(archive["continuity"])


class ListsView:
    """``PageLists`` of the archive with the lists-stage links restored (identity check)."""

    @staticmethod
    def model_validate(data):
        page = data["page"]
        sha = data["source_sha256"]
        to, came = LISTS_LINKS.get(sha, {}).get(page, ({}, {}))
        units = [{**u, "continues_to": to.get(u["id"]), "continues_from": came.get(u["id"])}
                 for u in data["units"]]  # fmt: skip
        return PageLists.model_validate({**data, "units": units})


def check_tables(payload, source, units):
    counts = Counter(_tables_14b(payload, source, units))
    record = RECORDS[source.source_sha256]
    number = source.geometry.page
    links = record.links(number)
    view = payload["table_view"]
    removed = set(view["removed"])
    final = {u["id"]: u for u in payload["units"]["units"] if u["id"] not in removed}
    final |= {u["id"]: u for u in view["added"]}
    for uid, unit in final.items():
        came, to = links.get(uid, (None, None))
        assert (unit["continues_from"], unit["continues_to"]) == (came, to), "unit links"
    tables = {t["id"]: t for t in payload["tables"]["tables"]}
    for brk in payload["continuity"]:
        for side, page_of, member, line in (("from", brk["from_page"], brk["from_id"],
                                             brk["from_line_id"]),
                                            ("to", brk["to_page"], brk["to_id"],
                                             brk["to_line_id"])):  # fmt: skip
            if page_of != number:
                continue
            if member in tables:
                assert line in tables[member]["line_ids"], "table break line"
                counts["table_break_sides"] += 1
                continue
            assert member in final, f"break {side} member in the final view"
            lines = final[member]["line_ids"]
            assert line == (lines[-1] if side == "from" else lines[0]), "break line"
            counts["unit_break_sides"] += 1
        if brk["kind"] == "column":
            assert brk["from_page"] == brk["to_page"] == number
            counts["column_breaks"] += 1
    counts["breaks_on_page"] += len(payload["continuity"])
    return counts


gates.PageLists = ListsView
gates.check_tables = check_tables

if __name__ == "__main__":
    for name in ("spanish_us_history", "immigrant_children", "art_therapy_index",
                 "medical_anatomy", "statistics"):  # fmt: skip
        _load(name)
    gates.main()
