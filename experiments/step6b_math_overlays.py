"""Render completed math evidence from verified caches; never extract or analyze."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from book_core.accuracy.cache import canonical_digest
from book_core.accuracy.math_evidence import MathPageEvidence
from book_core.caching import code_digest, runtime_versions
from book_core.extraction.cache import atomic_json
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.extraction.rasters import RasterPage
from book_core.objects.analysis import verified_read
from book_core.objects.roles import raster_array

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b/math"
COLORS = {
    "digital": (230, 90, 0),
    "image": (30, 150, 30),
    "mixed": (180, 0, 180),
    "uncertain": (90, 90, 90),
}
FONT = cv2.FONT_HERSHEY_SIMPLEX


def local_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Overlay cache/output must stay in the active workspace")
    return path


def retry_json(path, value):
    for attempt in range(20):
        try:
            atomic_json(path, value)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1)


def render(raster, evidence, target):
    image = raster_array(raster).copy()
    scale = max(0.4, raster.height / 1800)
    text_height = cv2.getTextSize("Ag", FONT, scale, 1)[0][1]
    margin = max(text_height, 8)
    row_height = text_height * 2 + margin // 2
    labels = [
        f"{index}: {item.source_type} / {item.presentation}  c={item.confidence:.2f}"
        for index, item in enumerate(evidence.candidates, 1)
    ]
    headings = [
        f"Page {evidence.page}: math evidence",
        "ID: source / presentation / confidence",
        "All candidates require review",
    ]
    sidebar_width = (
        max(cv2.getTextSize(text, FONT, scale, 1)[0][0] for text in labels + headings) + margin * 2
    )
    header_height = row_height * (len(headings) + 1)
    height = max(raster.height, header_height + row_height * len(labels) + margin)
    canvas = np.full((height, raster.width + sidebar_width + margin, 3), 255, dtype=np.uint8)
    canvas[: raster.height, : raster.width] = image
    sidebar_x = raster.width + margin
    cv2.line(canvas, (raster.width, 0), (raster.width, height), (180, 180, 180), 1)
    for row, heading in enumerate(headings, 1):
        cv2.putText(
            canvas,
            heading,
            (sidebar_x, row * row_height),
            FONT,
            scale,
            (40, 40, 40),
            1,
            cv2.LINE_AA,
        )
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    tag_scale = scale * 0.8
    for index, item in enumerate(evidence.candidates, 1):
        left = round(item.bbox.x0 * sx), round(item.bbox.y0 * sy)
        right = round(item.bbox.x1 * sx), round(item.bbox.y1 * sy)
        color = COLORS[item.source_type]
        cv2.rectangle(canvas, left, right, color, 2)
        text = str(index)
        (width, tag_height), baseline = cv2.getTextSize(text, FONT, tag_scale, 1)
        x = max(0, min(left[0], raster.width - width - 4))
        y = max(tag_height + 2, min(left[1] - 2, raster.height - baseline - 2))
        cv2.rectangle(
            canvas,
            (x, y - tag_height - 2),
            (x + width + 3, y + baseline + 1),
            (255, 255, 255),
            -1,
        )
        cv2.putText(canvas, text, (x + 1, y), FONT, tag_scale, color, 1, cv2.LINE_AA)
        cv2.putText(
            canvas,
            labels[index - 1],
            (sidebar_x, header_height + index * row_height),
            FONT,
            scale,
            color,
            1,
            cv2.LINE_AA,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), canvas):
        raise OSError("Math overlay could not be written")
    return {
        "page": evidence.page,
        "path": target.relative_to(ROOT).as_posix(),
        "sha256": source_digest(target),
        "width": canvas.shape[1],
        "height": canvas.shape[0],
        "candidate_ids": [item.id for item in evidence.candidates],
        "source_types": dict(Counter(item.source_type for item in evidence.candidates)),
        "presentations": dict(Counter(item.presentation for item in evidence.candidates)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    out = local_path(args.out)
    summary_path = out / "math_summary.json"
    summary_sha256 = source_digest(summary_path)
    summary = json.loads(summary_path.read_text("utf-8"))
    phase_path = out / "detection_manifest.json"
    phase_sha256 = source_digest(phase_path)
    phase = json.loads(phase_path.read_text("utf-8"))
    if summary["status"] != "completed" or phase["status"] != "completed":
        raise ValueError("Overlay rendering requires completed analysis and detection")
    if (
        summary["source_sha256"] != phase["source_sha256"]
        or summary["producer_sha256"] != code_digest("accuracy")
        or summary["detector_producer_sha256"] != code_digest("detection")
        or phase["native_producer_sha256"] != code_digest("extraction")
    ):
        raise ValueError("Cached source or producer fingerprints differ")
    raster_key = canonical_digest(
        {
            "source_sha256": summary["source_sha256"],
            "extractor": PyMuPDFExtractor(device="cpu").identity.model_dump(mode="json"),
            "producer_sha256": code_digest("extraction"),
            "runtime": runtime_versions(),
            "dpi": phase["configuration"]["render_dpi"],
        }
    )
    rows = {row["page"]: row for row in summary["pages"]}
    rendered = []
    for sample in summary["sample_overlays"]:
        row = rows[sample["page"]]
        evidence = verified_read(
            local_path(row["evidence_path"]), MathPageEvidence, row["math_cache_key"]
        )
        raster_path = ROOT / ".cache/step6b/math_rasters" / raster_key / f"{sample['page']}.json"
        raster = verified_read(raster_path, RasterPage, raster_key)
        if (
            evidence.source_sha256 != summary["source_sha256"]
            or evidence.page != sample["page"]
            or evidence.render_sha256 != hashlib.sha256(raster.png).hexdigest()
            or evidence.producer_sha256 != summary["producer_sha256"]
            or [item.id for item in evidence.candidates] != sample["candidate_ids"]
        ):
            raise ValueError("Sample cached evidence or render differs")
        rendered.append(render(raster, evidence, local_path(sample["overlay"])))
    if source_digest(summary_path) != summary_sha256 or source_digest(phase_path) != phase_sha256:
        raise ValueError("Analysis artifacts changed during cache-only overlay rendering")
    retry_json(
        out / "overlay_manifest.json",
        {
            "status": "completed",
            "mode": "verified_cache_only",
            "renderer_sha256": source_digest(Path(__file__)),
            "summary_sha256": summary_sha256,
            "detection_manifest_sha256": phase_sha256,
            "source_sha256": summary["source_sha256"],
            "book_key": summary["book_key"],
            "raster_cache_key": raster_key,
            "overlays": rendered,
        },
    )
    print(json.dumps({"status": "completed", "overlays": len(rendered)}))


if __name__ == "__main__":
    main()
