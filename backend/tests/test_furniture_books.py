"""Step 8 regression targets on the approved books (cached decisions of the single runs).

The book decisions are read from the Step 8 cache written by experiments/step8_run.py; these
tests never start a new whole-book run (book 2 is a hold-out that runs once).
"""

import json
import unicodedata

import pytest
from conftest import ROOT, reference_path

from book_core.document_analysis.metadata import cached_metadata
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.furniture.cache import load_book_furniture, page_furniture
from book_core.furniture.inputs import PageInputs
from book_core.furniture.labels import parse_label
from book_core.objects.analysis import cached_repetition

CACHE7 = ROOT / ".cache/step7"
CACHE8 = ROOT / ".cache/step8"
BOOKS = {"spanish_us_history": "spanish_pdf", "immigrant_children": "small_pdf"}


def _vocabulary(book):
    name = (
        "step7_vocabulary.json" if book == "spanish_us_history" else f"step7_vocabulary_{book}.json"
    )
    return json.loads((CACHE7 / name).read_text("utf-8"))


def pages_of(book, numbers):
    """{page: [(role, stream kind, NFKC text)]} from the cached Step 8 results."""
    source = reference_path(BOOKS[book])
    if not source.exists():
        pytest.fail(f"approved reference PDF missing: {source}")
    extractor = PyMuPDFExtractor(device="cpu")
    inputs = PageInputs(
        source, extractor, cached_repetition(source, extractor, CACHE7), CACHE7, _vocabulary(book)
    )
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    decisions, key = load_book_furniture(inputs, metadata, CACHE8)
    if decisions is None:
        pytest.fail(f"run experiments/step8_run.py --book {book} first (no cached decision)")
    result = {}
    for number in numbers:
        page = extractor.extract_object_page(source, number).page
        layout, _ = inputs(page)
        furniture = page_furniture(page, inputs, decisions, key, CACHE8)
        stream = {lid: s.kind for s in furniture.order.streams for lid in s.line_ids}
        role = {r.line_id: r.role for r in furniture.roles}
        result[number] = [
            (
                role[line.id],
                stream[line.id],
                unicodedata.normalize(
                    "NFKC", "".join(page.store.spans[s].raw_text for s in line.span_ids)
                ).strip(),
            )
            for line in layout.lines
        ]
        result[number, "marker"] = furniture.marker
    return result


@pytest.fixture(scope="module")
def book1():
    return pages_of("spanish_us_history", [30, 31, 669, 696])


def test_book1_glossary_and_index_guide_words_are_running_heads(book1):
    glossary = [r for r in book1[669] if r[2].startswith("casa de vecindad") and "•" in r[2]]
    index = [r for r in book1[696] if r[2].startswith("ejecuciones hipotecarias") and "•" in r[2]]
    assert glossary and all(role == "running_head" for role, _, _ in glossary)
    assert index and all(role == "running_head" for role, _, _ in index)
    assert all(kind == "furniture" for _, kind, _ in glossary + index)
    # An index entry Step 4 took for furniture is content again, read in the main flow.
    entry = [r for r in book1[696] if r[2].startswith("entente cordiale")]
    assert entry and entry[0][0] == "content" and entry[0][1] == "main"


def test_book1_slug_lines_are_production_marks(book1):
    for number in (30, 31, 669, 696):
        slug = [r for r in book1[number] if ".indd" in r[2] or r[2].startswith("Program:")]
        assert slug and all(role == "production_mark" for role, _, _ in slug), number


def test_book1_conectate_is_repeated_box_content(book1):
    box = [r for r in book1[31] if r[2].startswith("CONÉCTATE")]
    assert box and all(role == "repeated_box" for role, _, _ in box)
    assert all(kind not in {"furniture", "artifact"} for _, kind, _ in box)


def test_book1_folios_carry_fitted_labels(book1):
    assert (book1[669, "marker"].label, book1[669, "marker"].source) == ("645", "printed")
    assert book1[30, "marker"].label == "6" and book1[31, "marker"].label == "7"
    folios = [r for r in book1[669] if r[0] == "folio"]
    assert [text for _, _, text in folios] == ["645"]


def test_book2_page_124_table_numbers_are_not_folios():
    page = pages_of("immigrant_children", [124])[124]
    numbers = [r for r in page if parse_label(r[2]) is not None and r[1] == "table"]
    assert numbers, "expected number-only table cells on book 2 p124"
    assert all(role == "content" for role, _, _ in numbers)
