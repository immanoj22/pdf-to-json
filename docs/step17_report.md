# Step 17 — assembly: one validated JSON per book

Stage 1 now publishes a documented, versioned `universal-book` 1.0.0 JSON, images,
review crops and a checksummed manifest for each of the five books. All required
Step 17 gates pass, with the explicitly allowed Statistics I7 = 1 exception.
This step stops for review; no Stage 2 adapter has been started.

## Final results

| Book | Pages | Retained ledger | Missing / extra | Schema errors | Round trip | Reviews |
|---|---|---|---|---|---|---|
| Spanish history | 758 | 495,751 | 0 / 0 | 0 | identical | 2686 |
| Immigrant children | 331 | 124,019 | 0 / 0 | 0 | identical | 112 |
| Art therapy | 9 | 4,249 | 0 / 0 | 0 | identical | 0 |
| Medical anatomy | 314 | 95,957 | 0 / 0 | 0 | identical | 1065 |
| Statistics | 871 | 307,948 | 0 / 0 | 0 | identical | 3636 |

The Spanish ledger remains **495,751** retained tokens; all 34,160 explicit TrimBox
discard tokens also reconstruct exactly. All five books have zero missing/extra
retained and discarded tokens. Furniture, source markers and confirmed hidden text
remain reconstructible from the JSON. The token check does not discard hidden text.

Every-page I1–I7 totals are zero on books 1–4. Statistics has I1–I6 = 0 and the
known I7 = 1. Every page has each line/unit owned and ordered once. The fresh native
source crosscheck covers 30 pages with **0 missing / 0 extra**. Archive image hashes,
references and manifests pass, including the OCR-cover raster. The archive gate retains
the earlier assertions with two explicit extensions: OCR raster assets count as images;
post-publication assembly evidence is excluded from the pre-publication archive key set.

**1,183 backend tests pass** in 1762.25 seconds. The post-deletion cache-closure check
passes 62 tests; Ruff passes. The built wheel contains the exact committed JSON Schema
and default TOML bytes. Validation logs and SHA-256 receipts are in
`experiments/out/step17/final/validation_record.json`.

### Output and performance

| Book | JSON MB | Folder MB | Units | Archive run s | Archive peak GB | Publication s | Publication peak GB |
|---|---|---|---|---|---|---|---|
| Spanish history | 27.424 | 416.994 | 19772 | 4726.4 | 9.605 | 718.1 | 4.427 |
| Immigrant children | 5.185 | 7.304 | 3978 | 4718.8 | 2.585 | 293.3 | 0.368 |
| Art therapy | 0.763 | 0.764 | 922 | 166.2 | 0.216 | 5.6 | 0.101 |
| Medical anatomy | 9.956 | 140.347 | 9597 | 656.8 | 0.958 | 161.3 | 0.484 |
| Statistics | 27.759 | 93.099 | 20581 | 2076.7 | 1.356 | 252.6 | 0.924 |

MB/GB are decimal. Archive timing and process-tree peak are the original complete run,
including its original assembly. The final publication is rebuilt from that unchanged
semantic archive and measured separately; those two times must not be added as a new
complete run. Earlier publications and measurements are retained in `assembly_history`.

| Book | Final publication | File manifest |
|---|---|---|
| Spanish history | [book.json](../.cache/step11d2/final_books/step13/book-211da4ac822e49ef8520f53f15247e27167d68a7c4ec7751f83aa7fa7e73d07f/book.json) | [manifest.json](../.cache/step11d2/final_books/step13/book-211da4ac822e49ef8520f53f15247e27167d68a7c4ec7751f83aa7fa7e73d07f/manifest.json) |
| Immigrant children | [book.json](../.cache/step11d2/final_books/step13/book-dab6d0ffaa6c4852bf46a639c74004e38e762283e7c3ff62854e3c73858f4722/book.json) | [manifest.json](../.cache/step11d2/final_books/step13/book-dab6d0ffaa6c4852bf46a639c74004e38e762283e7c3ff62854e3c73858f4722/manifest.json) |
| Art therapy | [book.json](../.cache/step11d2/final_books/step13/book-3ed404136ddbfe13dc0b34d4518b973b215a0be848694277d692d03fa910c8c1/book.json) | [manifest.json](../.cache/step11d2/final_books/step13/book-3ed404136ddbfe13dc0b34d4518b973b215a0be848694277d692d03fa910c8c1/manifest.json) |
| Medical anatomy | [book.json](../.cache/step11d2/final_books/step13/book-1e2574f3dc7003e499d4dbf240efa768c3d00913667ab39a15046645c3caa58b/book.json) | [manifest.json](../.cache/step11d2/final_books/step13/book-1e2574f3dc7003e499d4dbf240efa768c3d00913667ab39a15046645c3caa58b/manifest.json) |
| Statistics | [book.json](../.cache/step13/final_books/final/book-3a1d4ec5835b15c4ca055fc7b048cdc6726551b2e912cf29d9efdaaa9b6f4d59/book.json) | [manifest.json](../.cache/step13/final_books/final/book-3a1d4ec5835b15c4ca055fc7b048cdc6726551b2e912cf29d9efdaaa9b6f4d59/manifest.json) |

These are generated local output folders; their compact measurements and checksums
are committed as evidence, rather than duplicating the publication binaries in Git.

The authoritative publication paths, file counts, content hashes, process measurements
and disk-reserve records are in `final/performance/*.json` and `final/report_data.json`
under `experiments/out/step17`. Statistics completed all 871 pages with the required
5 GB reserve; no further pruning was needed.

### Review workload

Counts by severity:

| Severity | Spanish history | Immigrant children | Art therapy | Medical anatomy | Statistics |
|---|---|---|---|---|---|
| must_check | 0 | 6 | 0 | 0 | 123 |
| needs_review | 2686 | 106 | 0 | 1065 | 3513 |

Counts by kind:

| Kind | Spanish history | Immigrant children | Art therapy | Medical anatomy | Statistics |
|---|---|---|---|---|---|
| alt_text | 470 | 1 | 0 | 315 | 373 |
| caption | 590 | 0 | 0 | 212 | 217 |
| character | 0 | 0 | 0 | 30 | 16 |
| credit | 381 | 2 | 0 | 0 | 0 |
| figure | 141 | 0 | 0 | 190 | 1443 |
| footnote | 224 | 0 | 0 | 54 | 266 |
| heading | 29 | 41 | 0 | 153 | 148 |
| hidden_text | 422 | 0 | 0 | 18 | 0 |
| join | 13 | 1 | 0 | 5 | 21 |
| language | 81 | 0 | 0 | 1 | 0 |
| mathml | 0 | 19 | 0 | 0 | 618 |
| ocr_page | 0 | 2 | 0 | 0 | 0 |
| page_label | 2 | 0 | 0 | 1 | 0 |
| structure | 293 | 24 | 0 | 64 | 448 |
| table | 40 | 22 | 0 | 22 | 86 |

All uncertain content units have a review entry. All review unit targets resolve,
including nested text, furniture and retained suppression records; IDs are unique
and continuation targets are reciprocal (`final/contract_check.json`).

### Development parity and determinism

Continuity and table parity pass on all five full archives. Independent development
assembly matched all five publications. The last publication correction preserves each
entry's own nesting level: a flat index container must not overwrite levels 2/3 with
its own level 1. A failing regression reproduced the defect; all 45 assembly tests pass
after the fix. Art index level accuracy returns to .998821 and anatomy to .962480.

For the four unchanged archives, the expensive independent proof was frozen before
this final correction. Every new item level is then checked against its source unit;
every other JSON field is exactly unchanged apart from producer/content hashes.
The OCR-cover book has fresh complete assembly parity. The method and proof hashes
are recorded in `final/parity` and `final/parity_before_entry_levels`; this is scoped
proof reuse, not five repeated full render runs. Full invariant proof reuse likewise
requires exact unchanged input keys and records the proof checksum in `proof_reuse.jsonl`.

One-worker, two-worker and development outputs have identical `book.json` and manifest
bytes for the worker fixture. The final producer and every file hash are recorded in
`final/workers_book3.json`.

### Reference metrics on the JSON

| Book | Paragraph F1 page / chained | Exact paragraph page / chained | Main-flow order / tau | Float anchors / within |
|---|---|---|---|---|
| Spanish history | 0.942888 / 0.943165 | 0.896304 / 0.882864 | 0.978726 / 0.957453 | 0.853532 / 0.942094 |
| Immigrant children | 0.854897 / 0.944556 | 0.680317 / 0.877147 | 0.998551 / 0.997102 | 0.666667 / 0.987231 |
| Art therapy | None / None | None / None | 0.990615 / 0.98123 | 0.0 / 1.0 |
| Medical anatomy | 0.901479 / 0.903072 | 0.765632 / 0.766334 | 0.962046 / 0.924093 | 0.57783 / 0.995577 |
| Statistics | None / None | None / None | None / None | None / None |

| Book | List item F1 / exact | List boundary F1 / nesting exact | Index exact / level accuracy | Bibliography F1 |
|---|---|---|---|---|
| Spanish history | 0.890553 / 0.796069 | 0.674471 / 0.793977 | 0.936015 / 1.0 | None |
| Immigrant children | None / None | None / None | None / None | 0.997199 |
| Art therapy | None / None | None / None | 0.922742 / 0.998821 | None |
| Medical anatomy | 0.887994 / 0.743559 | 0.517425 / 0.794349 | 0.862773 / 0.96248 | None |
| Statistics | None / None | None / None | None / None | None |

`None` means no applicable reference, not a zero score. Statistics uses joined-table
TEDS and archive order checks; it has no paragraph/list/order gold here. Main-flow
adjacent-unit order agrees with the archive on every measured pair: Spanish 8,126;
immigrant children 934; art 3; anatomy 2,444; Statistics 7,928.

Anatomy's 15/15 joined reference tables retain TEDS .9258 (full .8516; whole-only
.9702). Statistics scores 65 of 69 reference tables, retaining .9586 (full .8635;
whole-only .9961). These equal the earlier joined-table measurements.

Spanish paragraph F1 changes from .942928 to .942888 per page and .943204 to .943165
chained; exact matches change .896309 to .896304 and .882887 to .882864. The JSON
owner comparison records 75 aligned tokens leaving the scored content view: hidden
table text 14, markers 19, heading candidates 5, paragraphs 3 and figure text 34.
They remain in source-marker/suppression/figure evidence and the lossless ledger.
Anatomy loses one marker token from the scored text view; F1 changes .901418 to
.901479 per page and .903011 to .903072 chained. Statistics similarly excludes one
marker from aligned content scoring. Art and immigrant children have no aligned-owner
difference. These comparisons count reference-aligned tokens, not the ledger totals.

Spanish list-item F1 is .890553 and anatomy .887994. The earlier Spanish pre-table
list score .895674 is not the same final table-owned view. Anatomy main-flow order
changes from .933847 to .962046, float anchors from .606 to .577830 and within-float
order from .930191 to .995577 as figures, boxes and tables acquire explicit output
ownership. These representation effects are reported rather than called unchanged
accuracy. Complete list, nesting, index, bibliography and split/merge counts are in
`json_eval/*.json`. Art still has four missed cross-page entries and one false join;
Spanish has nine misses and two false joins. Continuity experiments did not fix them.

### Cleanup counts

| Book | Before unlinked figure-text/figure-stream paragraphs | After embedded figure text | After flagged figure-text paragraphs | Covered spans before / suppression records after |
|---|---|---|---|---|
| Spanish history | 76 | 3623 | 0 | 72 / 72 |
| Immigrant children | 0 | 0 | 0 | 0 / 0 |
| Art therapy | 0 | 0 | 0 | 0 / 0 |
| Medical anatomy | 1 | 240 | 56 | 18 / 18 |
| Statistics | 570 | 335 | 934 | 0 / 0 |

Embedded-entry totals also include text already linked in the archive; they are not
net moves of the unlinked cohort. Confirmed hidden spans leave visible content but
remain in suppression/source runs. Spanish additionally has 350 `not_rendered`
suppression records. Suppression record counts are not ledger token counts.

| Book | Items with marker before | Structured markers after | Glued markers flagged | Index dividers after |
|---|---|---|---|---|
| Spanish history | 1213 | 1198 | 0 | 1 |
| Immigrant children | 68 | 60 | 0 | 0 |
| Art therapy | 0 | 0 | 0 | 0 |
| Medical anatomy | 3154 | 3121 | 4 | 1 |
| Statistics | 7163 | 7163 | 0 | 1 |

The marker cohorts include table ownership and suppression changes; totals do not
imply that every original marker became a new item. Marker type counts, original
divider kinds and suppression-token reasons are retained per book in `cleanup`.

## OCR measurements

The additional real-scan set contains 54 pages: 15 Arabic, 18 Greek and 21 Chinese
(simplified and traditional, horizontal, vertical print and vertical handwriting).
Frozen scans, proofread transcriptions and licence/revision records are in
`experiments/test_data/step17_real_scans`. Three earlier Arabic pages were rechecked
separately. The engine comparison uses common pages, not different reader samples.
The truth comes from the recorded Wikisource proofreading revisions (levels 3/4),
without an additional independent local full-page transcription audit. Multiple pages
come from the same work. The original download status is preserved in source records.
Tesseract CER uses its emitted order; PP-OCRv5 CER uses geometric line ordering for
evaluation, including column/vertical handling. This is a recognition comparison
after that evaluation ordering, not a claim that PP detector emission is reading order.

| New-page group | Pages | Tesseract CER | PP-OCRv5 CER | Pages PP wins |
|---|---:|---:|---:|---:|
| Arabic | 15 | 24.83% | 24.82% | 7 |
| Simplified Chinese, horizontal | 9 | 75.69% | 10.66% | 9 |
| Traditional Chinese, horizontal | 3 | 92.40% | 5.71% | 3 |
| Traditional Chinese, vertical print | 6 | 113.07% | 99.47% | 6 |
| Traditional Chinese, vertical handwriting | 3 | 112.83% | 99.56% | 2 |
| Greek, monotonic | 3 | 7.02% | 10.23% | 1 |
| Greek, monotonic table pages | 3 | 11.49% | 31.64% | 0 |
| Greek, monotonic two columns | 3 | 2.56% | 1.94% | 2 |
| Greek, polytonic | 9 | 33.84% | 17.26% | 4 |

The stated selection margin is at least 20% fewer character errors and wins on at
least two thirds of pages. Only horizontal simplified/traditional Chinese meets this
consistently at a usable absolute error level. Vertical Chinese remains unreliable;
a relative win near 100% CER does not establish support. Arabic and Greek retain
Tesseract as primary. Other installed languages remain unmeasured. Reader selection
must also establish horizontal Han geometry in both readers; its replay audit is complete.
Re-reading Tesseract geometry for all 21 Chinese scans reproduced every frozen
hypothesis. Requiring horizontal evidence from both readers rejects all nine vertical
pages while retaining PP eligibility for 8/9 simplified and 3/3 traditional horizontal
pages. This dual-reader condition is applied by the final producer.

The page flag now uses the share of words below that reader's threshold rather than
mean confidence. The held-out 540-case fold catches 47/61 bad pages, with 30 false
positives: recall 77.05%, precision 61.04%, versus the earlier 2/61. Two-fold pooled
counts are TP 65, FP 119, FN 20, TN 874 (recall 76.47%, precision 35.33%). These are
page/degradation cases, not 1,078 independent books. Fold thresholds are approximately
0.082 and 0.088; 0.092 is the subsequent fit on all cases, not a held-out result.
The low-confidence-line alternative was also measured in `ocr/page_flag.json`.

Tesseract's default word threshold is 0.84. PP-OCRv5's separate word threshold is
0.94, fitted on 25,088 words in 52 two-reader cases. Its page-share threshold is
borrowed from Tesseract, **not separately calibrated**. Profiles may override both.
These word thresholds do not calibrate PP's full-line scores: line granularity is
preserved, those segments require review and their pages are always `must_check`.
RTL alternatives are normalized to logical order by a general Unicode bidi helper;
the original reading and alternatives remain evidence. Scanned-page tables remain
backlog.

## Continuity follow-ups

Continuity is the canonical join source; list page links remain audit evidence.
Cross-page glossary rows remain unlinked. The equation-input variant changes no
accepted joins on any of the five books (1, 161, 55, 138 and 168 respectively).
Consequently this measurement does not establish that the Statistics example was
fixed; it must not be reported as an improvement.

The proposed old-Step-9 column-start filter removes three medical-anatomy joins:
one clearly wrong, and two apparently valid continuations. It is disabled. Its audit
also records four withdrawn candidates subsequently re-established by other evidence;
candidate withdrawals must not be confused with net removals. The broader float
experiment removes two Spanish-history joins whose text reads as valid sentence
continuations. It is not accepted as a general improvement.

## Model and publication

`backend/src/book_core/assembly/schema.py` defines the Pydantic model and generates
the Draft 2020-12 JSON Schema, `universal-book` version 1.0.0. Publication validates
both the JSON Schema and model invariants, writes sorted compact UTF-8 JSON, checks
asset hashes, then publishes a folder containing `book.json`, images, review crops
and a manifest. Run date is outside the content digest. See
[json_schema.md](json_schema.md) for the complete consumer contract.

The model contains ordered semantic units, stable identifiers, page labels and
geometry, confidence and provenance, inline character spans, continuity links,
navigation, separate furniture, suppression records and a unified review list.
Markers become structure; figure-owned text is retained on figures; letter dividers
get their own role. Image alt-text slots remain flagged for review. Client profiles
are validated and versioned, reject unknown keys, carry their hash into output and
keep personal-name splitting off by default.

Confirmed hidden text is excluded from rendered content and explicitly retained in
suppression records. `source_runs` reference existing text slices so a hidden glyph
inside a visible token does not manufacture two ledger tokens. Source order comes
from each source line's explicit span sequence, never serialized dictionary-key
order. Whitespace-only figure, furniture and table fragments are retained because they
can separate two hidden words in a source line. Dropping these fragments concatenated
six anatomy chapter labels and numbers (12 missing and 6 extra); the corrected JSON
has zero missing and zero extra. Section token counts describe the reconstructed ledger
view; a mixed hidden/visible line is assigned to its visible owner, even if only a space
remains visible. The hidden words remain in suppression records.

The final standalone audit also found six Spanish-history hidden-text reviews naming
content units that had been removed. Hidden-span reviews now name the retained
suppression record, which carries the text, source references and visibility evidence.
This is a publication-only correction: completed semantic conversion archives remain
valid inputs. Assembly refreshes retain the original archive measurements and record
their own build time, peak memory and producer instead of claiming a new archive run.

## Inline styling

Styling derives from learned font names/flags, baseline geometry, drawn underline
evidence and PDF link annotations. OCR text receives no guessed style. Equation
content keeps its own records and is not styled a second time as sup/subscript.
Per-kind/per-book reference measurements are in `styling`; absent reference markup
does not provide a precision denominator.

The seeded 40-span hand check records 37 correct, one unclear and two wrong:
bold 6/6, italic 6/6, bold-italic 5 correct plus one unclear, links 6/6,
superscript 5/5, subscript 5/6, underline 4/5. Small caps lacks a hand-check sample.
Inline Lingua language spans remain off by default after the initial sample was
0/5 correct (foreign names and terms misled the detector); this is a limitation,
not a claim of reliable mixed-language span classification.

The following are aligned-token reference counts, not 40-span hand-check results.
`Both / reference / ours` gives the precision/recall denominators explicitly. Bold-italic
contributes to both bold and italic. These are the frozen styling experiment's source-span
measurements; publication-only review-link corrections do not change styling decisions.

| Book | Kind | Both / reference / ours | Precision | Recall |
|---|---|---:|---:|---:|
| Spanish history | Italic | 6457 / 6635 / 7766 | .8314 | .9732 |
| Spanish history | Bold | 35286 / 36701 / 39557 | .8920 | .9614 |
| Spanish history | Superscript | 10 / 10 / 15 | .6667 | 1.0000 |
| Immigrant children | Italic | 5720 / 5728 / 6396 | .8943 | .9986 |
| Immigrant children | Bold | 24 / 32 / 1176 | .0204 | .7500 |
| Immigrant children | Superscript | 2 / 3 / 3 | .6667 | .6667 |
| Art therapy | Italic | 2 / 2 / 2 | 1.0000 | 1.0000 |
| Medical anatomy | Italic | 3342 / 3721 / 5023 | .6653 | .8981 |
| Medical anatomy | Bold | 4394 / 4488 / 7586 | .5792 | .9791 |
| Medical anatomy | Underline | 81 / 81 / 135 | .6000 | 1.0000 |
| Medical anatomy | Small caps | 0 / 2 / 0 | — | .0000 |
| Statistics | Italic | 14983 / 18949 / 15195 | .9860 | .7907 |
| Statistics | Bold | 458 / 459 / 10860 | .0422 | .9978 |
| Statistics | Superscript | 56 / 104 / 90 | .6222 | .5385 |
| Statistics | Subscript | 6 / 58 / 82 | .0732 | .1034 |
| Statistics | Underline | 21 / 24 / 2211 | .0095 | .8750 |
| Statistics | Link | 265 / 265 / 2221 | .1193 | 1.0000 |

Reference links have zero recovered token matches in Spanish history (10,617 reference
tokens), immigrant children (4,591), and medical anatomy (3,169): these PDFs supplied no
matching PDF link annotations for the measured token pairs. This does not recreate links
that exist only in a reference format. For kinds with no reference markup, no reliable
precision/recall claim is made: Spanish history has 10 detected subscript and 3,140
underline tokens with no corresponding reference tags; all remaining absent-markup kinds
and their zero/nonzero counts are recorded in `styling/<book>.json`.

Heading markup explains part, but not all, of the bold mismatch: excluding reference
heading tokens changes bold precision to .6000 for immigrant children, .8800 for anatomy,
and only .0645 for Statistics. Statistics subscript/underline agreement remains weak;
small caps has no positive recovery in the two annotated anatomy tokens. These scores
are limitations, not evidence that every detected style is correct. The small hand sample
does not resolve the broader reference disagreement. The default profile avoids emitting
bold/italic inside headings, while retaining the source evidence in the JSON.

## Approved cache cleanup

The original 614-folder plan was frozen at SHA-256
`f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793`.
After protecting Step 15/16/17 baselines, parity inputs and the current registry,
55 folders with unverifiable source identity were excluded. No identified baseline,
parity input or current registry entry was selected. Only 559 listed eligible
folders were deleted: 30,935 files and 5,421,779,171 bytes in 176.356 seconds.
Free space immediately afterwards was 11,864,662,016 bytes. No additional pruning
has been performed. The post-deletion 62-test cache-closure check passes.

The broader suite then exposed a missed indirect dependency from retained fixture
analysis to 15 deleted native fixture caches. Those 15 files (15,140,963 bytes)
were regenerated from unchanged repository fixtures under matching current native
fingerprints; the original deletion record is preserved. This was a cleanup-audit
gap, not a converter invariant failure. The affected and remaining partition passed all
621 tests; details are in `cache_fixture_restoration_record.json`.

The first Statistics retry encountered the OCR-cover run's maintenance lock. Once
that run exited, Statistics passed its required 5 GB reserve preflight and resumed.
See `cache_cleanup_report.md`, `cache_prune_audit.json` and
`cache_deletion_record.json` under `experiments/out/step17` for exact exclusions,
file verification and timestamps. Gold, references, models and hold-outs were not
cleanup candidates.

## Review decisions and limitations

- Keep the measured horizontal-Chinese PP primary policy and revised page flag, with
  the stated sample/calibration limits. Vertical Chinese remains unreliable; Arabic
  and Greek retain Tesseract. Scanned-page tables remain backlog.
- Keep the column-start and broader-float continuity filters disabled: correct joins
  were lost. Explicit equation inputs change no accepted joins and do not establish
  a fix for the Statistics example. Its known I7 count remains one.
- Review weak style agreement, unresolved figure ownership and alt-text slots. Names,
  inline language splitting and model-generated alt text remain off by default.
- Linked/uniquely contained figure text is embedded in `figure.text`. Ambiguous text
  remains explicitly flagged: anatomy has 56 figure-text paragraphs; Statistics has
  934, of which 914 have no surviving figure after table/equation ownership. The
  remaining units cannot be assigned to a figure without evidence. No source text
  is dropped. The before/after counts are in `cleanup/*.json`.
- The OCR cover adds a book title; the prior title-page heading changes only role
  and reasons, with the same ID/level. Body-style letter and candidate counters
  include OCR evidence. English-only job settings also change native language
  annotations on 319 pages: en→und 90, und→en 22, es→en 15, es→und 10 labels.
  Every other non-OCR page field is identical. Those conditional detector scores
  do not demonstrate better language accuracy. The complete audit is in
  `final/book2_change_audit.json`; native text was never OCRed.
- The cleanup audit missed 15 indirect fixture dependencies; they were restored
  under exact current fingerprints. Preserve the deletion/restoration records and
  include indirect dependencies in any future cleanup audit.

The ledger keeps the existing benchmark token rule. Word segmentation for unspaced
CJK remains later work; the new scan comparison uses character error rate. Script
and text direction may remain unknown where the source provides no reliable evidence.

Free space at final gate measurement: **9,062,596,608 bytes** (9.06 GB decimal).
The original approved plan hash is unchanged; no additional pruning was performed.

ENT, mideast and the math hold-out were not run. Gold, reference XML, ledger, models
and old projects were not edited. No NIMAS or other Stage 2 adapter work is included.

See `experiments/out/step17/README.md` for evidence provenance and the final records.
