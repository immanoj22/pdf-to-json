"""Step 20 structure rules: letter-spaced sectioning labels, the book's own order of sectioning
words, glossary evidence from the set-off terms, and units that never change writing
direction."""

from types import SimpleNamespace

from book_core.paragraphs.segment import _turned
from book_core.structure.hierarchy import book_role_order
from book_core.structure.navigation import _alphabetical_kind
from book_core.structure.numbering import despaced, numbering, sectioning_word

CONFIG = {"alphabetical_entries": 8, "alphabetical": 0.8, "dated_entries": 0.5,
          "glossary_terms": 0.5}  # fmt: skip


def test_letter_spaced_sectioning_words_are_read_as_words():
    assert despaced("C H A P T E R 4 Title") == "CHAPTER 4 Title"
    assert sectioning_word("SEC TION") == "section"
    assert sectioning_word("C H A P T E R") == "chapter"
    assert sectioning_word("Capítulo 3") == "chapter"
    assert numbering("SEC TION 2")["role_hint"] == "section"
    # Short words that do not spell a sectioning word, and ordinary titles, stay text.
    assert sectioning_word("A B C D") is None
    assert sectioning_word("Part of the book") is None
    assert despaced("I am here") == "I am here"


def _keyword(role, page):
    return {"page": page, "attached": False,
            "numbering": {"kind": "keyword", "role_hint": role}}  # fmt: skip


def test_a_section_word_enclosing_chapters_ranks_above_them():
    items = []
    for _ in range(5):  # five sections, each opening before its chapters
        items.append(_keyword("section", len(items) + 1))
        for _ in range(3):
            items.append(_keyword("chapter", len(items) + 1))
    order = book_role_order(items, {})
    assert order.index("section") < order.index("chapter")


def test_section_words_inside_chapters_stay_unranked():
    items = []
    for _ in range(4):  # "Section 1.2" headings: more of them, opened after their chapter
        items.append(_keyword("chapter", len(items) + 1))
        for _ in range(3):
            items.append(_keyword("section", len(items) + 1))
    assert book_role_order(items, {}) == ["part", "unit", "chapter"]


def _stats(**changes):
    row = {"entries": 25, "alphabetical": 0.95, "dated": 0.0, "locators": 0.0,
           "mean_tokens": 22.0, "terms": 0.9, "term_entries": 22, "term_order": 0.97}  # fmt: skip
    return {**row, **changes}


def test_a_glossary_needs_enough_terms_in_alphabetical_order():
    assert _alphabetical_kind(_stats(), CONFIG) == "glossary"
    # A structured abstract: "Background: Objective: Methods: Results: Conclusion:" reads as
    # term entries, but too few and not in alphabetical order.
    abstract = _stats(entries=10, terms=0.5, mean_tokens=34.0, term_entries=5, term_order=0.5)
    assert _alphabetical_kind(abstract, CONFIG) is None
    assert _alphabetical_kind(_stats(term_order=0.4), CONFIG) is None


def test_a_unit_never_changes_writing_direction():
    flat = SimpleNamespace(rotation=0.0, writing_mode="horizontal")
    turned = SimpleNamespace(rotation=90.0, writing_mode="horizontal")
    skewed = SimpleNamespace(rotation=359.4, writing_mode="horizontal")
    vertical = SimpleNamespace(rotation=0.0, writing_mode="vertical")
    assert _turned(flat, turned)
    assert _turned(flat, vertical)
    assert not _turned(flat, skewed)  # a scanned page's slight skew
