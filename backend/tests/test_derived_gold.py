"""Derived gold provenance/round trip and the per-stage, per-book evaluation harness."""

import json
from collections import Counter
from pathlib import Path

import pytest
from test_reference_alignment import BODY, DIALECTS, extracted_page, read_reference

from book_core.evaluation.derived_gold import write_derived_gold
from book_core.evaluation.derived_harness import (
    STUBS,
    DerivedGold,
    evaluate,
    ingestion_output,
)
from book_core.reference.aligner import align
from book_core.reference.pdf_tokens import page_tokens

GOLD_ROOT = Path(__file__).resolve().parent / "gold_derived"
XML = (
    '<dtbook><book><frontmatter><pagenum page="front">i</pagenum><h1>Ríos del valle</h1>'
    "</frontmatter><bodymatter><level1>"
    f'<pagenum page="normal">1</pagenum><h1>Capítulo uno</h1><p>{BODY}</p>'
    "<list><li>primer elemento de la lista</li><li>segundo elemento</li></list>"
    f'<pagenum page="normal">2</pagenum><table><tr><td>celda uno</td><td>celda dos</td></tr>'
    "</table></level1></bodymatter></book></dtbook>"
)
PAGES = [
    ["Ríos del valle", "i"],
    ["Capítulo uno", BODY, "primer elemento de la lista", "segundo elemento", "1"],
    ["celda uno celda dos", "2"],
]


def build(tmp_path, split="development"):
    extracted = [extracted_page(n, lines) for n, lines in enumerate(PAGES, 1)]
    pages = [page_tokens(page) for page in extracted]
    doc = read_reference(XML.encode())
    result = align(doc, pages)
    manifest = write_derived_gold(
        tmp_path / "book",
        book="synthetic",
        split=split,
        notes=[],
        pdf_sha256="b" * 64,
        extractor={"name": "test"},
        doc=doc,
        pages=pages,
        result=result,
        dialects_digest=DIALECTS.digest,
    )
    return extracted, manifest, DerivedGold.load(tmp_path / "book")


def test_derived_gold_labels_and_provenance(tmp_path):
    _, manifest, gold = build(tmp_path)
    assert manifest["human_approved"] is False
    assert manifest["provenance"]["xml_sha256"] and manifest["provenance"]["aligner_version"]
    kinds = [(u["kind"], u["zone"], u["heading_level"]) for u in gold.units]
    assert kinds == [
        ("heading", "front", 1),
        ("heading", "body", 1),
        ("paragraph", "body", None),
        ("list_item", "body", None),
        ("list_item", "body", None),
        ("table_cell", "body", None),
        ("table_cell", "body", None),
    ]
    assert gold.units[3]["list"]["depth"] == 1 and gold.units[5]["table"]["row"]
    assert all(unit["aligned_tokens"] == unit["xml_tokens"] for unit in gold.units)
    assert [m["pdf_page"] for m in gold.markers] == [1, 2, 3]
    assert [m["label"] for m in gold.markers] == ["i", "1", "2"]
    # Paragraph boundaries: start/end reference the first and last aligned PDF tokens.
    paragraph = gold.units[2]
    assert paragraph["start"] == [2, 2] and paragraph["end"][0] == 2


def test_harness_scores_one_stage_per_book_without_overall(tmp_path):
    extracted, _, gold = build(tmp_path)
    output = ingestion_output("synthetic", extracted)
    report = evaluate([gold], {"synthetic": output})
    assert report["overall"] is None and report["stage"] == "ingestion"
    book = report["books"]["synthetic"]
    assert book["text_unit_coverage"]["token_coverage"] == 1.0
    assert book["zone_coverage"] == {
        "body": {"tokens": book["zone_coverage"]["body"]["tokens"], "covered": 1.0},
        "front": {"tokens": 3, "covered": 1.0},
    }
    assert book["page_marker_coverage"]["coverage"] == 1.0
    assert book["not_implemented"] == sorted(STUBS)
    for stub in STUBS.values():
        with pytest.raises(NotImplementedError):
            stub(gold, output)


def test_holdout_requires_explicit_opt_in_and_tokens_must_match(tmp_path):
    extracted, _, gold = build(tmp_path, split="holdout")
    output = ingestion_output("synthetic", extracted)
    assert evaluate([gold], {"synthetic": output})["books"]["synthetic"]["skipped"]
    assert (
        "text_unit_coverage"
        in evaluate([gold], {"synthetic": output}, include_holdout=True)["books"]["synthetic"]
    )
    changed = ingestion_output("synthetic", [extracted_page(1, ["otro texto"]), *extracted[1:]])
    with pytest.raises(ValueError, match="token references changed"):
        evaluate([gold], {"synthetic": changed}, include_holdout=True)


def test_tampered_gold_is_rejected(tmp_path):
    build(tmp_path)
    path = tmp_path / "book" / "page_markers.json"
    path.write_text(path.read_text("utf-8").replace('"i"', '"ii"'), "utf-8")
    with pytest.raises(ValueError, match="manifest digest"):
        DerivedGold.load(tmp_path / "book")


@pytest.mark.parametrize(
    "book", sorted(p.name for p in GOLD_ROOT.iterdir() if p.is_dir()) if GOLD_ROOT.exists() else []
)
def test_committed_derived_gold_is_provisional_and_consistent(book):
    gold = DerivedGold.load(GOLD_ROOT / book)
    manifest = gold.manifest
    assert manifest["human_approved"] is False
    assert manifest["split"] in {"development", "holdout"}
    assert gold.units and manifest["counts"]["units"] == len(gold.units)
    assert all(0 <= unit["confidence"] <= 1 for unit in gold.units)
    assert [unit["unit"] for unit in gold.units] == list(range(len(gold.units)))
    pages = {row["page"]: row["tokens"] for row in gold.pages}
    for unit in gold.units:
        for page, ordinal, length in unit["pdf"]:
            assert ordinal + length <= pages[page]
    claimed = Counter(
        (page, ordinal + d)
        for unit in gold.units
        for page, ordinal, n in unit["pdf"]
        for d in range(n)
    )
    shared = Counter(tuple(position) for unit in gold.units for position in unit["shared_pdf"])
    for position, count in claimed.items():
        # Only a declared split shared by both units may give a PDF token two owners.
        assert count == 1 or shared[position] == count, f"{position} has undeclared owners"
    json.dumps(manifest)  # serialisable provenance
