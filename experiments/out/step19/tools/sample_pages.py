"""Step 19 sample gate: 30 pages (the frozen Step 11d sample of 24 plus 6 Statistics pages,
random.Random("step19:statistics")), fresh native extraction vs the archived page source;
retained-token Counter, 0 missing / 0 extra. Usage: sample_pages.py TAG OUT.json [BOOK...]"""
import json
import random
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.spans import ExtractedPage
from book_core.run_context import source_session
from reference_paths import reference_path
from step4b_run import retained_counter
from step19_run import BOOKS

tag, out = sys.argv[1], Path(sys.argv[2])
sample = json.loads((ROOT / "experiments/out/step11d/before/sample.json").read_text())["pages"]
n = json.loads((ROOT / f"experiments/out/step19/{tag}/performance/statistics.json").read_text())["run"]["pages"]
sample["statistics"] = sorted(random.Random("step19:statistics").sample(range(1, n + 1), 6))
books = sys.argv[3:] or list(sample)
rows = json.loads(out.read_text())["rows"] if out.exists() else []
rows = [r for r in rows if r["book"] not in books]
for book in books:
    run = json.loads((ROOT / f"experiments/out/step19/{tag}/performance/{book}.json").read_text())["run"]
    source = reference_path(BOOKS[book])
    with source_session(source):
        for number in sample[book]:
            expected = retained_counter(PyMuPDFExtractor("cpu").extract_object_page(source, number).page)
            page = read_json(Path(run["output"]) / f"page_{number:06d}.json.gz")
            actual = retained_counter(ExtractedPage.model_validate(page["source"]))
            rows.append({"book": book, "page": number, "tokens": expected.total(),
                         "missing": (expected - actual).total(), "extra": (actual - expected).total()})
            print(rows[-1], flush=True)
out.write_text(json.dumps({"tag": tag, "pages": len(rows), "missing": sum(r["missing"] for r in rows),
    "extra": sum(r["extra"] for r in rows), "sample": sample, "rows": rows}, indent=1))
print(len(rows), sum(r["missing"] for r in rows), sum(r["extra"] for r in rows))
