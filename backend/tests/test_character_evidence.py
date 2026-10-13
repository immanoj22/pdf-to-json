"""Character evidence: general glyph-name and repeated-marker flags, never text changes."""

import unicodedata
from pathlib import Path

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.characters.cache import decide, observe_page
from book_core.characters.models import GlyphEvidence, PageCharacterEvidence
from book_core.characters.rules import marker_character, name_codepoint, name_disagrees
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

TO_UNICODE = b"""/CIDInit /ProcSet findresource begin 12 dict begin begincmap
/CMapName /Fixture def /CMapType 2 def
1 begincodespacerange <00> <FF> endcodespacerange
1 beginbfchar <41> <01CA> endbfchar
endcmap CMapName currentdict /CMap defineresource pop end end"""


def fixture(path, mapped, lines=2):
    """Lines opening with a Helvetica bullet glyph (code 41) set off before Times text."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=220)
    marker = doc.get_new_xref()
    extra = ""
    if mapped:
        cmap = doc.get_new_xref()
        doc.update_object(cmap, "<< >>")
        doc.update_stream(cmap, TO_UNICODE)
        extra = f" /ToUnicode {cmap} 0 R"
    doc.update_object(
        marker,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        f"/Encoding << /Type /Encoding /Differences [65 /bullet] >>{extra} >>",
    )
    body = doc.get_new_xref()
    doc.update_object(body, "<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>")
    resources = doc.get_new_xref()
    doc.update_object(resources, f"<< /Font << /FM {marker} 0 R /FB {body} 0 R >> >>")
    doc.xref_set_key(page.xref, "Resources", f"{resources} 0 R")
    stream = b"".join(
        b"BT /FM 12 Tf 40 %d Td (A) Tj /FB 12 Tf ( Item number %d text) Tj ET\n" % (180 - 30 * i, i)
        for i in range(lines)
    )
    contents = doc.get_new_xref()
    doc.update_object(contents, "<< >>")
    doc.update_stream(contents, stream)
    doc.xref_set_key(page.xref, "Contents", f"{contents} 0 R")
    doc.save(path)
    doc.close()


def test_name_rule_uses_unicode_properties_only():
    assert name_codepoint("bullet.034") == ord("•")
    assert name_codepoint("glyph00190") is None and name_codepoint(None) is None
    assert name_disagrees(ord("•"), [0x01CA])
    # Case conventions (small capitals) and format characters are not disagreements.
    assert not name_disagrees(name_codepoint("H.smcp"), [ord("h")])
    assert not name_disagrees(name_codepoint("hyphen"), [0x00AD])
    # Compatibility decompositions compare after NFKC (a ligature glyph and its letters).
    assert not name_disagrees(0xFB01, [ord("f"), ord("i")])
    # A space glyph that also carries a leader dot names its first character.
    assert not name_disagrees(name_codepoint("space"), [ord(" "), ord(".")])
    assert name_disagrees(name_codepoint("bullet"), [ord("x"), ord("y")])
    assert not name_disagrees(None, [0x01CA])
    assert marker_character("¾") and marker_character("Ǌ") and not marker_character("•")
    assert not marker_character(" ")


def evidence(page, sid, font, gid, marker, disagrees):
    glyph = GlyphEvidence(
        offset=0,
        glyph_id=gid,
        decoded_codepoints=[0xBE],
        font=font,
        marker_candidate=marker,
        name_disagrees=disagrees,
    )
    return PageCharacterEvidence(
        source_sha256="0" * 64, page=page, version="t", candidates={sid: [glyph]}
    )


def test_marker_flags_need_book_level_repetition_of_the_same_glyph():
    lines = {1: {"a": "la", "b": "lb"}, 2: {"c": "lc"}}
    single = decide([evidence(1, "a", "F", 7, True, False)], lines)
    assert single[0].flags == []
    other_glyph = decide(
        [evidence(1, "a", "F", 7, True, False), evidence(2, "c", "F", 8, True, False)], lines
    )
    assert all(not r.flags for r in other_glyph)
    repeated = decide(
        [evidence(1, "a", "F", 7, True, False), evidence(2, "c", "F", 7, True, False)], lines
    )
    assert [f.reasons for r in repeated for f in r.flags] == [
        ["unnamed_or_mismatched_glyph_repeated_as_marker"]
    ] * 2
    assert all(f.needs_review and f.line_id for r in repeated for f in r.flags)


@pytest.mark.parametrize("mapped", [True, False])
def test_page_observation_flags_without_changing_text(tmp_path, mapped):
    source = tmp_path / "fixture.pdf"
    fixture(source, mapped)
    extractor = PyMuPDFExtractor("cpu")
    native = extractor.extract_object_page(source, 1)
    original = native.page.model_dump_json()
    with pymupdf.open(source) as document:
        result = observe_page(document, native.page, layout=_NoLines(), units=[])
    assert native.page.model_dump_json() == original
    flagged = {
        sid for sid, glyphs in result.candidates.items() if any(g.name_disagrees for g in glyphs)
    }
    texts = {native.page.store.spans[sid].raw_text for sid in flagged}
    assert texts == ({"Ǌ"} if mapped else set())
    for sid in flagged:
        span = native.page.store.spans[sid]
        assert span.text == unicodedata.normalize("NFKC", span.raw_text)


class _NoLines:
    lines = ()


def test_book_run_records_character_flags_in_final_archive(tmp_path):
    source = tmp_path / "markers.pdf"
    fixture(source, mapped=True, lines=3)
    result = run_book(source, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = read_json(Path(result["output"]) / "page_000001.json.gz")
    flags = page["character_evidence"]["flags"]
    spans = page["source"]["store"]["spans"]
    assert flags and all(spans[f["span_id"]]["raw_text"] == "Ǌ" for f in flags)
    assert {r for f in flags for r in f["reasons"]} == {
        "glyph_name_disagrees_with_unicode",
        "unnamed_or_mismatched_glyph_repeated_as_marker",
    }
    assert "candidates" not in page["character_evidence"]
    assert result["cache_keys"]["characters"] and result["source_hashes"] == 1


def test_missing_character_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(caching.DEPENDENCIES, "characters", ("paint",))
    missing = closure("characters/cache.py") - set(caching.coverage_files("characters"))
    assert "lists/lines.py" in missing
    monkeypatch.setitem(caching.DEPENDENCIES, "final", ("lists", "metadata"))
    missing = closure("book_run.py") - set(caching.coverage_files("final"))
    assert "characters/cache.py" in missing
