"""Freeze independent old-cache Counters for both native image-boundary regressions."""

import hashlib
import json
from pathlib import Path

from book_core.evaluation.cached_benchmark import CachedBenchmark
from reference_paths import reference_path

root = Path(__file__).resolve().parents[1]
directory = root / "backend/tests/fixtures"
manifest = json.loads((directory / "image_boundary_manifest.json").read_text("utf-8"))
benchmark = CachedBenchmark(reference_path("spanish_cache"))
assert benchmark.source_sha256 == manifest["source_sha256"]
results = {}
for case in manifest["cases"]:
    source = directory / case["fixture"]
    expected = benchmark.expected_page(case["physical_page"])
    results[case["fixture"]] = {
        "fixture_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "counter": dict(sorted(expected.items())),
        "expected_retained_tokens": sum(expected.values()),
    }
(directory / "image_boundary_expected_counters.json").write_text(
    json.dumps(
        {
            "source_sha256": benchmark.source_sha256,
            "truth": "Read-only old normalized extraction cache; explicit TrimBox exclusions only.",
            "cases": results,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    "utf-8",
)
print({name: data["expected_retained_tokens"] for name, data in results.items()})
