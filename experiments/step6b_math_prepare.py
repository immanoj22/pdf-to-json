"""Prepare source-hashed native object/render caches for detected or native math candidates."""

import json
import time
from pathlib import Path

from reference_paths import reference_path
from step6b_math_analyze import (
    cached_objects,
    cached_raster,
    glyph_evidence,
    has_math_evidence,
    native_directory,
    read_native_page,
)

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = ROOT / "experiments/out/step6b/math/detection_manifest.json"
    source = reference_path("science_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    processed = 0
    prepared = 0
    while True:
        phase = json.loads(manifest.read_text("utf-8"))
        directory = native_directory(phase["source_sha256"], extractor, phase)
        for row in phase["pages"][processed:]:
            page = read_native_page(directory, row, phase["source_sha256"])
            eligible = row["formula_regions"] or any(
                page.geometry.content_bbox.contains_center(line.bbox)
                and has_math_evidence(glyph_evidence(page.store.raw_line_text(line)))
                for line in page.store.lines
            )
            if eligible:
                cached_objects(source, extractor, page)
                cached_raster(
                    source,
                    extractor,
                    phase["source_sha256"],
                    page.geometry.page,
                    phase["configuration"]["render_dpi"],
                )
                prepared += 1
                print(
                    f"math native prep {page.geometry.page}: {prepared} candidate pages", flush=True
                )
            processed += 1
        if phase["status"] != "started":
            break
        time.sleep(2)
    print(f"math native prep complete: {processed} pages screened, {prepared} prepared", flush=True)


if __name__ == "__main__":
    main()
