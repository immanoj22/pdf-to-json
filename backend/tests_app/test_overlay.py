"""Edits applied to a copy of the book: text is moved, never lost."""

import copy

import pytest

from book_app import overlay
from tests_adapters.adapter_fixtures import BookBuilder


def book_with_bullets():
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    b.heading(p, "Chapter", 1, "chapter")
    a = b.para(p, "■ First point\nruns on", spans=[{"kind": "bold", "start": 2, "end": 7}])
    c = b.para(p, "■ Second point")
    d = b.para(p, "Line one\nLine two\nLine three")
    return b, a, c, d


def data_of(b, tmp_path):
    import json

    return json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())


def test_split_moves_text_without_loss(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    out, applied, failed = overlay.apply_edits(
        data, [{"op": "split", "unit": d["id"], "line": 1, "id": "e1"}]
    )
    assert not failed and len(applied) == 1
    ix = overlay.index_units(out)
    first, second = ix[d["id"]][0], ix[overlay.new_id(d["id"], "split", "1")][0]
    assert (
        first["content"]["text"] == "Line one"
        and second["content"]["text"] == "Line two\nLine three"
    )
    assert not overlay.schema_errors(out)
    assert data["content"] != out["content"] and ix  # the input was copied, not edited
    assert "Line two" in [u for u in data["content"] if u["id"] == d["id"]][0]["content"]["text"]


def test_make_list_drops_only_the_mark(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    out, _, failed = overlay.apply_edits(
        data, [{"op": "make_list", "units": [a["id"], c["id"]], "id": "e"}], {"■": "square"}
    )
    assert not failed and not overlay.schema_errors(out)
    lst = next(u for u in out["content"] if u["type"] == "list")
    assert [i["content"]["text"] for i in lst["items"]] == ["First point\nruns on", "Second point"]
    assert lst["items"][0]["marker"]["text"] == "■"
    assert lst["items"][0]["content"]["spans"] == [
        {**overlay.index_units(data)[a["id"]][0]["content"]["spans"][0], "start": 0, "end": 5}
    ]
    # not consecutive / no mark are refused with a reason
    _, _, failed = overlay.apply_edits(
        data, [{"op": "make_list", "units": [a["id"], d["id"]], "id": "x"}], {"■": "square"}
    )
    assert failed and "follow each other" in failed[0]["reason"]
    _, _, failed = overlay.apply_edits(
        data, [{"op": "make_list", "units": [d["id"]], "id": "y"}], {}
    )
    assert "No bullet mark" in failed[0]["reason"]


def test_join_and_unjoin_set_continuation_links(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    out, _, failed = overlay.apply_edits(data, [{"op": "join_next", "unit": a["id"], "id": "j"}])
    ix = overlay.index_units(out)
    assert (
        not failed
        and ix[a["id"]][0]["continues_to"]["unit"] == c["id"]
        and ix[c["id"]][0]["continues_from"]["unit"] == a["id"]
    )
    out2, _, _ = overlay.apply_edits(out, [{"op": "unjoin", "unit": a["id"], "id": "u"}])
    assert overlay.index_units(out2)[a["id"]][0]["continues_to"] is None


def test_heading_ops_and_failures_are_reported_not_raised(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    before = copy.deepcopy(data)
    out, applied, failed = overlay.apply_edits(
        data,
        [
            {"op": "heading_set", "unit": d["id"], "level": 3, "id": "1"},
            {"op": "new_chapter", "unit": a["id"], "id": "2"},
            {"op": "heading_set", "unit": "0" * 16, "level": 2, "id": "3"},
            {"op": "char", "unit": c["id"], "offset": 0, "char": "−", "id": "4"},
        ],
    )
    ix = overlay.index_units(out)
    assert (ix[d["id"]][0]["type"], ix[d["id"]][0]["level"]) == ("heading", 3)
    assert ix[a["id"]][0]["role"] == "chapter" and ix[a["id"]][0]["level"] == 1
    assert [f["edit"] for f in failed] == ["3"] and len(applied) == 3
    assert ix[c["id"]][0]["content"]["text"].startswith("−")
    assert data == before and not overlay.schema_errors(out)


@pytest.mark.parametrize("op", ["alt_text", "decorative"])
def test_figure_ops(tmp_path, op):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    fig = b.figure(p, "1", "f1")
    data = data_of(b, tmp_path)
    edit = {"op": op, "unit": fig["id"], "text": "A cell.", "value": True, "id": "a"}
    out, _, failed = overlay.apply_checked(data, [edit])
    assert not failed
    u = overlay.index_units(out)[fig["id"]][0]
    assert (u["alt_text"]["text"] == "A cell.") if op == "alt_text" else u["decorative"] is True
