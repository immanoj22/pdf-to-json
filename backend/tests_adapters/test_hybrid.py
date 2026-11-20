"""The two readers of a reference (the trained parser and the rules), the validators that choose,
the mapping of the parser's record, and the training file."""

from __future__ import annotations

import json
import os

import pytest

from book_adapters import refmodel
from book_adapters.formats import anystyle, hybrid, tail, vancouver

IEEE = 'B. J. Martin and D. G. Altman., “Statistics notes: measurement error”, BMJ., vol. 313, no. 7059, 1996.'
IEEE_RECORD = {
    "author": [{"family": "Martin", "given": "B.J."}, {"family": "Altman", "given": "D.G."}],
    "title": ["Statistics notes: measurement error”"], "volume": ["313"], "issue": ["7059"],
    "date": ["1996"], "container-title": ["BMJ"], "type": "article-journal",
}  # fmt: skip
VANCOUVER = "Newman DJ, Cragg GM. Natural products as sources of new drugs. J Nat Prod 2012; 75(3): 311-35."
VANCOUVER_RECORD = {
    "author": [{"family": "Newman", "given": "D.J."}, {"family": "Cragg", "given": "G.M."}],
    "title": ["Natural products as sources of new drugs"], "container-title": ["J Nat Prod"], "date": ["2012"],
    "volume": ["75"], "issue": ["3"], "pages": ["311–35"], "type": "article-journal",
}  # fmt: skip


def test_the_parsers_record_becomes_a_structured_reference():
    r = anystyle.to_reference(1, IEEE, IEEE_RECORD)
    assert r.authors == [("B.J.", "Martin"), ("D.G.", "Altman")] and r.title == "Statistics notes: measurement error"
    assert (r.source, r.year, r.volume, r.issue, r.engine) == ("BMJ", "1996", "313", "7059", "anystyle")
    assert hybrid.problems(r) == []
    p = anystyle.to_reference(2, VANCOUVER, VANCOUVER_RECORD)
    assert (p.first_page, p.last_page) == ("311", "335")
    d = anystyle.to_reference(3, "x", {**IEEE_RECORD, "doi": ["10.1007/s1"], "pmid": ["12"], "author": [{"family": "A", "given": "Joseph F."}, {"others": True}]})
    assert d.url == "http://dx.doi.org/10.1007/s1" and d.pmid == "12" and d.authors == [("J.F.", "A")] and d.et_al


def test_an_ieee_reference_the_rules_cannot_read_is_read_by_the_trained_parser_without_a_flag():
    r = hybrid.resolve(1, IEEE, IEEE_RECORD)
    assert r.engine == "anystyle" and r.flags == [] and r.source == "BMJ" and r.volume == "313"
    xml = tail.document([r]).decode("ascii")
    assert "<ref-titletext-english>Statistics notes: measurement error</ref-titletext-english>" in xml
    assert "<ce:initials>B.J.</ce:initials>" in xml and "<vol-first>313</vol-first>" in xml and "<iss-first>7059</iss-first>" in xml


def test_both_readers_agree_the_rules_reading_is_used_without_a_flag():
    r = hybrid.resolve(1, VANCOUVER, VANCOUVER_RECORD)
    assert r.engine == "rules" and r.flags == [] and (r.first_page, r.last_page) == ("311", "335")


def test_a_disagreement_on_the_authors_is_a_review_item_never_silent():
    other = {**VANCOUVER_RECORD, "author": [{"family": "Smith", "given": "J."}]}
    r = hybrid.resolve(1, VANCOUVER, other)
    assert r.flags and "disagree on authors" in r.flags[0]


def test_what_fails_the_validators_is_flagged_and_a_one_letter_source_is_never_written():
    bad = {**IEEE_RECORD, "container-title": ["B"], "author": [{"family": "R", "given": "A.Calinger"}]}
    r = hybrid.resolve(1, IEEE, bad)
    assert r.flags and any("not confident" in f for f in r.flags)
    assert any("not a title" in p for p in hybrid.problems(anystyle.to_reference(1, IEEE, bad)))
    year = {**IEEE_RECORD, "date": ["Brooks/Cole, 19"]}
    assert "no valid year" in hybrid.problems(anystyle.to_reference(1, IEEE, year))
    ident = {**IEEE_RECORD, "container-title": ["PMC 5290745, PMID 28155863"]}
    assert any("identifier" in p for p in hybrid.problems(anystyle.to_reference(1, IEEE, ident)))


def test_an_organisation_is_the_author_when_the_words_before_the_title_look_like_a_name():
    text = "National Institute for Health and Care Excellence. Hypertension in adults: diagnosis and management. NICE guideline. 2023."
    rec = {"title": ["National Institute for Health and Care Excellence. Hypertension in adults: diagnosis and management"],
           "container-title": ["NICE guideline"], "date": ["2023"], "type": "article-journal", "volume": ["9"]}  # fmt: skip
    r = hybrid.organisation(anystyle.to_reference(1, text, rec))
    assert r.authors == [(None, "National Institute for Health and Care Excellence")]
    assert r.title == "Hypertension in adults: diagnosis and management"


def test_without_the_trained_parser_the_rules_read_alone_and_flag_what_fails(monkeypatch):
    monkeypatch.delenv(anystyle.COMMAND_ENV, raising=False)
    assert anystyle.parse_many([IEEE]) is None
    ok = hybrid.resolve_all([(1, VANCOUVER)])[0]
    assert ok.flags == [] and ok.engine == "rules"
    bad = hybrid.resolve_all([(2, IEEE)])[0]
    assert bad.flags  # nothing is written silently


@pytest.mark.skipif(not os.environ.get(anystyle.COMMAND_ENV), reason="the trained parser is not set up")
def test_the_real_trained_parser_reads_an_ieee_reference():
    r = hybrid.resolve_all([(1, IEEE)])[0]
    assert r.engine == "anystyle" and r.source == "BMJ" and r.flags == []


# ------------------------------------------------------------------ training data


def test_a_corrected_reference_is_kept_once_with_its_job_and_can_be_deleted(tmp_path):
    ref = anystyle.to_reference(1, VANCOUVER, VANCOUVER_RECORD)
    assert refmodel.record(tmp_path, "job1", ref) is True
    assert refmodel.record(tmp_path, "job1", ref) is False  # once per job
    assert refmodel.record(tmp_path, "job2", ref) is True
    rows = refmodel.read(tmp_path)
    assert [r["job"] for r in rows] == ["job1", "job2"] and rows[0]["text"] == VANCOUVER
    assert refmodel.delete_job(tmp_path, "job1") == 1
    assert [r["job"] for r in refmodel.read(tmp_path)] == ["job2"]


def test_the_training_xml_labels_every_part_of_the_printed_text(tmp_path):
    ref = anystyle.to_reference(1, VANCOUVER, VANCOUVER_RECORD)
    ref.first_page, ref.last_page = "311", "335"
    refmodel.record(tmp_path, "j", ref)
    xml, count = refmodel.training_xml(tmp_path)
    assert count == 1 and "<author>Newman DJ, Cragg GM.</author>" in xml
    assert "<title>Natural products as sources of new drugs.</title>" in xml and "<container-title>J Nat Prod</container-title>" in xml
    assert "<volume>" in xml and "<date>" in xml


def test_retrain_needs_the_parser_and_samples(tmp_path, monkeypatch):
    monkeypatch.delenv(anystyle.COMMAND_ENV, raising=False)
    with pytest.raises(RuntimeError, match="not set up"):
        refmodel.retrain(tmp_path)


def test_the_training_folder_is_outside_git():
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    assert "reference_training/" in open(os.path.join(root, ".gitignore")).read()


def test_a_reference_list_is_read_in_one_parser_call_for_bits_and_jats(monkeypatch):
    from lxml import etree

    from book_adapters.formats.jatsbase import JatsBase

    calls = []
    book = {"author": [{"family": "Smith", "given": "J."}], "title": ["A tale of two cities in the north"],
            "publisher": ["Penguin"], "date": ["1999"], "type": "book"}  # fmt: skip
    records = {IEEE: IEEE_RECORD, "Smith J. A tale of two cities in the north. London: Penguin; 1999.": book}

    def fake(texts, model=None, timeout=600):
        calls.append(list(texts))
        return [records.get(t, {}) for t in texts]

    monkeypatch.setattr(anystyle, "parse_many", fake)
    conv = JatsBase.__new__(JatsBase)
    conv.refs_total = conv.refs_structured = 0
    conv.reviews = []
    pending = []
    for text in (IEEE, "Smith J. A tale of two cities in the north. London: Penguin; 1999.", "References and nothing else"):
        ref = etree.fromstring(f"<ref><mixed-citation>{text}</mixed-citation></ref>")
        pending.append((ref, ref.find("mixed-citation")))
    conv.structure_references(pending)
    assert len(calls) == 1 and len(calls[0]) == 3  # one call for the whole list
    assert conv.refs_structured == 2 and conv.refs_total == 3
    ec = pending[0][0].find("citation-alternatives/element-citation")
    assert ec.findtext("source") == "BMJ" and ec.findtext("volume") == "313"
    assert any("not structured" in r.message for r in conv.reviews)
