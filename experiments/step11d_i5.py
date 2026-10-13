"""Explain full-book baseline I5 failures without changing any layout decision."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11c_identity import BOOKS  # noqa: E402

from book_core.layout.evidence import (  # noqa: E402
    credit_like,
    isolated_rotated,
    line_text,
    near_figure_edge,
    page_body_style,
)
from book_core.layout.models import PageLayout  # noqa: E402
from book_core.objects.analysis import verified_read  # noqa: E402
from book_core.objects.models import ObjectAnalysis  # noqa: E402

OUT = ROOT / "experiments/out/step11d"
rows = []
for book in BOOKS:
    path = OUT / "before" / f"{book}_full_gates.json"
    if not path.exists():
        raise ValueError("Finish the four-book baseline before diagnosing its I5 failures")
    gates = json.loads(path.read_text("utf8"))
    keys = json.loads((OUT / "before" / f"{book}.json").read_text("utf8"))["keys"]
    for number, violations in gates["invariants"].items():
        if not violations["I5"]:
            continue
        analysis = verified_read(
            ROOT / ".cache/step7/analysis" / keys["analysis"] / f"{number}.json",
            ObjectAnalysis,
            keys["analysis"],
        )
        layout = verified_read(
            ROOT / ".cache/step7/layout" / keys["layout"] / f"{number}.json",
            PageLayout,
            keys["layout"],
        )
        style = page_body_style(layout.lines, analysis.native.page.store)
        body_size = style[1] if style else None
        figures = [b.bbox for b in layout.blocks if b.kind == "figure"]
        region_of = {lid: region for region in layout.regions for lid in region.line_ids}
        failed = []
        for line in layout.lines:
            region = region_of.get(line.id)
            if region is None or region.type != "credit_candidate":
                continue
            if credit_like(line, layout.lines, figures, body_size):
                continue
            failed.append(
                {
                    "line": line.model_dump(mode="json"),
                    "region": region.model_dump(mode="json"),
                    "text": line_text(line, analysis.native.page.store),
                    "small_relative_to_body": body_size is None
                    or line.font_size <= 1.05 * body_size,
                    "isolated_rotated": isolated_rotated(line, layout.lines),
                    "near_figure_edge": near_figure_edge(line, figures),
                }
            )
        rows.append(
            {
                "book": book,
                "page": int(number),
                "violations": violations["I5"],
                "body_style": style,
                "figure_boxes": [box.model_dump(mode="json") for box in figures],
                "failed_credit_candidates": failed,
            }
        )
(OUT / "diagnosis/i5_full.json").write_text(json.dumps(rows, indent=2) + "\n", "utf8")
print([(r["book"], r["page"], len(r["violations"])) for r in rows])
