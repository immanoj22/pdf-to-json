"""Structured references: the pattern the book prints, and what is left as printed."""

from __future__ import annotations

from lxml import etree

from book_adapters.formats.jatsbase import JatsBase
from book_adapters.formats.refparse import parse_reference


def cut(text):
    """The parts of a reference as strings (the parser returns positions in the text)."""
    p = parse_reference(text)
    if p is None:
        return None
    at = lambda sp: text[sp[0] : sp[1]] if sp else None  # noqa: E731
    out = {k: at(v) for k, v in p.items() if k != "authors"}
    out["authors"] = [(at(a), at(g)) for a, g in p["authors"]]
    return out


def test_a_printed_article_reference_is_split_into_its_parts():
    p = cut(
        "Behrens, S. H. and Borkovec, M. Electrostatic interaction of colloidal surfaces with "
        "variable charge. (1999) J. Phys. Chem. B 103, pp. 2918–2928."
    )
    assert p["authors"] == [("Behrens", "S. H."), ("Borkovec", "M.")]
    assert p["title"] == "Electrostatic interaction of colloidal surfaces with variable charge"
    assert (p["year"], p["source"], p["volume"], p["fpage"], p["lpage"]) == (
        "1999", "J. Phys. Chem. B", "103", "2918", "2928")  # fmt: skip


def test_three_authors_a_single_page_and_a_volume_without_pages():
    p = cut("Lin, S., Chen, X. and Wang, Z. L. A title. (2022) Chem. Rev. 122, pp. e2409998.")
    assert [a[0] for a in p["authors"]] == ["Lin", "Chen", "Wang"] and p["fpage"] == "e2409998" and p["lpage"] is None
    q = cut("Chen, J. and Lee, P. S. A title. (2020) Adv. Energy Mater. 11.")
    assert (q["volume"], q["fpage"], q["source"]) == ("11", None, "Adv. Energy Mater.")


def test_what_does_not_fit_stays_as_printed():
    assert cut("Marcus, Y. Ion Solvation. (1985) Wiley.") is None  # a book: publisher only
    assert cut("References") is None
    assert cut("Smith J. A paper. 2020;1:1–5.") is None


def test_structure_reference_adds_the_parts_beside_the_printed_text_and_only_when_it_fits():
    conv = JatsBase.__new__(JatsBase)
    conv.refs_total = conv.refs_structured = 0
    text = "Lin, S. T. Title here. (2022) Chem. Rev. 122, pp. 5209–5232."
    ok = etree.fromstring(f"<ref><label>1.</label><mixed-citation>Lin, S. T. Title here. (2022) <italic>Chem. Rev.</italic> <bold>122</bold>, pp. 5209–5232.</mixed-citation></ref>")
    conv.structure_reference(ok, ok.find("mixed-citation"))
    alt = ok.find("citation-alternatives")
    assert alt is not None and [c.tag for c in alt] == ["mixed-citation", "element-citation"]
    assert "".join(alt.find("mixed-citation").itertext()) == text.replace("Chem. Rev. 122", "Chem. Rev. 122")  # printed text kept
    ec = alt.find("element-citation")
    assert [e.tag for e in ec] == ["person-group", "article-title", "year", "source", "volume", "fpage", "lpage"]
    assert ec.findtext("person-group/name/surname") == "Lin" and ec.findtext("person-group/name/given-names") == "S. T."
    assert (ec.findtext("source"), ec.findtext("volume"), ec.findtext("fpage"), ec.findtext("lpage")) == ("Chem. Rev.", "122", "5209", "5232")
    assert ok.find("label").text == "1."
    bad = etree.fromstring("<ref><mixed-citation>References</mixed-citation></ref>")
    conv.structure_reference(bad, bad.find("mixed-citation"))
    assert bad.find("mixed-citation") is not None and bad.find("citation-alternatives") is None
    assert (conv.refs_structured, conv.refs_total) == (1, 2)
