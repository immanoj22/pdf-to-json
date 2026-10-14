"""Step 12 source, ledger and final-archive gates for the four approved books.

The frozen Step 11d six-pages-per-book sample (fresh Extractor text vs the final archive), the
full Spanish ledger (495,751), and on every archive page: checksums, source/unit digests, line
and span references, and the figure records (every linked unit exists with the same lines;
every figure's image file exists with its checksum; the alt-text slot is never verified
without a human source). Hidden-text proofs stay diagnosis only.
"""

# ruff: noqa: E402
import hashlib
import json
import os
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

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.figures.models import PageFigures
from book_core.lists.models import PageLists
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session

RUN = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
SAMPLE = ROOT / "experiments/out/step11d/before/sample.json"


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def write(name, value):
    path = RUN / name
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8", newline="\n")


def check_figures(payload, units, line_spans, output):
    figures = PageFigures.model_validate(payload["figures"])
    lines_of = {u.id: u.line_ids for u in units.units}
    counts = Counter()
    for figure in figures.figures:
        for link in (*figure.captions, *figure.credits, *figure.internal_text):
            assert lines_of[link.unit_id] == link.line_ids, "linked unit lines differ"
            assert all(line in line_spans for line in link.line_ids)
        if figure.image is not None:
            data = (output / "images" / figure.image.file_name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == figure.image.sha256
            assert figure.image.file_name == f"{figure.name}.{figure.image.format}"
        assert figure.alt_text.status == "needs_review" and figure.alt_text.source == "none"
        counts["figures"] += 1
        counts["links"] += len(figure.captions) + len(figure.credits) + len(figure.internal_text)
    for caption in figures.unlinked_captions:
        assert lines_of[caption.unit_id] == caption.line_ids
    ids = {f.id for f in figures.figures}
    for credit in figures.page_credits:
        assert lines_of[credit.unit_id] == credit.line_ids
        assert credit.review_required and set(credit.proposed_figure_ids) <= ids
        counts["page_credits"] += 1
        counts["page_credits_one_proposal"] += len(credit.proposed_figure_ids) == 1
    return counts


def main():
    sample = read(SAMPLE)
    rows, final_tokens, archives = [], {}, {}
    for book, numbers in sample["pages"].items():
        run = read(RUN / f"performance/{book}.json")["run"]
        output = Path(run["output"])
        identity = read(RUN / f"after/{book}.json")
        baseline = read(ROOT / f"experiments/out/step12/before/{book}.json")
        manifest = read_json(output / "manifest.json.gz")
        assert manifest["complete"] and manifest["source_sha256"] == identity["source_sha256"]
        assert manifest["keys"] == run["cache_keys"]
        pages = {f"page_{int(n):06d}.json.gz" for n in identity["pages"]}
        images = {name for name in manifest["files"] if name.startswith("images/")}
        assert set(manifest["files"]) == {"book.json.gz", *pages, *images}
        total, figure_counts = 0, Counter()
        for name, checksum in manifest["files"].items():
            path = output / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
            if name.startswith("images/"):
                continue
            payload = read_json(path)
            if name == "book.json.gz":
                assert digest(payload["structure"]) == identity["books"]["structure"]
                assert digest(payload["lists"]) == identity["books"]["lists"]
                assert payload["figures"]["profile"]["images"] == len(images)
                continue
            source = ExtractedPage.model_validate(payload["source"])
            number = str(source.geometry.page)
            assert (
                digest(source.model_dump(mode="json")) == identity["pages"][number]["native_text"]
            )
            assert (
                identity["pages"][number]["native_text"] == baseline["pages"][number]["native_text"]
            )
            units = PageLists.model_validate(payload["units"])
            assert digest(units.model_dump(mode="json")) == identity["pages"][number]["lists"]
            counts = Counter(line for unit in units.units for line in unit.line_ids)
            assert set(counts) == set(payload["line_spans"]) and set(counts.values()) <= {1}
            assert all(
                ids and all(sid in source.store.spans for sid in ids)
                for ids in payload["line_spans"].values()
            )
            invisible = {
                sid
                for unit in units.units
                if unit.kind == "invisible"
                for lid in unit.line_ids
                for sid in payload["line_spans"][lid]
            }
            for proof in payload.get("visibility_evidence", []):
                if proof["decision"] == "invisible":
                    assert proof["span_id"] not in invisible  # still diagnosis only
            figure_counts.update(check_figures(payload, units, payload["line_spans"], output))
            total += retained_counter(source).total()
        archives[book] = {
            "output": str(output),
            "files": len(manifest["files"]),
            "image_files": len(images),
            "figures": figure_counts["figures"],
            "figure_links": figure_counts["links"],
            "page_credits": figure_counts["page_credits"],
            "page_credits_with_one_proposed_figure": figure_counts["page_credits_one_proposal"],
            "all_checks_pass": True,
        }
        final_tokens[book] = total
        with source_session(reference_path(SOURCES[book][0])):
            for number in numbers:
                fresh = (
                    PyMuPDFExtractor("cpu")
                    .extract_object_page(reference_path(SOURCES[book][0]), number)
                    .page
                )
                final = ExtractedPage.model_validate(
                    read_json(output / f"page_{number:06d}.json.gz")["source"]
                )
                expected, actual = retained_counter(fresh), retained_counter(final)
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
        },
    )
    assert len(rows) == 24 and all(r["missing"] == r["extra"] == 0 for r in rows)
    ledger = step7_gates.full_book()
    assert ledger["node_token_count"] == 495751 and all(ledger["gate"].values())
    write("full_book.json", ledger)
    write("final_outputs.json", archives)
    print(json.dumps({"archives": archives, "tokens": final_tokens}, indent=1))
    print("24 source pages: 0/0; Spanish ledger and final source archive: 495751")


if __name__ == "__main__":
    main()
