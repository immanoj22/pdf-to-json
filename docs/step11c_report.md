# Step 11c — performance, memory and caches

Status: **PASS**. Step 11c is complete; stopped for review before Step 12.

## Scope and identity proof

Only books 1–4 are used: Spanish US history (758 pages), immigrant children (331),
art-therapy index (9, anecdotal), and medical anatomy (314, development). The sealed
intake books and the excluded mismatched pair are not run or scored. No adapter,
XML, OCR, heading, paragraph, list, reading-order or ledger rule is added.

The pre-change checkout was clean at `6ccc541`. Before editing existing producers,
the identity capture froze every page's native text, layout, reading order, furniture,
paragraphs and lists, together with book decisions and structure evidence. Per-page
structure projections were subsequently recovered from the original cached decision
and checked against its already frozen whole-book digest. Native-object and analysis
models have separate exact serialization digests. The preserved snapshot's 150 Python
files match `6ccc541`; committed intake summaries supply the frozen metric baseline.

Cache identities necessarily change in this step. Canonical content comparison excludes
only `cache_key_inputs` and `page_keys`; their old and new values remain recorded.
The metric comparison additionally excludes elapsed time, cache-hit state, producer
digests, the paragraph book key, and the flag comparing a producer digest with the
old Step 10b freeze. No accuracy score, count, source text, stable ID, unit, relationship
or decision is excluded.

Evidence: [baseline](../experiments/out/step11c/before/),
[producer verification](../experiments/out/step11c/before/snapshot.json), and
[metric provenance](../experiments/out/step11c/before/metrics_provenance.json).

## Implementation

- Producer scopes contain their own code and shared primitives. Upstream stage keys
  carry upstream changes. The registry is excluded from producer hashes; closure tests
  audit explicit upstream dependencies, including a deliberately missing dependency.
- New model payloads use versioned gzip JSON and SHA-256 checksums, atomically replaced
  after flush/fsync. Legacy JSON remains readable. Analysis references the native cache;
  default-valued fields are restored by the model. Small native-text caches prevent later
  stages from repeatedly loading vector and glyph evidence. No pickle or runtime dependency
  is added.
- A run hashes its PDF once and passes a checked source snapshot to workers. File identity
  is checked during use and before final publication. Producer hashing is memoized only
  while file names, sizes and timestamps stay unchanged. Validated model reuse is bounded
  and returns independent copies; every disk load still checks its checksum.
- CPU process workers receive shared job arguments once and use a bounded queue. Automatic
  selection reserves 12 GiB per worker plus 2 GiB and caps at two; this laptop selects one.
  Explicit worker counts and the existing optional automatic GPU path remain available.
- Development resumes complete page caches and writes book completion last. Production
  uses a temporary intermediate cache, removes it on success or handled failure, and
  publishes only final page span stores/units, book decisions and a checksum manifest.
  Final pages also retain visual-line/span ID maps required to resolve their units.
  Existing final outputs must match exactly. An OS lock is released after process exit.
- Cache maintenance reports registered bytes by source/book and stage. Pruning requires
  a saved dry run and removes only registered superseded producers. Current entries,
  other configurations of the same producer, unknown files, gold and outputs are protected.
  A budget reports failure when protected data prevents meeting it. Before a run, the
  default estimate is 12 MiB/page with a 5 GB reserve. Below 10 GB free, known superseded
  entries are planned, cleaned and capacity checked again.

Details and commands: [caching.md](caching.md).

## Measurement method

Laptop: Intel Core i5-8265U, four physical/eight logical cores, 21,349,158,912 bytes RAM
(19.9 GiB), Windows 10 build 19045, CPython 3.14.8, CPU execution. Package versions and
initial free disk are in [hardware.json](../experiments/out/step11c/hardware.json).

Before/after tables measure full cached-output load sweeps for each stage and book,
including decompression, checksum verification and model validation. These are cache-load
costs, not historical cold extraction times. Both sides use the same measurement helper.
Independent verification jobs ran concurrently; wall times include contention and are
not an isolated speedup benchmark. CPU, sampled RSS and stored bytes are reported directly.
RSS is sampled every 20 ms; workers also record OS process high-water marks. End-to-end
tables use the largest recorded combined sample, parent sample or individual process
high-water mark. Brief simultaneous spikes between aggregate samples may be missed.
OS high-water marks can include setup before the timed run.
The raw field named `peak_memory_upper_bound_bytes` is a sampling estimate, not a strict
bound, and is not used as the reported peak or as a sizing guarantee.
Page-stage times are sums of page work, so parallel stage
totals are not the elapsed end-to-end time.

The earlier native/analysis proof sweep includes proof serialization in its memory
measurement and is retained as supporting evidence, not used for the comparable RSS table.
Each cache-load sweep performs zero PDF reads and zero PDF hashes. A separate preserved
setup probe measures five PDF hashes and one native PDF open for each book; it consumes
one page because the old iterator hashes/opens once at entry. Hash streams are separate
from those PDF opens.

## Gates

- All 869 tests pass: 864 core tests in 975.63 seconds plus five cached-book furniture
  regressions. All 11 performance/archive tests pass again after the final publisher change.
- All four books have identical page and book identities and identical reported metrics.
- One/two-worker runs have identical final files and all 1,200 intermediate page caches.
- 24-page source crosscheck: zero missing / zero extra.
- I1–I7: all zero; every line retained exactly once.
- Fixture paragraph, structure and list coverage/order gates: pass.
- Full 758-page book: 495,751 node tokens; all source/retention/exclusion gates pass.

Evidence: [audited verification](../experiments/out/step11c/verification.json),
[core tests](../experiments/out/step11c/pytest_core.xml),
[furniture tests](../experiments/out/step11c/pytest_furniture.xml), and
[gates](../experiments/out/step11c/gates/).

## 300-page end-to-end runs

The fixture is an explicit 1–300 excerpt of approved book 1. Source digest and
preparation arguments are in [source.json](../experiments/out/step11c/book300/source.json).
The current development run resumes complete caches; production starts with empty
temporary intermediates and performs extraction and every implemented stage. Both
use the corrected archive publisher. Cache conditions and worker counts differ, so
these runs do not isolate a mode or worker-count speedup.

| Mode and cache condition | Workers | Wall minutes | CPU s | Observed peak RSS MiB | Intermediate MiB | Final MiB | PDF hashes | Source opens/reads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development, resumed | 1 | 6.95 | 396.08 | 3389.47 | 709.73 retained | 14.35 | 1 | 2 |
| Production, cold | 2 | 22.60 | 3005.41 | 3630.10 | 709.73 temporary, then removed | 14.35 | 1 | 965 |

Final files are **byte-identical**. Every native, analysis, layout and reading-order
cache also matches byte for byte: 300 pages × four stages. Production temporary
directories are absent after completion. Source opens include rendering/extraction
opens; they are separate from the single PDF hash stream.

Cold production CPU ranking: analysis 1879.28 s, layout 452.52 s, native 322.66 s.

Evidence: [development](../experiments/out/step11c/book300/development_workers1.json),
[production](../experiments/out/step11c/book300/production_workers2.json),
[final equality](../experiments/out/step11c/book300/identity.json), and
[1,200 intermediate comparisons](../experiments/out/step11c/book300/parallel_pages.json).

The earlier cold development/production experiment is preserved separately in
[book300_before_archive](../experiments/out/step11c/book300_before_archive/):
67.76 / 39.68 wall minutes, 4363.11 / 4437.02 CPU seconds and 2713.46 / 3335.25 MiB
observed peaks. Those runs predate the final line/span map and are supporting cold
compute measurements, not the current final-archive benchmark. Concurrent verification
activity affected wall times. Upstream stage producers and outputs remain unchanged.

## PC sizing

For office deployment, provision **at least four physical CPU cores, 24 GB RAM and an SSD
with 25 GB free per active job**; prefer 32 GB RAM and additional free space for simultaneous
jobs or dense vector pages. CPU-only execution is supported; a GPU is optional and is not
required by these measurements. The current 300-page runs record 3.31 / 3.55 GiB peaks, but
the complete book contains much denser pages: the pre-change cached native/analysis sweeps
reach 8.94 / 10.47 GiB, and serialization adds transient memory. The current full Spanish
run records a 10.61 GiB observed peak, while the current standalone analysis-load sweep
reaches 10.96 GiB. The safe worker default therefore remains one on
this laptop. Two workers were explicitly selected for measurement, not recommended
automatically for every full book. Capacity checks use the actual page
count and preserve a 5 GB reserve; more space is needed for larger jobs or multiple retained
development runs. This is a measured sizing recommendation, not a guarantee for arbitrary PDFs.

## Cache migration and cleanup

All 1,412 pages match their frozen model digests across native, analysis, layout and
reading order. Each new payload is reread and checked before its old producer is
registered as superseded. Saved dry runs are inspected for only those old stage/key
prefixes before application.

| Book | Four-stage cache before, bytes | After, bytes | Reduction |
|---|---:|---:|---:|
| Spanish US history | 20,067,964,564 | 1,865,511,209 | 90.70% |
| Immigrant children | 6,888,780,830 | 365,636,823 | 94.69% |
| Art-therapy index | 18,356,435 | 1,391,749 | 92.42% |
| Medical anatomy | 612,679,123 | 42,752,444 | 93.02% |

The five saved cleanup plans remove 5,648 superseded files, reclaiming **27,587,780,952
bytes (27.59 GB / 25.69 GiB)**. These are this project's caches. External old projects,
reference caches, gold, frozen paragraph comparison caches, final outputs and unknown
files are retained. Migration evidence and the before measurements remain committed.
The interrupted Spanish migration resumed by checking existing new payloads against the
frozen digest; completed native proof remains preserved after pruning. This also avoided
allocating a second full-size UTF-8 copy during proof hashing.

Evidence: [migration records](../experiments/out/step11c/migration/),
[native cleanup](../experiments/out/step11c/prune_native_applied.json),
[remaining Spanish cleanup](../experiments/out/step11c/prune_spanish_remaining_applied.json),
[book 2 cleanup](../experiments/out/step11c/prune_immigrant_children_applied.json),
[book 3 cleanup](../experiments/out/step11c/prune_art_therapy_index_applied.json),
[book 4 cleanup](../experiments/out/step11c/prune_medical_anatomy_applied.json).
Matching `*_dry_run.json` files record every candidate and its size/timestamps.

## Four-book verification and measurements

Each end-to-end run uses the migrated native/analysis/layout/order caches and freshly
populates the current metadata and downstream book caches. These are resumed development
runs, not cold extraction timings. Their timing records precede the final line/span
archive correction; its separate publication measurements follow below. Every corrected
final manifest and its page/book file checksums are audited against the captured run
keys. Each PDF is hashed exactly once.

| Book | Pages | Page identities | Book identities | Metrics |
|---|---:|---|---|---|
| spanish_us_history | 758 | identical | identical | identical |
| immigrant_children | 331 | identical | identical | identical |
| art_therapy_index | 9 | identical | identical | identical |
| medical_anatomy | 314 | identical | identical | identical |

| Book | Workers | Wall s | CPU s | Observed peak RSS MiB | PDF hashes | Source reads |
|---|---:|---:|---:|---:|---:|---:|
| spanish_us_history | 1 | 3922.24 | 2283.92 | 10861.38 | 1 | 144 |
| immigrant_children | 1 | 880.07 | 837.48 | 833.19 | 1 | 6 |
| art_therapy_index | 1 | 10.46 | 9.66 | 735.62 | 1 | 3 |
| medical_anatomy | 1 | 254.55 | 232.53 | 847.30 | 1 | 3 |

The Spanish run records 1,674.39 seconds wall / 191.52 seconds CPU in metadata.
That difference includes waiting and concurrent activity; it is not evidence of a CPU
speedup or a timing guarantee. Its native stage takes 826.86 wall / 777.97 CPU seconds.
The densest cached native page expands from about 91.54 MiB compressed to 643.30 MiB
of serialized JSON, explaining why dense pages still need substantial memory.

Evidence: [identity comparison](../experiments/out/step11c/after/comparison.json),
[metric comparison](../experiments/out/step11c/metrics_comparison.json),
[final-output audit](../experiments/out/step11c/four_book_outputs.json), and
[complete run measurements](../experiments/out/step11c/performance/).

The corrected archive retains a `line_spans` map for all unit line IDs. This is needed
because visual lines can merge or split native source lines, and plain text does not
have style-run references. The archive publisher is shared by normal execution and
republication; no Stage 2 adapter or new semantic decision is involved. Each republished
source store and unit payload matches its frozen digest. Publication times include
source fingerprinting, layout validation and final-file writing.

| Book | Publication wall s | CPU s | Peak RSS MiB | Final MiB |
|---|---:|---:|---:|---:|
| spanish_us_history | 53.04 | 38.25 | 154.20 | 44.17 |
| immigrant_children | 9.61 | 4.48 | 117.42 | 5.96 |
| art_therapy_index | 0.49 | 0.34 | 117.54 | 0.58 |
| medical_anatomy | 14.12 | 8.66 | 120.37 | 10.64 |

Evidence: [archive publication](../experiments/out/step11c/archive/).

### Comparable cached-load costs

All stage sweeps below perform **zero PDF reads and zero hashes**, before and after.
Peak RSS is the sampled process RSS for that sweep; it includes resident state from
earlier stages. Stored bytes and bytes/page refer to that stage's measured cache files.
Native references needed to restore analysis models contribute to load time; the disk
column counts analysis storage itself, without double-counting native storage.

### Book 1 — Spanish US history (758 pages)

All pairs are **before → after**.

| Stage | Wall s | CPU s | Peak RSS MiB | Cache MiB | KiB/page |
|---|---:|---:|---:|---:|---:|
| native | 804.25 → 334.82 | 654.52 → 328.75 | 9158.04 → 10580.85 | 5856.05 → 625.56 | 7911.07 → 845.09 |
| analysis | 1051.80 → 606.25 | 947.44 → 583.44 | 10718.26 → 11223.66 | 13092.04 → 1109.04 | 17686.34 → 1498.22 |
| layout | 19.32 → 3.52 | 6.59 → 3.52 | 118.31 → 117.68 | 155.54 → 38.54 | 210.13 → 52.06 |
| reading order | 13.75 → 0.77 | 1.98 → 0.77 | 90.10 → 92.20 | 34.67 → 5.95 | 46.84 → 8.04 |
| furniture | 17.77 → 1.58 | 4.50 → 1.58 | 178.81 → 174.07 | 72.65 → 10.17 | 98.15 → 13.74 |
| paragraphs | 16.51 → 1.96 | 4.62 → 1.97 | 99.49 → 96.40 | 88.01 → 12.65 | 118.90 → 17.09 |
| structure evidence | 1.30 → 0.59 | 1.23 → 0.56 | 587.12 → 1522.31 | 4.54 → 4.54 | 6.14 → 6.14 |
| structure | 0.12 → 0.07 | 0.11 → 0.06 | 104.72 → 103.09 | 2.44 → 0.28 | 3.30 → 0.38 |
| lists | 17.22 → 2.16 | 4.83 → 2.17 | 98.97 → 96.75 | 95.68 → 13.55 | 129.25 → 18.30 |

### Book 2 — Immigrant children (331 pages)

All pairs are **before → after**.

| Stage | Wall s | CPU s | Peak RSS MiB | Cache MiB | KiB/page |
|---|---:|---:|---:|---:|---:|
| native | 400.35 → 181.38 | 363.20 → 177.75 | 809.04 → 1542.66 | 3275.43 → 344.60 | 10133.06 → 1066.07 |
| analysis | 426.57 → 179.79 | 375.92 → 177.73 | 811.89 → 786.82 | 3276.54 → 0.30 | 10136.49 → 0.93 |
| layout | 6.41 → 0.46 | 1.00 → 0.23 | 512.84 → 1445.22 | 12.35 → 2.89 | 38.22 → 8.94 |
| reading order | 5.03 → 1.74 | 0.55 → 0.20 | 507.26 → 1444.42 | 5.33 → 0.91 | 16.48 → 2.81 |
| furniture | 4.96 → 1.70 | 0.81 → 0.47 | 513.53 → 1445.10 | 12.16 → 1.71 | 37.62 → 5.29 |
| paragraphs | 5.26 → 1.89 | 1.03 → 0.42 | 507.24 → 1437.73 | 15.26 → 2.09 | 47.22 → 6.47 |
| structure evidence | 0.25 → 0.11 | 0.23 → 0.09 | 684.80 → 688.00 | 0.78 → 0.78 | 2.41 → 2.41 |
| structure | 0.04 → 0.02 | 0.02 → 0.00 | 511.81 → 1431.10 | 0.39 → 0.04 | 1.22 → 0.11 |
| lists | 5.26 → 2.09 | 1.19 → 0.39 | 510.03 → 1437.01 | 16.90 → 2.34 | 52.28 → 7.25 |

### Book 3 — Art-therapy index (9 pages; anecdotal)

All pairs are **before → after**.

| Stage | Wall s | CPU s | Peak RSS MiB | Cache MiB | KiB/page |
|---|---:|---:|---:|---:|---:|
| native | 0.83 → 0.36 | 0.67 → 0.25 | 689.00 → 684.16 | 7.82 → 0.95 | 889.61 → 108.27 |
| analysis | 0.80 → 0.48 | 0.66 → 0.41 | 693.70 → 686.16 | 8.28 → 0.07 | 942.05 → 7.41 |
| layout | 0.21 → 0.03 | 0.06 → 0.03 | 667.66 → 668.54 | 0.99 → 0.24 | 112.75 → 26.97 |
| reading order | 0.14 → 0.05 | 0.06 → 0.03 | 667.84 → 668.64 | 0.42 → 0.07 | 47.40 → 8.36 |
| furniture | 0.18 → 0.08 | 0.03 → 0.02 | 667.96 → 669.18 | 0.96 → 0.13 | 109.50 → 14.82 |
| paragraphs | 0.22 → 0.09 | 0.06 → 0.03 | 668.30 → 669.37 | 1.12 → 0.18 | 127.10 → 20.21 |
| structure evidence | 0.02 → 0.01 | 0.02 → 0.00 | 690.83 → 684.68 | 0.02 → 0.02 | 2.60 → 2.60 |
| structure | 0.02 → 0.00 | 0.00 → 0.00 | 669.80 → 671.28 | 0.01 → 0.00 | 1.31 → 0.31 |
| lists | 0.32 → 0.11 | 0.12 → 0.06 | 669.82 → 671.30 | 1.65 → 0.24 | 187.90 → 27.08 |

### Book 4 — Medical anatomy (314 pages; development)

All pairs are **before → after**.

| Stage | Wall s | CPU s | Peak RSS MiB | Cache MiB | KiB/page |
|---|---:|---:|---:|---:|---:|
| native | 32.44 → 12.97 | 24.03 → 10.83 | 683.00 → 748.86 | 245.48 → 26.63 | 800.54 → 86.86 |
| analysis | 36.59 → 15.36 | 27.70 → 13.47 | 730.21 → 757.46 | 304.88 → 7.00 | 994.26 → 22.81 |
| layout | 6.03 → 0.84 | 1.62 → 0.61 | 693.65 → 685.98 | 24.55 → 5.69 | 80.05 → 18.55 |
| reading order | 6.12 → 1.56 | 0.88 → 0.44 | 693.72 → 685.54 | 9.39 → 1.45 | 30.62 → 4.74 |
| furniture | 5.81 → 1.77 | 1.14 → 0.53 | 703.95 → 693.61 | 18.65 → 2.47 | 60.80 → 8.06 |
| paragraphs | 6.55 → 2.43 | 1.61 → 0.62 | 474.11 → 687.44 | 22.99 → 3.12 | 74.97 → 10.18 |
| structure evidence | 0.52 → 0.40 | 0.44 → 0.27 | 747.83 → 775.90 | 1.20 → 1.20 | 3.92 → 3.92 |
| structure | 0.06 → 0.03 | 0.05 → 0.03 | 491.13 → 692.86 | 0.92 → 0.10 | 2.99 → 0.31 |
| lists | 6.40 → 2.41 | 1.62 → 0.84 | 486.16 → 691.17 | 26.34 → 3.64 | 85.90 → 11.86 |

### Largest measured costs

- Before cached-load CPU, pooled over four books: analysis 1351.72 s, native 1042.42 s, layout 9.28 s.
- After cached-load CPU, pooled over four books: analysis 775.05 s, native 517.58 s, layout 4.39 s.

Cold extraction is ranked separately above: analysis, layout, then native.
Compression chiefly reduces disk; native restoration can remain expensive, and no
uniform speedup or memory reduction is claimed. Spanish cached-native RSS rises
from 8.94 to 10.33 GiB, and analysis from 10.47 to 10.96 GiB, despite lower CPU and
wall times. Large model restoration remains a memory cost; later stage RSS includes
resident allocator state from earlier sweeps. Raw per-stage source I/O, CPU, wall and
memory data are retained in the JSON measurements.

### Built-in cache report

The built-in report records 2,374,219,744 registered bytes,
0 remaining superseded bytes, and
37.77 GiB free at capture. Entries identify each source SHA-256 and stage.
This is a registered-cache inventory, not a whole-filesystem total:
historical unregistered caches, metadata/repetition operational files, references and
final outputs are outside its byte total. Unknown files remain protected.

Evidence: [cache report](../experiments/out/step11c/cache_report.json).

## Reproduction

Commands run from the repository root, using the existing environment and configured
read-only references:

```powershell
.venv\Scripts\python.exe experiments/step11c_gates.py
.venv\Scripts\python.exe experiments/step11c_identity.py after --compare
.venv\Scripts\python.exe experiments/step11c_run.py compare-metrics
.venv\Scripts\python.exe experiments/step11c_book300.py compare
.venv\Scripts\python.exe experiments/step11c_archive.py
.venv\Scripts\python.exe experiments/step11c_verify.py
```

The cache-load profiler is `step11c_cached_reads.py before|after`; its preserved producer
snapshot is verified against `6ccc541` by `step11c_snapshot.py`. The baseline is frozen
and cannot be overwritten by the identity command. Migration verifies every restored
model against that baseline before its superseded cache is eligible for cleanup.
After cleanup, reproducing historical cache-load measurements requires rebuilding the
old caches from the preserved producer revision; the measured results and digests remain
in the committed evidence. Current end-to-end runs use `step11c_run.py run --book NAME
--workers 1`. The excerpt driver is `step11c_book300.py run --mode MODE --workers N`;
development resumes its existing cache, while production always uses an empty temporary
cache. To measure a fresh cold development run without replacing this evidence, use
`book-core run-book .cache/step11c/book300/excerpt.pdf` with unused `--cache-dir` and
`--out` directories and the desired `--mode` / `--workers` arguments.

Ruff runs from `backend/`:

```powershell
$stepFiles = (Get-ChildItem ../experiments/step11c_*.py).FullName
..\.venv\Scripts\python.exe -m ruff check src tests $stepFiles
..\.venv\Scripts\python.exe -m ruff format --check src tests $stepFiles
```

Tests use a short workspace temporary root, for example
`--basetemp=../.cache/step11c/tc`, for Windows path length compatibility.

**Step 12 has not started.**
