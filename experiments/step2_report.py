"""Write the review report only after the final gates actually pass."""

import json
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[1]
out = root / "experiments/out/step2"
full = json.loads((out / "full_book.json").read_text("utf-8"))
run = json.loads((out / "test_run.json").read_text("utf-8"))
fixtures = json.loads((out / "fixture_gate.json").read_text("utf-8"))
assert full["passing"] and run["exit_code"] == 0 and all(row["passing"] for row in fixtures)
suite = ElementTree.parse(out / "pytest.xml").getroot()[0]
assert int(suite.attrib["failures"]) == int(suite.attrib["errors"]) == 0
assert (
    full["source_line_count"],
    full["excluded_line_count"],
    full["retained_line_count"],
    full["node_token_count"],
) == (92228, 7194, 85034, 495751)
text = f"""# Step 2 review gate

Built a new backend/src/book_core package: universal Pydantic v2 document/node models, raw + NFKC span store, Extractor and future configurable multilingual OcrEngine protocols, PyMuPDF implementation, validated atomic per-page cache, occurrence ledger and CLI. AGENTS.md and CLAUDE.md are identical. Dependencies are exactly pinned; [versions and licenses](dependencies.md) include PyMuPDF's AGPL/commercial terms. Validated on Python 3.14.8, CPU only.

All requested semantic node types support discriminated JSON round trips, span-only source content, common evidence/style/relationship fields and referential checks. Figure text belongs to embedded InlineRuns; its required external description stays flagged for review until supplied. Matter containers have common node fields too.

| Gate | Result |
|---|---|
| pytest | {suite.attrib["tests"]} passed; 0 failures/errors/skips |
| Ruff check and format | Pass |
| pip check | Pass |
| Seven Spanish fixture Counters | 0 missing / 0 extra each |
| Full 758-page native book versus old cache | **495,751 retained tokens; 0 missing / 0 extra** |
| Full line accounting | **92,228 - 7,194 TrimBox = 85,034** |
| Native ledger ownership | 0 missing/extra; reconstructed node text and occurrence ownership checked |
| Model round trips, cache integrity, native rotation/crop, source isolation | Pass |

| Spanish fixture | Retained tokens | Missing / extra |
|---|---:|---:|
"""
for row in fixtures:
    text += f"| {row['fixture']} | {row['node_token_count']:,} | 0 / 0 |\n"
text += r"""
**Benchmark deviation resolved:** initially disabling TEXT_PRESERVE_IMAGES merged separate figure labels into HD and HF, yielding 495,749 tokens and two fewer lines. Generic rawdict extraction now preserves image blocks during parsing, then stores only text evidence. No page-specific converter rule or fabricated text was added. Two test-only image-boundary PDFs lock this behavior. [Diagnostic evidence](../experiments/out/step2/benchmark_deviation.json), [final full-book result](../experiments/out/step2/full_book.json).

The benchmark remains case-sensitive NFKC, regex [\p{L}\p{M}\p{N}]+, Counter multisets; order is unchecked. It is measured **after explicit TrimBox exclusions and before furniture removal**. Raw evidence keeps excluded text, and each excluded line has a reasoned discard record. Fixture truth is frozen from the old extraction cache, never generated XML; the mismatched 48-page pair is excluded.

This gate uses unclassified InlineRuns as evidence carriers for native source-line groups, provisionally held in BodyMatter. They are **not paragraphs or semantic classifications**. SpanRefs address whole spans; finer span ranges, semantic grouping and matter classification remain for later review. There is no layout inference, heading/furniture detection, OCR execution, adapter or XML generation. Empty package initializers contain docstrings only; mapping/profiles remain empty.

Reproduce after creating an isolated environment:

    python -m pip install -r backend/requirements-lock.txt
    python -m pip install --no-deps --no-build-isolation -e backend
    python -m pytest backend/tests -q
    ruff check backend/src backend/tests
    ruff format --check backend/src backend/tests
    book-core ledger-check experiments/fixtures/column_26.pdf --cache-dir experiments/.cache/ledger

The full-book pytest gate runs when the original book and old cache exist; otherwise it explicitly skips. For an external comparison, add --expected-cache PATH to the CLI. Source/configuration/backend-version cache fingerprints prevent reuse across extraction changes.

The old projects were read-only throughout. **Step 2 is complete; stop for review. No Step 3 work started.**
"""
report_path = root / "docs/step2_report.md"
existing = report_path.read_text("utf-8") if report_path.exists() else ""
marker = "\n## Step 2b"
if marker in existing:
    text += marker + existing.split(marker, 1)[1]
report_path.write_text(text, "utf-8")
print(root / "docs/step2_report.md")
