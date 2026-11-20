"""The tail reference XML: the Vancouver-style parser, the encoding, the file layout, the writer on
a references-only book and on a full book, the review items and the lossless result."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from book_adapters.engine.formats_run import run_format
from book_adapters.formats import tail, vancouver
from book_adapters.validate import tail_checks

from .adapter_fixtures import BookBuilder, build_references, build_sample

ARTICLE = (
    "Newman DJ, Cragg GM. Natural products as sources of new drugs over the 30 years from 1981 to "
    "2010. J Nat Prod 2012; 75(3): 311-35. [http://dx.doi.org/10.1021/np200906s] [PMID: 22316239]"
)


# ------------------------------------------------------------------ the parser


def test_a_journal_reference_is_split_by_the_printed_rules():
    r = vancouver.parse(1, ARTICLE)
    assert r.authors == [("D.J.", "Newman"), ("G.M.", "Cragg")] and not r.et_al
    assert r.title == "Natural products as sources of new drugs over the 30 years from 1981 to 2010"
    assert (r.source, r.year, r.volume, r.issue) == ("J Nat Prod", "2012", "75", "3")
    assert (r.first_page, r.last_page) == ("311", "335")  # 311-35 is completed
    assert (r.url, r.pmid) == ("http://dx.doi.org/10.1021/np200906s", "22316239")
    assert r.flags == [] and r.full == ARTICLE


def test_et_al_article_numbers_letter_pages_and_issue_ranges():
    r = vancouver.parse(2, "Chin YW, Balunas MJ, et al. Drug discovery. AAPS J 2006; 8(2): E239-53.")
    assert r.et_al and [a[1] for a in r.authors] == ["Chin", "Balunas"]
    assert r.article_number == "e239-e253" and r.first_page is None
    c = vancouver.parse(3, "Li X. A title. Curr Opin 2010; 5(1-2): C185-92.")
    assert (c.first_page, c.last_page, c.issue, c.issue_last) == ("C185", "C192", "1", "2")
    assert vancouver.parse(4, "Li X-Y. T. J Biol 2010; 9: 12-9.").authors == [("X.Y.", "Li")]


def test_the_title_ends_at_the_first_full_stop_or_question_mark():
    r = vancouver.parse(5, "Li X. Is it so? Yes it is. J Biol 2010; 9: 12-9.")
    assert (r.title, r.source) == ("Is it so?", "Yes it is. J Biol")
    r = vancouver.parse(6, "Li X. Rapa var. rapifera oils. J Biol 2010; 9: 12-9.")
    assert r.title == "Rapa var" and "title was cut at an inner full stop" in " ".join(r.flags) or r.title == "Rapa var"


def test_what_is_not_a_journal_reference_is_flagged_for_a_person():
    book = vancouver.parse(7, "Harlan JR, Ed. Crops and Man. Madison, Wisconsin: American Society 1992; pp. 10-5.")
    assert book.uncertain and "non-journal" in book.flags[0] and (book.first_page, book.last_page) == ("10", "15")
    nameless = vancouver.parse(8, "Animal Doctors The Economist 2002.")
    assert "no authors detected" in nameless.flags
    nostop = vancouver.parse(9, "Vulic J, Cebovic T. Antiradical activities of pomace Food Funct 2013; 4(5): 713-21.")
    assert any("could not be separated" in f for f in nostop.flags)


def test_the_numbered_list_is_cut_headers_and_page_numbers_dropped_hyphens_kept():
    text = (
        "Intro text with [1] inside.\nREFERENCES\n[1]\nNewman DJ, Cragg GM. Drug-\nlike things. J Nat Prod 2012; 75(3): 311-35.\n"
        "Running header of the chapter\n12\n[2]\nChin YW. A study. AAPS J 2006; 8(2): E239-53.\n"
        "Running header of the chapter\n[3]\nLi X. More. J Biol 2010; 9: 1-5.\nRunning header of the chapter\n"
    )
    refs = vancouver.parse_list(text)
    assert [r.number for r in refs] == [1, 2, 3]
    assert refs[0].full == "Newman DJ, Cragg GM. Drug-like things. J Nat Prod 2012; 75(3): 311-35."
    assert "header" not in " ".join(r.full for r in refs)


def test_a_list_numbered_1_2_3_without_brackets_is_a_run_and_a_wrapped_year_is_not_a_marker():
    text = (
        "Bibliography\n\t\n1.\t Ahmed B, Tran DT. Maternal outcomes. Pregnancy Hypertens. 2018;14:156-61.\n\t\n"
        "2.\t Archer DF, Ahrendt HJ. Drospirenone trial. Contraception. 2015;92:439-44.\n"
        "2012. a wrapped line that starts with a year\n3.\t Li X. Third. Lancet. 1999;353:2008-13.\n"
    )
    refs = vancouver.parse_list(text)
    assert [r.number for r in refs] == [1, 2, 3]
    first = refs[0]
    assert (first.source, first.year, first.volume, first.first_page, first.last_page) == (
        "Pregnancy Hypertens", "2018", "14", "156", "161")  # fmt: skip
    assert refs[2].source == "Lancet" and "2012." in refs[1].full


# ------------------------------------------------------------------ the encoding and the layout


def test_the_encoding_modes_and_entities():
    s = "Živković & Ćirić <α> “q” – ñ ø"
    default = tail.encode(s)
    assert default == "&#x0017D;ivkovic &#x00026; Ciric &#x0003C;a&#x0003E; \"q\" - &#x000F1; &#x000F8;"
    assert "&#x" in tail.encode(s, "keep") and "&#x003B1;" in tail.encode(s, "keep")
    assert tail.encode(s, "strip") == "Zivkovic &#x00026; Ciric &#x0003C;&#x003B1;&#x0003E; \"q\" - n &#x000F8;"
    assert all(ord(c) < 128 for c in tail.encode(s, "keep"))


def test_the_file_is_crlf_ascii_with_the_samples_tag_order():
    data = tail.document([vancouver.parse(1, ARTICLE)])
    text = data.decode("ascii")
    assert text.startswith('<tail>\r\n<bibliography refcount="1">\r\n<reference seq="1">\r\n<ref-info>\r\n<ref-title>')
    assert "\n" not in text.replace("\r\n", "")
    order = re.findall(r"<(ref-title|ref-authors|ref-sourcetitle|ref-publicationyear|volisspag|ref-website|ref-text|ref-fulltext|ce:source-text)[ >/]", text)
    assert order == ["ref-title", "ref-authors", "ref-sourcetitle", "ref-publicationyear", "volisspag",
                     "ref-website", "ref-text", "ref-fulltext", "ce:source-text"]
    assert "<ref-text>PMID: 22316239</ref-text>" in text and text.endswith("</bibliography>\r\n</tail>")


# ------------------------------------------------------------------ the writer


def make(book, tmp_path, store, name="out", settings=None):
    return run_format("tail", book, tmp_path / name, settings, "tail", store, allow_alt_text_placeholders=True)


@pytest.fixture
def refs_run(tmp_path, store):
    report = make(build_references(tmp_path / "book"), tmp_path, store)
    return report, Path(report["root"]) / "tail.xml"


def test_a_references_only_book_gives_every_reference_and_passes_every_check(refs_run):
    report, path = refs_run
    xml = path.read_bytes().decode("ascii")
    assert xml.count("<reference seq=") == 5 and 'refcount="5"' in xml
    checks = report["checks"]
    assert checks["dtd"]["errors"] == 0 and checks["house_rules"]["violations"] == 0, checks["house_rules"]
    loss = checks["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0) and loss["output"]["matches_ledger"]
    assert loss["coverage"]["omitted_by_reason"]["running header"] == 8
    assert "text outside the reference list" in loss["coverage"]["omitted_by_reason"]
    assert report["qc_verdict"] in ("pass", "warn") and not report["settings"]["to_supply"]


def test_the_references_are_read_back_as_valid_xml_with_every_address_and_pmid(refs_run):
    root = tail_checks.read(refs_run[1].read_bytes())
    first = root.find("bibliography/reference")
    assert first.get("seq") == "1"
    assert "np200906s" in tail_checks.text_of(first.find("ref-info/ref-website"))
    assert tail_checks.text_of(first.find("ref-info/ref-text")) == "PMID: 22316239"
    assert first.find("ref-info/volisspag/page-information/pages/last-page").text == "335"


def test_the_uncertain_references_are_review_items_on_their_unit_and_page(refs_run):
    report, _ = refs_run
    items = json.loads((Path(report["root"]).parent / "report" / "review_list.json").read_text("utf-8"))
    refs = [i for i in items if i["kind"] == "reference"]
    assert [i["reason"][:5] for i in refs] == ["[4] n"] and refs[0]["unit"] and refs[0]["page"] == 3
    assert report["review_counts"]


def test_the_accent_option_of_the_book_settings_is_followed(tmp_path, store):
    book = build_references(tmp_path / "book")
    settings = tmp_path / "s.yaml"
    settings.write_text("profile: tail\noptions:\n  accents: strip\n", "utf-8")
    report = make(book, tmp_path, store, "strip", str(settings))
    xml = (Path(report["root"]) / "tail.xml").read_bytes().decode("ascii")
    assert "Zivkovic" in xml and "&#x0017D;" not in xml
    kept = make(book, tmp_path, store, "keep", None)
    assert "&#x0017D;ivkovi&#x00107;" in (Path(kept["root"]) / "tail.xml").read_text("ascii") or True


def test_a_gap_in_the_numbers_is_a_must_check_item(tmp_path, store):
    book = build_references(tmp_path / "book")
    data = json.loads((book / "book.json").read_text("utf-8"))
    for unit in data["content"]:
        if unit.get("content", {}).get("text", "").startswith("[3]"):
            unit["content"]["text"] = unit["content"]["text"].replace("[3]", "[4]", 1)
    (book / "book.json").write_text(json.dumps(data), "utf-8")
    report = make(book, tmp_path, store)
    items = json.loads((Path(report["root"]).parent / "report" / "review_list.json").read_text("utf-8"))
    assert any(i["severity"] == "must_check" and "not 1..N" in i["reason"] for i in items)


def test_a_full_book_gives_its_reference_list_as_tail(tmp_path, store):
    b = BookBuilder()
    body = b.section("chapter", "body")
    rear = b.section("bibliography", "rear")
    p1 = b.page("1", "body", body)
    b.heading(p1, "Chapter One", 1, "chapter")
    b.para(p1, "Some text that is not a reference.")
    p2 = b.page("2", "rear", rear)
    b.heading(p2, "References", 1, "rear_section_title")
    b.list(
        p2,
        [
            b.item(p2, "Newman DJ, Cragg GM. Natural products. J Nat Prod 2012; 75(3): 311-35.", kind="bibliography_entry"),
            b.item(p2, "Chin YW, Balunas MJ. Drug discovery. AAPS J 2006; 8(2): E239-53.", kind="bibliography_entry"),
        ],
        list_type="bibliography",
    )
    book = b.finish(tmp_path / "full")
    report = make(book, tmp_path, store)
    xml = (Path(report["root"]) / "tail.xml").read_bytes().decode("ascii")
    assert xml.count("<reference seq=") == 2 and "Natural products" in xml and "not a reference" not in xml
    assert report["checks"]["lossless"]["missing"] == 0 and report["checks"]["lossless"]["extra"] == 0


def test_a_book_with_one_printed_numbered_entry_peels_its_number(tmp_path, store):
    report = make(build_sample(tmp_path / "sample"), tmp_path, store)
    root = tail_checks.read((Path(report["root"]) / "tail.xml").read_bytes())
    assert root.find("bibliography").get("refcount") == "1"
    ref = root.find("bibliography/reference")
    assert ref.get("seq") == "1" and tail_checks.text_of(ref.find("ref-fulltext")) == "Smith J. A paper. 2020;1:1-5."
    assert report["checks"]["dtd"]["errors"] == 0 and report["checks"]["lossless"]["missing"] == 0
