"""Check whether image-preservation flags change nearby native text segmentation."""

import json
from pathlib import Path
import pymupdf
from reference_paths import reference_path

root = Path(__file__).resolve().parents[1]
failures = json.loads((root / "experiments/out/step2/benchmark_deviation.json").read_text("utf-8"))
with pymupdf.open(reference_path("spanish_pdf")) as pdf:
    for failure in failures:
        p = pdf[failure["page"] - 1]
        involved = set(failure["missing"]) | set(failure["extra"])
        for kind, flags in [
            ("rawdict_keep_images", pymupdf.TEXTFLAGS_RAWDICT),
            ("dict_drop_images", pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES),
        ]:
            raw = p.get_text(
                "rawdict" if kind.startswith("raw") else "dict", flags=flags, sort=False
            )
            lines = []
            for block in raw["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    text = "".join(
                        "".join(c["c"] for c in span["chars"]) if "chars" in span else span["text"]
                        for span in line["spans"]
                    )
                    if text in involved:
                        lines.append(text)
            print(failure["page"], kind, lines)
