"""A printed list marker is published once, by the part of its item that holds its glyphs.

Step 18 found list markers repeated on every part of an item cut by a table, and markers
published by parts (another column, a continuation) whose own lines do not hold them.
"""

from pathlib import Path
from types import SimpleNamespace

from test_continuity import _book, _run

from book_core.assembly.build import Context, PageBuild
from book_core.assembly.fonts import FontTable
from book_core.assembly.profile import load_profile
from book_core.cache_store import read_json
from book_core.lists.models import Marker
from book_core.model.common import SpanRef
from book_core.model.spans import ExtractedPage
from book_core.tables.view import unit_view

join = lambda a, b: SimpleNamespace(previous_line_id=a, next_line_id=b)  # noqa: E731


class Unit(SimpleNamespace):
    def model_copy(self, update):
        return Unit(**{**vars(self), **update})


def item(lines):
    joins = [join(a, b) for a, b in zip(lines, lines[1:], strict=False)]
    return Unit(id="item", line_ids=lines, joins=joins, continues_from=None, continues_to=None,
                marker="1.")  # fmt: skip


def test_an_item_cut_by_a_table_keeps_its_marker_on_the_first_part_only():
    # Rows of a table inside the item (or a column-wide table between its two columns).
    table = SimpleNamespace(line_ids=["b", "d"])
    final, _, parts = unit_view([item(["a", "b", "c", "d", "e"])], [table])
    assert [u.line_ids for u in final] == [["a"], ["c"], ["e"]]
    assert [u.marker for u in final] == ["1.", None, None]
    assert final[0].id == "item" and set(parts.values()) == {"item"}


def test_a_marker_line_owned_by_a_table_leaves_no_part_with_the_marker():
    final, _, _ = unit_view([item(["a", "b", "c"])], [SimpleNamespace(line_ids=["a"])])
    assert [u.line_ids for u in final] == [["b", "c"]]
    assert final[0].marker is None


def page_build(tmp_path):
    result = _run(_book(tmp_path / "items.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    payload = read_json(Path(result["output"]) / "page_000001.json.gz")
    fonts = FontTable()
    fonts.add(ExtractedPage.model_validate(payload["source"]).store)
    fonts.freeze()
    list_id = "f" * 64
    ctx = Context(profile=load_profile(), fonts=fonts, language=None, book={}, headings={},
                  run_in={}, styled={}, lists={list_id: {"kind": "ordered", "level": 1}},
                  navigation={}, markers={}, zones={})  # fmt: skip
    page = PageBuild(ctx, 1, payload, None, {})
    source = next(u for u in page.units.values() if u.kind == "paragraph" and len(u.line_ids) > 1)
    first_span = page.line_spans[source.line_ids[0]][0]
    # The whole first word, so the marker is not glued to a following letter.
    word = len(page.spans[first_span].raw_text.split(" ")[0])
    marker = Marker(refs=[SpanRef(span_id=first_span, start=0, end=word)], type="decimal", value=1)
    whole = source.model_copy(
        update={"kind": "list_item", "list_id": list_id, "level": 1, "marker": marker}
    )
    rest = whole.model_copy(
        update={"id": "e" * 64, "line_ids": whole.line_ids[1:], "joins": whole.joins[1:]}
    )
    return page, whole, rest


def test_a_part_without_the_marker_glyphs_never_publishes_the_marker(tmp_path):
    # The rest of an item in the next column or on the next page: its own lines do not
    # hold the printed marker, so it neither repeats nor invents it, and it is reviewed.
    page, whole, rest = page_build(tmp_path)
    part = page.unit_node(rest)
    assert part.marker is None
    reasons = [reason for _, _, reason in page.ctx.flag_rows[part.id]]
    assert any("marker is on another part" in reason for reason in reasons)
    node = page.unit_node(whole)
    assert node.marker is not None and node.marker.value == 1


def test_a_marker_is_published_once_per_page(tmp_path):
    page, whole, _ = page_build(tmp_path)
    assert page.unit_node(whole).marker is not None
    assert page.unit_node(whole).marker is None
