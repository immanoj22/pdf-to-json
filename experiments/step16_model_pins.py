"""Load every runtime model offline from the project cache at its pinned revision."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src")]
os.environ["HF_HUB_OFFLINE"] = "1"  # any attempted fetch fails loudly
cache = ROOT / ".cache/huggingface"
from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
from book_core.mathml.recognition import PPFormulaNet
from book_core.tables.recognizers import (
    TableFormerStructure,
    TATRDetector,
    TATRStructure,
)

rows = []
for kind in (
    HeronDetector,
    PPDocLayoutV3Detector,
    PPFormulaNet,
    TATRDetector,
    TATRStructure,
    TableFormerStructure,
):
    reader = kind(device="cpu", cache_dir=cache, local_files_only=True)
    row = {"model": kind.__name__, "repo": reader.repo_id, "revision": reader.revision}
    try:
        if kind is TableFormerStructure:
            from huggingface_hub import snapshot_download

            snapshot_download(
                reader.repo_id,
                revision=reader.revision,
                cache_dir=str(cache),
                allow_patterns=[f"model_artifacts/tableformer/{reader.mode}/*"],
                local_files_only=True,
            )
        elif kind is TATRStructure:
            from book_core.tables.recognizers import _tatr_load

            _tatr_load(reader.repo_id, reader.revision, cache, True)
        else:
            reader._load()
        row["loaded_offline"] = True
    except Exception as error:  # noqa: BLE001 - every load failure is reported
        row["loaded_offline"] = False
        row["error"] = f"{type(error).__name__}: {str(error)[:200]}"
    rows.append(row)
    print(row, flush=True)
(ROOT / "experiments/out/step16/dependencies/runtime_model_pins.json").write_text(
    json.dumps(rows, indent=1)
)
