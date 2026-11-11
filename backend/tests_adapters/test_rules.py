"""Each named rule on its own."""

from __future__ import annotations

from book_adapters.engine.model import (
    BibEntry,
    Bibliography,
    BookInfo,
    Division,
    Document,
    Figure,
    Item,
    ListBlock,
    Para,
    QandaSet,
    Sidebar,
    Table,
)
from book_adapters.engine.text import TextRef
from book_adapters.rules import RULES, active_rules, characters, links, structure, writer_switches


def ref(text, addr="u1", order=0):
    return TextRef(addr, {"text": text, "spans": [], "joins": []}, order)


def doc_with(nodes):
    chapter = Division(kind="chapter", children=nodes, number=1)
    return Document(BookInfo(), [], [chapter], [])


# --------------------------------------------------------------------------- characters


def test_apostrophe_straight():
    text, reviews = characters.apostrophe_straight("the world’s parents’ and ‘quoted’ x", {})
    assert text == "the world's parents' and ‘quoted’ x" and not reviews
    assert len(text) == len("the world’s parents’ and ‘quoted’ x")


def test_apostrophe_right_single_quote_setting():
    """Owner decision (differs from item 18): apostrophes and closing quotes are U+2019."""
    ctx = {"apostrophe": "right_single_quote"}
    source = "the world’s parents’ and ‘quoted’ x"
    assert characters.apostrophe_straight(source, ctx) == (source, [])  # already U+2019
    text, reviews = characters.apostrophe_straight("the world's parents' don't 'quoted' x", ctx)
    assert text == "the world’s parents’ don’t 'quoted’ x"  # the opening quote is left
    assert len(text) == len("the world's parents' don't 'quoted' x") and reviews == []
    assert characters.apostrophe_straight("in the '90s it's", ctx)[0] == "in the ’90s it’s"
    assert characters.apostrophe_straight("a ' b", ctx)[1]  # a lone quote is reviewed
    assert characters.apostrophe_straight("it’s", {"apostrophe": "straight"})[0] == "it's"


def test_double_quotes_curly_and_unpaired_review():
    assert characters.double_quotes_curly('say "hi" now', {})[0] == "say “hi” now"
    text, reviews = characters.double_quotes_curly('a " b', {})
    assert text == 'a " b' and reviews


def test_minus_vs_en_dash_by_context():
    fn = characters.minus_sign_by_context
    assert fn("at –196°C", {})[0] == "at −196°C"
    assert fn("(–2.5)", {})[0] == "(−2.5)"
    assert fn("2010–2020", {})[0] == "2010–2020"  # range stays an en dash
    assert fn("pages 10 – 20", {})[0] == "pages 10 – 20"
    text, reviews = fn("pH–7", {})
    assert text == "pH–7" and reviews  # unclear: kept and reviewed


def test_index_range_en_dash_only_inside_locators():
    fn = characters.index_range_en_dash
    assert (
        fn("Alpha 3-4, co-op", {"index_entry": True, "locator_ranges": [(6, 9)]})[0]
        == "Alpha 3–4, co-op"
    )
    assert fn("Alpha 3-4", {})[0] == "Alpha 3-4"


# --------------------------------------------------------------------------- tree rules


def test_sidebar_not_in_list_splits_and_continues():
    side = Sidebar(None, children=[Para([ref("inside", "s", 2)])])
    items = [Item([ref("one", "a", 1)], children=[side]), Item([ref("two", "b", 3)])]
    lst = ListBlock("numbered", "decimal", items)
    doc = doc_with([lst])
    structure.sidebar_not_in_list(doc, {})
    nodes = doc.body[0].children
    assert [type(n).__name__ for n in nodes] == ["ListBlock", "Sidebar", "ListBlock"]
    assert nodes[2].continues and not nodes[0].items[0].children
    assert nodes[1].children[0].parts[0].move  # declared move


def test_numbered_figure_alone_in_table_is_unwrapped():
    fig = Figure({"id": "f"}, formal=True, num="1")
    table = Table({"id": "t"})
    table.cells_blocks = {"c1": [fig]}
    doc = doc_with([table])
    structure.numbered_figure_alone_in_table(doc, {})
    assert doc.body[0].children == [fig]
    titled = Table({"id": "t2"}, title=ref("A table"))
    titled.cells_blocks = {"c1": [fig]}
    doc = doc_with([titled])
    structure.numbered_figure_alone_in_table(doc, {})
    assert doc.body[0].children == [titled]


class _Profile:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_suggested_reading_becomes_a_chapter():
    bib = Bibliography(ref("Suggested Reading", "t", 5), [BibEntry([ref("A book.", "e", 6)])])
    doc = doc_with([Para([ref("text", "p", 1)]), bib])
    profile = _Profile(
        {"bibliography.suggested_reading_patterns": [r"(?i)^\s*suggested\s+readings?\s*$"]}
    )
    structure.suggested_reading_as_chapter(doc, {"profile": profile})
    assert len(doc.body) == 2 and doc.body[1].kind == "chapter" and doc.body[1].number == 2
    assert isinstance(doc.body[1].children[0], ListBlock)
    assert doc.body[1].children[0].list_type == "bulleted"


def test_qanda_sets_from_title():
    title = Para([ref("Review Questions", "q", 1)], "display_title")
    lst = ListBlock("numbered", "decimal", [Item([ref("Define anatomy.", "i", 2)])])
    doc = doc_with([title, lst])
    profile = _Profile({"qanda.set_title_patterns": [r"(?i)^\s*review questions\s*$"]})
    structure.qanda_sets(doc, {"profile": profile})
    [qs] = doc.body[0].children
    assert isinstance(qs, QandaSet) and qs.title.plain() == "Review Questions"


def test_color_plate_note_removed_and_listed():
    para = Para([ref("A figure (For color version, see Color Plate 3) here.", "c", 1)])
    doc = doc_with([para])
    profile = _Profile(
        {
            "color_plates.note_pattern": r"(?i)\(\s*for colou?r version,? see colou?r plate"
            r"\s*[0-9A-Z.]*\s*\)"
        }
    )
    structure.color_plate_note_removal(doc, {"profile": profile})
    assert para.parts[0].plain() == "A figure here."
    assert doc.omissions and "colour plate" in doc.omissions[0].reason


def test_continued_figure_stays_formal():
    fig = Figure({"id": "f"}, continued=True)
    doc = doc_with([fig])
    structure.continued_figure(doc, {})
    assert fig.formal


def test_epigraph_roles():
    quote, source = Para([ref("q")], "epigraph"), Para([ref("s")], "attribution")
    doc = doc_with([quote, source])
    structure.epigraph_as_paras(doc, {})
    assert (quote.role_override, source.role_override) == ("noindent", "alignright")


def test_set_figure_caption_goes_to_review():
    fig = Figure({"id": "f"}, formal=True, num="5.5A", label_ref=ref("Figs 5.5A and B"))
    doc = doc_with([fig])
    structure.set_figures_separate(doc, {})
    assert doc.reviews and doc.reviews[0].rule == "set_figures_separate"


# --------------------------------------------------------------------------- links, switches


def test_link_citations_only_known_numbers():
    spans = [{"kind": "superscript", "start": 5, "end": 8}]
    out = links.link_citations("text 1–8 more", spans, {"bib_ids": {1: "ch1bib1", 8: "ch1bib8"}})
    assert out == [(5, 6, "#ch1bib1"), (7, 8, "#ch1bib8")]
    assert (
        links.link_citations(
            "x 9", [{"kind": "superscript", "start": 2, "end": 3}], {"bib_ids": {1: "a"}}
        )
        == []
    )


def test_link_object_mentions():
    ctx = {
        "object_ids": {("figure", "1"): "ch1fig1", ("table", "2"): "ch1tbl2"},
        "mention_words": {"fig": "figure", "table": "table"},
    }
    out = links.link_object_mentions("see Fig. 1 and Table 2 and Fig. 3", [], ctx)
    assert out == [(4, 10, "#ch1fig1"), (15, 22, "#ch1tbl2")]
    # delivery: "Tables 1 and 2" links "Tables 1" and "2" separately
    ctx["object_ids"][("table", "1")] = "ch1tbl1"
    ctx["mention_words"]["tables"] = "table"
    out = links.link_object_mentions("(Tables 1 and 2)", [], ctx)
    assert out == [(1, 9, "#ch1tbl1"), (14, 15, "#ch1tbl2")]


def test_link_urls_and_emails():
    text = "Available from: https://www.eshre.\neu/Guidelines.\nMail info@x.org. See www.a.com, ok"
    out = links.link_urls_emails(text, [], {"www_scheme": "http://"})
    hrefs = [o[2] for o in out]
    assert hrefs == ["https://www.eshre.eu/Guidelines", "mailto:info@x.org", "http://www.a.com"]
    assert out[0][3] == [text.index("\n")]  # the line end inside the address is dropped


def test_writer_switches():
    assert writer_switches.sidebar_children_in_para({"container": "sidebar", "block": "list"})
    assert not writer_switches.sidebar_children_in_para({"container": "section", "block": "list"})
    assert writer_switches.nested_list_in_para({"container": "listitem", "block": "list"})
    assert writer_switches.list_in_entry_in_para({"container": "entry", "block": "list"})
    assert writer_switches.no_italic_heading_level3(
        {"container": "section_title", "depth": 3, "span": "italic"}
    )


def test_book_option_switches_its_rule_on():
    class S:
        data = {"options": {"colour_plates": True}}

    profile = _Profile(
        {
            "rules": ["apostrophe_straight"],
            "book_options": {
                "colour_plates": {
                    "type": "boolean",
                    "default": False,
                    "description": "x",
                    "rule": "color_plate_note_removal",
                }
            },
        }
    )
    assert active_rules(profile, S()) == {"apostrophe_straight", "color_plate_note_removal"}
    assert all(r.func.__doc__ for r in RULES.values())


def test_a_page_number_is_never_an_opener_title():
    from book_adapters.engine.outline import is_folio_text

    for folio in ("x", "xii", "XIII", "7", "(14)", "- 9 -", "iv.", "٣", "xvi"):
        assert is_folio_text(folio), folio
    for title in ("Mix", "Foreword", "Preface", "Civil", "IV Contents", "Chapter 3", "", "dim"):
        assert not is_folio_text(title), title


def test_a_numbered_segment_starts_at_its_first_printed_number():
    from book_adapters.engine.outline import printed_start

    # a continuation on a later page: the list started at 10, this segment prints 13 first
    segment = {"start": 10, "items": [{"marker": {"value": 13}}, {"marker": {"value": 14}}]}
    assert printed_start(segment) == 13
    assert printed_start({"start": 1, "items": [{"marker": {"value": 1}}]}) == 1
    assert printed_start({"start": 4, "items": [{"marker": None}]}) == 4  # no printed number
    assert printed_start({"start": None, "items": [{"marker": {"value": None}}]}) is None
