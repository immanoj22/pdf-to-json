"""Write compact gate artifacts and validate the full historical extraction totals."""

import json
from collections import Counter
from pathlib import Path
from reference_paths import reference_path

from book_core.evaluation.cached_benchmark import CachedBenchmark
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check

root = Path(__file__).resolve().parents[1]
cases = json.loads((root / "backend/tests/fixtures/expected_counters.json").read_text("utf-8"))["cases"]
rows = []
for case in cases:
    page = next(
        PyMuPDFExtractor().extract_pages(root / "experiments/fixtures" / f"{case['fixture']}.pdf")
    )
    document, ledger = provision_page(page)
    result = check(document, ledger, Counter(case["counter"]))
    rows.append({"fixture": case["fixture"], **result.model_dump(), "passing": result.passing})
(root / "experiments/out/step2/fixture_gate.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf-8"
)
snapshot = json.loads((root / "backend/tests/fixtures/expected_counters.json").read_text("utf-8"))
old = reference_path("spanish_cache")
benchmark = CachedBenchmark(old)
tokens = 0
source_lines = 0
excluded = 0
for path in sorted((old / "normalized/pages").glob("*.json")):
    page = json.loads(path.read_text("utf-8"))
    for block in page["blocks"]:
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"])
            if text.strip():
                source_lines += 1
                excluded += line["provenance"]["source_id"] in benchmark.exclusions
    tokens += sum(benchmark.expected_page(int(path.stem)).values())
result = {
    "source_line_count": source_lines,
    "excluded_line_count": excluded,
    "retained_line_count": source_lines - excluded,
    "retained_token_count": tokens,
}
(root / "experiments/out/step2/old_cached_totals.json").write_text(
    json.dumps(result, indent=2) + "\n", "utf-8"
)
print(result)
