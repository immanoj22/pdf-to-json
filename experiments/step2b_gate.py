"""Run the complete fresh-venv gate and record compact nine-fixture/full-book evidence."""

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check

root = Path(__file__).resolve().parents[1]
out = root / "experiments/out/step2b"
out.mkdir(parents=True, exist_ok=True)
started = time.perf_counter()
run = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "backend/tests",
        "-q",
        "--tb=short",
        f"--junitxml={out / 'pytest.xml'}",
    ],
    cwd=root,
    capture_output=True,
    text=True,
)
(out / "pytest.log").write_text(run.stdout + run.stderr, "utf-8")
(out / "test_run.json").write_text(
    json.dumps(
        {
            "exit_code": run.returncode,
            "seconds": round(time.perf_counter() - started, 3),
            "python": sys.version,
            "executable": sys.executable,
            "prefix": sys.prefix,
        },
        indent=2,
    )
    + "\n",
    "utf-8",
)
print(run.stdout)
print(run.stderr)
if run.returncode:
    raise SystemExit(run.returncode)
rows = []
truth = json.loads(
    (root / "backend/tests/fixtures/expected_counters.json").read_text("utf-8")
)
cases = [
    (c["fixture"], root / "experiments/fixtures" / f"{c['fixture']}.pdf", c["counter"])
    for c in truth["cases"]
]
regressions = json.loads(
    (root / "backend/tests/fixtures/image_boundary_expected_counters.json").read_text(
        "utf-8"
    )
)
cases.extend(
    (name, root / "backend/tests/fixtures" / name, c["counter"])
    for name, c in regressions["cases"].items()
)
for name, path, expected in cases:
    page = next(PyMuPDFExtractor().extract_pages(path))
    document, ledger = provision_page(page)
    result = check(document, ledger, Counter(expected))
    assert result.passing
    rows.append({"fixture": name, **result.model_dump(), "passing": result.passing})
(out / "fixture_gate.json").write_text(json.dumps(rows, indent=2) + "\n", "utf-8")
print("Recorded all 9 fixture gates")
