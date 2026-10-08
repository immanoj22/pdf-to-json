"""Review sample validity and explicit native paint-order accounting."""

import json

import pytest
from conftest import ROOT

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.objects.analysis import analyze_page

GOLD = sorted((ROOT / "backend/tests/gold").glob("roles_*.json"))


@pytest.mark.parametrize("path", GOLD, ids=[path.stem for path in GOLD])
def test_review_gold_and_all_visual_paint_accounted(path):
    gold = json.loads(path.read_text("utf-8"))
    source = ROOT / "experiments/fixtures" / f"{gold['fixture']}.pdf"
    analysis = analyze_page(source, 1, PyMuPDFExtractor(), cache_dir=ROOT / ".cache/objects")
    assert gold["source_sha256"] == analysis.native.page.source_sha256
    assert gold["objects"] and gold["human_approved"] is False
    assets = {record.object_id: record for record in analysis.asset_ledger.records}
    assert len({item["object_id"] for item in gold["objects"]}) == len(gold["objects"])
    for item in gold["objects"]:
        assert item["object_id"] in assets
        if item["expected_role"] is None:
            assert item["review_required"] and item["note"]
    covered = {seq for obj in analysis.native.objects for seq in obj.paint_sequences}
    assert all(
        command.seqno in covered
        for command in analysis.native.paint_commands
        if command.operation in {"fill-path", "stroke-path", "fill-image", "fill-shade"}
    )
    commands = {command.seqno: command for command in analysis.native.paint_commands}
    for obj in analysis.native.objects:
        if obj.kind == "drawing":
            assert all(
                commands[seq].operation in {"fill-path", "stroke-path"}
                for seq in obj.paint_sequences
            )
    # Role accuracy is reported separately; uncertain visual annotations are not invented truth.
