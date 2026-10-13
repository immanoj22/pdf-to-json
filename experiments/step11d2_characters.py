"""General character-review diagnosis on frozen 11e source stores; never replaces text."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import pymupdf
from reference_paths import reference_path
from step7_layouts import BOOKS
from step11d2_device import PAINT, PaintDevice, m
from step11d2_hidden import attribute, write

from book_core.cache_store import read_json
from book_core.model.spans import ExtractedPage
from book_core.run_context import open_source, source_session

OUT = ROOT / "experiments/out/step11d2/characters"


class GlyphDevice(PaintDevice):
    def text_items(self, text, matrix):
        rows = super().text_items(text, matrix)
        fonts, span, index = {}, text.head, 0
        while span:
            fonts[index] = m.FzTextSpan(span).font()
            span, index = span.next, index + 1
        for row in rows:
            row["glyph_name"] = (
                m.fz_get_glyph_name2(fonts[row["index"][0]], row["glyph_id"])
                if row["glyph_id"] >= 0
                else None
            )
        return rows

    def dispatch(self, name, args):
        if name in PAINT:
            if name in {"fill_text", "stroke_text", "ignore_text"}:
                index = 2 if name == "stroke_text" else 1
                self.events.append(
                    {
                        "seqno": self.seq,
                        "kind": name,
                        "glyphs": self.text_items(args[0], args[index]),
                    }
                )
            self.seq += 1
        return 0 if name == "begin_tile" else None


class FontMappings:
    def __init__(self, document):
        self.document = document
        self.pdf = pymupdf._as_pdf_document(document)
        self.cmaps = {}

    def mapping(self, font, glyph):
        xref, _, kind, _, _, encoding, _ = font
        cid = glyph["raw_code_or_cid"]
        if cid < 0 or kind not in {"Type1", "TrueType", "Type0"}:
            return None
        if kind == "Type0" and encoding not in {"Identity-H", "Identity-V"}:
            return None
        size = 2 if kind == "Type0" else 1
        if cid >= 256**size:
            return None
        if xref not in self.cmaps:
            key_kind, value = self.document.xref_get_key(xref, "ToUnicode")
            cmap = None
            if key_kind == "xref":
                reference = m.pdf_new_indirect(self.pdf, int(value.split()[0]), 0)
                cmap = m.pdf_load_embedded_cmap(self.pdf, reference)
            self.cmaps[xref] = cmap
        cmap = self.cmaps[xref]
        if cmap is None:
            return None
        count, first = m.pdf_lookup_cmap_full(cmap, cid)
        # The installed binding exposes only the first output slot. Multi-codepoint
        # mappings stay unsupported; no guessed ligature expansion is recorded.
        if count != 1 or first != glyph["unicode"]:
            return None
        return {
            "raw_code_hex": cid.to_bytes(size, "big").hex(),
            "to_unicode": first,
            "font_xref": xref,
            "pdf_font_type": kind,
            "encoding": encoding,
        }

    def evidence(self, page, glyph):
        fonts = {
            f[0]: f for f in page.get_fonts(full=True) if f[3].split("+", 1)[-1] == glyph["font"]
        }
        rows = [r for font in fonts.values() if (r := self.mapping(font, glyph)) is not None]
        distinct = {(r["raw_code_hex"], r["to_unicode"]) for r in rows}
        known = len(distinct) == 1
        return {
            "raw_code_hex": rows[0]["raw_code_hex"] if known else None,
            "raw_cid": glyph["raw_code_or_cid"],
            "to_unicode": rows[0]["to_unicode"] if known else None,
            "decoded_unicode": glyph["unicode"],
            "glyph_id": glyph["glyph_id"],
            "glyph_name": glyph["glyph_name"],
            "mapping_sources": rows,
            "mapping_confidence": 1.0 if known and len(rows) == 1 else 0.5 if known else 0.0,
            "mapping_limitation": None if known else "Raw code/ToUnicode attribution unavailable",
        }


def marker_spans(payload):
    groups = defaultdict(list)
    spans = payload["source"]["store"]["spans"]
    for unit in payload["units"]["units"]:
        marker = unit.get("marker")
        if not marker or marker["type"] != "bullet" or marker["punctuation"] != "none":
            continue
        for ref in marker["refs"]:
            span = spans[ref["span_id"]]
            text = span["raw_text"][ref.get("start") or 0 : ref.get("end")]
            if len(text) == 1:
                groups[unit["list_id"], text, span["font"]].append(ref["span_id"])
    return {
        sid
        for (_, text, _), ids in groups.items()
        if len(ids) >= 2 and unicodedata.category(text)[0] in {"L", "N", "C"}
        for sid in ids
    }


class CharacterExtractor:
    def __init__(self, native_extractor):
        self.native_extractor = native_extractor

    @property
    def identity(self):
        return self.native_extractor.identity

    def extract_pages(self, source):
        return self.native_extractor.extract_pages(source)

    def inspect(self, page, native, payload, mappings):
        device = GlyphDevice()
        m.fz_run_page(page.this, device, m.FzMatrix(), m.FzCookie())
        m.fz_close_device(device)
        assert not device.errors, device.errors
        raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
        matches, attribution = attribute(native, raw, device.events)
        markers = marker_spans(payload)
        flags = []
        for sid, pairs in matches.items():
            reasons, glyphs = set(), []
            for _, glyph in pairs:
                name = glyph["glyph_name"]
                named = m.fz_unicode_from_glyph_name_strict(name.split(".", 1)[0]) if name else 0
                mapped = glyph["unicode"]
                mismatch = (
                    named > 0
                    and mapped >= 0
                    and (
                        unicodedata.normalize("NFKC", chr(named))
                        != unicodedata.normalize("NFKC", chr(mapped))
                    )
                )
                if mismatch:
                    reasons.add("glyph_name_and_decoded_unicode_disagree")
                if sid in markers:
                    reasons.add("letter_or_number_mapped_to_repeated_set_off_marker")
                if mismatch or sid in markers:
                    glyphs.append(
                        {**mappings.evidence(page, glyph), "glyph_name_unicode": named or None}
                    )
            if reasons:
                flags.append(
                    {
                        "span_id": sid,
                        "raw_text": native.store.spans[sid].raw_text,
                        "needs_review": True,
                        "confidence": 0.8,
                        "evidence_source": "MuPDF glyph occurrence, glyph name and PDF ToUnicode; "
                        "frozen baseline list repetition where present",
                        "reasons": sorted(reasons),
                        "glyphs": glyphs,
                    }
                )
        return {
            "attribution": attribution,
            "flags": flags,
            "unattributed_marker_span_ids": sorted(markers - matches.keys()),
        }


def main(book):
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

    performance = json.loads(
        (OUT.parent.parent / f"step11e/performance/{book}.json").read_text("utf8")
    )
    archive = Path(performance["run"]["output"])
    manifest_hash = hashlib.sha256((archive / "manifest.json.gz").read_bytes()).hexdigest()
    source = reference_path(BOOKS[book][0])
    with source_session(source) as snapshot, open_source(source) as document:
        inputs = {
            "source": snapshot.digest,
            "archive_manifest": manifest_hash,
            "producers": {
                name: hashlib.sha256((ROOT / "experiments" / name).read_bytes()).hexdigest()
                for name in ("step11d2_characters.py", "step11d2_device.py", "step11d2_hidden.py")
            },
            "pymupdf": pymupdf.VersionBind,
        }
        key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        rows, mappings = [], FontMappings(document)
        extractor = CharacterExtractor(PyMuPDFExtractor("cpu"))
        for page in document:
            number = page.number + 1
            checkpoint = ROOT / ".cache/step11d2/characters" / key / f"{number}.json"
            if checkpoint.exists():
                row = json.loads(checkpoint.read_text("utf8"))
            else:
                payload = read_json(archive / f"page_{number:06d}.json.gz")
                native = ExtractedPage.model_validate(payload["source"])
                assert native.source_sha256 == snapshot.digest
                row = {"page": number, **extractor.inspect(page, native, payload, mappings)}
                write(checkpoint, row)
            rows.append(row)
            if number % 25 == 0:
                print(book, number, flush=True)
        totals = Counter(
            reason for row in rows for flag in row["flags"] for reason in flag["reasons"]
        )
        write(
            OUT / f"{book}.json",
            {
                "inputs": inputs,
                "pages": rows,
                "flagged_spans": sum(len(r["flags"]) for r in rows),
                "reasons": dict(totals),
            },
        )
        print(book, dict(totals), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    main(parser.parse_args().book)
