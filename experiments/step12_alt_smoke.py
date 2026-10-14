"""Step 12 Part 0: SmolVLM-256M licence and CPython 3.14 smoke test (optional generator).

Downloads the immutable revision into the project's ignored Hugging Face cache and generates
one English draft for a synthetic image. Records licence metadata, versions and the result.
"""

# ruff: noqa: E402
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src")]
from book_core.figures.alt_text import DEFAULT_MODEL, DEFAULT_REVISION, DraftGenerator

OUT = ROOT / "experiments/out/step12/alt_text/smoke.json"


def main():
    import numpy as np

    image = np.full((256, 256, 3), 255, np.uint8)
    image[64:192, 64:192] = (30, 60, 200)  # a blue square on white
    started = time.perf_counter()
    row = {"python": platform.python_version(), "model": DEFAULT_MODEL,
           "revision": DEFAULT_REVISION}  # fmt: skip
    try:
        generator = DraftGenerator(cache_dir=ROOT / ".cache/huggingface", device="cpu")
        draft = generator.describe(image)
        row.update(ok=True, draft=draft.model_dump(mode="json"), identity=generator.identity())
    except Exception as error:  # noqa: BLE001 - the smoke result records any failure
        row.update(ok=False, error=f"{type(error).__name__}: {error}")
    row["seconds"] = round(time.perf_counter() - started, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(row, indent=1))


if __name__ == "__main__":
    main()
