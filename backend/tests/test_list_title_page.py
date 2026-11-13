"""A page that ends with a numbered list after running text is judged as a list from the unit
before the list on (structure.navigation._from_list_title). Layout evidence only: no title
words, so it works in any language."""

from book_core.structure.navigation import _from_list_title


def unit(text):
    return {"text": text, "tokens": len(text.split()), "letters": sum(c.isalpha() for c in text)}


def test_a_chapter_page_ending_with_numbered_references_is_read_from_the_list():
    units = [unit("Documentation and auditing: keep records."), unit("CONCLUSION"),
             unit("Quality control is a cycle of vigilance."), unit("BIBLIOGRAFIA"),
             unit("1. Esfandiari N. Impact. 2017."), unit("2. Gardner DK. Impact. 2014."),
             unit("3. Magli MC. Morphology. 2016.")]
    page = {"page": 31, "units": units}
    assert [u["text"] for u in _from_list_title(page)["units"]][0] == "BIBLIOGRAFIA"


def test_pages_without_a_closing_numbered_list_or_with_only_its_title_are_unchanged():
    whole = {"page": 1, "units": [unit("Riferimenti"), unit("1. A"), unit("2. B")]}
    prose = {"page": 2, "units": [unit("Some text."), unit("More text."), unit("1. A")]}
    broken = {"page": 3, "units": [unit("Text."), unit("Title"), unit("1. A"), unit("3. C")]}
    for page in (whole, prose, broken):
        assert _from_list_title(page) is page
