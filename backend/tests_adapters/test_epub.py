"""ePub 3 writer on the synthetic book: package, navigation, Jaypee EPUB items 1-5, accessibility,
lossless, determinism, schema extension (v3 profiles stay valid) and DocBook unchanged."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from book_adapters.engine.epub_run import run_epub
from book_adapters.engine.profile import ProfileError, epub_section, load_profile
from book_adapters.engine.run import ExportBlocked, run_book
from book_adapters.validate import epub_checks

from .adapter_fixtures import PROFILES

MOD = "2026-11-04T00:00:00Z"
X = "{http://www.w3.org/1999/xhtml}"
OPF = {"o": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


@pytest.fixture
def v4_settings(tmp_path, settings_file) -> Path:
    path = tmp_path / "s4.yaml"
    path.write_text(settings_file.read_text().replace("jaypee_v3", "jaypee_v4"), "utf-8")
    return path


def make(sample_book, tmp_path, store, settings, name="out", **kw):
    return run_epub(
        sample_book,
        tmp_path / name,
        settings,
        None,
        store,
        allow_alt_text_placeholders=True,
        modified=MOD,
        **kw,
    )


@pytest.fixture
def epub(sample_book, tmp_path, store, v4_settings):
    report = make(sample_book, tmp_path, store, v4_settings)
    return report, zipfile.ZipFile(report["epub"])


def parse(zf, name):
    return etree.fromstring(zf.read(name))


def test_own_checks_and_lossless(epub):
    report, _ = epub
    own = report["checks"]["epub"]
    failed = {k: v["examples"] for k, v in own["checks"].items() if v["violations"]}
    assert not failed, failed
    loss = own["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0), loss["coverage"]
    assert loss["output"]["matches_ledger"], loss["output"]
    assert loss["order"]["undeclared_out_of_order"] == 0
    assert loss["character_changes"]["unexplained"] == 0
    ec = report["checks"]["epubcheck"]
    assert ec["status"] in ("run", "not run")
    if ec["status"] == "run":
        assert ec["errors"] == 0, ec["messages"]


def test_package_layout(epub):
    _, zf = epub
    first = zf.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert zf.read("mimetype") == b"application/epub+zip"
    assert "META-INF/container.xml" in zf.namelist()
    opf = parse(zf, "OEBPS/package.opf")
    assert opf.get("version") == "3.0"
    assert opf.find("o:metadata/dc:identifier", OPF).text == "urn:isbn:9780306406157"
    assert opf.find("o:metadata/dc:title", OPF).text == "A Test Book"
    assert opf.find("o:metadata/dc:creator", OPF).text == "Ann Author"
    mod = [
        m for m in opf.findall("o:metadata/o:meta", OPF) if m.get("property") == "dcterms:modified"
    ]
    assert mod[0].text == MOD
    names = zf.namelist()
    assert "OEBPS/nav.xhtml" in names and "OEBPS/Styles/jaypee.css" in names
    assert any(n.startswith("OEBPS/Text/ch") for n in names)


def test_cover_rule_front_only(sample_book, tmp_path, store, v4_settings):
    # no cover given: no cover page and a must-check item
    report = make(sample_book, tmp_path, store, v4_settings)
    zf = zipfile.ZipFile(report["epub"])
    assert "OEBPS/Text/cover.xhtml" not in zf.namelist()
    review = (tmp_path / "out" / "report" / "review_list.json").read_text()
    assert "front cover image" in review
    # with a cover: exactly one cover page, one cover image, no back or inside cover
    from PIL import Image

    img = tmp_path / "cover.png"
    Image.new("RGB", (60, 90), "white").save(img)
    v4_settings.write_text(v4_settings.read_text() + f"epub:\n  cover_image: {img}\n", "utf-8")
    report = make(sample_book, tmp_path, store, v4_settings, "withcover")
    zf = zipfile.ZipFile(report["epub"])
    covers = [n for n in zf.namelist() if re.search(r"cover", n, re.I)]
    assert sorted(covers) == ["OEBPS/Images/cover.jpg", "OEBPS/Text/cover.xhtml"]
    opf = parse(zf, "OEBPS/package.opf")
    props = [i.get("properties") for i in opf.findall("o:manifest/o:item", OPF)]
    assert props.count("cover-image") == 1
    assert not report["checks"]["epub"]["checks"]["cover"]["violations"]


def test_link_colour_never_blue(epub):
    _, zf = epub
    css = zf.read("OEBPS/Styles/jaypee.css").decode()
    m = re.search(r"(?m)^a \{ color: ([^;]+);", css)
    assert m.group(1) == "#231F20"
    assert "@LINK_COLOUR@" not in css


def test_half_title_heading(epub):
    _, zf = epub
    page = parse(zf, "OEBPS/Text/halftitle.xhtml")
    assert page.findtext(f"{X}head/{X}title") == "Half Title Page"
    assert page.find(f".//{X}h1").text == "Half Title Page"
    assert b"Halftitle" not in zf.read("OEBPS/nav.xhtml")
    assert b"Half Title Page" in zf.read("OEBPS/nav.xhtml")


def test_guide_and_landmarks(epub):
    _, zf = epub
    opf = parse(zf, "OEBPS/package.opf")
    refs = opf.findall("o:guide/o:reference", OPF)
    assert {r.get("type") for r in refs} >= {"title-page", "toc", "text"}
    nav = parse(zf, "OEBPS/nav.xhtml")
    types = [
        a.get(EPUB_TYPE)
        for n in nav.iter(f"{X}nav")
        if n.get(EPUB_TYPE) == "landmarks"
        for a in n.iter(f"{X}a")
    ]
    assert "bodymatter" in types and "toc" in types


def test_two_way_toc_links(epub):
    report, zf = epub
    toc = parse(zf, "OEBPS/Text/toc.xhtml")
    assert toc.find(f".//{X}nav").get("id") == "TOC"
    returns = 0
    for name in zf.namelist():
        if name.startswith("OEBPS/Text/") and name != "OEBPS/Text/toc.xhtml":
            for a in parse(zf, name).iter(f"{X}a"):
                if a.get("class") == "toc-return":
                    returns += 1
                    assert a.get("href").startswith("toc.xhtml#toc-")
    assert returns and returns == report["checks"]["epub"]["counts"]["toc_return_links"]
    # every toc entry has a heading that links back (the check runs this too)
    assert not report["checks"]["epub"]["checks"]["toc_two_way"]["violations"]


def test_container_mode_returns_to_toc_container(sample_book, tmp_path, store, v4_settings):
    prof = tmp_path / "prof.yaml"
    src = (PROFILES / "jaypee" / "jaypee_v4.yaml").read_text()
    prof.write_text(
        src.replace("profile: jaypee_v4", "profile: jaypee_v4c")
        .replace("extends: jaypee_v3", "extends: jaypee/jaypee_v3")
        .replace("toc_return: entry", "toc_return: container")
    )
    v4_settings.write_text(v4_settings.read_text().replace("jaypee_v4", str(prof)))
    report = make(sample_book, tmp_path, store, v4_settings, "cont")
    zf = zipfile.ZipFile(report["epub"])
    hrefs = {
        a.get("href")
        for n in zf.namelist()
        if n.startswith("OEBPS/Text/ch")
        for a in parse(zf, n).iter(f"{X}a")
        if a.get("class") == "toc-return"
    }
    assert hrefs == {"toc.xhtml#TOC"}
    assert not report["checks"]["epub"]["checks"]["toc_two_way"]["violations"]


def test_page_list_complete_and_ordered(epub):
    report, zf = epub
    counts = report["checks"]["epub"]["counts"]
    assert counts["page_list"] == counts["page_breaks"] > 0
    assert not report["checks"]["epub"]["checks"]["page_list"]["violations"]
    ch = parse(zf, "OEBPS/Text/ch1.xhtml")
    spans = [s for s in ch.iter(f"{X}span") if s.get(EPUB_TYPE) == "pagebreak"]
    assert spans and all(s.get("title") and s.get("role") == "doc-pagebreak" for s in spans)


def test_content_elements(epub):
    _, zf = epub
    html = b"".join(zf.read(n) for n in zf.namelist() if n.startswith("OEBPS/Text/"))
    root = etree.fromstring(zf.read("OEBPS/Text/ch1.xhtml"))
    assert root.find(f".//{X}h1") is not None and root.find(f".//{X}h2") is not None
    assert b"<figure" in html and b"<img " in html and b"<figcaption" in html
    assert b"<table" in html and b"<caption" in html and b"<th " in html or b"<thead" in html
    assert b"<ul " in html or b"<ol " in html
    assert b'lang="en"' in html


def test_accessibility_metadata(epub):
    _, zf = epub
    opf = parse(zf, "OEBPS/package.opf")
    props = {}
    for m in opf.findall("o:metadata/o:meta", OPF):
        props.setdefault(m.get("property"), []).append(m.text)
    assert "textual" in props["schema:accessMode"]
    assert props["schema:accessibilityHazard"] == ["none"]
    assert "structuralNavigation" in props["schema:accessibilityFeature"]
    assert "printPageNumbers" in props["schema:accessibilityFeature"]
    # the sample has placeholder alt texts: alternativeText must not be claimed
    assert "alternativeText" not in props["schema:accessibilityFeature"]
    assert "placeholder" in props["schema:accessibilitySummary"][0]


def test_alt_text_blocks_export(sample_book, tmp_path, store, v4_settings):
    with pytest.raises(ExportBlocked) as exc:
        run_epub(sample_book, tmp_path / "blocked", v4_settings, None, store, modified=MOD)
    assert exc.value.report["alt_text"]["placeholders"] > 0
    assert not list((tmp_path / "blocked").glob("*.epub"))


def test_override_recorded(epub):
    report, _ = epub
    assert report["alt_text"]["override"] and report["alt_text"]["placeholders"] > 0
    assert any("OVERRIDE" in w for w in report["warnings"])


def test_deterministic(sample_book, tmp_path, store, v4_settings):
    a = make(sample_book, tmp_path, store, v4_settings, "a")
    b = make(sample_book, tmp_path, store, v4_settings, "b")
    assert Path(a["epub"]).read_bytes() == Path(b["epub"]).read_bytes()
    assert a["delivery"]["epub_sha256"] == b["delivery"]["epub_sha256"]


def test_lossless_detects_loss(epub, tmp_path):
    _, zf = epub
    page = zf.read("OEBPS/Text/ch1.xhtml").decode()
    root = etree.fromstring(page.encode())
    tokens = epub_checks.xhtml_tokens(root)
    assert tokens
    # dropping a paragraph's words changes the token list
    p = root.find(f".//{X}p")
    p.getparent().remove(p)
    assert epub_checks.xhtml_tokens(root) != tokens


def test_docbook_unchanged_with_v4(sample_book, tmp_path, store, settings_file):
    a = run_book(
        sample_book,
        tmp_path / "v3",
        settings_file,
        "jaypee_v3",
        store,
        allow_alt_text_placeholders=True,
    )
    b = run_book(
        sample_book,
        tmp_path / "v4",
        settings_file,
        "jaypee_v4",
        store,
        allow_alt_text_placeholders=True,
    )
    fa = (
        zipfile.ZipFile(a["root"] + ".zip" if False else Path(a["root"]).with_suffix(".zip"))
        if False
        else None
    )
    _ = fa
    ta = sorted(p.relative_to(a["root"]) for p in Path(a["root"]).rglob("*") if p.is_file())
    tb = sorted(p.relative_to(b["root"]) for p in Path(b["root"]).rglob("*") if p.is_file())
    assert ta == tb
    for rel in ta:
        assert (Path(a["root"]) / rel).read_bytes() == (Path(b["root"]) / rel).read_bytes(), rel


def test_schema_extension_old_profiles_valid():
    for name in (
        "jaypee/jaypee_v3.yaml",
        "jaypee/jaypee_generated.yaml",
        "_base/docbook_base.yaml",
        "_test/other_client.yaml",
    ):
        prof = load_profile(PROFILES / name)
        assert prof.get("epub") is None  # the optional section stays absent
        assert epub_section(prof)["package"]["nav_file"] == "nav.xhtml"
    v4 = load_profile(PROFILES / "jaypee/jaypee_v4.yaml")
    assert v4.get("epub.half_title.heading") == "Half Title Page"
    assert v4.get("delivery.chapters_folder") == "Chapters"  # DocBook part inherited


def test_schema_rejects_bad_epub_field(tmp_path):
    src = (
        (PROFILES / "jaypee/jaypee_v4.yaml")
        .read_text()
        .replace("toc_return: entry", "toc_retrun: entry")
    )
    path = tmp_path / "bad.yaml"
    path.write_text(src)
    with pytest.raises(ProfileError) as exc:
        load_profile(path, [PROFILES])
    assert "toc_return" in str(exc.value)


def test_profile_without_epub_section_uses_defaults(sample_book, tmp_path, store, settings_file):
    report = run_epub(
        sample_book,
        tmp_path / "d",
        settings_file,
        "jaypee_v3",
        store,
        allow_alt_text_placeholders=True,
        modified=MOD,
    )
    assert not report["profile_has_epub"]
    assert report["qc_verdict"] != "pass"
    assert Path(report["epub"]).is_file()


def test_epubcheck_not_run_is_reported(sample_book, tmp_path, store, v4_settings, monkeypatch):
    monkeypatch.setattr(epub_checks.shutil, "which", lambda _: None)
    report = make(sample_book, tmp_path, store, v4_settings, "nojava")
    assert report["checks"]["epubcheck"]["status"] == "not run"
    qc = (tmp_path / "nojava" / "report" / "qc_report.json").read_text()
    assert "EPUBCheck not run" in qc


def test_zip_is_valid_bytes(epub):
    _, zf = epub
    assert zf.testzip() is None
    assert isinstance(io.BytesIO(zf.read("mimetype")), io.BytesIO)


def test_question_entry_is_a_section_with_a_question_and_an_answer(tmp_path, store, v4_settings):
    from .test_adapter_b import question_book

    report = make(question_book(tmp_path), tmp_path, store, v4_settings, "q")
    zf = zipfile.ZipFile(report["epub"])
    page = next(n for n in zf.namelist() if n.endswith(".xhtml")
                and b"qandaentry" in zf.read(n))  # fmt: skip
    entry = parse(zf, page).find(f".//{X}section[@class='qandaentry']")
    assert entry.get("data-number") == "7"
    question = entry.find(f"{X}div[@class='question']")
    assert question.find(f"{X}ol").get("type") == "a"
    assert [li.text for li in question.iter(f"{X}li")] == ["Thiamine", "Niacin", "Biotin", "Folate"]
    answer = entry.find(f"{X}aside[@class='answer']")
    assert "Niacin deficiency causes pellagra." in "".join(answer.itertext())
