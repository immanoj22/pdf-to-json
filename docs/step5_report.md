# Step 5: ground-truth aligner

The reference XML is aligned token by token to the retained PDF tokens of the three approved
books. From the alignment, provisional derived gold is written (`human_approved: false`), and an
evaluation-harness skeleton scores a stage per book. All gates pass. The text ledger is unchanged.
Book 1 was used for tuning. Books 2 and 3 are hold-outs, run once, then re-run once for a logged
correctness fix. Step 6 has not started.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests (earlier + new) | **439 passed**, 0 failed, 0 skipped (215 earlier + 224 new) | [junit](../experiments/out/step5/pytest.xml) |
| Fixtures and 24 measured pages vs original sources | **0 missing / 0 extra**, all 24 | [cross-check](../experiments/out/step5/original_source_crosscheck.json) |
| Full 758-page book | **495,751 retained tokens**, 0/0 (`-m full_book` gate passes) | pytest |
| Synthetic pairs | Hyphenation, soft hyphen, glued/split words, ligatures, furniture-only PDF tokens, XML-only tokens, duplicated phrases, a moved sidebar, repeated headings vs running heads, a moved page block, no-native-text page, determinism, header repair, fragment wrap: **all pass** | [tests](../backend/tests/test_reference_alignment.py) |
| No double-claimed PDF tokens | Link step refuses claimed tokens; 200 seeded repetitive-text cases pass. **Shown to fail without the fix** | same file |
| Schema-vocabulary boundary test | **Passes unchanged** (no exception added). Dialect vocabulary lives in [backend/reference_dialects/dialects.json](../backend/reference_dialects/dialects.json), loaded via `Settings.reference_dialects` | [test_boundaries.py](../backend/tests/test_boundaries.py) |
| Ruff check / format | Pass, run from `backend/` | [log](../experiments/out/step5/ruff.log) |

No ledger, layout, existing gold or earlier gate was edited. The old projects stay read-only.
The NIMAS original is read with the approved in-memory header repair: the file is never modified,
no corrected copy is written, and the repair is recorded in every output.

## Design (brief)

- **Reading.** The `src` reader and aligner know no schema. A dialect profile (data) maps element
  names to neutral unit kinds (heading, paragraph, list_item, table_cell, caption,
  image_description, index_entry, ...), zones and sectioning. Inline markup never splits a word;
  every other element boundary does. Benchmark tokens are case-sensitive NFKC
  `[\p{L}\p{M}\p{N}]+`; the PDF side uses the ledger's own token ids and retention rule.
- **Stage A, segments to page ranges.** Text between page markers (fixed chunks if a reference
  has none) is placed by a Viterbi pass. The next page is free, staying or skipping one page is
  cheap, and any other move pays a jump penalty. Each segment's window is its page plus the
  following unassigned pages.
- **Stage B, tokens within windows.** Tokens and n-grams unique on both sides become anchors and
  are extended into runs. A weighted chain keeps runs ordered; long out-of-chain runs survive as
  moved blocks. Gaps get an anchored LCS that prefers the duplicate occurring at the same
  distance from the anchor, which is what keeps a running head from taking a heading's place.
  Joins and splits cover hyphenation, soft hyphens and glued words; case and near variants
  follow.
- **Later passes.** Spill to neighbouring pages; an order-free pass for image-description labels
  that matches values unique on both sides only; relocation of unique long runs; a context pass
  for short runs between aligned neighbours.
- **Nothing is guessed or dropped.** Every token is aligned, or unaligned with an explicit cause.
  Ambiguous single tokens without ordered context stay unaligned.
- **Cache.** The Step 4b discipline applies: the key covers XML and PDF hashes, extractor, every
  producing file of the new `alignment` scope, runtime, configuration and the dialect-profile
  digest. Figure evidence is cached separately. Results are deterministic (tested).

## Coverage per book

| | Book 1 Spanish US history | Book 2 Immigrant Children | Book 3 art-therapy index |
|---|---:|---:|---:|
| Split | development | hold-out (identity by text only) | hold-out, **anecdotal** (9 pages) |
| Dialect / repairs | DTBook / header quotes | DocBook / none | index fragments / fragment wrap |
| PDF pages | 758 | 331 | 9 |
| **PDF tokens aligned** | **474,071 / 495,751 (95.63%)** | **115,398 / 124,017 (93.05%)** | **4,184 / 4,249 (98.47%)** |
| **XML tokens aligned** | **473,171 / 474,850 (99.65%)** | **114,028 / 114,617 (99.49%)** | **4,185 / 4,294 (97.46%)** |
| Segments located / with tokens | 756 / 756 | 295 / 295 | 1 / 4 |
| Placement jumps | 3: the moved HT block and the special pages | 12: skipped blank pages, and the index block absent from the XML | 2: markers do not delimit content |
| Median / lower-quartile confidence | 1.0 / 0.95 | 1.0 / 0.95 | 0.27 / 0.26 |

### Unaligned tokens by cause

| PDF-only cause | Book 1 | Book 2 | Book 3 |
|---|---:|---:|---:|
| figure_text_candidate (inside native image/compound region) | 11,818 | 0 | 0 |
| furniture_candidate (line text repeats on 3+ pages) | 3,937 | 1,250 | 36 |
| folio_candidate (single-token number or page label) | 2,642 | 359 | 6 |
| absent_from_reference | 2,069 | 5,548 | 23 |
| surplus_occurrence (value present, reference occurrences used) | 1,214 | 1,460 | 0 |
| page_not_in_reference | 0 | 2 | 0 |

| XML-only cause | Book 1 | Book 2 | Book 3 |
|---|---:|---:|---:|
| image_description (unmatched or repeated figure labels) | 1,382 | 1 | 0 |
| reference_metadata (book-level head/info) | 0 | 408 | 0 |
| surplus_occurrence | 184 | 53 | 8 |
| absent_from_pdf | 113 | 127 | 5 |
| segment_not_located | 0 | 0 | 96 |

Methods, book 1: anchor 294,758; extension 126,726; moved 48,144; spill 1,152; join_split 866;
leftover 671; figure_label 531; gap 220; rest under 50 each. Book 2 exercises hyphenation
heavily: join_hyphen 1,358 and case 259. In book 1, consecutive XML tokens of one unit landed on
adjacent PDF tokens in **99.85%** of cases (100% for anchors and extensions), a precision
indicator that needs no gold.

Notes on causes:
- **Book 1, PDF:** figure text is map and diagram labels.
- **Book 2, PDF:** `absent_from_reference` is mostly the printed index (about 21 pages), which
  the XML does not contain. Those pages fall inside the last segment's window, so the cause
  reads "absent" rather than "page not in reference".
- **XML side:** `absent_from_pdf` covers reference differences, for example glued words such as
  "delhistoriador", and text present only in the XML.

Full summaries: [book 1](../experiments/out/step5/spanish_us_history/alignment_summary.json),
[book 2](../experiments/out/step5/immigrant_children/alignment_summary.json),
[book 3](../experiments/out/step5/art_therapy_index/alignment_summary.json).

### Book 1 page order (was flagged in Part 1)

The three placement jumps are exactly the editorial moves found in Part 1:
- PDF pages 723–758 (HT1–HT36) appear in the reference after page xxii.
- The reference then returns to page 25 (label 1).
- The `special` pages come at the end.

The three single-page "outliers" from the Part 1 diagnostic (labels 327, 477, 517) are placed on
their own pages: their opener captions are reprinted on the table-of-contents pages, and the
diagnostic's argmax vote picked the reprint.

## Correctness fix: double-claimed PDF tokens (not tuning)

Overlapping unique n-gram anchors could let two reference tokens claim one PDF token. Two
changes fix it:
- The anchor pass now re-checks availability before taking a position.
- The link step refuses any PDF token that is already claimed, and counts the refusals.

A regression test (direct link refusal plus 200 seeded repetitive-text cases) fails without the
fix. All three books were re-run with the reason logged
([before/after](../experiments/out/step5/double_claim_fix.json),
[hold-out log](../experiments/out/step5/holdout_runs.jsonl)).

| Book | Double-claimed PDF tokens before / after | XML tokens involved before / after | PDF aligned before / after | XML aligned before / after |
|---|---|---|---|---|
| 1 | 5 / 0 | 10 / 0 | 474,071 / 474,071 | 473,178 / 473,171 |
| 2 (hold-out) | 2 / 0 | 4 / 0 | 115,399 / 115,398 | 114,031 / 114,028 |
| 3 (hold-out) | 0 / 0 | 0 / 0 | 4,184 / 4,184 | 4,185 / 4,185 |

Refused links after the fix: 0 in every book.

### Hold-out log

Only aligner producer `f0bceda9…` was tuned, on book 1. Books 2 and 3 then ran once.

After those runs, the producer changed once, to `f1e57576…`: the correctness fix above plus the
schema-neutral dialect refactor (no behaviour change). Every hold-out run and derived-gold write is
appended to [holdout_runs.jsonl](../experiments/out/step5/holdout_runs.jsonl). No threshold or
configuration was changed after the hold-out runs.

## Derived gold (provisional, `human_approved: false`)

Location: [backend/tests/gold_derived/](../backend/tests/gold_derived/), one directory per book.
It is not merged with the hand-made gold.

| File | Content |
|---|---|
| `manifest.json` | Split, notes, `human_approved: false`, provenance (PDF/XML SHA-256, dialect, repairs, extractor, aligner version, configuration, producer digest, dialect-profile digest), counts and file digests |
| `units.jsonl.gz` | Text units in **reference (XML) order**: element path, neutral kind, zone (front/body/rear/metadata), heading level with method (declared or nesting), list/table membership, token counts, confidence, methods, unaligned causes, start/end PDF token (paragraph boundaries), PDF token runs, `shared_pdf` |
| `page_markers.json` | Label, element path, placed PDF page, containment, confidence, low-confidence flag, `excluded_from_gates` (true for all of book 3) |
| `pages.json` | Per-page token count and token-id digest. References are `[page, ordinal]` over retained native tokens, so they can be verified against any later extraction |

Unit counts:
- **Book 1: 18,041 units.** 8,252 paragraphs, 5,278 list items, 1,240 + 1,240 definition
  term/description, 622 table cells, 505 headings, 438 captions.
- **Book 2: 4,499 units.**
- **Book 3: 926 units**, of which 920 are index entries.

Two PDF tokens in book 2 carry text of two adjacent table/bibliography units (one split link
over a word glued in the PDF). Both units declare them in `shared_pdf`.

## Evaluation harness (skeleton)

[derived_harness.py](../backend/src/book_core/evaluation/derived_harness.py) works as follows:
- It scores one stage at a time, per book, and returns `overall: None`.
- Hold-out books are skipped unless `include_holdout=True`, and every row carries its split.
- Token references are verified against the stage's pages before scoring.

Implemented metrics: text-unit coverage (overall and by kind), zone coverage and page-marker
coverage. Documented stubs, each raising `NotImplementedError` until its stage exists: paragraph
boundaries, heading levels, list/table membership and reading order.

| Current ingestion stage | Book 1 | Book 2 | Book 3 |
|---|---|---|---|
| Text units fully covered | 18,004 / 18,004 | 4,433 / 4,433 | 925 / 925 |
| Zone coverage | front, body, rear 1.0 | front, body, metadata 1.0 | rear 1.0 |
| Page markers present | 755 / 755 placed | 294 / 294 placed | excluded (low confidence) |

These 1.0 values are expected: provisional ingestion retains every token. They validate the
harness, not converter quality.

## Five sample pages

Line boxes are coloured by the neutral kind of the aligned reference unit; dark grey means
unaligned. Per-line tables (text, element path, methods, confidence, causes) sit next to each
image as `sample_p*.json`.

| Page | What it shows | Aligned |
|---|---|---|
| [Book 1 p26](../experiments/out/step5/spanish_us_history/sample_p26.png) | Two columns, pull quote and repeated quotation, glossary definition: all aligned. The reference tags the visual title "LA CONFEDERACIÓN IROQUESA" as a paragraph | 564 / 564 |
| [Book 1 p465](../experiments/out/step5/spanish_us_history/sample_p465.png) | Two prose columns plus four organisation cards (the reference uses table cells); only the folio is unaligned | 675 / 676 |
| [Book 1 p723 (HT1)](../experiments/out/step5/spanish_us_history/sample_p723.png) | The moved block, aligned in place. The reference omits the titles of TOC items 04–06 and glues "delhistoriador", so those PDF tokens stay unaligned with causes | 89 / 107 |
| [Book 2 p124](../experiments/out/step5/immigrant_children/sample_p124.png) | Rotated regression table: cells and title aligned; the running head is furniture. β is extracted as "b" (absent from the reference) | 204 / 216 |
| [Book 3 p3](../experiments/out/step5/art_therapy_index/sample_p3.png) | Three-column index: entries aligned; running head and folio unaligned; "see also" is absent from the reference text | 488 / 503 |

## Limitations found

1. **Book 2 heading labels.** 1,553 of 1,813 "heading" units are cited-work titles inside
   bibliography entries (`title` maps to heading regardless of context). The other 260 are real
   chapter and section titles. Alignment is unaffected; only derived labels are. Found on a
   hold-out book, so it was not changed.
2. **Book 3 confidence.** Its page markers do not delimit page content, so one segment of 1,809
   tokens is aligned mostly by spill and relocation. Confidence: median 0.27.
3. **`folio_candidate` over-reports.** A single-number table cell (book 2 p124 ".23") is labelled
   folio-like. These cause labels are diagnostic evidence, not converter decisions.
4. **A missed glued word.** "delhistoriador" on book 1 HT1 was not joined, because its neighbours
   were aligned by a later pass.
5. **Cache side effect.** Adding the `alignment` scope to `caching.py` changes every cache key
   (as designed: `caching.py` is a producer). Existing extraction, layout and detection caches
   rebuild on next use; results are unchanged, as the gates confirm.

## Decisions for review

1. **Book 2 heading labels:** approve a profile rule that makes `title` a heading only under
   sectioning/info (not inside bibliography entries), applied as a logged post-hold-out change.
   Alternatively, leave book 2 heading gold out of any future heading gate.
2. **Book 3:** keep it anecdotal as is, or approve a chunked fallback for references whose
   markers do not delimit content (would be a logged post-hold-out change).
3. **Furniture and folio cause labels:** these are aligner-side diagnostics. Should a later
   furniture stage replace them before any furniture gate uses them?
4. **Derived-gold size** is about 1.2 MB committed (gzipped units). Is committing it acceptable,
   or should it be regenerated from cache in CI instead?

## Step 5b: logged label fixes (not aligner tuning)

Applied after owner review; recorded in [decisions.md](decisions.md) and in
[holdout_runs.jsonl](../experiments/out/step5/holdout_runs.jsonl). They supersede limitation 1 and
the book 2 cause counts above. Decisions taken: book 3 stays anecdotal (no chunked fallback);
aligner furniture/folio causes are diagnostics only (the Step 8 furniture stage decides
furniture, and no gate uses aligner causes); derived gold stays committed.

1. **Title rule (dialect data).** A title is a heading only when it belongs to a sectioning element
   or that element's info. Titles inside bibliography or citation entries are part of the entry.
   The rule is a `contextual_units` entry in
   [dialects.json](../backend/reference_dialects/dialects.json); `src` stays schema-neutral.
2. **Page coverage.** PDF tokens on a page that is not a located segment's own page and has no
   aligned tokens now get `page_not_in_reference`. A page lying inside a segment's window no
   longer counts as covered.

Each fix has a test, and the page-coverage test was shown to fail under the old rule
([tests](../backend/tests/test_reference_alignment.py)).

| | Book 1 | Book 2 | Book 3 |
|---|---|---|---|
| Alignment coverage (PDF / XML aligned, methods, XML causes, placements) | **identical**: 474,071 / 473,171 | **identical**: 115,398 / 114,028 | **identical**: 4,184 / 4,185 |
| Heading units before → after | 505 → 505 | **1,813 → 246** | 2 → 2 |
| Units before → after | 18,041 → 18,041 | 4,499 → 2,946 (1,553 bibliography titles merged into their entries; 14 table/figure titles now `other`) | 926 → 926 |
| `page_not_in_reference` | 0 → 6 (front cover, p1) | **2 → 6,779** (printed index) | 0 → 0 |
| `absent_from_reference` | 2,069 → 2,069 | 5,548 → 418 | 23 → 23 |
| `surplus_occurrence` | 1,214 → 1,214 | 1,460 → 87 | 0 → 0 |
| `furniture_candidate` | 3,937 → 3,937 | 1,250 → 1,013 | 36 → 36 |
| `folio_candidate` | 2,642 → 2,642 | 359 → 322 | 6 → 6 |
| `figure_text_candidate` | 11,818 → 11,812 | 0 → 0 | 0 → 0 |

Furniture and folio counts fall on book 2's index pages only because `page_not_in_reference` takes
precedence there. Full before/after record: [label_fix_5b.json](../experiments/out/step5/label_fix_5b.json).
Gates after 5b: **441 tests pass**; 24 pages 0 missing / 0 extra; full book 495,751; Ruff clean.

## Reproduce

Run from `experiments/`:
1. `python step5_inventory.py`
2. `python step5_run.py --book spanish_us_history`
3. Hold-out books need an explicit flag and a reason:
   `python step5_run.py --book immigrant_children --holdout --reason "..."`
4. `python step5_gold.py --book <book> [--holdout] --sample-pages ...`
5. `python step5_fix_report.py`

Pytest and Ruff run from `backend/`. Caches: `.cache/step5/` (native pages, alignments, figure
regions). Inventory and approvals: [step5_inventory.md](step5_inventory.md).

**Step 5 stops here for owner review. No Step 6 work.**
