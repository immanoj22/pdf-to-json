"""Adapter B: index locators and ranges, web/e-mail links, character changes in the ledger,
authors from the title page, structure fixes, QC report, review list, compare and
``profile test``. Each test builds a small synthetic book."""

from __future__ import annotations

import json

from lxml import etree

from book_adapters.cli import main
from book_adapters.compare import compare_deliveries
from book_adapters.engine.ledger import Ledger
from book_adapters.engine.run import run_book
from book_adapters.validate.lossless import character_changes

from .adapter_fixtures import BookBuilder

ISBN = "9780306406157"


def settings(tmp_path, authors=True) -> str:
    path = tmp_path / "settings.yaml"
    text = f"isbn: '{ISBN}'\ntitle: A Test Book\nedition: First Edition\nprofile: jaypee_v3\n"
    if authors:
        text += "authorgroups:\n  - - firstname: Ann\n      surname: Author\n"
    path.write_text(text, "utf-8")
    return str(path)


def export(book, tmp_path, store, authors=True):
    out = tmp_path / "out"
    report = run_book(book, out, settings(tmp_path, authors), None, store,
                      allow_alt_text_placeholders=True)  # fmt: skip
    root = out / ISBN
    return report, root, etree.parse(str(root / f"{ISBN}.xml")).getroot()


def assert_lossless(report):
    loss = report["checks"]["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0), loss["coverage"]
    assert loss["output"]["matches_ledger"], loss["output"]
    assert loss["character_changes"]["unexplained"] == 0, loss["character_changes"]
    assert loss["order"]["undeclared_out_of_order"] == 0, loss["order"]
    assert report["checks"]["dtd"]["errors"] == 0, report["checks"]["dtd"]


def base_book():
    b = BookBuilder()
    secs = {k: b.section(k, z) for k, z in (("title_page", "front"), ("chapter", "body"))}
    p = b.page("i", "front", secs["title_page"])
    b.heading(p, "A Test Book", 1, "book_title")
    pages = [b.page(str(n), "body", secs["chapter"]) for n in (1, 2, 3)]
    b.heading(pages[0], "The First Chapter", 1, "chapter")
    return b, pages


# --------------------------------------------------------------------------- index


def index_book(tmp_path):
    b, pages = base_book()
    b.para(pages[0], "Body text on the first page.")
    idx = b.section("index", "rear")
    pi = b.page("4", "rear", idx)
    b.heading(pi, "Index", 1, "rear_section_title")
    note = "Page numbers followed by f refer to figure and t refer to table."
    b.list(
        pi,
        [
            b.item(pi, note, kind="index_entry", level=1),
            b.item(pi, "Abdomen  1, 2", kind="index_entry", level=1, locators=[
                {"kind": "page", "start": 9, "end": 10, "label": "1", "target_page": pages[0],
                 "confidence": 0.9},
                {"kind": "page", "start": 12, "end": 13, "label": "2", "target_page": pages[1],
                 "confidence": 0.9}]),
            # Stage 1 gave no locators, and two sub-entries in one item
            b.item(pi, "four quadrants of  2f, 3t\nnine regions of  3f", kind="index_entry",
                   level=2),
            b.item(pi, "Achondroplasia  1–3", kind="index_entry", level=1, locators=[
                {"kind": "range", "start": 16, "end": 19, "label": "1", "end_label": "3",
                 "target_page": pages[0], "end_target_page": pages[2], "confidence": 0.9}]),
        ],
        list_type="index",
    )  # fmt: skip
    return b.finish(tmp_path / "book")


def test_index_locators_inferred_lines_split_ranges_and_note(tmp_path, store):
    report, root, xml = export(index_book(tmp_path), tmp_path, store)
    assert_lossless(report)
    index = xml.find(".//index")
    # the note is a para before the first letter (delivery: aligncenter)
    note = index.find("para")
    assert note.get("role") == "aligncenter" and "Page numbers" in "".join(note.itertext())
    second = [" ".join("".join(e.itertext()).split()) for e in index.iter("secondaryie")]
    assert second == ["four quadrants of 2f, 3t", "nine regions of 3f"]
    links = {(u.get("url"), etree.tostring(u, encoding="unicode", with_tail=False))
             for u in index.iter("ulink")}  # fmt: skip
    # item 36: the f/t suffix is inside the link (adapter-inferred locators)
    assert any(url == "#page2" and "2f</ulink>" in x for url, x in links)
    entry = next(e for e in index.iter("primaryie") if "Achondroplasia" in "".join(e.itertext()))
    text = etree.tostring(entry, encoding="unicode")
    assert '<ulink url="#page1">1</ulink>–<ulink url="#page3">3</ulink>' in text
    reviews = json.loads((tmp_path / "out/report/review.json").read_text())
    rules = {r["rule"] for r in reviews if r["kind"] == "adapter-inferred"}
    assert {"index.infer_locators", "index.split_lines", "index.note"} <= rules


# --------------------------------------------------------------------------- links, characters


def links_book(tmp_path):
    b, pages = base_book()
    b.para(pages[0], "Website: www.example.com\ne-mail: info@example.org")
    b.para(pages[0], "Available from https://example.org/a/\nb/c.html [accessed].")
    b.para(pages[0], "No part may be photo\xadcopying or stan\xad\ndard.", joins=[
        {"at": 37, "decision": "soft_join", "hyphen_at": 36, "confidence": 0.9}])  # fmt: skip
    return b.finish(tmp_path / "book")


def test_web_and_email_links(tmp_path, store):
    report, root, xml = export(links_book(tmp_path), tmp_path, store)
    assert_lossless(report)
    urls = {u.get("url"): "".join(u.itertext()) for u in xml.iter("ulink")}
    assert urls["http://www.example.com"] == "www.example.com"
    # a line end inside a web address is not a space (a recorded character change)
    assert urls["https://example.org/a/b/c.html"] == "https://example.org/a/b/c.html"
    assert [e.text for e in xml.iter("email")] == ["info@example.org"]
    changes = report["checks"]["lossless"]["character_changes"]
    assert changes["by_rule"]["link_urls_emails"] == 1


def test_soft_hyphen_removed_and_recorded(tmp_path, store):
    report, _, xml = export(links_book(tmp_path), tmp_path, store)
    text = "".join(xml.itertext())
    assert "photocopying" in text and "\xad" not in text and "standard" in text
    changes = report["checks"]["lossless"]["character_changes"]
    assert changes["by_rule"]["soft_hyphen_removal"] == 1  # the line-end one is a join
    # both source tokens "photo" and "copying" are proven written once
    assert report["checks"]["lossless"]["coverage"]["missing"] == 0


def test_unrecorded_character_change_is_caught():
    content = {"text": "photocopying", "spans": [], "joins": []}

    class Doc:
        records = {"u1": content}

    ledger = Ledger()
    from book_adapters.engine.ledger import Entry

    ledger.entries.append(Entry("text", "photocopyinq", 0, "u1", [(0, 12)], 0))
    assert character_changes(Doc(), ledger)["unexplained"] == 1
    ledger.entries[0] = Entry("text", "photocopying", 0, "u1", [(0, 12)], 0)
    assert character_changes(Doc(), ledger)["unexplained"] == 0


# --------------------------------------------------------------------------- authors


def authors_book(tmp_path, name_line="Ann B Author  MD PhD"):
    b = BookBuilder()
    tp = b.section("title_page", "front")
    body = b.section("chapter", "body")
    p = b.page("i", "front", tp)
    b.heading(p, "A Test Book", 1, "book_title")
    b.heading(p, "Editors", 2, "subsection")
    b.list(p, [b.item(p, f"{name_line}\n\nProfessor\n\nDepartment of Testing\n\n"
                          "Test Medical College\n\nPune, Maharashtra, India")])  # fmt: skip
    b.para(p, "Foreword\nCarl Dee")
    b.heading(p, "TEST BOOK PUBLISHERS", 2, "subsection")
    p1 = b.page("1", "body", body)
    b.heading(p1, "The First Chapter", 1, "chapter")
    b.para(p1, "Body text.")
    return b.finish(tmp_path / "book")


def test_authors_from_title_page(tmp_path, store):
    report, _, xml = export(authors_book(tmp_path), tmp_path, store, authors=False)
    assert_lossless(report)
    groups = xml.find("bookinfo").findall("authorgroup")
    first = groups[0].find("author")

    def t(path):
        return " ".join("".join(first.find(path).itertext()).split())

    assert t("contrib") == "Editors"
    assert (t("firstname"), t("surname"), t("othername")) == ("Ann B", "Author", "MD PhD")
    assert first.find("othername").get("role") == "degrees"
    assert (t("affiliation/jobtitle"), t("affiliation/orgname")) == (
        "Professor", "Test Medical College")  # fmt: skip
    assert t("affiliation/orgdiv") == "Department of Testing"
    assert [t(f"affiliation/address/{x}") for x in ("city", "state", "country")] == [
        "Pune", "Maharashtra", "India"]  # fmt: skip
    foreword = groups[1].find("author")
    assert foreword.find("contrib").text == "Foreword" and foreword.find("surname").text == "Dee"
    assert report["authors"] == {"source": "title_page", "people": 2, "must_check": 0}
    assert "authorgroups" not in report["settings"]["to_supply"]
    # DTD order inside affiliation (orgdiv printed before orgname); the move is declared
    assert [c.tag for c in first.find("affiliation")] == [
        "jobtitle",
        "orgname",
        "orgdiv",
        "address",
    ]
    reviews = json.loads((tmp_path / "out/report/review.json").read_text())
    assert sum(1 for r in reviews if r["kind"] == "author") == 2


def test_unclear_author_split_is_must_check(tmp_path, store):
    report, _, _ = export(authors_book(tmp_path, "Vishnu Mohan PT"), tmp_path, store,
                          authors=False)  # fmt: skip
    assert report["authors"]["must_check"] == 1
    items = json.loads((tmp_path / "out/report/review_list.json").read_text())
    author = next(i for i in items if i["kind"] == "author" and "PT" in i["reason"])
    assert author["severity"] == "must_check"
    assert items[0]["severity"] == "must_check"  # must_check first


def test_settings_authors_win_over_title_page(tmp_path, store):
    _, _, xml = export(authors_book(tmp_path), tmp_path, store, authors=True)
    names = [a.findtext("surname") for a in xml.iter("author")]
    assert names == ["Author"]  # from the book settings (Ann Author)


# --------------------------------------------------------------------------- structure


def test_box_holding_only_a_table_is_the_table(tmp_path, store):
    b, pages = base_book()
    cells = [{"id": b.uid(), "row": 0, "column": 0, "role": "data",
              "box": {"page": pages[0], "x0": 0, "y0": 0, "x1": 1, "y1": 1},
              "content": [{"type": "text", "refs": {}, "content": b.content("cell")}]}]  # fmt: skip
    table = b.base("table", pages[0], rows=1, columns=1, header_rows=0, cells=cells,
                   title={"id": b.uid(), "role": "title", "numbered": True, "number": "1",
                          "refs": {}, "content": b.content("TABLE 1: Values.")})  # fmt: skip
    b.units.append(b.base("box", pages[0], box_kind="callout", children=[table]))
    report, _, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    assert xml.find(".//sidebar") is None
    assert xml.find(".//table").get("label") == "Table 1"


def test_part_without_chapters_is_a_chapter_and_unmapped_kind_is_reviewed(tmp_path, store):
    b = BookBuilder()
    front = b.section("strange_list", "front")
    body = b.section("chapter", "body")
    p = b.page("i", "front", front)
    b.para(p, "Front words in a section kind the profile does not name.")
    p1 = b.page("1", "body", body)
    b.heading(p1, "The First Chapter", 1, "chapter")
    b.para(p1, "Body text.")
    p2 = b.page("2", "body", body)
    b.heading(p2, "A Lonely Part", 1, "part")
    b.para(p2, "Part text without chapters.")
    report, root, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    assert [c.get("id") for c in xml.iter("chapter")] == ["ch1", "ch2"]
    assert [c.get("label") for c in xml.iter("chapter")] == ["CHAPTER 1", "CHAPTER 2"]
    assert xml.find(".//part") is None
    assert report["checks"]["house_rules"]["violations"] == 0
    assert xml.find("preface") is not None  # delivered like front_other, not as body text
    reviews = json.loads((tmp_path / "out/report/review.json").read_text())
    assert any("strange_list" in r["message"] for r in reviews)


def test_body_after_back_matter_keeps_book_order(tmp_path, store):
    b, pages = base_book()
    b.para(pages[0], "Body text.")
    idx = b.section("index", "rear")
    pi = b.page("4", "rear", idx)
    b.list(pi, [b.item(pi, "Alpha  1", kind="index_entry", level=1, locators=[
        {"kind": "page", "start": 7, "end": 8, "label": "1", "target_page": pages[0],
         "confidence": 0.9}])], list_type="index")  # fmt: skip
    tail = b.section("chapter", "body")
    pt = b.page("5", "body", tail)
    b.heading(pt, "A Late Chapter", 1, "chapter")
    b.para(pt, "Text after the index.")
    report, _, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    order = [c.tag for c in xml if c.tag in ("chapter", "index", "part")]
    assert order[-2:] == ["index", "chapter"]


# --------------------------------------------------------------------------- QC, review list


def test_qc_report_and_review_list(tmp_path, store):
    b, pages = base_book()
    para = b.para(pages[0], "Body text.")
    b.review_items.append({"id": "00000000000000ff", "page": pages[0], "kind": "table",
                           "reason": "table structure uncertain", "severity": "must_check",
                           "action": "Check it.", "unit": para["id"],
                           "crop": "review/00000000000000ff.png"})  # fmt: skip
    b.crops["review/00000000000000ff.png"] = (20, 10)
    b.figure(pages[1], "1", "page_2_1", captions=["Fig. 1: A drawing."])
    report, _, _ = export(b.finish(tmp_path / "book"), tmp_path, store)
    out = tmp_path / "out/report"
    qc = json.loads((out / "qc_report.json").read_text())
    assert qc["verdict"] == "warn"  # alt-text override, must-check items
    assert qc["dtd"]["errors"] == 0 and qc["lossless"]["missing"] == 0
    assert qc["profile"]["ref"].startswith("jaypee_v3@")
    assert qc["overrides"]["alt_text_placeholders"] == 1
    fields = {c["field"] for c in qc["confirm_with_client"]}
    assert "images.max_width" in fields
    assert "item" in next(iter(qc["house_rules"]["by_rule"].values()))
    items = json.loads((out / "review_list.json").read_text())
    assert [i["severity"] for i in items] == sorted(
        (i["severity"] for i in items), key=lambda s: s != "must_check"
    )
    stage1 = next(i for i in items if i["source"] == "Stage 1")
    assert stage1["crop"] == "review_crops/00000000000000ff.png"
    assert (out / stage1["crop"]).exists()
    alt = next(i for i in items if i["kind"] == "alt_text")
    assert alt["crop"] and (out / alt["crop"]).exists()  # the figure image
    html = (out / "review_list.html").read_text()
    assert "must check" in html and "review_crops/" in html
    assert (out / "qc_report.html").read_text().count("WARN") == 1


def test_qc_fails_when_text_is_lost():
    from book_adapters.qc import verdict

    lossless = {"missing": 2, "extra": 0, "output": {"matches_ledger": True}}
    report = {"status": "written", "alt_text": {}, "profile": {}, "settings": {},
              "checks": {"dtd": {"errors": 0}, "lossless": lossless}}  # fmt: skip
    v, reasons = verdict(report)
    assert v == "fail" and "2 missing" in reasons[0]


def test_reports_are_deterministic(tmp_path, store):
    book = index_book(tmp_path)
    texts = []
    for n in (1, 2):
        out = tmp_path / f"out{n}"
        run_book(book, out, settings(tmp_path), None, store, allow_alt_text_placeholders=True)
        texts.append({p.name: p.read_bytes() for p in (out / "report").glob("*.*")
                      if p.name != "run.json"})  # fmt: skip
    assert texts[0] == texts[1]


# --------------------------------------------------------------------------- compare, profile test


def test_compare_labels_and_tolerates_not_well_formed_reference(tmp_path, store, capsys):
    report, root, _ = export(links_book(tmp_path), tmp_path, store)
    ref = tmp_path / "ref"
    (ref / "Chapters").mkdir(parents=True)
    main_xml = (root / f"{ISBN}.xml").read_text("utf-8")
    (ref / f"{ISBN}.xml").write_text(main_xml.replace("<para", "<para", 1).replace(
        "</bookinfo>", "</bookinfo><index><indexentry><primaryie>x</primaryie></indexentry>"
        "</index>", 1), "utf-8")  # fmt: skip
    (ref / "Chapters/ch1.xml").write_text("<part><chapter><title>x</title></chapter>", "utf-8")
    result = compare_deliveries(root, ref, book=tmp_path / "book")
    assert result["well_formed"]["ours"] == "all"
    assert list(result["well_formed"]["reference"]) == ["Chapters/ch1.xml"]
    labels = {d["element"]: d["label"] for d in result["biggest_differences"]}
    assert labels["indexentry"] == "source"  # book.json has no index
    code = main(["compare", str(root), str(ref), "--book", str(tmp_path / "book"),
                 "--out", str(tmp_path / "cmp.json")])  # fmt: skip
    assert code == 0 and (tmp_path / "cmp.html").exists()
    assert "not well-formed (reference): Chapters/ch1.xml" in capsys.readouterr().out


def test_profile_test_lists_profile_differences(tmp_path, store):
    from book_adapters.profile_test import test_profile

    book = links_book(tmp_path)
    report, root, _ = export(book, tmp_path, store)
    examples = tmp_path / "examples.yaml"
    examples.write_text(
        f"examples:\n  - name: one\n    book: {book}\n    delivery: {root}\n"
        f"    settings: {settings(tmp_path)}\n",
        "utf-8",
    )
    # the delivery itself as reference: a profile that writes it again leaves nothing to fix
    from .adapter_fixtures import PROFILES

    summary = test_profile(PROFILES / "jaypee/jaypee_v3.yaml", examples, tmp_path / "pt")
    assert summary["remaining"] == 0, summary
    # a profile that names images differently is caught
    other = tmp_path / "other.yaml"
    text = (PROFILES / "jaypee/jaypee_v3.yaml").read_text("utf-8")
    other.write_text(
        text.replace("profile: jaypee_v3", "profile: jaypee_try").replace(
            'chapter: "ch{chapter}"', 'chapter: "chap{chapter}"'
        ),
        "utf-8",
    )
    summary = test_profile(other, examples, tmp_path / "pt2")
    whats = [d["what"] for d in summary["examples"]["one"]["fix"]]
    assert any("chapter id patterns" in w for w in whats), whats


def test_lower_case_label_word_in_artwork_is_not_a_part_opener(tmp_path, store):
    b, pages = base_book()
    b.para(pages[0], "Body text.")
    b.figure(pages[1], "2", "page_2_1", texts=["Reporter\npart 2", "Prey"])
    report, _, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    assert xml.find(".//part") is None
