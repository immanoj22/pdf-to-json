"""I5 also covers free rotated text beside figure-owned rotated labels."""

from collections import Counter
from types import SimpleNamespace

import pytest

from book_core.layout.models import Scope, VisualBlock, VisualLine
from book_core.layout.pipeline import build_regions
from book_core.model.common import BBox


def line(name, x, y, size=6, rotation=90):
    return VisualLine(
        id=name,
        span_ids=[name],
        source_line_ids=[name],
        bbox=BBox(x0=x, y0=y, x1=x + size, y1=y + 60),
        baseline_start=(x, y + 60),
        baseline_end=(x, y),
        direction=(0, -1),
        rotation=rotation,
        writing_mode="horizontal",
        font_size=size,
        visible=True,
        inside_content=True,
    )


@pytest.mark.parametrize("scale", [0.5, 1, 3])
@pytest.mark.parametrize("case", ["near", "far", "adjacent", "solitary"])
def test_fallback_uses_full_page_rotated_group(case, scale):
    # The figure owns two rotated labels. Only one/two free lines remain, so
    # ownership cannot create an independent rotated frame for them.
    free = line("credit", 350 if case in {"far", "solitary"} else 208, 120)
    labels = [] if case == "solitary" else [line("label-a", 120, 130), line("label-b", 160, 130)]
    neighbours = [line("note", free.bbox.x0 + 8, 120)] if case == "adjacent" else []
    body = line("body", 40, 300, size=10, rotation=0)
    lines = [free, *labels, *neighbours, body]
    figure = VisualBlock(
        id="figure",
        kind="figure",
        bbox=BBox(x0=100, y0=100, x1=200, y1=240),
        confidence=0.9,
        reasons=["test"],
    )

    def scaled(item):
        update = {"bbox": BBox(**{k: v * scale for k, v in item.bbox.model_dump().items()})}
        if isinstance(item, VisualLine):
            update["font_size"] = item.font_size * scale
        return item.model_copy(update=update)

    lines = [scaled(item) for item in lines]
    figure = scaled(figure)
    content = BBox(x0=0, y0=0, x1=500 * scale, y1=500 * scale)
    scope = Scope(id="page", kind="page", bbox=content)
    store = SimpleNamespace(
        spans={
            item.id: SimpleNamespace(
                raw_text=item.id, font="test", size=item.font_size, color=0, flags=0
            )
            for item in lines
        }
    )
    owner = {item.id: ("figure", "figure") for item in labels}
    owner.update({item.id: ("rotated", None) for item in [free, *neighbours]})
    owner[body.id] = ("scope", None)
    regions = build_regions(
        lines,
        [figure],
        owner,
        [scope],
        {None: scope.id},
        {figure.id: scope.id},
        [],
        {},
        store,
        content,
        scope,
    )
    region = next(r for r in regions if free.id in r.line_ids)
    assert region.type == ("unknown" if case in {"far", "adjacent"} else "credit_candidate")
    if region.type == "unknown":
        assert region.review_required
    assert all(
        r.type == "figure" for r in regions if set(r.line_ids) & {item.id for item in labels}
    )
    assert Counter(lid for r in regions for lid in r.line_ids) == Counter(item.id for item in lines)
