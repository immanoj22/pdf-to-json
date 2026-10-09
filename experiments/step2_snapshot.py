"""Freeze independent, read-only extraction-cache evidence for seven regression fixtures."""

import hashlib
import json
from pathlib import Path
from book_core.evaluation.cached_benchmark import CachedBenchmark

from reference_paths import reference_path
root = Path(__file__).resolve().parents[1]
old = reference_path("spanish_cache")
benchmark = CachedBenchmark(old)
manifest = json.loads((root / "experiments/out/fixtures_manifest.json").read_text("utf-8"))
cases = []
for fixture in manifest:
    if fixture["source_sha256"] != benchmark.source_sha256:
        continue
    old_page = old / "normalized/pages" / f"{fixture['physical_page']:06d}.json"
    counter = benchmark.expected_page(fixture["physical_page"])
    cases.append(
        {
            "fixture": fixture["id"],
            "physical_page": fixture["physical_page"],
            "fixture_sha256": fixture["fixture_sha256"],
            "source_sha256": fixture["source_sha256"],
            "old_page_sha256": hashlib.sha256(old_page.read_bytes()).hexdigest(),
            "expected_retained_tokens": sum(counter.values()),
            "counter": dict(sorted(counter.items())),
        }
    )
target = root / "backend/tests/fixtures/expected_counters.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    json.dumps(
        {
            "truth": "Old normalized extraction cache, explicit TrimBox exclusions only; not generated XML.",
            "case_sensitive": True,
            "normalization": "NFKC",
            "regex": r"[\p{L}\p{M}\p{N}]+",
            "old_cache": str(old),
            "validation_sha256": hashlib.sha256((old / "validation.json").read_bytes()).hexdigest(),
            "cases": cases,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    "utf-8",
)
print({case["fixture"]: case["expected_retained_tokens"] for case in cases})
