"""The standard format writers (HTML, NIMAS/DTBook, DAISY 3, JATS, BITS) on the synthetic
book: checks pass, lossless 0/0, deterministic, alt-text rule, schema extension."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from book_adapters.engine.format_profile import format_section
from book_adapters.engine.formats_run import SPECS, run_format, supported_formats
from book_adapters.engine.profile import load_profile
from book_adapters.engine.run import ExportBlocked
from book_adapters.validate import format_checks as fc

from .adapter_fixtures import PROFILES

BASES = {"html": "html_base", "dtbook": "dtbook_nimas_base",
         "daisy3": "daisy3_base", "jats": "jats_base", "bits": "bits_base"}  # fmt: skip


def make(fmt, sample_book, tmp_path, store, settings, name="out", **kw):
    kw.setdefault("allow_alt_text_placeholders", True)
    return run_format(fmt, sample_book, tmp_path / name, settings, BASES[fmt], store, **kw)


def tree_sha(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(params=sorted(SPECS))
def fmt_run(request, sample_book, tmp_path, store, settings_file):
    report = make(request.param, sample_book, tmp_path, store, settings_file)
    return request.param, report, Path(report["root"])


def test_checks_pass(fmt_run):
    fmt, report, _ = fmt_run
    checks = report["checks"]
    assert checks["dtd"]["errors"] == 0, checks["dtd"]
    assert checks["house_rules"]["violations"] == 0, checks["house_rules"]
    loss = checks["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0)
    assert loss["output"]["matches_ledger"]
    assert loss["character_changes"]["unexplained"] == 0
    assert report["qc_verdict"] in ("pass", "warn")


def test_deterministic(fmt_run, sample_book, tmp_path, store, settings_file):
    fmt, report, root = fmt_run
    again = make(fmt, sample_book, tmp_path, store, settings_file, name="again")
    assert tree_sha(root) == tree_sha(Path(again["root"]))
    assert report["delivery"]["zip_sha256"] == again["delivery"]["zip_sha256"]


def test_alt_text_blocks_export_unless_overridden(sample_book, tmp_path, store, settings_file):
    for fmt in SPECS:
        with pytest.raises(ExportBlocked):
            make(fmt, sample_book, tmp_path, store, settings_file, name=f"b{fmt}",
                 allow_alt_text_placeholders=False)  # fmt: skip
        assert not any((tmp_path / f"b{fmt}").glob("*_*/"))


def test_base_profiles_valid_and_declared(store):
    for ref in BASES.values():
        profile, stored = store.load(ref)
        assert supported_formats(profile) == [f for f, b in BASES.items() if b == ref]


def test_old_profiles_stay_valid_and_get_defaults(store):
    for name in ("jaypee/jaypee_v3.yaml", "jaypee/jaypee_v4.yaml", "_base/docbook_base.yaml"):
        profile = load_profile(PROFILES / name)
        assert format_section(profile, "html")["package"]["index_file"] == "index.html"
    assert "html" not in supported_formats(store.load("jaypee_v3")[0])


def test_strict_html_reader_finds_errors():
    _, errors, _ = fc.parse_html(b"<html><body><p>a<b>b</p></b><br/></body></html>")
    assert errors
    _, ok, _ = fc.parse_html(b"<!DOCTYPE html><html><body><p>a<br><b>b</b></p></body></html>")
    assert ok == []


def test_html_structure(sample_book, tmp_path, store, settings_file):
    report = make("html", sample_book, tmp_path, store, settings_file)
    root = Path(report["root"])
    files = sorted(p.name for p in root.glob("*.html"))
    assert "index.html" in files and (root / "style.css").is_file()
    pages = {n: fc.parse_html((root / n).read_bytes())[0] for n in files}
    for name, tree in pages.items():
        assert tree.get("lang"), name
    body = "".join(etree_text(t) for t in pages.values())
    assert body
    assert any(s.get("role") == "doc-pagebreak" for t in pages.values() for s in t.iter("span"))
    for t in pages.values():
        for img in t.iter("img"):
            assert img.get("alt") is not None
        for th in t.iter("th"):
            assert th.get("scope")
    assert report["checks"]["house_rules"]["checks"]["links"]["checked"] > 0


def etree_text(tree) -> str:
    return "".join(tree.itertext())


def test_nimas_file_set(sample_book, tmp_path, store, settings_file):
    report = make("dtbook", sample_book, tmp_path, store, settings_file)
    root = Path(report["root"])
    names = sorted(p.name for p in root.iterdir())
    assert "9780306406157.xml" in names and "9780306406157.opf" in names
    data = (root / "9780306406157.xml").read_text("utf-8")
    assert 'PUBLIC "-//NISO//DTD dtbook 2005-3//EN"' in data
    assert "<frontmatter>" in data and "<bodymatter>" in data and "<pagenum " in data
    opf = (root / "9780306406157.opf").read_text("utf-8")
    assert "<dc:Format>NIMAS 1.1</dc:Format>" in opf and "urn:isbn:9780306406157" in opf
    reviews = [
        r["message"]
        for r in __import__("json").loads(
            (Path(report["root"]).parent / "report/review.json").read_text("utf-8")
        )
    ]
    assert any("dc:Publisher to supply" in m for m in reviews)  # listed, never invented
    assert any("title/copyright PDF to supply" in m for m in reviews)  # no source PDF given


def test_dtbook_dtd_rejects_bad_nesting():
    from book_adapters.validate import schemas

    bad = (
        b'<?xml version="1.0"?><!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" '
        b'"http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd"><dtbook xmlns="http://www.daisy.org/'
        b'z3986/2005/dtbook/" version="2005-3"><head/><book><bodymatter><level2><h2>x</h2><p/>'
        b"</level2></bodymatter></book></dtbook>"
    )
    assert schemas.validate(bad, ["dtbook2005_3"])


def test_nimas_title_copyright_pdf_is_cut_and_stable(sample_book, tmp_path, store, settings_file):
    import pypdfium2 as pdfium

    src = tmp_path / "src.pdf"
    doc = pdfium.PdfDocument.new()
    for _ in range(12):
        doc.new_page(200, 300)
    doc.save(str(src))
    kw = {"source_pdf": src}
    a = make("dtbook", sample_book, tmp_path, store, settings_file, name="a", **kw)
    b = make("dtbook", sample_book, tmp_path, store, settings_file, name="b", **kw)
    pdf = Path(a["root"]) / "9780306406157_titlecopyright.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes() == (Path(b["root"]) / pdf.name).read_bytes()
    cut = pdfium.PdfDocument(str(pdf))
    assert 0 < len(cut) < 12
    assert a["checks"]["dtd"]["errors"] == 0


def test_daisy3_file_set(sample_book, tmp_path, store, settings_file):
    report = make("daisy3", sample_book, tmp_path, store, settings_file)
    root = Path(report["root"])
    names = sorted(p.name for p in root.iterdir() if p.is_file())
    assert any(n.endswith(".ncx") for n in names) and any(n.endswith(".smil") for n in names)
    assert any(n.endswith(".res") for n in names) and any(n.endswith(".opf") for n in names)
    opf = next(root.glob("*.opf")).read_text("utf-8")
    assert "ANSI/NISO Z39.86-2005" in opf and "textNCX" in opf
    assert "application/smil" in opf and '<itemref idref="smil1"/>' in opf
    ncx = next(root.glob("*.ncx")).read_text("utf-8")
    assert "<pageList>" in ncx and 'playOrder="1"' in ncx and "dtb:totalPageCount" in ncx
    data = (root / report["delivery"]["main_file"]).read_text("utf-8")
    assert 'smilref="' in data
    checks = report["checks"]["house_rules"]["checks"]
    assert checks["ncx"]["checked"] > 0 and checks["smil"]["checked"] > 0


def test_jats_structure(sample_book, tmp_path, store, settings_file):
    report = make("jats", sample_book, tmp_path, store, settings_file)
    root = Path(report["root"])
    data = (root / "9780306406157.xml").read_text("utf-8")
    assert "JATS (Z39.96) Journal Publishing DTD with MathML3 v1.4" in data
    for tag in (
        "<front>",
        "<article-meta>",
        "<body>",
        "<sec",
        "<string-name>",
        "<table-wrap",
        "<ref-list",
    ):
        assert tag in data, tag
    assert "<given-names>Ann</given-names>" in data or "<given-names>" in data
    reviews = [
        r["message"]
        for r in __import__("json").loads((root.parent / "report/review.json").read_text("utf-8"))
    ]
    assert any("journal id to supply" in m or "JATS journal id" in m for m in reviews)


def test_jats_per_article_mode(sample_book, tmp_path, store, settings_file):
    profile = tmp_path / "pa.yaml"
    profile.write_text(
        "profile: pa\nversion: 1.0.0\ndate: '2026-11-04'\nextends: _base/jats_base\n"
        "jats:\n  mode: per_article\n", "utf-8")  # fmt: skip
    report = run_format("jats", sample_book, tmp_path / "pa", settings_file, str(profile), store,
                        allow_alt_text_placeholders=True)  # fmt: skip
    names = sorted(p.name for p in Path(report["root"]).glob("*.xml"))
    assert len(names) >= 2 and names[0].endswith("_001.xml") or any("_front" in n for n in names)
    assert report["checks"]["dtd"]["errors"] == 0
    loss = report["checks"]["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0)


def test_bits_structure(sample_book, tmp_path, store, settings_file):
    report = make("bits", sample_book, tmp_path, store, settings_file)
    data = (Path(report["root"]) / "9780306406157.xml").read_text("utf-8")
    assert "BITS Book Interchange DTD v2.2" in data
    for tag in ("<book-meta>", "<book-title-group>", "<book-body>", "<book-part", "<isbn"):
        assert tag in data, tag


def test_sec_continuation_keeps_text_order():
    from lxml import etree

    from book_adapters.formats.jatsbase import JatsBase

    conv = JatsBase.__new__(JatsBase)
    conv.continued = 0
    sec = etree.Element("sec")
    etree.SubElement(sec, "title")
    etree.SubElement(sec, "sec")
    target = conv.slot(sec, "para")
    assert target is not sec and target.get("specific-use") == "continued"
    assert conv.slot(sec, "para") is target  # reused, not one per paragraph
    assert conv.continued == 1
