"""20 seeded overlays over all cached Tesseract cases (all books), via the frozen benchmark."""
import glob
import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step16_benchmark as bench

records = {}
for path in sorted(glob.glob(str(bench.OUT / "cases/*/*.json.gz"))):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        row = json.load(stream)
    if row["identity"]["secondary"] is None:
        i = row["identity"]
        records[(i["book"], i["page"], i["degradation"])] = row
shutil.rmtree(bench.OUT / "overlays", ignore_errors=True)
bench.overlays(list(records.values()))
