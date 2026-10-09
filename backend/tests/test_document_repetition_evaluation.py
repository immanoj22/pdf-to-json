"""Synthetic whole-book repetition, evidence scoring and overlay integrity checks."""

from copy import deepcopy

import cv2
import numpy as np
import pytest
from test_document_styles_vocabulary import _page as style_page

from book_core.debug.document_overlay import render_document_overlay
from book_core.document_analysis.repetition import (
    RepetitionConfig,
    build_repetition,
    masked_key,
)
from book_core.document_analysis.styles import build_style_profile
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.document_evidence import evaluate_document
from book_core.extraction.rasters import RasterPage
from book_core.model.spans import ExtractedPage
from book_core.reference.pdf_tokens import page_tokens


def _page(number, rows, *, source="a" * 64):
    page = style_page([[text] for text, _ in rows], number=number, source=source)
    payload = page.model_dump()
    for line, (_, coordinates) in zip(payload["store"]["lines"], rows, strict=True):
        box = dict(zip(("x0", "y0", "x1", "y1"), coordinates, strict=True))
        line["bbox"] = box
        for sid in line["span_ids"]:
            payload["store"]["spans"][sid]["bbox"] = box
    return ExtractedPage.model_validate(payload)


def _unit(page, line_index, kind, ordinal):
    pdf = page_tokens(page)
    indices = [token.ordinal for token in pdf.tokens if token.line == line_index]
    assert indices
    return {"unit": ordinal, "kind": kind, "pdf": [[pdf.page, indices[0], len(indices)]]}


def _gold(pages, units):
    return DerivedGold(
        book="synthetic",
        split="development",
        manifest={"notes": [], "provenance": {"pdf_sha256": pages[0].source_sha256}},
        units=units,
        markers=[],
        pages=[
            {"page": pdf.page, "tokens": len(pdf.tokens), "token_digest": pdf.digest}
            for pdf in map(page_tokens, pages)
        ],
    )


def _evidence(pages, *, entries=(), repetition=None):
    return {
        "style": build_style_profile(pages),
        "navigation": {"entries": list(entries)},
        "repetition": repetition if repetition is not None else {"candidates": []},
    }


def _bookmark(identifier, title, targets):
    return {
        "id": identifier,
        "kind": "bookmark",
        "title": title,
        "source_page": None,
        "target_pages": targets,
    }


def test_odd_and_even_running_heads_are_position_conditioned_evidence_only():
    pages = [
        _page(
            number,
            [
                (
                    "Historia del valle" if number % 2 else "Studies in education",
                    (25, 2, 75, 8),
                ),
                ("Central repeated prose", (25, 45, 75, 55)),
            ],
        )
        for number in range(1, 7)
    ]
    before = [page.model_dump_json() for page in pages]
    result = build_repetition(pages)
    candidates = result["candidates"]
    assert len(candidates) == 2
    by_parity = {candidate["periodicity"]: candidate for candidate in candidates}
    assert by_parity["odd"]["pages"] == [1, 3, 5]
    assert by_parity["even"]["pages"] == [2, 4, 6]
    for periodicity, candidate in by_parity.items():
        assert candidate["band"] == "top"
        assert candidate["page_coverage"] == 0.5
        assert candidate["parity"][periodicity]["local_coverage"] == 1
        assert 0 < candidate["confidence"] <= 1
        assert candidate["decision"] is None
    assert [page.model_dump_json() for page in pages] == before
    assert build_repetition(list(reversed(pages))) == result


def test_fuzzy_digit_masking_covers_unicode_digits_without_losing_occurrences():
    assert masked_key("CAPÍTULO ١") == masked_key("capítulo １") == masked_key("capítulo 1")
    pages = [
        _page(number, [(text, (25, 2, 75, 8))])
        for number, text in enumerate(
            ["Running heading ١", "Running headings ２", "Running heading 3"], 1
        )
    ]
    candidate = build_repetition(pages)["candidates"][0]
    assert candidate["pages"] == [1, 2, 3]
    assert len(candidate["occurrences"]) == 3
    assert min(row["similarity"] for row in candidate["occurrences"]) < 1
    assert not candidate["digit_only"]


def test_opposite_side_edges_stay_separate_and_central_repetition_is_excluded():
    pages = [
        _page(
            number,
            [
                ("Margin", (1, 40, 7, 50)),
                ("Margin", (93, 40, 99, 50)),
                ("Repeated centre", (30, 40, 70, 50)),
            ],
        )
        for number in range(1, 4)
    ]
    candidates = build_repetition(pages)["candidates"]
    assert len(candidates) == 2
    assert all(candidate["band"] == "side" for candidate in candidates)
    assert sorted(candidate["position_center"] for candidate in candidates) == [0.04, 0.96]
    assert all(len(candidate["occurrences"]) == 3 for candidate in candidates)
    assert not any(
        row["line_id"].endswith("-2")
        for candidate in candidates
        for row in candidate["occurrences"]
    )


def test_fuzzy_matching_occurs_within_each_position_before_support_is_counted():
    pages = [
        _page(
            number,
            [
                ("References 2" if number == 2 else f"Reference {number}", (1, 40, 7, 50)),
                (f"Reference {number}", (93, 40, 99, 50)),
            ],
        )
        for number in range(1, 4)
    ]
    candidates = build_repetition(pages)["candidates"]
    assert len(candidates) == 2
    assert all(candidate["pages"] == [1, 2, 3] for candidate in candidates)
    assert sorted(candidate["position_center"] for candidate in candidates) == [0.04, 0.96]


def test_distinct_pages_are_required_for_repetition_support():
    page = _page(1, [("Same", (20, 2, 80, 8))] * 4)
    assert not build_repetition([page])["candidates"]
    assert not build_repetition([])["candidates"]


@pytest.mark.parametrize(
    "configuration",
    [
        {"edge_fraction": 0},
        {"edge_fraction": 0.5},
        {"position_tolerance": float("nan")},
        {"similarity": 101},
        {"minimum_pages": 1},
    ],
)
def test_repetition_configuration_rejects_invalid_support(configuration):
    with pytest.raises(ValueError):
        RepetitionConfig(**configuration)


def test_repetition_eval_preserves_aligned_figure_labels_and_table_numbers_as_false_candidates():
    pages = [
        _page(
            number,
            [
                ("Study Guide", (20, 1, 80, 5)),
                ("Energy", (20, 7, 80, 11)),
                ("12", (40, 93, 60, 97)),
                (f"Actual Heading {number}", (20, 45, 80, 55)),
            ],
        )
        for number in range(1, 4)
    ]
    units = []
    for page in pages:
        for line, kind in [(1, "image_description"), (2, "table_cell"), (3, "heading")]:
            units.append(_unit(page, line, kind, len(units)))
    evidence = _evidence(pages, repetition=build_repetition(pages))
    before_pages = [page.model_dump_json() for page in pages]
    before_evidence = deepcopy(evidence)
    report = evaluate_document(_gold(pages, units), pages, evidence, {})
    repetition = report["repetition"]
    assert repetition["candidates"] == 3
    assert repetition["unique_candidate_tokens"] == 12
    assert repetition["not_aligned_to_reference"] == 6
    assert repetition["aligned_to_reference"] == 6
    assert repetition["aligned_unit_kinds"] == {"image_description": 3, "table_cell": 3}
    assert sum(row["aligned"] for row in repetition["candidate_details"]) == 6
    styles = report["heading_styles"]
    assert styles["heading_units"] == 3
    assert sum(row["aligned_heading_tokens"] for row in styles["clusters"]) == 9
    assert report["overall"] is None
    assert report["reference_human_approved"] is False
    assert evidence == before_evidence
    assert [page.model_dump_json() for page in pages] == before_pages


def _navigation_fixture():
    pages = [
        _page(1, [("Alpha Title .... 2", (20, 20, 80, 30))]),
        _page(2, [("Alpha Title", (20, 45, 80, 55))]),
        _page(3, [("Beta Topic", (20, 45, 80, 55))]),
    ]
    units = [_unit(pages[1], 0, "heading", 0), _unit(pages[2], 0, "heading", 1)]
    return pages, _gold(pages, units), {0: "Alpha Title", 1: "Beta Topic"}


def test_navigation_precision_is_one_to_one_and_target_precision_counts_wrong_destinations():
    pages, gold, titles = _navigation_fixture()
    entries = [
        _bookmark("alpha", "Alpha Title", [2]),
        _bookmark("alpha-duplicate", "Alpha Title", [2]),
        _bookmark("beta-wrong-page", "Beta Topic", [2]),
        _bookmark("invented", "Invented navigation", [3]),
    ]
    report = evaluate_document(gold, pages, _evidence(pages, entries=entries), titles)
    navigation = report["navigation"]["bookmark"]
    assert navigation["title_matches"] == 2
    assert navigation["title_precision"] == 0.5
    assert navigation["title_recall"] == 1
    assert navigation["title_and_target_matches"] == 1
    assert navigation["title_and_target_precision"] == 0.25
    assert navigation["title_and_target_recall"] == 0.5
    assert report["navigation"]["combined_unique"]["entries"] == 3
    assert len({match["unit"] for match in navigation["matches"]}) == 2


@pytest.mark.parametrize("labels,expected_unique", [(("10", "20"), 2), (("\uff11\uff10", "10"), 1)])
def test_combined_navigation_keeps_distinct_unresolved_labels(labels, expected_unique):
    pages = [
        _page(
            1,
            [
                ("Shared heading .... 10", (20, 20, 80, 30)),
                ("Shared heading .... 20", (20, 35, 80, 45)),
            ],
        ),
        _page(2, [("Shared heading", (20, 40, 80, 50))]),
        _page(3, [("Shared heading", (20, 40, 80, 50))]),
    ]
    units = [_unit(page, 0, "heading", ordinal) for ordinal, page in enumerate(pages[1:])]
    entries = [
        {
            "id": f"printed-{ordinal}",
            "kind": "printed_toc",
            "source_page": 1,
            "line_ids": [f"line-1-{ordinal}"],
            "title_refs": [{"span_id": f"span-1-{ordinal}-0", "start": 0, "end": 14}],
            "target_pages": [],
            "target_label": label,
        }
        for ordinal, label in enumerate(labels)
    ]
    entries.append({**entries[0], "id": "printed-duplicate"})
    report = evaluate_document(
        _gold(pages, units),
        pages,
        _evidence(pages, entries=entries),
        {0: "Shared heading", 1: "Shared heading"},
    )
    combined = report["navigation"]["combined_unique"]
    assert combined["entries"] == expected_unique
    assert combined["title_matches"] == expected_unique
    assert combined["unresolved_targets"] == expected_unique
    assert combined["title_and_target_matches"] == 0


def test_combined_navigation_prefers_resolved_pages_over_different_label_spellings():
    pages, gold, titles = _navigation_fixture()
    printed = {
        "id": "printed-alpha",
        "kind": "printed_toc",
        "source_page": 1,
        "line_ids": ["line-1-0"],
        "title_refs": [{"span_id": "span-1-0-0", "start": 0, "end": 11}],
        "target_pages": [2],
        "target_label": "\uff11\uff10",
    }
    bookmark = {**_bookmark("bookmark-alpha", "Alpha Title", [2]), "target_label": "different"}
    report = evaluate_document(gold, pages, _evidence(pages, entries=[bookmark, printed]), titles)
    assert report["navigation"]["combined_unique"]["entries"] == 1
    assert report["navigation"]["combined_unique"]["title_and_target_matches"] == 1


def test_matching_identical_heading_titles_uses_destinations_to_break_ties():
    pages = [
        _page(1, [("Shared heading", (20, 40, 80, 50))]),
        _page(2, [("Shared heading", (20, 40, 80, 50))]),
    ]
    units = [_unit(page, 0, "heading", ordinal) for ordinal, page in enumerate(pages)]
    entries = [
        _bookmark("second", "Shared heading", [2]),
        _bookmark("first", "Shared heading", [1]),
    ]
    report = evaluate_document(
        _gold(pages, units),
        pages,
        _evidence(pages, entries=entries),
        {0: "Shared heading", 1: "Shared heading"},
    )
    assert report["navigation"]["bookmark"]["title_and_target_matches"] == 2


def test_printed_title_resolves_source_ranges_and_ambiguous_target_is_not_scored_correct():
    pages, gold, titles = _navigation_fixture()
    printed = {
        "id": "printed-alpha",
        "kind": "printed_toc",
        "source_page": 1,
        "line_ids": ["line-1-0"],
        "title_refs": [{"span_id": "span-1-0-0", "start": 0, "end": 11}],
        "target_pages": [2, 3],
    }
    report = evaluate_document(gold, pages, _evidence(pages, entries=[printed]), titles)
    navigation = report["navigation"]["printed_toc"]
    assert navigation["title_matches"] == 1
    assert navigation["ambiguous_targets"] == 1
    assert navigation["title_and_target_matches"] == 0
    assert navigation["matches"][0]["target_ambiguous"]


@pytest.mark.parametrize("corruption", ["digest", "count", "missing_page", "source"])
def test_document_evaluation_rejects_mismatched_gold_provenance(corruption):
    pages, gold, titles = _navigation_fixture()
    evidence = _evidence(pages)
    if corruption == "digest":
        gold.pages[0]["token_digest"] = "0" * 64
    elif corruption == "count":
        gold.pages[0]["tokens"] += 1
    elif corruption == "missing_page":
        pages = pages[1:]
    else:
        gold.manifest["provenance"]["pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        evaluate_document(gold, pages, evidence, titles)


@pytest.mark.parametrize("corruption", ["duplicate_page", "mixed_source", "bad_unit", "bad_line"])
def test_document_evaluation_rejects_corrupt_input_references(corruption):
    pages, gold, titles = _navigation_fixture()
    evidence = _evidence(pages)
    if corruption == "duplicate_page":
        pages = [*pages, pages[0]]
    elif corruption == "mixed_source":
        other = pages[1].model_dump()
        other["source_sha256"] = "b" * 64
        for span in other["store"]["spans"].values():
            span["provenance"]["source_sha256"] = "b" * 64
        pages[1] = ExtractedPage.model_validate(other)
    elif corruption == "bad_unit":
        gold.units[0]["pdf"] = [[2, -1, 1]]
    else:
        evidence["repetition"]["candidates"] = [
            {
                "id": "corrupt",
                "band": "top",
                "confidence": 1,
                "pages": [1],
                "occurrences": [{"page": 1, "line_id": "missing-line"}],
            }
        ]
    with pytest.raises(ValueError):
        evaluate_document(gold, pages, evidence, titles)


def test_overlay_sidecar_exposes_style_repetition_and_navigation_without_source_mutation(tmp_path):
    pages, _, _ = _navigation_fixture()
    printed = {
        "id": "printed-alpha",
        "kind": "printed_toc",
        "source_page": 1,
        "line_ids": ["line-1-0"],
        "target_pages": [2],
    }
    evidence = _evidence(pages, entries=[printed, _bookmark("incoming", "Alpha Title", [1])])
    evidence["repetition"] = {
        "candidates": [
            {
                "id": "repeat",
                "occurrences": [{"page": 1, "line_id": "line-1-0"}],
            }
        ]
    }
    success, png = cv2.imencode(".png", np.full((100, 100, 3), 255, dtype=np.uint8))
    assert success
    raster = RasterPage(png=png.tobytes(), width=100, height=100, page_width=100, page_height=100)
    before = pages[0].model_dump_json()
    output = tmp_path / "evidence.png"
    sidecar = render_document_overlay(raster, pages[0], evidence, output)
    image = cv2.imread(str(output))
    assert image.shape == (200, 100, 3)
    assert sidecar["incoming_navigation"] == ["incoming"]
    assert sidecar["lines"][0]["style_cluster_id"]
    assert sidecar["lines"][0]["repetition_candidates"] == ["repeat"]
    assert sidecar["lines"][0]["toc_links"] == ["printed-alpha"]
    assert pages[0].model_dump_json() == before
