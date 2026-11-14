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


def test_artwork_above_a_front_title_on_its_page_leads_that_division(tmp_path, store):
    b = BookBuilder()
    secs = {k: b.section(k, z) for k, z in
            (("title_page", "front"), ("front_other", "front"), ("chapter", "body"))}
    p = b.page("i", "front", secs["title_page"])
    b.heading(p, "A Test Book", 1, "book_title")
    p2 = b.page("v", "front", secs["front_other"])
    b.figure(p2, "v", "page_v_1", size=(300, 200))  # a photo printed above the title
    b.heading(p2, "A Doctor's Prayer", 1, "front_section_title")
    b.para(p2, "Bless me with insight.")
    pages = [b.page(str(n), "body", secs["chapter"]) for n in (1, 2)]
    b.heading(pages[0], "The First Chapter", 1, "chapter")
    b.para(pages[0], "Body text.")
    report, _, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    titled = [d for d in xml.iter() if d.tag in ("preface", "dedication")]
    titles = ["".join(d.find("title").itertext()).strip() for d in titled
              if d.find("title") is not None]  # fmt: skip
    assert titles == ["A Doctor's Prayer"], titles


# --------------------------------------------------------------------------- question banks


def question_book(tmp_path, with_options=True, with_box=False):
    b, pages = base_book()
    p = pages[0]
    marker = {"text": "7.", "value": 7, "type": "decimal"}
    stem = b.list(p, [b.item(p, "Which vitamin is lacking?", marker=marker)],
                  list_type="numbered", marker_type="decimal", add=False)
    parts = [stem]
    if with_options:
        texts = ("Thiamine", "Niacin", "Biotin", "Folate")
        letters = [
            b.item(p, t, marker={"text": f"{'abcd'[i]}.", "value": i + 1, "type": "lower_alpha"})
            for i, t in enumerate(texts)
        ]
        parts.append(b.list(p, letters, list_type="lettered", marker_type="lower_alpha",
                            add=False))
    question = b.base("question_part", p, children=parts)
    question["type"] = "question"
    answer_parts = [b.para(p, "Ans. is 'b' Niacin"), b.para(p, "Niacin deficiency causes pellagra.")]
    if with_box:
        box = b.base("box", p, box_kind="callout", children=[
            b.base("heading", p, level=1, role="sidebar_title", level_method="t",
                   content=b.content("Box 1: Remember")),
            b.base("paragraph", p, role="body", content=b.content("Pellagra: the three Ds.")),
        ])  # fmt: skip
        answer_parts.append(box)
    answer = b.base("question_part", p, key="b" if with_options else None, children=answer_parts)
    answer["type"] = "answer"
    inside = {id(u) for u in answer_parts} | {id(c) for u in answer_parts
                                               for c in u.get("children") or []}  # fmt: skip
    b.units = [u for u in b.units if id(u) not in inside]  # only inside the entry
    entry = b.base("question_entry", p, number=7, children=[question, answer])
    b.units.append(b.base("question_set", p, children=[entry]))
    return b.finish(tmp_path / "book")


def test_question_entry_is_a_qandaentry_with_options_and_an_answer(tmp_path, store):
    report, root, xml = export(question_book(tmp_path), tmp_path, store)
    assert_lossless(report)
    entry = xml.find(".//qandaset/qandadiv/qandaentry")
    assert entry.get("role") == "7"
    question, answer = entry.find("question"), entry.find("answer")
    assert question.find("para").text == "Which vitamin is lacking?"
    options = question.find("orderedlist")  # directly in the question, not inside a para
    assert options.get("numeration") == "loweralpha"
    assert ["".join(i.itertext()) for i in options.findall("listitem")] == [
        "Thiamine", "Niacin", "Biotin", "Folate"]  # fmt: skip
    assert [" ".join("".join(p.itertext()).split()) for p in answer.findall("para")] == [
        "Ans. is 'b' Niacin", "Niacin deficiency causes pellagra."]  # fmt: skip


def test_question_entry_without_lettered_options_stays_plain_text(tmp_path, store):
    report, root, xml = export(question_book(tmp_path, with_options=False), tmp_path, store)
    assert_lossless(report)
    assert xml.find(".//qandaset") is None
    assert "Niacin deficiency causes pellagra." in "".join(xml.itertext())


# --------------------------------------------------------------------------- chapters and parts


def chapters_book(tmp_path, number=None):
    b = BookBuilder()
    secs = {k: b.section(k, z) for k, z in (("title_page", "front"), ("chapter", "body"))}
    p = b.page("i", "front", secs["title_page"])
    b.heading(p, "A Test Book", 1, "book_title")
    pages = [b.page(str(n), "body", secs["chapter"]) for n in (1, 2, 3, 4)]
    b.heading(pages[0], "Upper Limb Blocks", 2, "section")  # holds the chapters below it
    first = b.heading(pages[0], "Interscalene Block", 3, "chapter")
    if number:
        first["number"] = number
    b.para(pages[0], "Text of the first chapter.")
    b.heading(pages[1], "REFERENCES", 1, "feature_title")  # attached: never a start
    b.para(pages[1], "Reference text.")
    b.heading(pages[2], "Supraclavicular Block", 3, "chapter")
    b.para(pages[2], "Text of the second chapter.")
    b.heading(pages[3], "REFERENCES", 2, "feature_title")
    b.para(pages[3], "More reference text.")
    return b.finish(tmp_path / "book")


def test_an_attached_title_never_opens_a_part_or_a_chapter(tmp_path, store):
    report, root, xml = export(chapters_book(tmp_path), tmp_path, store)
    assert_lossless(report)
    assert len(xml.findall(".//part")) == 1  # the section that holds the chapters
    chapters = [c for c in xml.iter("chapter")]
    titles = ["".join(c.find("title").itertext()).strip() for c in chapters]
    assert titles == ["Interscalene Block", "Supraclavicular Block"], titles


def test_the_number_a_reviewer_set_labels_the_chapter(tmp_path, store):
    report, root, xml = export(chapters_book(tmp_path, number="7"), tmp_path, store)
    assert_lossless(report)
    labels = [c.get("label") for c in xml.iter("chapter")]
    assert labels == ["CHAPTER 7", "CHAPTER 8"], labels  # the next chapter follows the number


# --------------------------------------------------------------------------- figure labels


def figure_label_book(tmp_path, caption):
    b, pages = base_book()
    b.para(pages[0], "Text before the figure.")
    b.figure(pages[0], None, "fig1", captions=[caption])
    return b.finish(tmp_path / "book")


def test_a_label_naming_several_figures_is_written_as_printed(tmp_path, store):
    caption = "Figs. 1A and B. The probe held along the vessel."
    report, root, xml = export(figure_label_book(tmp_path, caption), tmp_path, store)
    assert_lossless(report)
    figure = xml.find(".//figure")
    assert figure.get("label") == "Figs. 1A and B"  # not cut to "Fig. 1A"
    assert "".join(figure.find("title").itertext()).strip() == "The probe held along the vessel."
    assert figure.get("id").endswith("fig1A")
    qc = json.loads((tmp_path / "out" / "report" / "qc_report.json").read_text("utf-8"))
    assert qc["house_rules"]["by_rule"]["ids.figure_labels"]["violations"] == 0


def test_a_single_figure_label_keeps_the_house_form(tmp_path, store):
    report, root, xml = export(
        figure_label_book(tmp_path, "Figure 2. The probe held across the vessel."), tmp_path, store
    )
    assert_lossless(report)
    assert xml.find(".//figure").get("label") == "Fig. 2"


def test_rotated_opener_label_words_say_part_or_chapter(tmp_path, store):
    """A "SEC TION" / "CHAPTER" label on the opener artwork above a heading (often set
    vertically) decides the kind of start, whatever role the heading came with."""
    b = BookBuilder()
    body = b.section("chapter", "body")
    p1 = b.page("1", "body", body)
    b.figure(p1, None, "opener1", texts=["SEC TION"])
    b.heading(p1, "Upper Limb Blocks", 1, "chapter")
    b.para(p1, "The blocks of this section are listed below with their uses.")
    p2 = b.page("2", "body", body)
    b.figure(p2, None, "opener2", texts=["CHAPTER"])
    b.heading(p2, "Interscalene Block", 1, "chapter")
    b.para(p2, "Body text of the chapter.")
    report, root, xml = export(b.finish(tmp_path / "book"), tmp_path, store)
    assert_lossless(report)
    parts = list(xml.iter("part"))
    def title(el):
        return "".join(el.find("title").itertext()).strip()

    assert [title(p) for p in parts] == ["Upper Limb Blocks"]
    assert [title(c) for c in parts[0].iter("chapter")] == ["Interscalene Block"]
    assert report["checks"]["dtd"]["errors"] == 0


def test_opener_label_words_come_from_the_profile_in_any_language(tmp_path, store):
    """An Italian client profile ("SEZIONE", "CAPITOLO") works with no code change."""
    profile = tmp_path / "italian_test.yaml"
    profile.write_text(
        "profile: italian_test\nversion: 0.1.0\ndate: '2026-11-13'\nextends: jaypee/jaypee_v3\n"
        "outline:\n  part_label_words: [SEZIONE, PARTE]\n  chapter_label_words: [CAPITOLO]\n",
        "utf-8",
    )
    b = BookBuilder()
    body = b.section("chapter", "body")
    p1 = b.page("1", "body", body)
    b.figure(p1, None, "opener1", texts=["SE ZIONE"])
    b.heading(p1, "Blocchi dell'arto superiore", 1, "chapter")
    b.para(p1, "I blocchi di questa sezione sono elencati qui sotto con i loro usi.")
    p2 = b.page("2", "body", body)
    b.figure(p2, None, "opener2", texts=["CAPITOLO"])
    b.heading(p2, "Blocco interscalenico", 1, "chapter")
    b.para(p2, "Testo del capitolo.")
    out = tmp_path / "out"
    report = run_book(b.finish(tmp_path / "book"), out, settings(tmp_path), str(profile), store,
                      allow_alt_text_placeholders=True)  # fmt: skip
    assert_lossless(report)
    xml = etree.parse(str(out / ISBN / f"{ISBN}.xml")).getroot()
    parts = list(xml.iter("part"))
    assert ["".join(p.find("title").itertext()).strip() for p in parts] == [
        "Blocchi dell'arto superiore"]
    assert len(list(parts[0].iter("chapter"))) == 1


def test_a_box_inside_an_answer_is_a_blockquote_marked_as_a_box(tmp_path, store):
    """DocBook allows no sidebar in a question or answer: the box is written as a blockquote
    with role "box", keeping its title, label and text (DTD valid, lossless)."""
    report, root, xml = export(question_book(tmp_path, with_box=True), tmp_path, store)
    assert_lossless(report)
    assert report["checks"]["dtd"]["errors"] == 0
    answer = xml.find(".//qandaentry/answer")
    assert answer.find("sidebar") is None
    box = answer.find("blockquote")
    assert box.get("role") == "box"
    assert "Remember" in "".join(box.find("title").itertext())
    assert "Pellagra: the three Ds." in "".join(box.itertext())


def test_opener_artwork_after_a_reference_list_keeps_its_text(tmp_path, store):
    """A decorative figure with text right after the references (the next part's opener
    artwork, "SEC TION 2", once its heading was made a section) ends the reference list and is
    exported like any figure; it is not skipped as page-number artwork is."""
    b, pages = base_book()
    b.heading(pages[0], "References", 2, "section")
    b.list(pages[0], [b.item(pages[0], "Smith J. A paper. 2001."), b.item(pages[0], "Lee K. A book. 2010.")],
           list_type="bibliography")  # fmt: skip
    art = b.figure(pages[1], "2", "opener", texts=["SEC TION", "2"])
    art["decorative"] = True
    b.heading(pages[1], "Gamete Analysis", 2, "section")
    b.para(pages[1], "Text of the section.")
    report, root, xml = export(b.finish(tmp_path / "bk"), tmp_path, store)
    assert_lossless(report)
