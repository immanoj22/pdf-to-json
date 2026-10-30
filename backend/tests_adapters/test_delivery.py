"""End-to-end delivery on the synthetic book: Jaypee profile, the second test profile,
checks, determinism, book settings."""

from __future__ import annotations

import json
import re

import pytest
from adapter_fixtures import PROFILES, sha_tree
from lxml import etree

from book_adapters.engine.load import load_book
from book_adapters.engine.profile import ProfileError
from book_adapters.engine.run import run_book
from book_adapters.engine.settings import draft_settings, load_settings


@pytest.fixture
def jaypee_run(sample_book, tmp_path, store, settings_file):
    report = run_book(sample_book, tmp_path / "out", settings_file, None, store)
    root = tmp_path / "out" / "9780306406157"
    return report, root, etree.parse(str(root / "9780306406157.xml")).getroot()


def test_checks_pass(jaypee_run):
    report, _, _ = jaypee_run
    checks = report["checks"]
    assert checks["dtd"]["errors"] == 0, checks["dtd"]
    failed = {k: v for k, v in checks["house_rules"]["checks"].items() if v["violations"]}
    assert not failed, failed
    lossless = checks["lossless"]
    assert (lossless["missing"], lossless["extra"]) == (0, 0), lossless["coverage"]
    assert lossless["order"]["undeclared_out_of_order"] == 0, lossless["order"]
    assert lossless["output"]["matches_ledger"]


def test_layout_and_page_info(jaypee_run):
    _, root, _ = jaypee_run
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*.xml"))
    assert files == [
        "9780306406157.xml",
        "Chapters/ch1.xml",
        "Chapters/front.xml",
        "Chapters/index.xml",
        "page_info.xml",
    ]
    main = (root / "9780306406157.xml").read_text("utf-8")
    assert main.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!--<!DOCTYPE book PUBLIC')
    ch1 = (root / "Chapters/ch1.xml").read_text("utf-8")
    assert ch1.startswith('<part id="prt1" label="SECTION 1">')  # opens its part
    info = (root / "page_info.xml").read_text("utf-8")
    assert "<chnumber>ch1</chnumber>" in info and "<firstpage>2</firstpage>" in info
    assert "<lastpage>3</lastpage>" in info


def test_ids_roles_labels(jaypee_run):
    _, _, book = jaypee_run
    chapter = book.find(".//chapter")
    assert (chapter.get("id"), chapter.get("label")) == ("ch1", "CHAPTER 1")
    sections = book.findall(".//section")
    assert [s.get("id") for s in sections] == ["ch1lev1sec1", "ch1lev2sec1"]
    assert [s.find("title").get("role") for s in sections] == ["ch1lev1sect1", "ch1lev2sect1"]
    assert all(s.get("label") is None for s in sections)  # item 5.2
    table = book.find(".//table")
    assert (table.get("id"), table.get("label"), table.get("frame")) == (
        "ch1tbl1",
        "Table 1",
        "all",
    )
    assert table.find("title").get("role") == "ch1tblt1"
    assert book.find(".//bibliography").get("id") == "ch1bib"
    assert book.find(".//bibliomixed").get("id") == "ch1bib1"


def test_figure_vs_informalfigure(jaypee_run):
    _, root, book = jaypee_run
    figure = book.find(".//figure")
    assert (figure.get("id"), figure.get("label")) == ("ch1fig1", "Fig. 1")
    assert figure.find("title").get("role") == "ch1figt1"
    assert "".join(figure.find("title").itertext()) == "A labelled drawing."
    assert figure.find(".//phrase").text == "(no image)"  # placeholder + review
    assert (
        book.find(".//figure//imagedata").get("fileref")
        == "XML/9780306406157/Chapters/images/2-1.jpg"
    )
    assert sorted(p.name for p in (root / "Chapters/bigimages").iterdir()) == ["2-1.jpg"]
    assert book.find(".//informalfigure") is None  # opener artwork is not delivered


def test_anchors(jaypee_run):
    _, _, book = jaypee_run
    part_title = book.find(".//part/title")
    assert part_title.find("anchor").attrib == {"id": "page1", "role": "first"}
    chapter_title = book.find(".//chapter/title")
    assert chapter_title.find("anchor").attrib == {"id": "page2", "role": "first"}
    for section in book.iter("section"):
        assert section.find("title").find("anchor") is None  # item 8
    ids = [a.get("id") for a in book.iter("anchor")]
    assert ids == ["pageFM4", "pageFM3", "pageFM5", "page1", "page2", "page3", "page4"] or len(
        ids
    ) == len(set(ids))
    para = next(p for p in book.iter("para") if "continues" in "".join(p.itertext()))
    assert para.find("anchor").get("id") == "page3"  # inside the joined paragraph
    assert "intervention continues" in "".join(para.itertext())


def test_list_marks_and_nesting(jaypee_run):
    _, _, book = jaypee_run
    lists = book.findall(".//itemizedlist")
    assert lists and all(x.get("mark") == "square" for x in lists)  # ■ (item 7)
    for sidebar in book.iter("sidebar"):
        assert not any(a.tag in ("itemizedlist", "orderedlist") for a in sidebar.iterancestors())


def test_entities_and_characters(jaypee_run):
    _, root, _ = jaypee_run
    raw = (root / "9780306406157.xml").read_text("utf-8")
    assert "Smith &#x0026; Sons &#x003C;publisher&#x003E; said &#x0027;hello&#x0027;." in raw
    assert "world&#x0027;s" in raw  # item 18
    assert "&#x2212;10&#x00B0;C" in raw  # item 10: minus
    assert "2010&#x2013;2020" in raw  # range stays en dash
    assert not re.search(r"&(lt|gt|amp|apos|quot);", raw)
    assert all(ord(c) < 128 for c in raw)


def test_links(jaypee_run):
    _, _, book = jaypee_run
    urls = [u.get("url") for u in book.iter("ulink")]
    assert "#ch1fig1" in urls and "#ch1tbl1" in urls and "#ch1bib1" in urls


def test_index_links(jaypee_run):
    _, _, book = jaypee_run
    index = book.find(".//index")
    links = [(u.get("url"), "".join(u.itertext())) for u in index.iter("ulink")]
    assert ("#page2", "2f") in links  # item 36: suffix inside the link
    assert ("#page3", "3–4") in links  # item 9: en dash range
    assert index.find("indexdiv/title").text == "A"
    assert index.find(".//secondaryie") is not None


def test_empty_table_entry_self_closed(jaypee_run):
    _, root, _ = jaypee_run
    raw = (root / "9780306406157.xml").read_text("utf-8")
    assert '<entry colname="2" align="left" valign="top"/>' in raw  # item 21


def test_report_records_profile_and_hash(jaypee_run):
    report, _, _ = jaypee_run
    prof = report["profile"]
    assert prof["profile"] == "jaypee_v3" and prof["version"] == "3.0.0"
    assert prof["file_sha256"] and prof["resolved_sha256"] and prof["status"] == "builtin"


def test_deterministic(sample_book, tmp_path, store, settings_file):
    run_book(sample_book, tmp_path / "a", settings_file, None, store)
    run_book(sample_book, tmp_path / "b", settings_file, None, store)
    assert sha_tree(tmp_path / "a" / "9780306406157") == sha_tree(tmp_path / "b" / "9780306406157")
    assert (tmp_path / "a/report/delivery_report.json").read_bytes() == (
        tmp_path / "b/report/delivery_report.json"
    ).read_bytes()


def test_other_client_profile_changes_patterns(sample_book, tmp_path, store, settings_file):
    report = run_book(
        sample_book, tmp_path / "o", settings_file, str(PROFILES / "_test/other_client.yaml"), store
    )
    root = tmp_path / "o" / "book-9780306406157"
    book = etree.parse(str(root / "book.xml")).getroot()
    assert book.find(".//chapter").get("id") == "chap1"
    assert book.find(".//chapter").get("label") == "Chapter 1"
    assert book.find(".//part").get("id") == "pt1"
    assert [s.get("id") for s in book.iter("section")] == ["c1_s1_1", "c1_s2_1"]
    assert book.find(".//figure").get("id") == "c1_fig1"
    assert book.find(".//figure").get("label") == "Figure 1"
    assert book.find(".//figure//imagedata").get("fileref") == "media/img_p7_1.png"
    assert (root / "media/img_p7_1.png").exists() and not (root / "Chapters").exists()
    assert (root / "parts/chap1.xml").exists() and not (root / "page_info.xml").exists()
    assert "jaypee" not in (root / "book.xml").read_text("utf-8").lower()
    assert report["checks"]["dtd"]["errors"] == 0
    assert report["checks"]["lossless"]["missing"] == 0
    assert report["profile"]["status"] == "untested"
    assert any("untested" in w for w in report["warnings"])


def test_uploaded_profile_hash_in_report(sample_book, tmp_path, store, settings_file):
    path = tmp_path / "mine.yaml"
    path.write_text(
        (PROFILES / "_test/other_client.yaml")
        .read_text("utf-8")
        .replace("profile: other_client", "profile: mine"),
        "utf-8",
    )
    report = run_book(sample_book, tmp_path / "m", settings_file, str(path), store)
    import hashlib

    assert report["profile"]["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    saved = json.loads((tmp_path / "m/report/delivery_report.json").read_text("utf-8"))
    assert saved["profile"]["ref"] == "mine@0.1.0#r1"


def test_settings_missing_isbn_listed_to_supply(sample_book, tmp_path, store):
    path = tmp_path / "s.yaml"
    path.write_text("profile: jaypee_v3\ntitle: X\n", "utf-8")
    report = run_book(sample_book, tmp_path / "x", path, None, store)
    assert "isbn" in report["settings"]["to_supply"]
    assert (tmp_path / "x" / "ISBN_TO_SUPPLY").exists()
    assert any("ISBN" in w or "isbn" in w for w in report["warnings"])


def test_settings_reject_bad_isbn_and_unknown_option(tmp_path, store):
    profile, _ = store.load("jaypee_v3")
    path = tmp_path / "s.yaml"
    path.write_text(
        "profile: jaypee_v3\nisbn: '9780306406158'\noptions:\n  colour_plate: true\n", "utf-8"
    )
    with pytest.raises(ProfileError) as exc:
        load_settings(path, profile)
    text = str(exc.value)
    assert "check digit" in text and "colour_plates" in text


def test_draft_reads_printed_isbn_and_never_invents(sample_book):
    data, missing = draft_settings(load_book(sample_book).data, "jaypee_v3")
    assert data["isbn"] == "9780306406157" and "page 3" in data["sources"]["isbn"]
    assert data["edition"] == "First Edition: 2026"
    assert "authorgroups" in missing
    book = load_book(sample_book).data
    for unit in book["content"]:
        if unit.get("content") and "ISBN" in unit["content"]["text"]:
            unit["content"]["text"] = "ISBN: 978-0-306-40615-8"  # bad check digit
    data, missing = draft_settings(book, "jaypee_v3")
    assert data["isbn"] is None and "isbn" in missing


def test_fallbacks_do_nothing_when_headings_exist(jaypee_run):
    report, root, _ = jaypee_run
    reviews = json.loads((root.parent / "report/review.json").read_text("utf-8"))
    inferred = [r for r in reviews if r["kind"] == "adapter-inferred"]
    # the chapter has a Stage 1 heading: no chapter inference; the part has none: inferred
    assert [r["rule"] for r in inferred] == ["outline.opener"]
    assert "part start" in inferred[0]["message"]


def test_toc_fallback_supplies_chapter_and_title(sample_book, tmp_path, store, settings_file):
    data = json.loads((sample_book / "book.json").read_text("utf-8"))
    for unit in data["content"]:
        if unit.get("role") == "chapter":
            unit["role"] = "section"  # Stage 1 found no chapter heading
            unit["content"]["text"] = "Opening words"
    (sample_book / "book.json").write_text(json.dumps(data), "utf-8")
    report = run_book(sample_book, tmp_path / "t", settings_file, None, store)
    book = etree.parse(str(tmp_path / "t/9780306406157/9780306406157.xml")).getroot()
    chapter = book.find(".//chapter")
    assert chapter.get("id") == "ch1"
    assert "".join(chapter.find("title").itertext()) == "The First Chapter"
    reviews = json.loads((tmp_path / "t/report/review.json").read_text("utf-8"))
    rules = {r["rule"] for r in reviews if r["kind"] == "adapter-inferred"}
    assert {"outline.toc", "outline.toc_title"} <= rules
    assert report["checks"]["lossless"]["missing"] == 0
