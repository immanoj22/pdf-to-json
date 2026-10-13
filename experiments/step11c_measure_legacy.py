"""Measure the preserved pre-change implementation, never an old project.

The snapshot is made from this checkout before changing its producers. Only the four
approved books are selected by the already captured identity files.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cache/step11c/baseline_src"))
import book_core  # noqa: E402, F401
from book_core.telemetry import measure  # noqa: E402

sys.path.insert(0, str(ROOT / "experiments"))
from step11c_identity import BOOKS, OUT  # noqa: E402


def main():
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import NativeObjectPage, ObjectAnalysis

    result = {}
    for book in BOOKS:
        before = json.loads((OUT / "before" / f"{book}.json").read_text())
        stats, proof = {}, {}
        for stage, model in (("native", NativeObjectPage), ("analysis", ObjectAnalysis)):
            key = before["keys"][stage]
            paths = sorted((ROOT / before["cache_root"] / stage / key).glob("*.json"))
            bytes_total = sum(p.stat().st_size for p in paths)
            wall = cpu = 0
            with measure(stats, stage):
                for path in paths:
                    started, consumed = time.perf_counter(), time.process_time()
                    value = verified_read(path, model, key)
                    wall += time.perf_counter() - started
                    cpu += time.process_time() - consumed
                    # Native/analysis models contain no cache-key fields. Pydantic's
                    # field-order JSON is stable and avoids several deep full-size copies.
                    proof.setdefault(path.stem, {})[stage] = hashlib.sha256(
                        value.model_dump_json().encode("utf8")
                    ).hexdigest()
                    del value
                    if int(path.stem) % 100 == 0:
                        print(book, stage, path.stem, flush=True)
            stats[stage].update(
                wall_seconds=wall,
                cpu_seconds=cpu,
                cache_bytes=bytes_total,
                pages=len(paths),
                cache_bytes_per_page=bytes_total / len(paths),
                source_reads=0,
                source_hashes=0,
            )
            print(book, stage, round(wall, 2), bytes_total, flush=True)
        result[book] = stats
        (OUT / "before" / f"{book}_objects.json").write_text(json.dumps(proof, indent=2) + "\n")
        (OUT / "before" / "objects_performance.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
