"""Element changes of the editor: every change keeps every word, keeps the book valid, and
"this block and what follows" re-levels the headings after the change."""

import collections
import json

import pytest

from book_app import overlay
from book_app.edit_ops import number_mark
from tests_adapters.adapter_fixtures import BookBuilder


def words(data):
    out = collections.Counter()

    def add(c):
        if c and c.get("text"):
            out.update(c["text"].split())

    for u, _ in overlay.walk(data["content"]):
        add(u.get("content"))
        if u.get("marker"):
            add({"text": u["marker"]["text"]})
        for key in ("captions", "text", "credits", "notes"):
            for t in u.get(key) or []:
                add(t.get("content"))
        if isinstance(u.get("title"), dict):
            add(u["title"].get("content"))
        for cell in u.get("cells") or []:
            for item in cell.get("content") or []:
                if item.get("type") == "text":
                    add(item["content"])
    for f in data.get("furniture") or []:
        add(f.get("content"))
    return out


def book(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    units = {
        "chapter": b.heading(p, "1 Knobs", 1, "chapter"),
        "authors": b.para(p, "Ann Lee, Raj Rao"),
        "learn": b.heading(p, "WHAT YOU WILL LEARN", 2, "section"),
        "goal": b.para(p, "Goals of the chapter"),
        "intro": b.heading(p, "INTRODUCTION", 3, "section"),
        "p1": b.para(p, "First paragraph"),
        "basic": b.heading(p, "BASIC PRINCIPLE", 3, "section"),
        "deep": b.heading(p, "Deeper", 4, "section"),
        "p2": b.para(p, "Second paragraph"),
        "stem": b.para(p, "12. Which knob sets the gain?"),
        "a": b.para(p, "(a) Depth"),
        "b": b.para(p, "(b) Gain"),
        "c": b.para(p, "(c) Focus"),
        "ans": b.para(p, "Answer: (b)"),
        "head": b.para(p, "RUNNING HEAD TEXT"),
        "fig": b.figure(p, "1", "f1"),
        "cap": b.para(p, "Fig. 1: A probe"),
        "g1": b.para(p, "Gain: the brightness of echoes"),
        "g2": b.para(p, "Depth: how far the image reaches"),
    }
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    return data, {k: u["id"] for k, u in units.items()}


def apply(data, *edits):
    out, applied, failed = overlay.apply_edits(data, [{"id": f"e{i}", **e} for i, e in enumerate(edits)])
    assert not failed, failed
    assert not overlay.schema_errors(out)
    assert words(out) == words(data)  # no word lost, none added
    return out


def unit(data, uid):
    return overlay.index_units(data)[uid][0]


CASES = {
    "bulleted list": lambda i: {"op": "list_set", "units": [i["p1"]], "list_type": "bulleted"},
    "numbered list": lambda i: {"op": "list_set", "units": [i["a"], i["b"], i["c"]], "list_type": "numbered"},
    "box": lambda i: {"op": "box", "units": [i["learn"], i["goal"]], "kind": "box", "title": True},
    "quote": lambda i: {"op": "box", "units": [i["p1"]], "kind": "quote"},
    "pull quote": lambda i: {"op": "box", "units": [i["p2"]], "kind": "pull_quote"},
    "caption": lambda i: {"op": "caption", "unit": i["cap"], "figure": i["fig"]},
    "table": lambda i: {"op": "table_make", "units": [i["g1"], i["g2"]], "columns": 1},
    "footnote": lambda i: {"op": "footnote", "unit": i["p2"]},
    "chapter authors": lambda i: {"op": "chapter_authors", "units": [i["authors"]]},
    "question": lambda i: {"op": "question", "units": [i["stem"], i["a"], i["b"], i["c"], i["ans"]]},
    "bibliography": lambda i: {"op": "bibliography", "units": [i["p1"]]},
    "index": lambda i: {"op": "index_entries", "units": [i["g1"], i["g2"]]},
    "glossary": lambda i: {"op": "glossary", "units": [i["g1"], i["g2"]]},
    "not content": lambda i: {"op": "not_content", "units": [i["head"]], "kind": "running_head"},
    "merge": lambda i: {"op": "merge", "units": [i["g1"], i["g2"]]},
    "move": lambda i: {"op": "move", "unit": i["p2"], "direction": "up"},
    "swap columns": lambda i: {"op": "swap_columns", "unit": i["g1"]},
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_change_keeps_every_word_and_a_valid_book(tmp_path, name):
    data, ids = book(tmp_path)
    apply(data, CASES[name](ids))


def test_what_the_changes_make(tmp_path):
    data, i = book(tmp_path)
    out = apply(data, CASES["question"](i), CASES["caption"](i), CASES["glossary"](i),
                CASES["not content"](i), CASES["chapter authors"](i))  # fmt: skip
    qset = next(u for u in out["content"] if u["type"] == "question_set")
    entry = qset["children"][0]
    question, answer = entry["children"]
    assert entry["number"] == 12 and answer["key"] == "b"
    options = question["children"][-1]
    assert [o["marker"]["text"] for o in options["items"]] == ["(a)", "(b)", "(c)"]
    assert [o["content"]["text"] for o in options["items"]] == ["Depth", "Gain", "Focus"]
    assert unit(out, i["fig"])["captions"][-1]["content"]["text"] == "Fig. 1: A probe"
    gloss = next(u for u in out["content"] if u["type"] == "list" and u["list_type"] == "glossary")
    assert [it["term"] for it in gloss["items"]] == [[0, 4], [0, 5]]
    assert out["furniture"][-1]["kind"] == "running_head" and i["head"] not in overlay.index_units(out)
    assert "chapter_authors" in unit(out, i["authors"])["flags"]


def test_reading_order_moves_and_swaps(tmp_path):
    data, i = book(tmp_path)
    order = lambda d: [u["id"] for u in d["content"] if u["type"] != "page_marker"]  # noqa: E731
    out = apply(data, {"op": "move", "unit": i["p2"], "direction": "up"})
    assert order(out).index(i["p2"]) == order(out).index(i["deep"]) - 1
    out = apply(data, {"op": "swap_columns", "unit": i["g1"]})
    assert order(out)[:2] == [i["g1"], i["g2"]] and order(out)[-1] == i["cap"]


def test_a_nested_list_and_list_levels(tmp_path):
    data, i = book(tmp_path)
    out = apply(data, {"op": "list_set", "units": [i["a"], i["b"]], "list_type": "numbered"},
                {"op": "list_set", "units": [i["c"]], "list_type": "bulleted", "level": 2})  # fmt: skip
    lst = next(u for u in out["content"] if u["type"] == "list")
    assert lst["items"][-1]["children"][0]["items"][0]["level"] == 2
    out = apply(out, {"op": "list_level", "unit": lst["items"][1]["id"], "direction": "in"})
    lst = next(u for u in out["content"] if u["type"] == "list")
    assert len(lst["items"]) == 1 and lst["items"][0]["children"][0]["items"][0]["id"] == i["b"]
    out = apply(out, {"op": "list_level", "unit": i["b"], "direction": "out"})
    assert [it["id"] for it in next(u for u in out["content"] if u["type"] == "list")["items"]] == [i["a"], i["b"]]


def test_this_block_only_moves_nothing_else(tmp_path):
    data, i = book(tmp_path)
    out = apply(data, {**CASES["box"](i), "scope": "block"})
    assert [c["unit"] for c in overlay.heading_changes(data, out)] == [i["learn"]]
    assert unit(out, i["intro"])["level"] == 3 and unit(out, i["deep"])["level"] == 4


def test_this_block_and_what_follows_relevels_the_headings_after_it(tmp_path):
    data, i = book(tmp_path)
    out = apply(data, {**CASES["box"](i), "scope": "follow"})
    # the sections that were under the boxed heading move up one level, no level skips
    assert [unit(out, i[k])["level"] for k in ("intro", "basic", "deep")] == [2, 2, 3]
    assert unit(out, i["chapter"])["level"] == 1
    changes = {c["unit"]: c for c in overlay.heading_changes(data, out)}
    assert changes[i["learn"]]["after"]["role"] == "sidebar_title"
    assert changes[i["intro"]]["after"]["level"] == 2


def test_follow_removes_level_skips_after_a_changed_block(tmp_path):
    data, i = book(tmp_path)
    out = apply(data, {"op": "heading_remove", "unit": i["learn"], "scope": "follow"})
    assert [unit(out, i[k])["level"] for k in ("intro", "basic", "deep")] == [2, 2, 3]
    out = apply(data, {"op": "heading_remove", "unit": i["learn"]})
    assert [unit(out, i[k])["level"] for k in ("intro", "basic", "deep")] == [3, 3, 4]


def test_refused_changes_say_why(tmp_path):
    data, i = book(tmp_path)
    for edit, reason in [
        ({"op": "box", "units": [i["p1"], i["p2"]], "kind": "box"}, "follow each other"),
        ({"op": "question", "units": [i["g1"], i["g2"]]}, "options"),
        ({"op": "glossary", "units": [i["p1"]]}, "term"),
        ({"op": "caption", "unit": i["p1"], "figure": i["p2"]}, "figure"),
        ({"op": "swap_columns", "unit": i["chapter"]}, "already starts"),
        ({"op": "box", "units": [i["p1"]], "kind": "box", "scope": "everything"}, "this block"),
    ]:
        _, _, failed = overlay.apply_edits(data, [{"id": "x", **edit}])
        assert failed and reason in failed[0]["reason"], (edit, failed)


def test_number_marks():
    assert number_mark("(a) Depth")[0]["type"] == "lower_alpha"
    assert number_mark("iv) Fourth")[0] == {"text": "iv)", "type": "lower_roman", "punctuation": ")", "value": 4}
    assert number_mark("12. Which")[0]["value"] == 12
    assert number_mark("Answer: (b)") is None


def test_a_question_from_a_stem_and_its_lettered_list(tmp_path):
    b = BookBuilder()
    p = b.page("1", "body", b.section("chapter", "body"))
    stem = b.para(p, "Which probe is used for the lung?")
    opts = b.list(p, [b.item(p, "Linear", {"text": "a.", "type": "lower_alpha", "value": 1}),
                      b.item(p, "Convex", {"text": "b.", "type": "lower_alpha", "value": 2})],
                  list_type="numbered", marker_type="lower_alpha")  # fmt: skip
    ans = b.para(p, "Answer: (a)")
    bul = b.list(p, [b.item(p, "One", {"text": "•", "type": "bullet"}),
                     b.item(p, "Two", {"text": "•", "type": "bullet"})])  # fmt: skip
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    out = apply(data, {"op": "question", "units": [stem["id"], opts["id"], ans["id"]]})
    entry = next(u for u in out["content"] if u["type"] == "question_set")["children"][0]
    question, answer = entry["children"]
    assert question["children"][-1]["items"][1]["content"]["text"] == "Convex"
    assert answer["key"] == "a"
    _, _, failed = overlay.apply_edits(data, [{"id": "x", "op": "question",
                                               "units": [ans["id"], bul["id"]]}])  # fmt: skip
    assert failed and "lettered" in failed[0]["reason"]


def test_similar_blocks_are_printed_alike_and_get_the_same_change(tmp_path):
    from book_app import similar

    b = BookBuilder()
    s = b.section("chapter", "body")
    heads, lists = [], []
    for n in range(3):
        p = b.page(str(n + 1), "body", s)
        heads.append(b.heading(p, "WHAT YOU WILL LEARN?", 2, "section"))
        lists.append(b.list(p, [b.item(p, "One"), b.item(p, "Two")]))
        b.para(p, "Body text of the page")
    p = b.page("4", "body", s)
    odd = b.heading(p, "WHAT YOU WILL LEARN?", 2, "section")  # printed in another font
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    ix = overlay.index_units(data)
    lines = {}
    for n, h in enumerate([*heads, odd]):  # each heading's first line and its printed style
        ix[h["id"]][0]["refs"] = {"lines": [f"{n + 1:016x}"], "spans": []}
        style = ["Utopia-Bold", 11.0, True, False] if h is not odd else ["Myriad", 14.0, True, False]
        lines[f"{n + 1:016x}"] = style
    edit = {"op": "box", "units": [heads[0]["id"], lists[0]["id"]], "kind": "box", "title": True,
            "scope": "follow", "id": "e1", "who": "A"}  # fmt: skip
    found = similar.matches(data, edit, lines)
    assert [m["page"] for m in found["matches"]] == [2, 3]  # not page 4 (other font)
    assert found["matches"][0]["edit"] == {"op": "box", "units": [heads[1]["id"], lists[1]["id"]],
                                           "kind": "box", "title": True, "scope": "follow"}  # fmt: skip
    out = apply(data, edit, *(m["edit"] for m in found["matches"]))
    assert sum(u["type"] == "box" for u in out["content"]) == 3


def test_unwrap_and_split_table_keep_every_word(tmp_path):
    data, ids = book(tmp_path)
    table = apply(data, {"op": "table_make", "units": [ids["g1"], ids["g2"]], "columns": 1})
    t = next(u for u, _ in overlay.walk(table["content"]) if u["type"] == "table")
    # split before row 2: two tables of one row each, no cell lost or repeated
    split = apply(table, {"op": "table_split", "unit": t["id"], "row": 2})
    tables = [u for u, _ in overlay.walk(split["content"]) if u["type"] == "table"]
    assert [x["rows"] for x in tables] == [1, 1] and tables[0]["id"] != tables[1]["id"]
    assert {c["row"] for c in tables[1]["cells"]} == {0}
    with pytest.raises(AssertionError):  # row 1 and row 3 are not places to split a 2-row table
        apply(table, {"op": "table_split", "unit": t["id"], "row": 3})
    # unwrap: the table becomes its text, row by row, as paragraphs
    flat = apply(split, {"op": "unwrap", "unit": tables[0]["id"]})
    assert not [u for u, _ in overlay.walk(flat["content"]) if u["id"] == tables[0]["id"]]
    assert [u["type"] for u, _ in overlay.walk(flat["content"])].count("table") == 1
    # a box and a figure with text unwrap too
    boxed = apply(data, {"op": "box", "units": [ids["learn"], ids["goal"]], "kind": "box", "title": True})
    b = next(u for u, _ in overlay.walk(boxed["content"]) if u["type"] == "box")
    apply(boxed, {"op": "unwrap", "unit": b["id"]})


def test_a_build_resumed_after_a_new_edit_or_an_undo_equals_a_full_build(tmp_path):
    """The app starts from the last build when edits are added or the last one is undone;
    the book is then exactly the one a full build gives (also with a failing edit)."""
    import threading

    from book_app.service import Service

    data, i = book(tmp_path)
    edits = [{"id": f"e{n}", **CASES[name](i)} for n, name in enumerate(
        ["bulleted list", "box", "caption", "not content", "swap columns", "footnote"])]  # fmt: skip
    edits.insert(3, {"id": "bad", "op": "move", "unit": "missing-unit", "direction": "up"})
    svc = Service.__new__(Service)  # only what the resumed build uses
    svc.stages, svc.mem_lock, svc.base_book = {}, threading.RLock(), lambda _job: data
    job = {"profile": "p", "publication": "x"}

    def build(sequence):
        got = Service._apply_resumed(svc, "j", job, sequence, {})
        want = overlay.apply_edits(data, sequence, {})
        assert json.dumps(got, sort_keys=True) == json.dumps(want, sort_keys=True)
        return got

    build(edits)
    build(edits[:-1])  # undo the last
    build(edits[:-1] + [edits[-1]])  # a new edit
    build(edits[:-2])  # undo again (a full build)
    build(edits[:2] + edits[3:])  # undo in the middle
    assert [f["edit"] for f in build(edits)[2]] == ["bad"]


# ---------------------------------------------------------------- to paragraph, hyphen-aware join


def read(unit_):
    """The text as it is read: line ends without a join record read as a space."""
    from book_adapters.engine.text import render

    c = unit_["content"]
    return "".join(ch for ch, _ in render(c, [(0, len(c["text"]))]))


def paragraphs(data):
    return [u for u in data["content"] if u["type"] == "paragraph"]


def list_book(tmp_path, marks=("-", "-", "-")):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    dash = lambda m: {"text": m, "type": "dash", "punctuation": "none", "value": None}  # noqa: E731
    texts = ["Das ist kein Analysemo\ndell zu verstehen, sondern ein ", "Gegenstandsbereich der Arbeit auch an",
             "dere Fälle auf Meta- und Objektebene, vom Dis\nsens aus."]  # fmt: skip
    items = [b.item(p, t, dash(m)) for t, m in zip(texts, marks)]
    lst = b.list(p, items)
    b.para(p, "After")
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    return data, lst["id"], [i["id"] for i in items]


def test_a_list_becomes_one_paragraph_with_cut_words_joined(tmp_path):
    data, lst, items = list_book(tmp_path)
    out = apply_tokens(data, {"op": "to_paragraph", "units": [lst]})
    para = paragraphs(out)[0]
    assert para["id"] == items[0] and not any(u["type"] == "list" for u in out["content"])
    assert read(para) == ("Das ist kein Analysemodell zu verstehen, sondern ein Gegenstandsbereich der Arbeit "
                          "auch andere Fälle auf Meta- und Objektebene, vom Dissens aus.")  # fmt: skip
    assert {j["decision"] for j in para["content"]["joins"]} == {"word"}
    assert "added by" not in json.dumps(para["provenance"])  # a join, not typed text


def test_one_paragraph_per_item_keeps_the_items_apart(tmp_path):
    data, lst, items = list_book(tmp_path)
    out = apply_tokens(data, {"op": "to_paragraph", "units": [lst], "per_item": True})
    got = paragraphs(out)
    assert [u["id"] for u in got[:3]] == items
    assert read(got[0]).startswith("Das ist kein Analysemodell zu")
    assert read(got[2]).endswith("vom Dissens aus.")


def test_some_items_leave_the_rest_in_lists(tmp_path):
    data, lst, items = list_book(tmp_path)
    out = apply_tokens(data, {"op": "to_paragraph", "units": [items[1]]})
    kinds = [u["type"] for u in out["content"] if u["type"] != "page_marker"]
    assert kinds == ["list", "paragraph", "list", "paragraph"]
    assert [len(u["items"]) for u in out["content"] if u["type"] == "list"] == [1, 1]


def test_a_numbered_mark_stays_as_text(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    mark = lambda m: {"text": m, "type": "decimal", "punctuation": ".", "value": int(m[0])}  # noqa: E731
    lst = b.list(p, [b.item(p, "First point", mark("1.")), b.item(p, "Second point", mark("2."))], "numbered")
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    out = apply_tokens(data, {"op": "to_paragraph", "units": [lst["id"]]})
    assert read(paragraphs(out)[0]) == "1. First point 2. Second point"


def test_other_blocks_become_paragraphs_and_merge(tmp_path):
    data, i = book(tmp_path)
    out = apply_tokens(data, {"op": "to_paragraph", "units": [i["basic"]]})  # a heading
    assert unit(out, i["basic"])["type"] == "paragraph" and unit(out, i["basic"])["role"] == "body"
    out = apply_tokens(data, {"op": "to_paragraph", "units": [i["cap"]]})  # a caption
    assert unit(out, i["cap"])["type"] == "paragraph"
    out = apply_tokens(data, {"op": "to_paragraph", "units": [i["p1"], i["basic"], i["deep"], i["p2"]]})
    assert read(unit(out, i["p1"])) == "First paragraph BASIC PRINCIPLE Deeper Second paragraph"
    boxed = apply_tokens(data, {"op": "box", "units": [i["g1"], i["g2"]], "kind": "box"})
    box = next(u for u in boxed["content"] if u["type"] == "box")
    out = apply_tokens(boxed, {"op": "to_paragraph", "units": [box["id"]]})
    assert [u["type"] for u in out["content"] if u["id"] == i["g1"]] == ["paragraph"]


def test_merge_drops_a_break_hyphen_and_keeps_a_real_one(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    pairs = [("Ein Methoden-", "vergleich zeigt es"),  # break hyphen: dropped
             ("Der Nord-", "Süd-Konflikt dauert"),  # capital after the hyphen: a real compound
             ("Meta-", "und Objektebene"),  # suspended hyphen: kept
             ("Er sagte es ", "und ging")]  # a line end that is not a cut: a space
    paras = [[b.para(p, x), b.para(p, y)] for x, y in pairs]
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    out = apply_tokens(data, *({"op": "merge", "units": [x["id"], y["id"]]} for x, y in paras))
    got = [read(unit(out, x["id"])) for x, _ in paras]
    assert got == ["Ein Methodenvergleich zeigt es", "Der Nord-Süd-Konflikt dauert",
                   "Meta- und Objektebene", "Er sagte es und ging"]  # fmt: skip
    assert [unit(out, x["id"])["content"]["joins"][0]["decision"] for x, _ in paras[:2]] == ["join", "keep"]
    assert unit(out, paras[0][0]["id"])["content"]["joins"][0]["hyphen_at"] == len("Ein Methoden-") - 1


def apply_tokens(data, *edits):
    """Like ``apply``, but the check is on letters and digits: a join makes "Analysemo" +
    "dell" one word (stated by a line-end join record), so no letter or digit may be lost or
    added, marks of list items included."""
    out, applied, failed = overlay.apply_edits(data, [{"id": f"e{i}", **e} for i, e in enumerate(edits)])
    assert not failed, failed
    assert not overlay.schema_errors(out)

    def chars(d):
        texts = [u["content"]["text"] for u, _ in overlay.walk(d["content"]) if (u.get("content") or {}).get("text")]
        texts += [u["marker"]["text"] for u, _ in overlay.walk(d["content"]) if (u.get("marker") or {}).get("text")]
        return sorted(ch for t in texts for ch in t if ch.isalnum())

    assert chars(out) == chars(data)
    return out
