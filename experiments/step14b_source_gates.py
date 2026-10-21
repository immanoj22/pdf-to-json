"""Step 14b source, ledger and final-archive gates: the Step 14a gates on the Step 14b runs.

As ``step14a_source_gates`` (30 sample pages 0 missing / 0 extra, book 1 ledger 495,751,
archive manifests and images, every line owned once by the final unit view and the text-
owning tables, span ranges covering split lines exactly once), with the Step 14b records:
a title or note inside a table region holds whole table lines outside every cell; a linked
title or note names a unit of the final view and exactly that unit's lines; unlinked
candidates name units of the final view; header references and cell content are validated
by the record model (header cells of the same table; content covering each cell once).
"""

# ruff: noqa: E402
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_source_gates as gates

from book_core.tables.models import PageTables

gates.RUN = ROOT / "experiments/out/step14b/final"
gates.BASELINE = ROOT / "experiments/out/step14b/before"
_tables_14a = gates.check_tables


def check_tables(payload, source, units):
    tables = PageTables.model_validate(payload["tables"])
    view = payload["table_view"]
    removed = set(view["removed"])
    final = {u.id: list(u.line_ids) for u in units.units if u.id not in removed}
    final |= {u["id"]: list(u["line_ids"]) for u in view["added"]}
    counts = Counter()
    inside = {}
    for table in tables.tables:
        whole = {lid for c in table.cells for lid in c.line_ids}
        for text in [table.title, *table.notes]:
            if text is None:
                continue
            counts[f"{text.role}s"] += 1
            if text.unit_id is None:
                assert set(text.line_ids) <= set(table.line_ids) - whole, "inside text lines"
                inside.setdefault(table.id, set()).update(text.line_ids)
                counts[f"{text.role}s_inside"] += 1
            else:
                assert final.get(text.unit_id) == list(text.line_ids), "linked unit lines"
        for text in table.unlinked_texts:
            assert text.unit_id is None or text.unit_id in final, "unlinked unit"
            counts["unlinked"] += 1
        counts["row_header_tables"] += table.row_header_columns > 0
        counts.update(f"role_{c.role}" for c in table.cells)
        counts.update(f"content_{i.kind}" for c in table.cells for i in c.content)
        counts["header_references"] += sum(len(c.header_cell_ids) for c in table.cells)
    if inside:
        # Lines of an inside title or note are no cell's: give them to one cell as whole
        # lines for the Step 14a span-coverage check, which they then pass trivially.
        payload = dict(payload)
        data = payload["tables"] = dict(payload["tables"])
        data["tables"] = []
        for table in tables.tables:
            row = table.model_dump(mode="json")
            if table.id in inside:
                extra = sorted(inside[table.id])
                row["cells"][0]["line_ids"] = row["cells"][0]["line_ids"] + extra
                row["cells"][0]["content"] = row["cells"][0]["content"] + [
                    {"kind": "text", "unit_id": None, "line_ids": extra, "span_refs": [],
                     "figure_id": None}
                ]  # fmt: skip
            data["tables"].append(row)
    counts.update(_tables_14a(payload, source, units))
    return counts


gates.check_tables = check_tables

if __name__ == "__main__":
    gates.main()
