"""Source/ledger gates restricted to the four approved books and frozen sample."""

# ruff: noqa: E402
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step7_gates
from reference_paths import reference_path
from step4b_run import retained_counter
from step7_layouts import BOOKS as SOURCES
from step11c_identity import digest
from step11d2_hidden import write as write_file
from step11d2_run import read

VARIANT = "hidden"
OUT = ROOT / "experiments/out/step11d2" / VARIANT
BASE = ROOT / "experiments/out/step11d/before"


def write(name, value):
    write_file(OUT / name, value)


from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.lists.models import PageLists
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session


def main():
    sample = read(BASE / "sample.json")
    rows, final_tokens, archives, flags = [], {}, {}, {}
    for book, numbers in sample["pages"].items():
        run = read(OUT / f"performance/{book}.json")["run"]
        output = Path(run["output"])
        identity = read(OUT / f"after/{book}.json")
        manifest = read_json(output / "manifest.json.gz")
        assert manifest["complete"] and manifest["source_sha256"] == identity["source_sha256"]
        assert manifest["keys"] == run["cache_keys"]
        assert manifest["pages"] == len(identity["pages"])
        assert set(manifest["files"]) == {
            "book.json.gz",
            *(f"page_{int(n):06d}.json.gz" for n in identity["pages"]),
        }
        total = 0
        for name, checksum in manifest["files"].items():
            path = output / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
            payload = read_json(path)
            if name == "book.json.gz":
                assert digest(payload["structure"]) == identity["books"]["structure"]
                assert digest(payload["lists"]) == identity["books"]["lists"]
                continue
            source = ExtractedPage.model_validate(payload["source"])
            number = str(source.geometry.page)
            assert (
                digest(source.model_dump(mode="json")) == identity["pages"][number]["native_text"]
            )
            units = PageLists.model_validate(payload["units"])
            assert digest(units.model_dump(mode="json")) == identity["pages"][number]["lists"]
            counts = Counter(line for unit in units.units for line in unit.line_ids)
            assert set(counts) == set(payload["line_spans"]) and all(
                count == 1 for count in counts.values()
            )
            assert all(
                ids and all(sid in source.store.spans for sid in ids)
                for ids in payload["line_spans"].values()
            )
            invisible_spans = {
                sid
                for unit in units.units
                if unit.kind == "invisible"
                for lid in unit.line_ids
                for sid in payload["line_spans"][lid]
            }
            for proof in payload.get("visibility_evidence", []):
                assert proof["span_id"] in source.store.spans
                if proof["decision"] == "invisible":
                    # Hidden-only applied the proof; the combined product keeps the span as
                    # native visible text with a review flag (diagnosis only).
                    assert (proof["span_id"] in invisible_spans) == (VARIANT == "hidden")
                    assert len({r["dpi"] for r in proof["renders"]}) >= 2
                    assert all(
                        r["changed_pixels"] == 0 and r["before_sha256"] == r["after_sha256"]
                        for r in proof["renders"]
                    )
                if proof["decision"] == "already_trimbox_excluded":
                    line = next(
                        native_line
                        for native_line in source.store.lines
                        if native_line.id == proof["line_id"]
                    )
                    assert not source.geometry.content_bbox.contains_center(line.bbox)
            if VARIANT == "combined":
                characters = payload["character_evidence"]
                assert characters["page"] == source.geometry.page
                for flag in characters["flags"]:
                    span = source.store.spans[flag["span_id"]]
                    assert span.line_id == flag["line_id"] and flag["needs_review"]
                    assert all(0 <= g["offset"] < len(span.raw_text) for g in flag["glyphs"])
                flags[book] = flags.get(book, 0) + len(characters["flags"])
            baseline = read(ROOT / f"experiments/out/step11d2/before/{book}.json")
            assert (
                identity["pages"][number]["native_text"] == baseline["pages"][number]["native_text"]
            )
            total += retained_counter(source).total()
        archives[book] = {
            "manifest": manifest,
            "source_and_unit_digests_match_all_pages": True,
            "line_span_references_resolve_all_pages": True,
            "all_file_checksums_match": True,
        }
        final_tokens[book] = total
        with source_session(reference_path(SOURCES[book][0])):
            for number in numbers:
                source = (
                    PyMuPDFExtractor("cpu")
                    .extract_object_page(reference_path(SOURCES[book][0]), number)
                    .page
                )
                final = ExtractedPage.model_validate(
                    read_json(output / f"page_{number:06d}.json.gz")["source"]
                )
                expected, actual = retained_counter(source), retained_counter(final)
                rows.append(
                    {
                        "book": book,
                        "page": number,
                        "tokens": expected.total(),
                        "missing": (expected - actual).total(),
                        "extra": (actual - expected).total(),
                    }
                )
        if book == "spanish_us_history":
            assert total == 495751
    write(
        "source_crosscheck.json",
        {
            "sample": sample,
            "pages": len(rows),
            "missing": sum(r["missing"] for r in rows),
            "extra": sum(r["extra"] for r in rows),
            "results": rows,
            "final_archive_retained_tokens": final_tokens,
            "final_archive_character_flags": flags,
        },
    )
    assert len(rows) == 24 and all(r["missing"] == r["extra"] == 0 for r in rows)
    # Only this function is invoked: the historical fixture driver opens other books.
    ledger = step7_gates.full_book()
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    write("full_book.json", ledger)
    write("final_outputs.json", archives)
    print("24 source pages: 0/0; Spanish ledger and final source archive: 495751")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["hidden", "combined"], default="hidden")
    args = parser.parse_args()
    VARIANT = args.variant
    OUT = ROOT / "experiments/out/step11d2" / VARIANT
    main()
