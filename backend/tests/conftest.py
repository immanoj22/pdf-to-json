"""Shared source-evidence fixtures."""

import sys
import unicodedata
from pathlib import Path

import pytest

from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(ROOT / "experiments"))
from reference_paths import reference_path as reference_path  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_layout_models(monkeypatch):
    """Tests never load the real layout, formula or table models; evidence is supplied by stubs
    where needed."""
    import book_core.figures.evidence as evidence
    import book_core.mathml.settings as math_settings
    import book_core.tables.settings as table_settings

    monkeypatch.setattr(evidence, "models_available", lambda: False)
    monkeypatch.setattr(math_settings, "models_available", lambda: False)
    monkeypatch.setattr(table_settings, "models_available", lambda: False)


def pytest_configure(config):
    if config.option.basetemp is None:
        config.option.basetemp = str(ROOT / ".cache/pytest")


@pytest.fixture
def make_page():
    def build(parts=("Hello ", "world"), outside=False):
        bbox = BBox(x0=10, y0=10, x1=90, y1=25)
        spans = {}
        for index, text in enumerate(parts):
            sid = f"span-{index}"
            spans[sid] = TextSpan(
                id=sid,
                line_id="line",
                page=1,
                raw_text=text,
                text=unicodedata.normalize("NFKC", text),
                bbox=bbox,
                font="test",
                size=10,
                color=0,
                flags=0,
                provenance=Provenance(source_sha256="a" * 64),
            )
        return ExtractedPage(
            source_sha256="a" * 64,
            extractor=ExtractorIdentity(name="test", version="1", configuration={}),
            geometry=PageGeometry(
                page=1,
                width=100,
                height=100,
                rotation=0,
                content_bbox=BBox(x0=0, y0=40 if outside else 0, x1=100, y1=100),
            ),
            store=SpanStore(
                spans=spans,
                lines=[SourceLine(id="line", page=1, bbox=bbox, span_ids=list(spans))],
            ),
        )

    return build
