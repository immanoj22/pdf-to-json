"""Read-only marker-category counterfactual on frozen 11e upstream stages."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11_run
from reference_paths import reference_path
from step7_layouts import BOOKS, CACHE
from step8_run import CACHE8, step6_artifact, vocabulary_for
from step9_run import CACHE9
from step10_run import CACHE10
from step11c_identity import digest
from step11d2_hidden import write
from step11e_run import differences

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.furniture.cache import BookDecisions
from book_core.layout.models import PageLayout
from book_core.lists import cache as list_cache
from book_core.lists import lines as list_lines
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.paragraphs.cache import BookParagraphResult
from book_core.reading_order.models import PageReadingOrder
from book_core.run_context import source_session
from book_core.structure.evidence import _read

OUT = ROOT / "experiments/out/step11d2/markers"
BASE = OUT.parent / "before"
CACHE_VARIANT = ROOT / ".cache/step11d2/markers"
ORIGINAL_MARKER = list_lines.set_off_marker
ORIGINAL_ANALYZE = list_cache.analyze_book_lists
EXTRA_CANDIDATES = Counter()


def read(path):
    return json.loads(path.read_text("utf8"))


def category_agnostic(raw, spans, store):
    current = ORIGINAL_MARKER(raw, spans, store)
    if current is not None:
        return current
    first = len(raw) - len(raw.lstrip())
    if first >= len(raw):
        return None
    owner = next((row for row in spans if row[1] <= first < row[2]), None)
    if owner is None or raw[owner[1] : owner[2]].strip() != raw[first]:
        return None
    following = next(
        (row for row in spans if row[1] >= owner[2] and raw[row[1] : row[2]].strip()), None
    )
    if following is None or not list_lines.regex.match(r"\s*[\p{L}\p{N}]", raw[first + 1 :]):
        return None
    mark, text = store.spans[owner[0]], store.spans[following[0]]
    if mark.font == text.font and mark.color == text.color:
        return None
    glyph = raw[first]
    EXTRA_CANDIDATES[f"U+{ord(glyph):04X}"] += 1
    # Existing PageLister repetition, stream, geometry and sequence guards still apply.
    return list_lines.MarkerReading(
        first, first + 1, "bullet", None, "none", signature=(False, glyph, mark.font, text.font)
    )


class FrozenExtractor(PyMuPDFExtractor):
    def __init__(self, archive):
        super().__init__("cpu")
        self.archive = archive

    def extract_pages(self, source):
        for path in sorted(self.archive.glob("page_*.json.gz")):
            yield ExtractedPage.model_validate(read_json(path)["source"])


class FrozenInputs:
    def __init__(self, book, keys, source, extractor, source_digest):
        self.source, self.extractor, self.digest = source, extractor, source_digest
        self.layout_key, self.order_key = keys["layout"], keys["reading_order"]
        self.vocabulary = vocabulary_for(book)

    def __call__(self, page):
        number = page.geometry.page
        layout = verified_read(
            CACHE / "layout" / self.layout_key / f"{number}.json", PageLayout, self.layout_key
        )
        order = verified_read(
            CACHE / "reading_order" / self.order_key / f"{number}.json",
            PageReadingOrder,
            self.order_key,
        )
        assert page.source_sha256 == self.digest == layout.source_sha256 == order.source_sha256
        return layout, order


def frozen_book(book):
    before = read(BASE / f"{book}.json")
    keys = before["keys"]
    archive = Path(read(OUT.parent.parent / f"step11e/performance/{book}.json")["run"]["output"])
    source = reference_path(BOOKS[book][0])
    extractor = FrozenExtractor(archive)
    inputs = FrozenInputs(book, keys, source, extractor, before["source_sha256"])
    furniture = verified_read(
        CACHE8 / "furniture/book" / f"{keys['furniture']}.json", BookDecisions, keys["furniture"]
    )
    paragraphs = verified_read(
        CACHE9 / "paragraphs/book" / f"{keys['paragraphs']}.json",
        BookParagraphResult,
        keys["paragraphs"],
    )
    artifact, artifact_path = step6_artifact(inputs.digest)
    return (
        source,
        extractor,
        inputs,
        furniture,
        keys["furniture"],
        paragraphs,
        artifact,
        artifact_path,
    )


def frozen_evidence(book, loaded=None):
    key = read(BASE / f"{book}.json")["keys"]["structure_evidence"]
    return _read(CACHE10 / "structure/evidence" / f"{key}.json.gz", key), key, True


def main(book):
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def analyze(*args, **kwargs):
        kwargs["config"] = {
            **kwargs.get("config", {}),
            "experiment_producer_sha256": code,
            "marker_category_rule": "no_unicode_category_veto",
        }
        result = ORIGINAL_ANALYZE(*args, **kwargs)
        captured.append(result[0])
        return result

    captured = []
    list_lines.set_off_marker = category_agnostic
    list_cache.analyze_book_lists = analyze
    step11_run.load_book = frozen_book
    step11_run.evidence_for = frozen_evidence
    step11_run.CACHE11 = CACHE_VARIANT
    step11_run.OUT = OUT / "metrics"
    step11_run.HOLDOUT = {}
    with source_session(reference_path(BOOKS[book][0])) as snapshot:
        baseline = read(BASE / f"{book}.json")
        assert snapshot.digest == baseline["source_sha256"]
        sys.argv = ["step11_run.py", "--book", book]
        step11_run.main()
        result = captured[-1]
        pages = {}
        for number in baseline["pages"]:
            current = list_cache.load_page(result, int(number), CACHE_VARIANT)
            pages[number] = digest(current.model_dump(mode="json"))
        write(
            OUT / f"{book}.json",
            {
                "experiment_producer_sha256": code,
                "baseline_revision": "ad1acfc",
                "source_sha256": snapshot.digest,
                "upstream_keys": baseline["keys"],
                "list_key_inputs": result.book.cache_key_inputs,
                "list_page_digests": pages,
                "changed_pages": [
                    int(n) for n, value in pages.items() if value != baseline["pages"][n]["lists"]
                ],
                "extra_candidate_observations": dict(EXTRA_CANDIDATES),
                "metric_changes": differences(
                    read(BASE / f"metrics/{book}/summary.json"),
                    read(OUT / f"metrics/{book}/summary.json"),
                ),
                "upstream_stages": (
                    "Frozen baseline cache keys and checksummed models; no mutations"
                ),
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    main(parser.parse_args().book)
