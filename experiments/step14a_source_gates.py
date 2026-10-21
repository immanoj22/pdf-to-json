"""Step 14a source, ledger and final-archive gates (the Step 13c gates plus table records).

Added for 14a: the final unit view (``table_view``) and the text-owning tables together
hold every line of the page exactly once; a table line that is not a whole line of one cell
has its spans covered by cell span ranges exactly once (every character); possible tables
own nothing (their lines stay in units); every cell's equation unit is an equation unit of
the page and every cell figure a final figure; absorbed table pieces are not final figures
and their images are not archived; the archive images are the final figures' images plus
the equation fallbacks. Text, units (lists stage) and the ledger are checked as in Step 13c.
"""

# ruff: noqa: E402
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step7_gates
import step13b_source_gates as gates13b
import step13c_source_gates as gates13c
from reference_paths import reference_path
from step4b_run import retained_counter
from step11c_identity import digest
from step13_books import BOOKS

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.lists.models import PageLists
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session
from book_core.tables.models import PageTables

RUN = ROOT / "experiments/out/step14a/final"
BASELINE = ROOT / "experiments/out/step14a/before"
MATH_BOOK = "statistics"


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def write(name, value):
    (RUN / name).write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8", newline="\n")


def check_tables(payload, source, units):
    """Counts of one page; asserts ownership, span coverage and references."""
    tables = PageTables.model_validate(payload["tables"])
    view = payload["table_view"]
    removed = set(view["removed"])
    final = [u for u in units.units if u.id not in removed] + view["added"]
    final_lines = [lid for u in final for lid in (u.line_ids if hasattr(u, "line_ids")
                   else u["line_ids"])]  # fmt: skip
    table_lines = [lid for t in tables.tables for lid in t.line_ids]
    owned = Counter(final_lines + table_lines)
    assert set(owned) == set(payload["line_spans"]), "a line without an owner"
    assert set(owned.values()) == {1} or not owned, "a line owned twice"
    assert removed <= {u.id for u in units.units}
    for possible in tables.possible_tables:
        assert not possible.owns_text and not set(possible.line_ids) & set(table_lines)
    spans = source.store.spans
    equation_units = {u["id"] for u in payload["equations"]["units"]}
    figure_ids = {f["id"] for f in payload["figures"]["figures"]}
    counts = Counter()
    for table in tables.tables:
        counts["tables"] += 1
        counts["cells"] += len(table.cells)
        counts["rotated"] += bool(table.rotation)
        counts["continued"] += table.continues_to is not None
        whole = [lid for c in table.cells for lid in c.line_ids]
        for lid in set(table.line_ids) - set(whole):
            covered = Counter()
            for cell in table.cells:
                for ref in cell.span_refs:
                    if ref.span_id in payload["line_spans"][lid]:
                        start = ref.start or 0
                        end = ref.end if ref.end is not None else len(spans[ref.span_id].raw_text)
                        covered.update((ref.span_id, k) for k in range(start, end))
            expected = {
                (sid, k)
                for sid in payload["line_spans"][lid]
                for k in range(len(spans[sid].raw_text))
            }
            assert set(covered) == expected and set(covered.values()) == {1}, "span coverage"
            counts["lines_split_over_cells"] += 1
        for cell in table.cells:
            assert set(cell.equation_unit_ids) <= equation_units
            assert set(cell.figure_ids) <= figure_ids
            counts["cell_equation_units"] += len(cell.equation_unit_ids)
        assert not set(table.absorbed_figure_ids) & figure_ids, "an absorbed piece is a figure"
        counts["absorbed_figures"] += len(table.absorbed_figure_ids)
    counts["possible_tables"] += len(tables.possible_tables)
    counts["lines_in_tables"] += len(table_lines)
    return counts


def main():
    sample = read(gates13c.SAMPLE)
    math_run = read(RUN / f"performance/{MATH_BOOK}.json")["run"]
    sample["pages"][MATH_BOOK] = gates13b.math_sample(math_run["pages"])
    rows, final_tokens, archives = [], {}, {}
    for book, numbers in sample["pages"].items():
        run = read(RUN / f"performance/{book}.json")["run"]
        output = Path(run["output"])
        math = book == MATH_BOOK
        identity = None if math else read(RUN / f"after/{book}.json")
        baseline = None if math else read(BASELINE / f"{book}.json")
        manifest = read_json(output / "manifest.json.gz")
        assert manifest["complete"] and manifest["keys"] == run["cache_keys"]
        pages = {f"page_{n:06d}.json.gz" for n in range(1, run["pages"] + 1)}
        images = {name for name in manifest["files"] if name.startswith("images/")}
        assert set(manifest["files"]) == {"book.json.gz", *pages, *images}
        total = 0
        counts = {k: Counter() for k in ("figures", "equations", "mathml", "tables")}
        expected_images, equation_images = set(), []
        for name, checksum in manifest["files"].items():
            path = output / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
            if name.startswith("images/"):
                continue
            payload = read_json(path)
            if name == "book.json.gz":
                if not math:
                    assert digest(payload["structure"]) == identity["books"]["structure"]
                    assert digest(payload["lists"]) == identity["books"]["lists"]
                expected_images |= {f"images/{n}" for n in payload["mathml"]["images"]}
                continue
            source = ExtractedPage.model_validate(payload["source"])
            number = str(source.geometry.page)
            units = PageLists.model_validate(payload["units"])
            if not math:
                text_digest = digest(source.model_dump(mode="json"))
                assert text_digest == identity["pages"][number]["native_text"]
                assert text_digest == baseline["pages"][number]["native_text"]
                assert digest(units.model_dump(mode="json")) == identity["pages"][number]["lists"]
            lines = Counter(line for unit in units.units for line in unit.line_ids)
            assert set(lines) == set(payload["line_spans"]) and set(lines.values()) <= {1}
            counts["figures"].update(
                gates13b.check_figures(payload, units, payload["line_spans"], output)
            )
            counts["equations"].update(gates13b.check_equations(payload, source, units))
            found, names = gates13c.check_mathml(payload, source, output)
            counts["mathml"].update(found)
            equation_images += names
            counts["tables"].update(check_tables(payload, source, units))
            expected_images |= {
                f"images/{f['image']['file_name']}"
                for f in payload["figures"]["figures"]
                if f.get("image")
            }
            total += retained_counter(source).total()
        assert images == expected_images, "archive images differ from final figures + fallbacks"
        assert len(equation_images) == len(set(equation_images))
        archives[book] = {
            "output": str(output),
            "files": len(manifest["files"]),
            "image_files": len(images),
            "figures": counts["figures"]["figures"],
            "equations": dict(sorted(counts["equations"].items())),
            "mathml": dict(sorted(counts["mathml"].items())),
            "tables": dict(sorted(counts["tables"].items())),
            "all_checks_pass": True,
        }
        final_tokens[book] = total
        with source_session(reference_path(BOOKS[book][0])):
            for number in numbers:
                fresh = (
                    PyMuPDFExtractor("cpu")
                    .extract_object_page(reference_path(BOOKS[book][0]), number)
                    .page
                )
                final = ExtractedPage.model_validate(
                    read_json(output / f"page_{number:06d}.json.gz")["source"]
                )
                expected, actual = retained_counter(fresh), retained_counter(final)
                rows.append(
                    {
                        "book": book,
                        "page": number,
                        "tokens": expected.total(),
                        "missing": (expected - actual).total(),
                        "extra": (actual - expected).total(),
                    }
                )
        if book == "spanish_us_history":
            assert total == 495751
    write(
        "source_crosscheck.json",
        {
            "sample": sample,
            "pages": len(rows),
            "missing": sum(r["missing"] for r in rows),
            "extra": sum(r["extra"] for r in rows),
            "results": rows,
            "final_archive_retained_tokens": final_tokens,
        },
    )
    assert len(rows) == 30 and all(r["missing"] == r["extra"] == 0 for r in rows)
    ledger = step7_gates.full_book()
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    write("full_book.json", ledger)
    write("final_outputs.json", archives)
    print(json.dumps({"archives": archives, "tokens": final_tokens}, indent=1))
    print("30 source pages: 0/0; Spanish ledger and final source archive: 495751")


if __name__ == "__main__":
    main()
