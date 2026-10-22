"""Aggregate cached benchmark cases: CER/WER by book, degradation and reader."""

import glob
import gzip
import json
from collections import defaultdict

rows = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
orient = defaultdict(lambda: [0, 0])
for f in glob.glob("experiments/out/step16/benchmark/cases/*/*.json.gz"):
    with gzip.open(f) as stream:
        r = json.load(stream)
    book, deg = r["identity"]["book"], r["identity"]["degradation"]
    for reader, s in r["scores"].items():
        g = s["geometry_aligned"]
        a = rows[(book, deg)][reader]
        a[0] += g["characters"]
        a[1] += g["character_errors"]
        a[2] += g["words"]
        a[3] += g["word_errors"]
    o = orient[deg]
    o[0] += 1
    o[1] += r["orientation_expected"] == r["orientation_observed"]
for k in sorted(rows):
    for reader, a in rows[k].items():
        if reader in ("tesseract", "pp_ocrv5", "combined"):
            print(
                k,
                reader,
                f"CER {a[1] / a[0]:.4f} ({a[1]}/{a[0]}) WER {a[3] / a[2]:.4f} ({a[3]}/{a[2]})",
            )
print({d: v for d, v in orient.items()})
