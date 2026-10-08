"""Read-only comparison of current native evidence with historical cache differences."""

import json
from collections import Counter
from pathlib import Path
import pymupdf
from book_core.evaluation.cached_benchmark import CachedBenchmark
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ledger.tokenization import token_counter

from reference_paths import reference_path
root = Path(__file__).resolve().parents[1]
old = reference_path("spanish_cache")
benchmark = CachedBenchmark(old)
source = reference_path("spanish_pdf")
results = []
cached = CachedExtractor(PyMuPDFExtractor(), root / "experiments/out/step2/page_cache")
for page in cached.extract_pages(source):
    new = Counter()
    texts = []
    for line in page.store.lines:
        if page.geometry.content_bbox.contains_center(line.bbox):
            text = page.store.raw_line_text(line)
            new.update(token_counter(text))
            texts.append(text)
    expected = benchmark.expected_page(page.geometry.page)
    if new == expected:
        continue
    missing = expected - new
    extra = new - expected
    p = json.loads((old / "normalized/pages" / f"{page.geometry.page:06d}.json").read_text("utf-8"))
    oldtexts = [
        "".join(span["text"] for span in line["spans"])
        for b in p["blocks"]
        for line in b["lines"]
        if line["provenance"]["source_id"] not in benchmark.exclusions
    ]
    involved = set(missing) | set(extra)

    def relevant(ts):
        return [t for t in ts if involved.intersection(token_counter(t))]

    with pymupdf.open(source) as pdf:
        native = pdf[page.geometry.page - 1].get_text("dict", sort=False)
        dicttexts = [
            "".join(s["text"] for s in l["spans"])
            for b in native["blocks"]
            if b["type"] == 0
            for l in b["lines"]
        ]
    results.append(
        {
            "page": page.geometry.page,
            "missing": dict(missing),
            "extra": dict(extra),
            "old_lines": relevant(oldtexts),
            "rawdict_lines": relevant(texts),
            "dict_lines": relevant(dicttexts),
        }
    )
target = root / "experiments/out/step2/benchmark_deviation.json"
target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", "utf-8")
print(json.dumps(results, ensure_ascii=True, indent=2))
