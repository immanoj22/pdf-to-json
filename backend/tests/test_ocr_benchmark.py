"""Test benchmark counting and figure exclusion without opening any real reference."""

import importlib.util
from pathlib import Path

import pytest

from book_core.extraction.rasters import RasterPage
from book_core.ocr.engines import OcrOrientation, OcrReading, OcrWord
from book_core.ocr.geometry import ImageTransform


@pytest.fixture
def benchmark():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "step16_benchmark_test", root / "experiments/step16_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_figure_mask_excludes_the_whole_intersected_span(benchmark):
    data = {
        "source": {
            "store": {
                "spans": {
                    "inside": {"raw_text": "label", "bbox": {"x0": 5, "y0": 5, "x1": 20, "y1": 10}},
                    "outside": {
                        "raw_text": "body",
                        "bbox": {"x0": 30, "y0": 5, "x1": 50, "y1": 10},
                    },
                },
                "lines": [{"id": "one", "span_ids": ["inside", "outside"]}],
            }
        },
        "figures": {"figures": [{"bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 20}}]},
    }
    lines, masks, excluded = benchmark.native_truth(data)
    assert excluded == ["inside"]
    assert lines[0]["text"] == "body"
    assert (5, 5, 20, 10) in masks
    assert data["source"]["store"]["spans"]["inside"]["raw_text"] == "label"


def test_geometry_score_is_separate_from_emission_order_and_extra_words_count(benchmark):
    transform = ImageTransform.identity(100, 60)
    raster = RasterPage(png=b"unused", width=100, height=60, page_width=100, page_height=60)
    lines = [
        {"id": "one", "text": "first line", "bbox": (0, 0, 50, 10)},
        {"id": "two", "text": "second line", "bbox": (0, 20, 50, 30)},
    ]
    words = (
        OcrWord("second line", (0, 20, 50, 30), 0.9, (2,), granularity="line"),
        OcrWord("first line", (0, 0, 50, 10), 0.9, (1,), granularity="line"),
    )
    reading = OcrReading("test", "1", ("eng",), words, OcrOrientation(), transform)
    score = benchmark.score(reading, lines, raster, transform)
    assert score["geometry_aligned"]["word_errors"] == 0
    assert score["raw_emission_order"]["word_errors"] > 0
    assert len(score["observations"]) == 4
    reading = OcrReading(
        "test",
        "1",
        ("eng",),
        (*words, OcrWord("extra", (60, 40, 90, 50), 0.9, (3,))),
        OcrOrientation(),
        transform,
    )
    score = benchmark.score(reading, lines, raster, transform)
    assert score["geometry_aligned"]["word_errors"] == 1
    assert score["unmatched_items"] == 1
