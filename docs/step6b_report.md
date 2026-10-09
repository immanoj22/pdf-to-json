# Step 6b: optional accuracy extension points and math evidence

Step 6b adds inert extension contracts, richer Math metadata, restricted language
evidence and science-book equation candidates. No provider is wired into the
existing conversion pipeline. No book equation is converted, no reading order or
paragraph join is chosen, and no heading, furniture or zone policy is applied.
Text spans, ledger logic, gold and old projects remain untouched.

## Gates and unchanged results

| Gate | Result | Evidence |
|---|---|---|
| Earlier and new tests | 644 passed; 0 failed / 0 skipped; 224.67 s | [JUnit](../experiments/out/step6b/pytest.xml), [log](../experiments/out/step6b/pytest.log) |
| 24 measured pages | 0 missing / 0 extra; all rows identical to Step 6 | [independent source crosscheck](../experiments/out/step6b/original_source_crosscheck.json) |
| Full book | 495,751 retained tokens; 0 missing / 0 extra | [invariance report](../experiments/out/step6b/invariance.json) |
| Earlier outputs / ledger / tests / gold | 558 earlier output files unchanged byte-for-byte; ledger and protected earlier tests unchanged; 30 gold files exact and checksums verify | [byte inventory](../experiments/out/step6b/invariance.before.json) |
| Ruff, from backend/ | check and format pass | [log](../experiments/out/step6b/ruff.log) |
| Optional environment | All 55 lock pins match; pip check passes | [inventory](../experiments/out/step6b/optional_environment.json), [pip check](../experiments/out/step6b/pip_check.log) |

The pre-test checkout already contained CRLF working-tree files corresponding to
LF Git blobs: 111 earlier outputs, 20 old test/fixture files and four ledger
modules. All 135 were LF-equivalent to HEAD before this step's final tests.
The audit preserves that distinction and checks exact pre-test/post-test bytes;
it does not silently normalize the ledger or earlier evidence. Gold files are
exact bytes, including derived-gold checksums. The one changed earlier test
explicitly configures its Arabic/Hebrew/Japanese language candidates, preserving
its script assertions under the authorized default-language restriction.

## Interfaces and Math model

[accuracy/](../backend/src/book_core/accuracy/) contains typed requests, evidence
results, protocols, no-op providers, cache helpers and opt-in metadata bridges.

| Extension | Request / evidence result |
|---|---|
| TableStructureRecognizer | Source table region and optional pixels -> grid size, source-referenced cells, row/column spans and confidence |
| FormulaRecognizer | Image-region evidence -> recognized LaTeX, confidence and review flag; digital text is not OCRed |
| MathBuilder | Digital source glyph/rule geometry -> source-referenced math tree; unavailable stub builds nothing |
| MathConverter | Exactly one math tree or provenance-bound derived LaTeX -> generated MathML/LaTeX evidence; no conversion in the stub |
| ContinuationScorer | Two supplied source regions, languages/scripts/directions and optional verified source context -> continuation score |
| HeadingClassifier | Supplied candidate/features -> optional label, level and confidence; no book labels or levels are emitted |
| PageReviewer | One page and supplied low-confidence evidence -> referenced findings only; no edits |

Every result identifies the source hash, full request digest, cache key,
configuration, provider/source version, actual model digest/revision when present,
runtime versions, requested/execution device, confidence and provenance.
Unavailable providers return status `unavailable`, confidence `None` and no
invented grid, tree, text, label, level, score or finding. They import no model or
GPU runtime. CPU works independently; future providers use the existing device
policy and retain CPU fallback evidence. Cache keys bind complete request bytes,
source/configuration/code/runtime/model identity and actual execution device;
loaded-source guards refuse stale workers.

The existing OcrEngine and LanguageDetector remain compatible through
MetadataOcrEngine / MetadataLanguageDetector wrappers. Legacy methods delegate
unchanged. Their bare protocols previously lacked the complete evidence envelope;
the wrappers add it for opt-in callers rather than changing existing callers.
No OCR implementation or implicit OCR path was added.

[Math](../backend/src/book_core/model/nodes.py) now carries optional inline/display,
digital/image source, a neutral [MathTree](../backend/src/book_core/model/math.py),
LaTeX, MathML string, original image-asset reference, external alt text, confidence
and a review flag. Image math requires its original asset; unresolved conversion
or alt text stays under review. Tree references are validated against node spans
and document raw-text ranges. Span storage and ledger accounting remain
unchanged; generated mathematical representations are derived metadata.

MathML is a W3C mathematics standard stored as an opaque optional string. Existing
schema-vocabulary tests pass unchanged; no exception or output-schema tag literal
was added to src. JSON round-trip tests cover digital/image math, original alt
text, dangling ranges and non-Latin direction metadata. Source context resolves
supplied raw character ranges before NFKC and binds text/artifact digests;
geometry observations remain source evidence, not invented character boxes.

## Book 1 language evidence

Lingua now uses only Settings languages (default `spa`, `eng`) plus explicit
additional languages. An empty list fails instead of enabling all models; a
single configured language is supported. Models remain optional through
`language-evidence`; absence produces an actionable installation error.

The minimum count is relative to native block size:
`max(minimum_letters=10, ceil(0.25 * median(positive block letter counts)))`.
Only Unicode letters count; script, whitespace and reading direction do not
change this rule. Short blocks remain `und`. On book 1 the positive-block median
is 19, so the floor binds at 10 letters. Confidence remains conditional on the
configured candidates and is not a calibrated probability of correctness.

| Book 1: 34,340 native blocks | Step 6 | Step 6b |
|---|---:|---:|
| Spanish (`es`) | 10,733 | 14,530 |
| English (`en`) | 583 | 4,626 |
| Undetermined (`und`) | 22,961 | 15,184 |
| Other accepted languages | 63 | 0 |
| Mixed-segment evidence, overlapping the rows above | 6,750 | 3,332 |

The language-only rerun used 758 historical native-cache hits, zero misses, and
identical page/block/span/text digests. Wall time was 75.672 s. A lower `und` count
does not establish improved accuracy: the earlier small annotated comparison was
not rerun. Books 2/3 received no new whole-book analysis or predictions; the
24-page source gate is the unchanged, explicitly measured fixture check.

[Language summary](../experiments/out/step6b/language/summary.json),
[run log](../experiments/out/step6b/language/runs.jsonl),
[cached artifact](../.cache/step6b/language/969553957acef56954dd195c4ae3dcb467bbc71d7c5e508ede72ac1273e45a26.json).
The artifact was moved byte-for-byte to the ignored source-keyed cache; its
original producing script is archived and its digest retained in the
[migration record](../experiments/out/step6b/language/migration.json). No second
inference run was used to rename provenance.

## Candidate licenses and CPU smokes

Full per-slot comparison, code/weight licenses, exact revisions/hashes, sizes,
maintenance dates and CPython 3.14.8 status are in
[dependencies.md](dependencies.md). Estimates and measured cold-stage timings
are distinguished. No candidate with restricted code/weights was installed.

| Slot / selected smoke | Code / weights | Synthetic CPU result |
|---|---|---|
| TATR structure | MIT source, Apache-2.0 inference / MIT weights | 3 rows / 2 columns, plus header/table candidates; 21.87 s cold stage |
| TableFormer fast | MIT / CDLA-Permissive-2.0 + Apache-2.0 owner terms | 3 rows / 2 columns / 6 cells; 15.11 s |
| PP-FormulaNet-L | Apache-2.0 / Apache-2.0 | Styled LaTeX equivalent to synthetic E=mc²; 41.66 s |
| SymPy AST / latex2mathml | BSD-3-Clause / MIT code; no weights | AST construction and three valid MathML synthetic conversions; 0.032 s / 0.15-0.47 ms |
| PP-OCRv5 detector / Latin recognizer | Apache-2.0 / Apache-2.0 | One text box detected; recognition returned wrong text at model confidence 0.7689 |
| Multilingual MiniLM | Apache-2.0 / Apache-2.0 | English/Spanish translation cosine 0.9549 vs unrelated -0.0802; similarity only |
| Torch classifier | Existing permissive CPU wheel / own synthetic fit | 8/8 synthetic binary labels; no heading accuracy claim |
| SmolVLM-256M | Apache-2.0 / Apache-2.0 | Described synthetic red square; English-only model, no page-review accuracy claim |

[Smoke summary](../experiments/out/step6b/smoke_summary.json),
[math backends](../experiments/out/step6b/smoke_math_backends.json).
Cold timings include imports, loading, preprocessing and CPU inference while
other work ran; they are not a controlled benchmark. First API-scaffold failures
and model warnings remain recorded. TATR reports three extra BatchNorm counters,
with no missing/mismatched learned parameters. Optional `ftfy` cleanup was absent
for formula recognition. OCR failure demonstrates why a running model is not an
accuracy gate. Tesseract/MathJax/e5/SmolVLM-500M were audited alternatives and were
not selected for installation or smoke testing.

| Excluded candidate/workflow | License reason |
|---|---|
| pix2tex weights | Official release CC BY-NC-SA 4.0, despite MIT code |
| Nougat family | Upstream CC BY-NC 4.0; small-model card conflicts, family remains excluded under confirmed decision |
| Texify | GPL-3.0 code; CC BY-SA weights; archived/deprecated |
| Qwen2.5-VL-3B-Instruct | Noncommercial Qwen RESEARCH LICENSE, commercial permission required |
| scikit-learn / LightGBM standard Windows workflows | Mandatory SciPy wheel bundles GPL runtime with GCC exception |
| UniMERNet standard workflow | Mandatory albumentations -> same excluded SciPy Windows distribution |
| PadishahIII latex-ocr standard workflow | Mandatory GPL Levenshtein dependency |

The license audit happened before each new package/checkpoint installation. All
new packages are optional extras; Lingua's bundled models moved out of the base
install. Installed new direct pins: timm 1.0.30, docling-ibm-models 4.0.3,
latex2mathml 3.81.1. Existing model-runtime versions were retained. No weights are
committed or automatically downloaded. The full optional lock and license-file
inventory are linked in dependencies.md.

## Science-book math evidence

The complete 729-page science source was screened with the unchanged Heron
Formula label at threshold 0.5 and supplemental native Unicode glyph evidence.
All text/pixels/objects came through Extractor; models ran on CPU. Native/detector
and mathematical evidence are cached per source/configuration/producer/runtime
and actual input/model digests. No page, font or book-specific detection rule was
introduced. All candidates remain under review; confidence is uncalibrated.

| Science-book evidence | Count |
|---|---:|
| Pages screened / pages with candidates | 729 / 144 |
| Candidate regions after overlap deduplication | 669 |
| Heron Formula regions / supplemental native candidates | 198 / 471 |
| Raw native line screens before overlap deduplication | 754 |
| Digital-text source candidates | 653 |
| Image-only source candidates | 0 |
| Mixed native text + overlapping image candidates | 16 |
| Uncertain source candidates | 0 |
| Display / inline / uncertain presentation | 181 / 7 / 481 |

Zero image-only candidates does not establish that the book has no image
formulas. Mixed means native text plus an overlapping image object; background
artwork can cause that overlap. Native augmentation can include prose containing
units, table/figure labels and script digits, and can miss operator-free or
ASCII slash/caret-only expressions. No recall/precision against math gold is
claimed. Presentation evidence is deliberately uncertain on 481 candidates.

[Completed math summary](../experiments/out/step6b/math/math_summary.json),
[detector manifest](../experiments/out/step6b/math/detection_manifest.json),
[overlay checksums/provenance](../experiments/out/step6b/math/overlay_manifest.json).
The source hash is `d02f2b77b0f62c9c89f8428142af0f04fdbcacb89abe7b4ed10da9370bd5121d`;
book cache key is `3b254c866a75ce351badd3acd1db223b0fa4c18b7917228fe0d80ad4c76f0ee3`.
Detector CPU wall time was 2,233.90 s; the completed cached evidence pass was
166.96 s. A transient Windows atomic-replace lock stopped native preparation
and the first reporting pass. An experiment-local bounded retry completed from
verified caches; core cache behavior and model outputs were untouched. The
[first failure log](../experiments/out/step6b/math_analysis.first_atomic_failure.log)
is retained. The model was not rerun during that recovery.

Five samples were selected from evidence diversity/density, without page-specific
rules. Numbers below are physical PDF pages, not printed folios. All five were
visually inspected; short IDs and a sidebar legend keep dense pages readable.

| Physical page | Sample evidence | Overlay path |
|---:|---|---|
| 662 | Percentages/algebra; 27 digital candidates; 12 display, 15 uncertain | [math_p662.png](../experiments/out/step6b/math/math_p662.png) |
| 135 | Thermal-energy equation and inline units; 13 digital; 1 display, 3 inline, 9 uncertain | [math_p135.png](../experiments/out/step6b/math/math_p135.png) |
| 96 | Force/momentum equation and illustration labels; 2 digital + 4 mixed; all presentation-uncertain | [math_p96.png](../experiments/out/step6b/math/math_p96.png) |
| 658 | Fraction arithmetic; 20 digital; 17 display, 3 uncertain | [math_p658.png](../experiments/out/step6b/math/math_p658.png) |
| 496 | Chemical balancing; 4 digital; presentation-uncertain | [math_p496.png](../experiments/out/step6b/math/math_p496.png) |

Overlays show credible equation regions as well as broad prose/unit candidates;
visual inspection does not turn them into validated truth. The cache-only overlay
renderer verifies sample evidence/raster checksums and records its own provenance,
leaving the completed math summary unchanged. Full per-page payloads remain in
the ignored active-project cache; no source text or model weights are committed.


These are candidates, not an equation census validated against gold. Source and
presentation classifications retain mixed/uncertain bins. Isolated operators,
chemical notation, table symbols and figure labels can be false candidates;
image equations missed by the layout detector and operator-free inline math can
be missed. No OCR, formula recognition, MathML conversion or semantic Math nodes
are produced by this evidence scan.

## Decisions and limitations for review

Confirmed decisions are recorded in [decisions.md](decisions.md): math is required
and must ultimately produce MathML while retaining image/alt fallbacks; repeated
content needs explicit furniture evidence; navigation remains evidence pending
TOC/index disambiguation and folio mapping. The repeated CONÉCTATE box remains
content; final repeated-box policy is pending the owner.

No production accuracy model is selected here. Future work must validate the
glyph/rule geometry frontend, formula recognition, continuation training and
multilingual page review on reviewed examples before enabling providers. The
synthetic smokes establish runtime compatibility only. Style/navigation/
repetition/vocabulary evidence from Step 6 remains unchanged. No Step 7 work was
started.
