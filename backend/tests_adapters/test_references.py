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
    conv.reviews = []
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


# ------------------------------------------------------------------ the AOSIS pattern


def seq(text):
    p = parse_reference(text)
    if p is None:
        return None
    return p["pub_type"], [(k, text[a:b]) for k, (a, b) in p["sequence"]], p


ARTICLE = ("Abdullah Sani, H.A. & Jaafar, N.I., 2025, ‘A bibliometric analysis of IoT in the public sector’, "
           "Journal of Science and Technology Policy Management 16(6), 977–1110. https://doi.org/10.1108/JSTPM-04-2024-0154")
CHAPTER = ("Bajpai, N. & Singh, S., 2024, ‘Ethics in a modern technological world’, in R.K. Kushwaha, P.K. Yadav & A. Devi (eds.), "
           "Ethical frameworks in special education: A guide for researchers, vol. 2, pp. 62–78, Blue rosé Publishers, New Delhi.")


def test_an_aosis_article_with_issue_pages_and_a_doi():
    kind, parts, p = seq(ARTICLE)
    assert kind == "journal" and dict(parts)["volume"] == "16" and dict(parts)["issue"] == "6"
    assert (dict(parts)["fpage"], dict(parts)["lpage"]) == ("977", "1110")
    assert dict(parts)["source"] == "Journal of Science and Technology Policy Management"
    assert dict(parts)["doi"].endswith("JSTPM-04-2024-0154") and dict(parts)["year"] == "2025"
    assert [ARTICLE[a:b] for (a, b), _ in p["authors"]] == ["Abdullah Sani", "Jaafar"]


def test_an_aosis_book_chapter_has_editors_pages_publisher_and_city():
    kind, parts, p = seq(CHAPTER)
    d = dict(parts)
    assert kind == "book" and d["chapter-title"] == "Ethics in a modern technological world"
    assert d["source"].startswith("Ethical frameworks") and d["volume"] == "2"
    assert (d["fpage"], d["lpage"], d["publisher-name"], d["publisher-loc"]) == ("62", "78", "Blue rosé Publishers", "New Delhi")
    assert [CHAPTER[a:b] for (a, b), _ in p["editors"]] == ["Kushwaha", "Yadav", "Devi"]


def test_aosis_reports_et_al_and_what_does_not_fit():
    kind, parts, p = seq("United Nations, 2024, E-government survey 2024, viewed 30 November 2024, from https://x.org/a.pdf.")
    assert kind == "report" and p["collab"] and dict(parts)["uri"] == "https://x.org/a.pdf"
    _, _, q = seq("Page, M.J., Boutron, I. et al., 2021, ‘The PRISMA statement’, Research Methods 10(89), 1–11.")
    assert q["etal"]
    # not a reference of this pattern: no year, or text after the pages that is not a link
    assert parse_reference("Some free text without a year or any pattern at all.") is None
    assert parse_reference("Smith, J., 2020, ‘A title’, Journal 3(1), 1–5, and some other words.") is None


def test_an_unparsed_reference_is_a_review_item_and_the_doi_loses_line_end_spaces():
    conv = JatsBase.__new__(JatsBase)
    conv.refs_total = conv.refs_structured = 0
    conv.reviews = []
    bad = etree.fromstring("<ref><mixed-citation>References and nothing else</mixed-citation></ref>")
    conv.structure_reference(bad, bad.find("mixed-citation"))
    assert [r.kind for r in conv.reviews] == ["reference"] and "not structured" in conv.reviews[0].message
    good = etree.fromstring("<ref><mixed-citation>" + ARTICLE.replace("&", "&amp;").replace("https://doi.org/", "https://doi. org/") + "</mixed-citation></ref>")
    conv.structure_reference(good, good.find("mixed-citation"))
    ec = good.find("citation-alternatives/element-citation")
    assert ec.findtext("pub-id") == "10.1108/JSTPM-04-2024-0154" and ec.get("publication-type") == "journal"
    assert ec.findtext("issue") == "6"


def test_zero_width_spaces_leave_the_text_and_the_link_addresses(tmp_path, store):
    from .test_adapter_b import assert_lossless, base_book, export

    b, pages = base_book()
    text = "See https://example.org/a/​b​c.html for more."
    start = text.index("https")
    b.para(pages[0], text, spans=[{"kind": "link", "start": start, "end": start + 29, "href": "https://example.org/a/​b​c.html"}])
    report, _, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    out = etree.tostring(xml, encoding="unicode")
    assert "​" not in out and "https://example.org/a/bc.html" in out
    assert_lossless(report)



def test_the_book_option_writes_structured_references_in_bits_and_jats(tmp_path, store, settings_file):
    import re

    from book_adapters.engine.formats_run import run_format

    from .adapter_fixtures import BookBuilder

    def book(path):
        b = BookBuilder()
        s = b.section("chapter", "body")
        p1 = b.page("1", "body", s)
        b.heading(p1, "Chapter title", 1, "chapter")
        b.para(p1, "Words of the chapter alpha beta.")
        b.heading(p1, "REFERENCES", 2, "section")
        marker = lambda n: {"text": f"{n}.", "type": "decimal", "value": n, "punctuation": "period"}  # noqa: E731
        items = [b.item(p1, ARTICLE, marker=marker(1), kind="bibliography_entry"),
                 b.item(p1, CHAPTER, marker=marker(2), kind="bibliography_entry"),
                 b.item(p1, "Just some words that are not any known reference pattern.", marker=marker(3),
                        kind="bibliography_entry")]  # fmt: skip
        b.list(p1, items, list_type="bibliography", marker_type="decimal")
        return b.finish(path)

    for fmt, profile in (("bits", "bits_base"), ("jats", "jats_base")):
        for on in (False, True):
            out = tmp_path / f"{fmt}{on}"
            settings = tmp_path / f"s{fmt}{on}.yaml"
            settings.write_text(settings_file.read_text("utf-8") + ("options:\n  structured_references: true\n" if on else ""), "utf-8")
            report = run_format(fmt, book(tmp_path / f"b{fmt}{on}"), out, settings, profile, store,
                                allow_alt_text_placeholders=True)  # fmt: skip
            data = next(out.rglob("*.xml")).read_text("utf-8")
            assert len(re.findall("<citation-alternatives>", data)) == (2 if on else 0), (fmt, on)
            assert report["checks"]["dtd"]["errors"] == 0, (fmt, on, report["checks"]["dtd"])
            loss = report["checks"]["lossless"]
            assert (loss["missing"], loss["extra"]) == (0, 0)
            review = " ".join(str(r) for r in (report.get("reviews") or []))
            reviews = next(out.rglob("review_list.json"), None)
            text = reviews.read_text("utf-8") if reviews else review
            assert ("not structured" in text) == on, (fmt, on)
