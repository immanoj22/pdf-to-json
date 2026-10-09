"""Synthetic navigation evidence tests; no references or hold-out books are read."""

import copy
import unicodedata

import pymupdf
import pytest

from book_core.document_analysis.navigation import (
    NavigationConfig,
    analyze_navigation,
    resolve_entry_title,
)
from book_core.extraction.interfaces import DocumentExtractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)


def page_with_rows(rows, page_number=1):
    spans, lines = {}, []
    for ordinal, row in enumerate(rows):
        text, x0, y0, x1 = row
        sid = f"s-{page_number}-{ordinal}"
        lid = f"l-{page_number}-{ordinal}"
        bbox = BBox(x0=x0, y0=y0, x1=x1, y1=y0 + 10)
        spans[sid] = TextSpan(
            id=sid,
            line_id=lid,
            page=page_number,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=bbox,
            font="Synthetic",
            size=10,
            color=0,
            flags=0,
            provenance=Provenance(source_sha256="a" * 64),
        )
        lines.append(SourceLine(id=lid, page=page_number, bbox=bbox, span_ids=[sid]))
    return ExtractedPage(
        source_sha256="a" * 64,
        extractor=ExtractorIdentity(name="synthetic", version="1", configuration={}),
        geometry=PageGeometry(
            page=page_number,
            width=300,
            height=400,
            rotation=0,
            content_bbox=BBox(x0=0, y0=0, x1=300, y1=400),
        ),
        store=SpanStore(spans=spans, lines=lines),
    )


def metadata(labels=None, bookmarks=None):
    return {
        "source_sha256": "a" * 64,
        "page_count": 20,
        "page_labels": [{"page": page, "label": label} for page, label in (labels or [])],
        "bookmarks": bookmarks or [],
    }


def test_printed_toc_leaders_refs_and_labels_without_text_copy():
    page = page_with_rows(
        [
            ("Introduction .... 1", 20, 20, 260),
            ("Methods....iv", 30, 40, 260),
            ("Conclusion \u2026\u2026 7", 20, 60, 260),
        ]
    )
    before = copy.deepcopy(page.model_dump())
    result = analyze_navigation([page], metadata([(2, "1"), (3, "iv"), (9, "7")]))
    assert len(result["toc_pages"]) == 1
    assert [r["target_pages"] for r in result["printed_entries"]] == [[2], [3], [9]]
    assert [resolve_entry_title(r, {1: page}) for r in result["printed_entries"]] == [
        "Introduction",
        "Methods",
        "Conclusion",
    ]
    assert all("title" not in r and r["title_refs"] for r in result["printed_entries"])
    assert "heading_level" not in str(result)
    assert page.model_dump() == before


def test_ambiguous_and_missing_labels_are_not_guessed():
    page = page_with_rows(
        [
            ("First title .... 1", 20, 20, 260),
            ("Second title .... 2", 20, 40, 260),
            ("Third title .... 3", 20, 60, 260),
        ]
    )
    result = analyze_navigation([page], metadata([(4, "1"), (5, "1"), (6, "2")]))
    first, _, third = result["printed_entries"]
    assert first["target_pages"] == [4, 5] and first["target_page"] is None
    assert first["label_link_confidence"] == 0.5
    assert third["target_pages"] == [] and third["target_page"] is None


def test_split_cells_and_wrapped_title_preserve_ranges():
    page = page_with_rows(
        [
            ("A long opening", 20, 10, 150),
            ("chapter title", 20, 22, 150),
            ("1", 250, 22, 260),
            ("Second entry", 20, 50, 150),
            ("2", 250, 50, 260),
            ("Third entry", 20, 70, 150),
            ("3", 250, 70, 260),
        ]
    )
    result = analyze_navigation([page], metadata([(5, "1"), (7, "2"), (9, "3")]))
    assert len(result["printed_entries"]) == 3
    first = result["printed_entries"][0]
    assert first["split_cells"] and first["wrapped"]
    assert resolve_entry_title(first, [page]) == "A long opening chapter title"
    assert len(first["line_ids"]) == 3


def test_rtl_prefix_page_references_and_indentation_evidence():
    page = page_with_rows(
        [
            ("\u0661 .... \u0627\u0644\u0645\u0642\u062f\u0645\u0629", 20, 20, 260),
            ("\u0662 .... \u0627\u0644\u0645\u0646\u0647\u062c", 20, 40, 250),
            ("\u0663 .... \u0627\u0644\u062e\u0627\u062a\u0645\u0629", 20, 60, 260),
        ]
    )
    result = analyze_navigation([page], metadata([(4, "\u0661"), (5, "\u0662"), (6, "\u0663")]))
    assert len(result["printed_entries"]) == 3
    assert [r["target_pages"] for r in result["printed_entries"]] == [[4], [5], [6]]
    assert all(r["level_evidence"]["reference_side"] == "prefix" for r in result["printed_entries"])
    assert (
        resolve_entry_title(result["printed_entries"][0], [page])
        == "\u0627\u0644\u0645\u0642\u062f\u0645\u0629"
    )


def test_numeric_tables_and_prose_do_not_become_toc():
    numeric = page_with_rows(
        [("12.3 44 1", 20, 20, 260), ("13.4 55 2", 20, 40, 260), ("14.5 66 3", 20, 60, 260)]
    )
    prose = page_with_rows(
        [
            ("A narrative sentence ending in 2020", 20, 20, 260),
            ("Another sentence about year 2021", 20, 40, 260),
            ("More ordinary prose describing 2022", 20, 60, 260),
        ]
    )
    numbered = page_with_rows(
        [
            ("1 Introduction", 20, 20, 260),
            ("2 Methods", 20, 40, 260),
            ("3 Conclusions", 20, 60, 260),
        ]
    )
    for page in (numeric, prose, numbered):
        result = analyze_navigation([page], metadata())
        assert not result["toc_pages"] and not result["printed_entries"]


def test_bookmarks_keep_outline_depth_and_unresolved_actions():
    result = analyze_navigation(
        [],
        metadata(
            [(7, "vii")],
            [
                {"title": "Opening", "depth": 2, "target_page": 7},
                {"title": "Website", "depth": 1, "target_page": None, "action_kind": 2},
            ],
        ),
    )
    opening, external = result["bookmarks"]
    assert opening["level_evidence"] == {"outline_depth": 2}
    assert opening["target_label"] == "vii" and opening["target_pages"] == [7]
    assert resolve_entry_title(opening, {}) == "Opening"
    assert external["target_pages"] == []


def test_extractor_navigation_and_native_block_ids(tmp_path):
    source = tmp_path / "synthetic.pdf"
    doc = pymupdf.open()
    for text in ("First block", "Second block", "Third block"):
        page = doc.new_page()
        page.insert_text((40, 50), text)
        page.insert_text((40, 100), "Another native block")
    doc.set_page_labels([{"startpage": 0, "style": "r", "firstpagenum": 1}])
    doc.set_toc([[1, "First entry", 1], [2, "Second entry", 2]])
    doc.save(source)
    doc.close()
    extractor = PyMuPDFExtractor("cpu")
    identity = extractor.identity.model_dump()
    assert isinstance(extractor, DocumentExtractor)
    navigation = extractor.extract_navigation(source)
    assert [r["label"] for r in navigation["page_labels"]] == ["i", "ii", "iii"]
    assert [r["target_page"] for r in navigation["bookmarks"]] == [1, 2]
    assert [r["depth"] for r in navigation["bookmarks"]] == [1, 2]
    pages = list(extractor.extract_pages(source))
    blocks = extractor.extract_native_blocks(source)
    assert navigation["native_blocks"] == blocks
    assert [lid for block in blocks for lid in block["line_ids"]] == [
        line.id for page in pages for line in page.store.lines
    ]
    assert extractor.identity.model_dump() == identity


def test_metadata_mismatch_and_bad_config_rejected():
    page = page_with_rows([("Title .... 1", 20, 20, 260)])
    bad = metadata()
    bad["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="different sources"):
        analyze_navigation([page], bad)
    with pytest.raises(ValueError, match="repeated structure"):
        NavigationConfig(minimum_entries=1)


@pytest.mark.parametrize("direction", [(0.0, 1.0), (0.0, -1.0), (-1.0, 0.0)])
def test_rotated_and_vertical_toc_uses_native_writing_frame(direction):
    page = page_with_rows(
        [
            ("Opening", 20, 20, 150),
            ("1", 250, 20, 260),
            ("Methods", 20, 40, 150),
            ("2", 250, 40, 260),
            ("Results", 20, 60, 150),
            ("3", 250, 60, 260),
        ]
    )

    def transform(box):
        if direction == (0.0, 1.0):
            return BBox(x0=400 - box.y1, y0=box.x0, x1=400 - box.y0, y1=box.x1)
        if direction == (0.0, -1.0):
            return BBox(x0=box.y0, y0=300 - box.x1, x1=box.y1, y1=300 - box.x0)
        return BBox(x0=300 - box.x1, y0=400 - box.y1, x1=300 - box.x0, y1=400 - box.y0)

    payload = page.model_dump()
    for line in payload["store"]["lines"]:
        line["bbox"] = transform(BBox(**line["bbox"])).model_dump()
    for span in payload["store"]["spans"].values():
        span["bbox"] = transform(BBox(**span["bbox"])).model_dump()
    if direction[0] == 0:
        payload["geometry"].update(
            width=400, height=300, content_bbox={"x0": 0, "y0": 0, "x1": 400, "y1": 300}
        )
    page = ExtractedPage.model_validate(payload)
    data = metadata([(5, "1"), (7, "2"), (9, "3")])
    data["line_geometry"] = {
        line.id: {
            "direction": direction,
            "writing_mode": "vertical" if direction[0] == 0 else "horizontal",
        }
        for line in page.store.lines
    }
    result = analyze_navigation([page], data)
    assert len(result["printed_entries"]) == 3
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Methods",
        "Results",
    ]
    assert [r["target_pages"] for r in result["printed_entries"]] == [[5], [7], [9]]
    assert all(r["direction"] == list(direction) for r in result["printed_entries"])


def test_text_table_with_multiple_numeric_columns_is_not_toc():
    page = page_with_rows(
        [
            ("Apples", 20, 20, 100),
            ("1", 180, 20, 190),
            ("11", 250, 20, 260),
            ("Oranges", 20, 40, 100),
            ("2", 180, 40, 190),
            ("12", 250, 40, 260),
            ("Pears", 20, 60, 100),
            ("3", 180, 60, 190),
            ("13", 250, 60, 260),
        ]
    )
    data = metadata([(5, "1"), (6, "2"), (7, "3"), (8, "11"), (9, "12"), (10, "13")])
    result = analyze_navigation([page], data)
    assert result["printed_entries"] == []


def test_spaced_leaders_inline_need_no_pdf_labels():
    page = page_with_rows(
        [
            ("Opening . . . . . 1", 20, 20, 260),
            ("Methods . . . . . 4", 20, 40, 260),
            ("Results . . . . . 9", 20, 60, 260),
        ]
    )
    result = analyze_navigation([page], metadata())
    assert len(result["toc_pages"]) == 1
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Methods",
        "Results",
    ]
    assert [r["target_label"] for r in result["printed_entries"]] == ["1", "4", "9"]
    assert all(r["leaders"] and not r["target_pages"] for r in result["printed_entries"])


def test_spaced_leaders_split_cells_need_no_pdf_labels():
    page = page_with_rows(
        [
            ("Opening . . . . .", 20, 20, 230),
            ("1", 250, 20, 260),
            ("Methods . . . . .", 20, 40, 230),
            ("4", 250, 40, 260),
            ("Results . . . . .", 20, 60, 230),
            ("9", 250, 60, 260),
        ]
    )
    result = analyze_navigation([page], metadata())
    assert len(result["toc_pages"]) == 1
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Methods",
        "Results",
    ]
    assert [r["target_label"] for r in result["printed_entries"]] == ["1", "4", "9"]
    assert all(
        r["leaders"] and r["split_cells"] and not r["target_pages"]
        for r in result["printed_entries"]
    )


def test_repeated_locator_side_prevents_nearest_pair_crossing_gutter():
    rows = []
    for index in range(4):
        y = 20 + index * 20
        rows.extend(
            [
                (
                    "Short left title" if index == 3 else "Long left title",
                    20,
                    y,
                    120 if index == 3 else 210,
                ),
                (str(index + 1), 220, y, 230),
                ("Neighbour column title", 260, y, 400),
                (str(index + 5), 500, y, 510),
            ]
        )
    original = page_with_rows(rows)
    payload = original.model_dump()
    payload["geometry"].update(width=600, content_bbox={"x0": 0, "y0": 0, "x1": 600, "y1": 400})
    page = ExtractedPage.model_validate(payload)
    result = analyze_navigation([page], metadata([(n + 10, str(n)) for n in range(1, 9)]))
    assert len(result["printed_entries"]) == 8
    short = next(r for r in result["printed_entries"] if r["target_label"] == "4")
    assert resolve_entry_title(short, [page]) == "Short left title"
    assert short["reference_side"] == "suffix"
    assert short["pairing_side_support"] == 0.75
    assert short["pairing_selected_by"] == "repeated_locator_side"
    assert not short["pairing_ambiguous"]
    assert len(short["alternate_title_refs"]) == 1
    alternate = {**short, "title_refs": short["alternate_title_refs"][0]["title_refs"]}
    assert resolve_entry_title(alternate, [page]) == "Neighbour column title"


def test_leaderless_repeated_split_rows_remain_lower_confidence_evidence():
    page = page_with_rows(
        [
            ("Opening", 20, 20, 150),
            ("1", 250, 20, 260),
            ("Methods", 20, 40, 150),
            ("4", 250, 40, 260),
            ("Results", 20, 60, 150),
            ("9", 250, 60, 260),
        ]
    )
    result = analyze_navigation([page], metadata())
    assert len(result["toc_pages"]) == 1
    assert len(result["printed_entries"]) == 3
    assert result["toc_pages"][0]["features"]["geometry_only_ambiguous"]
    assert result["toc_pages"][0]["confidence"] <= 0.6
    assert all(
        r["geometry_only_ambiguous"] and not r["target_pages"] for r in result["printed_entries"]
    )
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Methods",
        "Results",
    ]


def test_insufficient_side_majority_preserves_alternates_and_reduces_confidence():
    rows = []
    for index in range(4):
        y = 20 + index * 20
        rows.extend(
            [
                ("Left title", 20, y, 210 if index < 2 else 120),
                (str(index + 1), 220, y, 230),
                ("Right title", 260, y, 290),
            ]
        )
    page = page_with_rows(rows)
    result = analyze_navigation([page], metadata())
    assert len(result["printed_entries"]) == 4
    assert all(
        r["pairing_ambiguous"] and r["alternate_title_refs"] for r in result["printed_entries"]
    )
    assert all(
        r["pairing_side_support"] == 0.5 and r["confidence"] < 0.4
        for r in result["printed_entries"]
    )


def test_mixed_inline_prefix_and_suffix_entries_have_boolean_alignment_support():
    page = page_with_rows(
        [
            ("Opening .... 1", 20, 20, 260),
            ("2 .... Background", 20, 40, 260),
            ("Methods .... 3", 20, 60, 260),
            ("4 .... Discussion", 20, 80, 260),
            ("Results .... 5", 20, 100, 260),
            ("6 .... Closing", 20, 120, 260),
        ]
    )
    result = analyze_navigation([page], metadata())
    assert len(result["toc_pages"]) == 1
    assert len(result["printed_entries"]) == 6
    assert {r["reference_side"] for r in result["printed_entries"]} == {"prefix", "suffix"}
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Background",
        "Methods",
        "Discussion",
        "Results",
        "Closing",
    ]


def test_native_block_wrap_includes_hanging_indent_and_excludes_adjacent_header():
    page = page_with_rows(
        [
            ("Separate section header", 20, 0, 180),
            ("Long opening title", 20, 12, 160),
            ("with hanging continuation", 42, 24, 190),
            ("1", 250, 24, 260),
            ("Methods", 20, 50, 150),
            ("4", 250, 50, 260),
            ("Results", 20, 70, 150),
            ("9", 250, 70, 260),
        ]
    )
    data = metadata([(5, "1"), (7, "4"), (10, "9")])
    data["native_blocks"] = [
        {"page": 1, "block": 0, "line_ids": [page.store.lines[0].id]},
        {"page": 1, "block": 1, "line_ids": [line.id for line in page.store.lines[1:4]]},
        {"page": 1, "block": 2, "line_ids": [line.id for line in page.store.lines[4:6]]},
        {"page": 1, "block": 3, "line_ids": [line.id for line in page.store.lines[6:8]]},
    ]
    result = analyze_navigation([page], data)
    first = next(r for r in result["printed_entries"] if r["target_label"] == "1")
    assert resolve_entry_title(first, [page]) == "Long opening title with hanging continuation"
    assert first["wrapped"] and not first["incomplete_wrap"]
    assert first["wrap_method"] == "single_entry_native_extraction_block"
    assert page.store.lines[0].id not in first["line_ids"]


def test_multiple_entries_in_native_block_are_not_folded_together():
    page = page_with_rows(
        [
            ("Separate header", 20, 0, 180),
            ("Opening", 20, 12, 150),
            ("1", 250, 12, 260),
            ("Methods", 20, 32, 150),
            ("4", 250, 32, 260),
            ("Results", 20, 52, 150),
            ("9", 250, 52, 260),
        ]
    )
    data = metadata([(5, "1"), (7, "4"), (10, "9")])
    data["native_blocks"] = [
        {"page": 1, "block": 0, "line_ids": [line.id for line in page.store.lines]}
    ]
    result = analyze_navigation([page], data)
    assert [resolve_entry_title(r, [page]) for r in result["printed_entries"]] == [
        "Opening",
        "Methods",
        "Results",
    ]
    assert all(not r["wrapped"] and r["incomplete_wrap"] for r in result["printed_entries"])
    assert all(
        r["wrap_method"] == "multiple_entries_in_native_block" for r in result["printed_entries"]
    )
