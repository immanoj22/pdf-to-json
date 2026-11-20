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


# --------------------------------------------------------------------------- chapter editing


def structure_book(tmp_path):
    """Two sections, three chapters, a "PART I" label and a REFERENCES title inside chapter 1,
    and a contents page the converter read as a chapter."""
    b = BookBuilder()
    s = b.section("chapter", "body")
    page = {n: b.page(str(n), "body", s) for n in range(1, 8)}
    heads = {
        "contents": b.heading(page[1], "Contents", 2, "chapter"),
        "sec1": b.heading(page[2], "1\nFundamentals", 1, "part"),
        "ch1": b.heading(page[3], "Introduction\n1", 2, "chapter"),
        "part1": b.heading(page[3], "PART I: PHYSICS", 2, "chapter"),
        "refs": b.heading(page[4], "REFERENCES", 2, "chapter"),
        "sec2": b.heading(page[5], "Upper Limb Blocks\n2", 2, "section"),
        "ch2": b.paragraph if False else b.para(page[6], "Interscalene Block"),
        "ch3": b.heading(page[7], "3. Supraclavicular Block", 2, "chapter"),
    }
    return heads, data_of(b, tmp_path)


def edit(data, *edits):
    out, applied, failed = overlay.apply_edits(
        data, [{**e, "id": f"e{i}"} for i, e in enumerate(edits)]
    )
    assert not overlay.schema_errors(out)
    return out, applied, failed


def test_a_heading_is_given_a_kind(tmp_path):
    heads, data = structure_book(tmp_path)
    out, _, failed = edit(
        data,
        {"op": "heading_kind", "unit": heads["sec2"]["id"], "kind": "part"},
        {"op": "heading_kind", "unit": heads["part1"]["id"], "kind": "section"},
        {"op": "heading_kind", "unit": heads["contents"]["id"], "kind": "front_matter"},
    )
    assert not failed
    ix = overlay.index_units(out)
    got = {k: (ix[v["id"]][0]["role"], ix[v["id"]][0]["level"]) for k, v in heads.items()
           if k != "ch2"}  # fmt: skip
    assert got["sec2"] == ("part", 1) and got["part1"] == ("section", 3)
    assert got["contents"] == ("front_section_title", 1)
    assert out["pages"][0]["zone"] == "front"  # the contents page touches the front matter


def test_a_page_inside_the_book_cannot_become_front_matter(tmp_path):
    heads, data = structure_book(tmp_path)
    _, _, failed = edit(data, {"op": "heading_kind", "unit": heads["sec2"]["id"],
                               "kind": "front_matter"})  # fmt: skip
    assert failed and "book parts" in failed[0]["reason"]


def test_start_a_chapter_here_with_its_number(tmp_path):
    heads, data = structure_book(tmp_path)
    out, _, failed = edit(
        data, {"op": "new_chapter", "unit": heads["ch2"]["id"], "number": "2"})
    assert not failed
    unit = overlay.index_units(out)[heads["ch2"]["id"]][0]
    assert (unit["type"], unit["role"], unit["number"]) == ("heading", "chapter", "2")
    _, _, failed = edit(data, {"op": "heading_number", "unit": heads["ch3"]["id"],
                               "number": "12 apples"})  # fmt: skip
    assert failed


def test_a_title_can_only_lose_a_number_and_the_change_is_kept(tmp_path):
    heads, data = structure_book(tmp_path)
    unit = heads["ch1"]["id"]
    out, _, failed = edit(data, {"op": "heading_text", "unit": unit, "text": "Introduction"})
    assert not failed
    assert overlay.index_units(out)[unit][0]["content"]["text"] == "Introduction"
    assert overlay.index_units(out)[unit][0]["number"] == "1"  # the number is kept as the number
    assert overlay.index_units(data)[unit][0]["content"]["text"] == "Introduction\n1"
    for text in ("Introductions", "Intro", ""):  # words may not change or go
        _, _, failed = edit(data, {"op": "heading_text", "unit": unit, "text": text})
        assert failed, text


def test_a_heading_belongs_to_the_chapter_before(tmp_path):
    heads, data = structure_book(tmp_path)
    out, _, failed = edit(data, {"op": "heading_attach", "unit": heads["refs"]["id"]})
    assert not failed
    unit = overlay.index_units(out)[heads["refs"]["id"]][0]
    assert (unit["role"], unit["level"]) == ("feature_title", 3)


def test_the_chapter_list_shows_what_will_be_exported(tmp_path):
    heads, data = structure_book(tmp_path)
    rows = overlay.chapter_rows(data)
    assert [(r["role"], r["number"], r["title"]) for r in rows][:4] == [
        ("chapter", None, "Contents"), ("part", "1", "Fundamentals"),
        ("chapter", "1", "Introduction"), ("chapter", None, "PART I: PHYSICS")]  # fmt: skip
    out, _, _ = edit(
        data,
        {"op": "heading_kind", "unit": heads["contents"]["id"], "kind": "front_matter"},
        {"op": "heading_kind", "unit": heads["part1"]["id"], "kind": "section"},
        {"op": "heading_attach", "unit": heads["refs"]["id"]},
        {"op": "heading_kind", "unit": heads["sec2"]["id"], "kind": "part"},
        {"op": "new_chapter", "unit": heads["ch2"]["id"], "number": "2"},
    )
    shown = [(r["role"], r["number"]) for r in overlay.chapter_rows(out)]
    assert shown == [("part", "1"), ("chapter", "1"), ("part", "2"), ("chapter", "2"),
                     ("chapter", "3")]  # fmt: skip


def test_demoting_a_chapter_leaves_the_converters_other_headings_alone(tmp_path):
    """Only the starts a person sets re-level the headings inside them (a book's own section
    openers keep their levels, or the export loses their opener words)."""
    heads, data = structure_book(tmp_path)
    ix = overlay.index_units(data)
    before = {k: ix[v["id"]][0]["level"] for k, v in heads.items() if k != "ch2"}
    out, _, failed = edit(data, {"op": "heading_kind", "unit": heads["ch1"]["id"],
                                 "kind": "section"})  # fmt: skip
    assert not failed
    ox = overlay.index_units(out)
    after = {k: ox[v["id"]][0]["level"] for k, v in heads.items() if k != "ch2"}
    assert {k: v for k, v in after.items() if k != "ch1"} == {
        k: v for k, v in before.items() if k != "ch1"}  # fmt: skip


# ---- Browse: the clean one-line text and the book search (display only)
def test_clean_text_joins_wrapped_lines_and_keeps_hyphens():
    from book_app.service import Service

    assert Service.clean_text("The quick\nbrown   fox\b\njumps") == "The quick brown fox jumps"
    assert Service.clean_text("a co-\nordinate system") == "a co-ordinate system"  # no letter lost
    assert Service.clean_text("") == ""


def test_clean_fields_list_has_items_and_no_pipe():
    from book_app.service import Service

    def item(i, text):
        return {"id": i, "type": "list_item", "level": 1, "content": {"text": text}}

    lst = {"id": "L", "type": "list", "list_type": "numbered",
           "items": [item("a", "one\ntwo"), item("b", "three")]}  # fmt: skip
    out = Service.clean_fields(lst, "")
    assert [i["text"] for i in out["items"]] == ["one two", "three"]
    assert out["item_ids"] == ["a", "b"]
    assert "|" not in str(out)


# ------------------------------------------------------------------ one copy per checkpoint


def reference_stage(data, edits, marks=None):
    """The edit loop as it was: a copy of the book before every edit, put back when it fails."""
    data, applied, failed = overlay.clone(data), [], []
    for edit in edits:
        content, furniture = overlay.clone(data["content"]), overlay.clone(data.get("furniture"))
        try:
            overlay._apply_one(data, edit, marks)
            applied.append(edit)
        except (overlay.EditError, KeyError, ValueError, TypeError) as exc:
            data["content"], data["furniture"] = content, furniture
            failed.append({"edit": edit.get("id"), "op": edit.get("op"), "reason": str(exc)})
    return data, applied, failed


def many_paragraphs(tmp_path, count=40):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    b.heading(p, "Chapter", 1, "chapter")
    paras = [b.para(p, f"Paragraph {i} first line\nsecond line of {i}") for i in range(count)]
    return data_of(b, tmp_path), [u["id"] for u in paras]


def long_edit_list(ids, n):
    edits = []
    for i in range(n):
        unit = ids[i % len(ids)]
        kind = i % 7
        if kind == 3:  # cannot be applied: no such unit
            edits.append({"op": "heading_set", "unit": f"{i:016x}", "level": 2, "id": f"e{i}"})
        elif kind == 5:
            edits.append({"op": "split", "unit": unit, "line": 1, "id": f"e{i}"})
        elif kind == 6:  # a change "to this block and what follows"
            edits.append({"op": "heading_set", "unit": unit, "level": 2, "id": f"e{i}",
                          "scope": "follow"})
        elif kind == 4:  # a bad scope: applied, then refused
            edits.append({"op": "heading_set", "unit": unit, "level": 3, "id": f"e{i}",
                          "scope": "nonsense"})
        else:
            edits.append({"op": "char", "unit": unit, "offset": 0, "char": "−", "id": f"e{i}"})
    return edits


@pytest.mark.parametrize("n", [1, 2, 63, 64, 65, 130, 200])
def test_one_copy_per_checkpoint_gives_the_same_book_as_a_copy_per_edit(tmp_path, n):
    data, ids = many_paragraphs(tmp_path)
    edits = long_edit_list(ids, n)
    want = reference_stage(data, edits)
    got = overlay.apply_stage(data, edits)[:3]
    assert got[0] == want[0] and got[1] == want[1] and got[2] == want[2]
    if n > 3:
        assert got[2]  # the list does contain edits that fail
    assert data == data_of_unchanged(tmp_path, ids)  # the input is not touched


def data_of_unchanged(tmp_path, ids):
    return many_paragraphs(tmp_path / "again")[0]


def test_the_last_edit_failing_and_undo_state(tmp_path):
    data, ids = many_paragraphs(tmp_path)
    edits = long_edit_list(ids, 30)[:-1] + [{"op": "heading_set", "unit": "f" * 16, "level": 2,
                                             "id": "last"}]
    book, applied, failed, before_last = overlay.apply_stage(data, edits)
    want = reference_stage(data, edits)
    assert book == want[0] and failed == want[2]
    content, furniture, na, nf = before_last
    assert na == len(applied) and nf == len(failed) - 1  # the state just before the last edit
    resumed = overlay.apply_stage(data, edits[:-1])[0]
    assert content == resumed["content"]
    # resuming from a stage after the first edits applies only the rest, with the same result
    mid = overlay.apply_stage(data, edits[:20])
    again = overlay.apply_stage(data, edits[20:], resume=mid[:3])
    assert again[0] == book and again[1] == applied and again[2] == failed


# ------------------------------------------------------------------ the schema check of what changed


def test_checking_only_what_changed_gives_the_answer_of_checking_everything(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    assert overlay.schema_errors(data) == []

    def both(book):
        return overlay.schema_errors(book), overlay.schema_errors(book, data)

    # valid edits
    out, _, failed = overlay.apply_edits(
        data, [{"op": "split", "unit": d["id"], "line": 1, "id": "s"},
               {"op": "heading_set", "unit": a["id"], "level": 2, "id": "h"}],
    )  # fmt: skip
    assert not failed and both(out) == ([], [])
    # a changed node that breaks the schema is found by both
    broken = overlay.clone(out)
    unit = overlay.index_units(broken)[c["id"]][0]
    unit["type"] = "nonsense"
    full, part = both(broken)
    assert full and part
    broken2 = overlay.clone(data)
    del overlay.index_units(broken2)[d["id"]][0]["content"]["text"]  # a required field gone
    assert all(both(broken2))
    # top-level parts: a missing required key, a wrong type in the pages list, a changed furniture
    for mutate in (lambda x: x.pop("pages"), lambda x: x.__setitem__("pages", "no"),
                   lambda x: x.__setitem__("metadata", [])):  # fmt: skip
        bad = overlay.clone(data)
        mutate(bad)
        full, part = both(bad)
        assert full and part
    # an entry that is new (an id the reference does not have) is checked too
    added = overlay.clone(data)
    added["content"].append({"id": "x" * 16, "type": "paragraph"})
    assert all(both(added))
    # nothing changed: nothing to check, and the answer is the same
    assert both(overlay.clone(data)) == ([], [])


def test_edits_that_break_the_book_are_still_refused_one_by_one(tmp_path):
    b, a, c, d = book_with_bullets()
    data = data_of(b, tmp_path)
    good = {"op": "heading_set", "unit": d["id"], "level": 3, "id": "good"}
    result, applied, failed = overlay.apply_checked(data, [good])
    assert [e["id"] for e in applied] == ["good"] and not failed
    ix = overlay.index_units(result)
    assert ix[d["id"]][0]["type"] == "heading"
