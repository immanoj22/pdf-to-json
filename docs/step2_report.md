# Step 2 review gate

Built a new backend/src/book_core package: universal Pydantic v2 document/node models, raw + NFKC span store, Extractor and future configurable multilingual OcrEngine protocols, PyMuPDF implementation, validated atomic per-page cache, occurrence ledger and CLI. AGENTS.md and CLAUDE.md are identical. Dependencies are exactly pinned; [versions and licenses](dependencies.md) include PyMuPDF's AGPL/commercial terms. Validated on Python 3.14.8, CPU only.

All requested semantic node types support discriminated JSON round trips, span-only source content, common evidence/style/relationship fields and referential checks. Figure text belongs to embedded InlineRuns; its required external description stays flagged for review until supplied. Matter containers have common node fields too.

| Gate | Result |
|---|---|
| pytest | 48 passed; 0 failures/errors/skips |
| Ruff check and format | Pass |
| pip check | Pass |
| Seven Spanish fixture Counters | 0 missing / 0 extra each |
| Full 758-page native book versus old cache | **495,751 retained tokens; 0 missing / 0 extra** |
| Full line accounting | **92,228 - 7,194 TrimBox = 85,034** |
| Native ledger ownership | 0 missing/extra; reconstructed node text and occurrence ownership checked |
| Model round trips, cache integrity, native rotation/crop, source isolation | Pass |

| Spanish fixture | Retained tokens | Missing / extra |
|---|---:|---:|
| column_26 | 564 | 0 / 0 |
| column_100 | 779 | 0 / 0 |
| complex_map | 619 | 0 / 0 |
| complex_cards | 676 | 0 / 0 |
| complex_sidebar | 401 | 0 / 0 |
| background_worksheet | 453 | 0 / 0 |
| colored_box | 420 | 0 / 0 |

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

## Step 2b - housekeeping and multilingual decision

Moved the 180 Git-identified Step 1/2 files and 1,520 generated cache files into the new project. Python package/tests/pyproject/lock are in backend/; frontend/ contains only a README placeholder. The new root has its own README, Git repository and fresh Python 3.14.8 venv. Existing environments, old root README/start.ps1, user archives and both old applications stayed in place. [Exact move list](step2b_move_list.md), [Git/timestamp/hash manifest](step2b_move_manifest.json).

External reference reads now use experiments/references.toml or BOOK_CONVERTER environment overrides; src has no absolute reference paths. Local links and package imports point to the new folder. Venvs, caches, bytecode and model weights are ignored.

Settings accepts OCR language codes per job (default spa/eng) and per region, with an empty language-pack registry. OcrEngine remains an interface. Spans and semantic nodes have optional script and text_direction (ltr/rtl/ttb), default None; no Latin/LTR inference is introduced. The Unicode benchmark regex is unchanged. [Ledger notes](ledger.md) record that CJK without spaces needs a different token rule later; none is implemented now.

| Fresh-venv gate | Result |
|---|---|
| pytest | **62 passed**, zero skips/failures/errors |
| Seven Spanish + two regression fixtures | **0 missing / 0 extra on all nine** |
| Full 758-page book | **495,751 retained tokens**, 0 missing / 0 extra |
| Line accounting | **92,228 - 7,194 = 85,034** |
| Ruff / dependency check / local links | Pass |
| Old source/config/docs/assets/tests/profile references | **1,309 hashes unchanged** |

Old Git HEAD is unchanged; its only tracked differences are the 180 authorized moves. Source/reference hash comparison excludes rebuildable environments/build/cache outputs: the all-file attempt encountered an OS-unreadable .run build dependency (.pth). None of those runtime files was moved or modified. [Old-project verification](step2b_old_project_verification.json), [gate evidence](../experiments/out/step2b/fixture_gate.json).

**Step 2b only. Stop for review.**
