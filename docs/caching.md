# Cache validity and operations

Each stage hashes its own producers, configuration and the keys of the upstream outputs it
reads. The stage registry in `caching.py` is excluded from producer hashes. The hashing
implementation in `cache_identity.py` is included. Registering an unrelated stage therefore
does not invalidate existing caches. Shared schemas and primitives remain explicit inputs.
Import-closure tests audit declared upstream boundaries and fail for missing dependencies.
Tests also edit producers, add files and edit the registry independently.

| Stage | Key inputs in addition to its own producer |
|---|---|
| Native | Source SHA-256, extractor identity, runtime versions |
| Analysis | Native key, repetition evidence, version and render configuration |
| Layout | Analysis key, version, scale, dependencies, resolved device |
| Reading order | Layout key, version, vocabulary |
| Furniture | Layout/order keys, metadata/vocabulary, settings/configuration |
| Paragraphs | Furniture key, vocabulary/navigation, detector identity, settings/configuration |
| Structure evidence | Paragraph key, navigation, settings |
| Structure | Evidence key, configuration/classifier identity |
| Lists | Paragraph and structure keys, settings/configuration |
| MathML (Step 13c) | Equations and native keys, recognizer identity (repository, immutable revision, generation settings, dependency versions, resolved device), configuration, client MathML settings, PyMuPDF/OpenCV/lxml/latex2mathml/SymPy versions |
| Tables (Step 14a) | Lists, analysis, figures and equations keys, the structure stage's printed navigation kinds, the table detectors' identity (repository, immutable revision, threshold, Table Transformer render dpi), table configuration and client table settings; table-model readings (structure comparison) are cached per image with the model identity and the `table_models` code |
| Formula readings (Step 13c) | Per image: the PNG digest of the rendered region or shape, the recognizer identity and the `formula` scope producer; shared by every stage key that renders the same image |

New model caches use version-2 gzip JSON envelopes and payload SHA-256 checksums. Existing
`.json` names are retained; gzip magic identifies compression. Legacy plain JSON is accepted
read-only. Structure evidence retains its checksummed gzip format. Writes flush and fsync
before atomic replacement, with the existing Windows retry. No pickle is persisted.
Default-valued fields are restored on load. Analysis references native evidence instead of
copying it. Small text caches let later stages avoid glyph and drawing evidence.

Every disk load checks its checksum. A bounded run-scoped cache reuses validated models and
returns independent copies. A changed payload never bypasses validation. Source content is
hashed once per run; workers receive a stat-checked snapshot. Source signatures are checked
during use and before publishing final output. Producer hashes are reused only while their
file names, sizes and timestamps remain unchanged. Deployment edits require worker restart.

```powershell
book-core run-book input.pdf --cache-dir .cache/books --out output --workers 1
book-core run-book input.pdf --cache-dir .cache/books --out output --mode production
book-core cache report --cache-dir .cache/books
book-core cache prune --cache-dir .cache/books --plan prune.json
book-core cache prune --cache-dir .cache/books --plan prune.json --apply
```

Development resumes completed pages and writes book completion records last. Production uses
a temporary intermediate cache, cleans it on success or exception, and publishes only final
source span stores, units and book decisions. Final files have a hash manifest; existing
files must match exactly to be reused. Final pages retain visual-line/span ID maps so units
remain resolvable after intermediate cleanup. An OS lock serializes runs and maintenance on a cache
root and is released after interruption. Process workers use a bounded task queue.

Only registered entries with superseded producers may be pruned. Current entries, other
configurations of the same producer, and unregistered files are protected. A saved dry run
records the index identity and candidate sizes/timestamps; changes invalidate the plan.
`--budget-bytes` reports when protected data prevents meeting a budget. Reports distinguish
registered storage from filesystem free space.

Before a book run, the configurable default disk estimate is 12 MiB/page, with a 5 GB reserve.
Below 10 GB free, the runner saves a cleanup dry run, applies known superseded entries, and
checks again. Estimates are capacity planning, not hard payload limits. Automatic worker
selection reserves 12 GiB per worker plus 2 GiB for the parent/system, capped at two; the
result is one on this laptop. Explicit worker counts remain available for measured workloads.
CPU and automatic optional GPU selection retain their established behavior.

External detectors provide producer fingerprints; external extractors carry their identity
through ExtractorIdentity. Model keys retain immutable revisions, thresholds and actual
execution devices. Old projects, references, gold and the ledger remain untouched.
