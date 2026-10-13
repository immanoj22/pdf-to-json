"""Extend review evidence to repeated set-off glyphs, independently of accepted lists."""

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
import step11d2_characters as characters
from reference_paths import reference_path
from step7_layouts import BOOKS, CACHE
from step11d2_hidden import write

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.models import PageLayout
from book_core.lists.lines import _spans, set_off_marker
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.run_context import open_source, source_session

OUT = ROOT / "experiments/out/step11d2/character_markers"


def read(path):
    return json.loads(path.read_text("utf8"))


def candidates(native, layout):
    ids, isolated = set(), set()
    for line in layout.lines:
        raw = "".join(native.store.spans[s].raw_text for s in line.span_ids)
        nonblank = [sid for sid in line.span_ids if native.store.spans[sid].raw_text.strip()]
        if len(nonblank) == 1 and len(raw.strip()) == 1:
            if unicodedata.category(raw.strip())[0] in {"L", "N", "C"}:
                ids.add(nonblank[0])
                isolated.add(nonblank[0])
        marker = set_off_marker(raw, _spans(native.store, line), native.store)
        if marker is None or unicodedata.category(raw[marker.start])[0] not in {"L", "N", "C"}:
            continue
        offset = 0
        for sid in line.span_ids:
            end = offset + len(native.store.spans[sid].raw_text)
            if offset <= marker.start < end:
                ids.add(sid)
            offset = end
    return ids, isolated


def main(book):
    baseline = read(OUT.parent / f"before/{book}.json")
    initial = read(OUT.parent / f"characters/{book}.json")
    archive = Path(read(OUT.parent.parent / f"step11e/performance/{book}.json")["run"]["output"])
    key = baseline["keys"]["layout"]
    pages, groups = [], defaultdict(set)
    source = reference_path(BOOKS[book][0])
    with source_session(source) as snapshot, open_source(source) as document:
        mappings = characters.FontMappings(document)
        extractor = characters.CharacterExtractor(PyMuPDFExtractor("cpu"))
        for page in document:
            number = page.number + 1
            payload = read_json(archive / f"page_{number:06d}.json.gz")
            native = ExtractedPage.model_validate(payload["source"])
            layout = verified_read(CACHE / "layout" / key / f"{number}.json", PageLayout, key)
            ids, isolated = candidates(native, layout)
            if not ids:
                continue
            characters.marker_spans = lambda _payload, ids=ids: ids
            inspected = extractor.inspect(page, native, payload, mappings)
            selected = [f for f in inspected["flags"] if f["span_id"] in ids]
            selected = [
                f
                for f in selected
                if f["span_id"] not in isolated
                or any(
                    g["glyph_name_unicode"] is None
                    or g["glyph_name_unicode"] != g["decoded_unicode"]
                    for g in f["glyphs"]
                )
            ]
            for flag in selected:
                if flag["span_id"] in isolated:
                    flag["reasons"] = ["repeated_isolated_glyph_with_unclear_name_semantics"]
                    flag["confidence"] = 0.5
            for flag in selected:
                for glyph in flag["glyphs"]:
                    sources = glyph["mapping_sources"]
                    if len(sources) == 1 and unicodedata.category(chr(glyph["decoded_unicode"]))[
                        0
                    ] in {"L", "N", "C"}:
                        groups[sources[0]["font_xref"], glyph["glyph_id"]].add(flag["span_id"])
            pages.append({"page": number, "candidates": selected})
            print(book, number, len(selected), flush=True)
        repeated = {sid for ids in groups.values() if len(ids) >= 2 for sid in ids}
        by_page = {r["page"]: {f["span_id"]: f for f in r["flags"]} for r in initial["pages"]}
        added = []
        for page in pages:
            for flag in page["candidates"]:
                if flag["span_id"] not in repeated or flag["span_id"] in by_page[page["page"]]:
                    continue
                flag["evidence_source"] = (
                    "MuPDF glyph occurrence and PDF ToUnicode; repeated font-resource/glyph ID "
                    "set off at visual-line starts or isolated with unclear name semantics; "
                    "independent of accepted list decisions; not a corruption diagnosis"
                )
                by_page[page["page"]][flag["span_id"]] = flag
                added.append({"page": page["page"], "span_id": flag["span_id"]})
        rows = [{"page": n, "flags": list(flags.values())} for n, flags in by_page.items()]
        write(
            OUT / f"{book}.json",
            {
                "source_sha256": snapshot.digest,
                "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "initial_sha256": hashlib.sha256(
                    (OUT.parent / f"characters/{book}.json").read_bytes()
                ).hexdigest(),
                "layout_key": key,
                "pages": rows,
                "added": added,
                "repetition_groups": [
                    {"font_xref": x, "glyph_id": g, "spans": sorted(ids)}
                    for (x, g), ids in groups.items()
                    if len(ids) >= 2
                ],
                "flagged_spans": sum(len(r["flags"]) for r in rows),
                "reasons": dict(
                    Counter(reason for r in rows for f in r["flags"] for reason in f["reasons"])
                ),
            },
        )
        print(book, "added", len(added), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    main(parser.parse_args().book)
