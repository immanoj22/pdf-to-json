"""Synthetic typography and vocabulary evidence; no book-specific assumptions."""

import json
import unicodedata

import pytest

from book_core.document_analysis.styles import build_style_profile, normalize_font_family
from book_core.document_analysis.vocabulary import build_vocabulary
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)


def _page(lines, *, number=1, source="a" * 64):
    spans = {}
    source_lines = []
    for line_ordinal, parts in enumerate(lines):
        line_id = f"line-{number}-{line_ordinal}"
        ids = []
        for ordinal, part in enumerate(parts):
            part = {"raw_text": part} if isinstance(part, str) else dict(part)
            raw = part.pop("raw_text")
            sid = f"span-{number}-{line_ordinal}-{ordinal}"
            ids.append(sid)
            spans[sid] = TextSpan(
                id=sid,
                line_id=line_id,
                page=number,
                raw_text=raw,
                text=unicodedata.normalize("NFKC", raw),
                bbox=BBox(x0=10, y0=10, x1=90, y1=20),
                font=part.pop("font", "Example-Regular"),
                size=part.pop("size", 10),
                color=part.pop("color", 0),
                flags=part.pop("flags", 0),
                provenance=Provenance(source_sha256=source),
                **part,
            )
        source_lines.append(
            SourceLine(
                id=line_id,
                page=number,
                bbox=BBox(x0=10, y0=10, x1=90, y1=20),
                span_ids=ids,
            )
        )
    return ExtractedPage(
        source_sha256=source,
        extractor=ExtractorIdentity(name="test", version="1", configuration={}),
        geometry=PageGeometry(
            page=number,
            width=100,
            height=100,
            rotation=0,
            content_bbox=BBox(x0=0, y0=0, x1=100, y1=100),
        ),
        store=SpanStore(spans=spans, lines=source_lines),
    )


@pytest.mark.parametrize(
    "font,expected",
    [
        ("ABCDEF+Example-BoldItalic", "example"),
        ("ZZZZZZ+Example-Bold-Oblique", "example"),
        ("Example Regular", "example"),
        ("Example-Condensed-Regular", "example-condensed"),
        ("ActualBold", "actualbold"),
        ("مرحبا", "مرحبا"),
    ],
)
def test_normalized_family_has_no_subset_or_delimited_style_suffix(font, expected):
    assert normalize_font_family(font) == expected


def test_character_mass_selects_body_not_line_or_span_count():
    page = _page(
        [[{"raw_text": "ordinary words " * 30, "font": "ABCDEF+Example-Regular"}]]
        + [[{"raw_text": "A", "font": "Other-Bold", "flags": 16, "size": 20}]] * 8
    )
    before = page.model_dump_json()
    profile = build_style_profile([page])
    body = next(style for style in profile["styles"] if style["key"] == profile["body_style_key"])
    assert body["font_family"] == "example"
    assert body["size"] == 10
    assert body["character_count"] == 13 * 30
    assert profile["body_confidence"] > 0.95
    assert profile["lines"][1]["body_relation"]["size_ratio"] == 2
    assert profile["lines"][1]["body_relation"]["bold_difference"]
    assert page.model_dump_json() == before
    assert "raw_text" not in json.dumps(profile)
    assert "heading" not in json.dumps(profile)


def test_mixed_line_retains_each_style_and_uses_native_flags():
    page = _page(
        [
            [
                {"raw_text": "long ordinary text", "font": "Example-Bold", "flags": 0},
                {"raw_text": "B", "font": "Example-Regular", "flags": 18, "color": 0xFF0000},
            ]
        ]
    )
    profile = build_style_profile([page])
    line = profile["lines"][0]
    assert len(line["style_weights"]) == 2
    assert not profile["styles"][0]["bold"]
    assert profile["styles"][1]["bold"] and profile["styles"][1]["italic"]
    assert line["span_ids"] == list(page.store.spans)
    assert 0 < line["confidence"] < 1


def test_rounding_and_complete_link_size_clusters_do_not_chain():
    page = _page([[{"raw_text": "same", "size": size}] for size in [10.05, 10.24, 10.45]])
    profile = build_style_profile([page])
    assert [cluster["sizes"] for cluster in profile["size_clusters"]] == [[10.1, 10.2], [10.5]]
    assert len(profile["style_clusters"]) == 2
    assert build_style_profile([page]) == profile


@pytest.mark.parametrize("direction", ["rtl", "ttb", None])
def test_uncased_scripts_and_directions_remain_evidence(direction):
    page = _page([[{"raw_text": "العربية 中文", "text_direction": direction, "script": None}]])
    profile = build_style_profile([page])
    assert profile["styles"][0]["caps"] == "uncased"
    assert profile["lines"][0]["span_ids"] == list(page.store.spans)
    assert build_vocabulary([page])["frequencies"] == {"العربية": 1, "中文": 1}
    assert page.store.spans["span-1-0-0"].text_direction == direction


def test_empty_profile_and_invalid_configuration_are_explicit():
    assert build_style_profile([])["body_style_key"] is None
    assert build_style_profile([_page([[" "]])])["body_style_key"] is None
    assert build_vocabulary([])["total_tokens"] == 0
    for tolerance in [-1, 1, float("nan")]:
        with pytest.raises(ValueError):
            build_style_profile([], size_cluster_tolerance=tolerance)


@pytest.mark.parametrize("builder", [build_style_profile, build_vocabulary])
def test_document_evidence_rejects_duplicate_pages_and_mixed_sources(builder):
    page = _page([["one"]])
    with pytest.raises(ValueError, match="Duplicate"):
        builder([page, page])
    with pytest.raises(ValueError, match="one source"):
        builder([page, _page([["two"]], number=2, source="b" * 64)])


def test_vocabulary_uses_benchmark_nfkc_and_unicode_tokens_without_changing_text():
    page = _page([["oﬃce OFFICE العربية ١٢ 中文测试"], ["Office"]])
    before = page.model_dump_json()
    vocabulary = build_vocabulary([page])
    assert vocabulary["frequencies"]["office"] == 1
    assert vocabulary["casefold_frequencies"]["office"] == 3
    assert vocabulary["frequencies"]["中文测试"] == 1
    assert vocabulary["total_tokens"] == 6
    assert page.model_dump_json() == before


@pytest.mark.parametrize("hyphen", ["-", "\u00ad", "\u2010", "\u2011"])
def test_hyphen_evidence_requires_independent_joined_spelling(hyphen):
    page = _page([[f"inter{hyphen}"], ["national cooperation"], ["INTERNATIONAL"]])
    vocabulary = build_vocabulary([page])
    evidence = vocabulary["hyphen_joins"][0]
    assert evidence["joined"] == "international"
    assert evidence["joined_occurs_elsewhere"]
    assert evidence["elsewhere_occurrences"] == 1
    assert evidence["elsewhere_exact_occurrences"] == 0
    assert not evidence["continuity_decided"]
    assert evidence["left_line_id"] == "line-1-0"
    assert evidence["right_line_id"] == "line-1-1"
    assert evidence["adjacency"] == "native_lines"


def test_hyphen_evidence_uses_blocks_when_provided():
    page = _page([["inter-"], ["national"], ["international"]])
    cross_block = [
        {"page": 1, "block": 1, "line_ids": ["line-1-0"]},
        {"page": 1, "block": 2, "line_ids": ["line-1-1", "line-1-2"]},
    ]
    assert not build_vocabulary([page], cross_block)["hyphen_joins"]
    same_block = [{"page": 1, "block": 1, "line_ids": [line.id for line in page.store.lines]}]
    evidence = build_vocabulary([page], same_block)["hyphen_joins"][0]
    assert evidence["adjacency"] == "same_native_block"
    assert evidence["native_block_id"] == "1"
    with pytest.raises(ValueError, match="multiple block"):
        build_vocabulary([page], same_block + same_block)


def test_no_join_across_pages_or_when_hyphen_is_a_separate_word():
    first = _page([["inter-"]])
    second = _page([["national international"]], number=2)
    assert not build_vocabulary([first, second])["hyphen_joins"]
    page = _page([["inter -"], ["national"], ["international"]])
    assert not build_vocabulary([page])["hyphen_joins"]


def test_uncertain_hyphen_evidence_is_retained_without_independent_spelling():
    page = _page([["frag-"], ["ment"]])
    evidence = build_vocabulary([page])["hyphen_joins"][0]
    assert not evidence["joined_occurs_elsewhere"]
    assert evidence["confidence"] < 0.5


def test_trimbox_excluded_line_breaks_join_adjacency_and_frequency():
    page = _page([["inter-"], ["excluded"], ["national"], ["international"]])
    payload = page.model_dump()
    payload["store"]["lines"][1]["bbox"] = {"x0": 101, "y0": 10, "x1": 102, "y1": 20}
    page = ExtractedPage.model_validate(payload)
    vocabulary = build_vocabulary([page])
    assert not vocabulary["hyphen_joins"]
    assert "excluded" not in vocabulary["frequencies"]
