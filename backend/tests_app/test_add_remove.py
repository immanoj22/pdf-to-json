"""Remove from book / Add text here: the book-model ops, the declared-change report and the
rules (text typed only where the PDF has no lines left out)."""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest
from book_adapters.validate.declared import declared_changes
from book_app import edit_ops, overlay
from book_core.assembly import lossless
from tests_app.test_restore_line import _furniture, _unit, book


def apply(data, *edits):
    edits = [{"id": f"e{i}", "who": "Ana", **e} for i, e in enumerate(edits)]
    return overlay.apply_edits(copy.deepcopy(data), edits)


def order(data):
    return [u["id"] for u, _ in overlay.walk(data["content"])]


def kept(data):
    f = lossless.json_tokens(data)
    return f["content"] + f["furniture"] + f["suppressed_retained"]


def schema_errors(data):
    """Schema errors of the content blocks and furniture of the (partial) test book."""
    from book_adapters.engine.load import book_schema

    full = json.loads(json.dumps(book_schema()).replace('"^[0-9a-f]{16}$"', '".*"'))  # fixture ids are short
    content_item = full["properties"]["content"]["items"]
    errors = []
    for items, item in ((data["content"], content_item), (data.get("furniture") or [], {"$ref": "#/$defs/Furniture"})):
        schema = {"$defs": full["$defs"], "type": "array", "items": item}
        items = [i for i in items if i.get("type") != "page_marker"]
        errors += [e.message[:120] for e in jsonschema.Draft202012Validator(schema).iter_errors(items)]
    return errors


def plain():
    data = book()
    for f in data["furniture"]:
        f["kind"] = "folio"  # page numbers only: no line of the PDF is left out of the text
    return data


def test_remove_moves_the_text_to_the_left_out_list_and_stays_lossless():
    data = plain()
    out, applied, failed = apply(data, {"op": "remove_block", "units": ["b"]})
    assert applied and not failed
    assert order(out) == ["m1", "a", "m2", "c"]
    item = next(f for f in out["furniture"] if f["id"] == "b")
    assert item["content"]["text"] == "Recognized language: Irish" and item["page"] == 1
    info = edit_ops.removed_info(item)
    assert info["who"] == "Ana" and info["event"] == "e0" and info["block"] == "paragraph"
    assert kept(out) == kept(data)  # Stage 1 lossless: the tokens moved, none lost
    assert schema_errors(out) == []
    back, _, _ = apply(data)  # undo = the edit is dropped
    assert order(back) == order(data) and not edit_ops.removed_info(back["furniture"][-1])


def test_remove_a_list_item_and_the_empty_list_goes_too():
    data = plain()
    ids = []
    items = [_unit(f"i{n}", "list_item", f"item {n}", 1, {"x0": 57, "x1": 200, "y0": 200 + n, "y1": 210 + n})
             for n in range(2)]
    for it in items:
        it.update(item_role="item", level=1, marker=None, children=[], locators=[], names=[], term=None)
    lst = {"id": "L" * 16, "type": "list", "pages": [1], "order": 1, "boxes": [], "confidence": 1.0,
           "continues_from": None, "continues_to": None, "flags": [], "items": items, "level": 1,
           "list_id": "x", "list_role": "body", "list_type": "bulleted", "marker_type": None,
           "provenance": {"stages": ["structure"]}, "refs": {"lines": [], "spans": []},
           "review_status": "ok", "segment": 0, "source": "native", "start": None}  # fmt: skip
    data["content"].insert(2, lst)
    one, _, bad = apply(data, {"op": "remove_block", "units": ["i0"]})
    assert not bad and "i0" not in order(one) and "L" * 16 in order(one)
    both, _, bad = apply(data, {"op": "remove_block", "units": ["i0", "i1"]})
    assert not bad and "L" * 16 not in order(both)
    assert {f["id"] for f in both["furniture"]} >= {"i0", "i1"}


def test_a_picture_or_empty_block_cannot_be_removed():
    data = plain()
    _, _, bad = apply(data, {"op": "remove_block", "units": ["m1"]})
    assert bad
    _, _, bad = apply(data, {"op": "remove_block", "units": []})
    assert bad


def test_add_a_paragraph_after_a_block_marks_it_added_by():
    data = plain()
    out, applied, failed = apply(data, {"op": "add_block", "anchor": "a", "where": "after",
                                        "text": "A new\n  sentence.", "as": "paragraph", "page": 1})
    assert applied and not failed
    new = [u for u, _ in overlay.walk(out["content"]) if u["id"] not in order(data)][0]
    assert order(out) == ["m1", "a", new["id"], "b", "m2", "c"]
    assert new["type"] == "paragraph" and new["content"]["text"] == "A new sentence."
    assert edit_ops.added_by(new) == "Ana"
    assert schema_errors(out) == []
    assert declared_changes(out)["added"][0]["text"] == "A new sentence."
    before, _, _ = apply(data, {"op": "add_block", "anchor": "a", "where": "before", "text": "First.", "page": 1})
    assert order(before)[1] != "a"


def test_added_heading_and_every_menu_element_can_follow():
    data = plain()
    out, _, bad = apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": "New part",
                               "as": "heading", "level": 2, "page": 1})
    assert not bad
    head = next(u for u, _ in overlay.walk(out["content"]) if u["type"] == "heading")
    assert head["level"] == 2 and edit_ops.added_by(head) == "Ana"
    thens = {
        "list": {"op": "list_set", "units": ["$new"], "list_type": "bulleted", "level": 1},
        "box": {"op": "box", "units": ["$new"], "kind": "box", "title": False},
        "quote": {"op": "box", "units": ["$new"], "kind": "quote"},
        "table": {"op": "table_make", "units": ["$new"], "columns": 1},
        "footnote": {"op": "footnote", "unit": "$new"},
        "authors": {"op": "chapter_authors", "units": ["$new"]},
        "biblio": {"op": "bibliography", "units": ["$new"]},
    }
    for name, then in thens.items():
        out, applied, bad = apply(data, {"op": "add_block", "anchor": "a", "where": "after",
                                         "text": f"typed {name}", "then": then, "page": 1})
        assert applied and not bad, (name, bad)
        d = declared_changes(out)
        assert [a["text"] for a in d["added"]] == [f"typed {name}"], name  # the mark survived
        assert schema_errors(out) == [], name
    _, _, bad = apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": "x",
                             "then": {"op": "move", "unit": "$new", "direction": "up"}, "page": 1})
    assert bad  # only element changes, not moves


def test_a_new_block_can_be_changed_later_like_any_other():
    data = plain()
    out, _, _ = apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": "Typed.", "page": 1})
    new = next(u for u, _ in overlay.walk(out["content"]) if u["id"] not in order(data))
    edits = [{"id": "e0", "who": "Ana", "op": "add_block", "anchor": "a", "where": "after",
              "text": "Typed.", "page": 1},
             {"id": "e1", "who": "Bo", "op": "heading_set", "unit": new["id"], "level": 3},
             {"id": "e2", "who": "Bo", "op": "list_set", "units": [new["id"]], "list_type": "numbered", "level": 1}]
    out, applied, failed = overlay.apply_edits(copy.deepcopy(data), edits[:2])
    assert not failed
    assert [a["who"] for a in declared_changes(out)["added"]] == ["Ana"]
    out, applied, failed = overlay.apply_edits(copy.deepcopy(data), [edits[0], edits[2]])
    assert not failed and len(declared_changes(out)["added"]) == 1


def test_list_item_goes_next_to_an_item_and_a_paragraph_goes_beside_the_list():
    data = plain()
    items = [_unit("i0", "list_item", "item 0", 1, {"x0": 57, "x1": 200, "y0": 200, "y1": 210})]
    items[0].update(item_role="item", level=1, marker=None, children=[], locators=[], names=[], term=None)
    lst = {"id": "L" * 16, "type": "list", "pages": [1], "order": 1, "boxes": [], "confidence": 1.0,
           "continues_from": None, "continues_to": None, "flags": [], "items": items, "level": 1,
           "list_id": "x", "list_role": "body", "list_type": "bulleted", "marker_type": None,
           "provenance": {"stages": ["structure"]}, "refs": {"lines": [], "spans": []},
           "review_status": "ok", "segment": 0, "source": "native", "start": None}  # fmt: skip
    data["content"].insert(2, lst)
    out, _, bad = apply(data, {"op": "add_block", "anchor": "i0", "where": "after", "text": "item 1",
                               "as": "list_item", "page": 1})
    assert not bad
    got = next(u for u, _ in overlay.walk(out["content"]) if u["type"] == "list")["items"]
    assert [i["type"] for i in got] == ["list_item", "list_item"] and edit_ops.added_by(got[1])
    out, _, bad = apply(data, {"op": "add_block", "anchor": "i0", "where": "after", "text": "after list",
                               "page": 1})
    assert not bad
    top = [u["type"] for u in out["content"]]
    assert top.index("list") + 1 < len(top) and out["content"][top.index("list") + 1]["type"] == "paragraph"
    _, _, bad = apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": "x", "as": "list_item", "page": 1})
    assert bad  # a list item only goes next to a list


def test_text_is_typed_only_where_the_pdf_has_no_lines_left_out():
    data = book()  # page 1 has the title "The Republic of Ireland" kept as a running head
    _, applied, bad = apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": "x", "page": 1})
    assert bad and "Restore them first" in bad[0]["reason"] and not applied
    # a block the reviewer removed is a line the PDF has too
    data = plain()
    gone, _, _ = apply(data, {"op": "remove_block", "units": ["b"]})
    _, _, bad = apply(gone, {"op": "add_block", "anchor": "a", "where": "after", "text": "x", "page": 1})
    assert bad
    # page 2 has only a page number: typing is fine there
    _, _, bad = apply(data, {"op": "add_block", "anchor": "c", "where": "after", "text": "x", "page": 2})
    assert not bad
    for text in ("", "   "):
        assert apply(data, {"op": "add_block", "anchor": "a", "where": "after", "text": text, "page": 1})[2]


def test_declared_changes_list_who_page_and_text():
    data = plain()
    out, _, _ = apply(data, {"op": "remove_block", "units": ["b"]},
                      {"op": "add_block", "anchor": "c", "where": "after", "text": "Two words", "page": 2})
    d = declared_changes(out)
    assert d["removed"] == [{"page": 1, "text": "Recognized language: Irish", "who": "Ana",
                             "block": "paragraph", "tokens": 3}]
    assert d["added"][0]["page"] == 2 and d["added"][0]["tokens"] == 2 and d["added_tokens"] == 2


def test_touched_names_the_anchor():
    assert edit_ops.touched({"op": "add_block", "anchor": "a"}) == ["a"]


def test_add_text_setting_managers_only_by_default(tmp_path):
    from conftest import make_app

    for setting, reviewer_status in (("managers", 403), ("everyone", None)):
        app, client = make_app(tmp_path / setting, add_text_by=setting)
        try:
            body = {"edit": {"op": "add_block", "anchor": "x", "where": "after", "text": "t"}}
            r = client.post("/api/jobs/aaaaaaaaaaaaaaaa/edits/preview", json=body,
                            headers={"X-User": "Rev", "X-Role": "reviewer"})
            assert (r.status_code == 403) == (reviewer_status == 403)
            assert client.get("/api/health").json()["add_text_by"] == setting
        finally:
            app.state.converter.stop()
