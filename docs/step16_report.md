# Step 16 — OCR for pages without usable text

Status: **complete for review.** An OCR stage now reads pages (or large regions) that have no
usable native text, with Tesseract 5.5.3 as the primary reader and PP-OCRv5 as the second
reader. OCR words become marked tokens (`source: "ocr"`) that flow through the existing
stages unchanged in logic. The native ledger is not touched. **No page of books 1–4 or
Statistics was OCR'd** (none qualifies without an owner decision, below), and their final
archives are **byte-identical to Step 15**.

## Results first

**Born-digital books (books 1–4, Statistics): unchanged.**

| Check | Result |
|---|---|
| Pages that qualify for OCR | **0 of 2,283** decided automatically; 1 page (book 2 p1, the cover) qualifies only after the visual check and is held for your decision (OCR not run on it) |
| Final archives vs Step 15 | **byte-identical, all five books**: 11 / 338 / 645 / 1,268 / 1,619 files, every SHA-256 equal ([archive_identity.json](../experiments/out/step16/final/archive_identity.json)) |
| Stage comparison (native text, layout, reading order, furniture, paragraphs, lists, structure) | no page changed in any stage on books 1–4 ([comparison files](../experiments/out/step16/final/)) |

**Recognition quality on real scans** (public-domain Wikisource pages with human-proofread
text; Tesseract with the page's language; counts behind every number in
[real_eval](../experiments/out/step16/real_eval/)). CER and WER use the reader's emitted
order; "order-free" is the character-multiset F1 (recognition without any order).

| Language (pages) | Tesseract CER | Tesseract WER | Order-free F1 Tess. | PP-OCRv5 line-ordered CER | Order-free F1 PP | Label¹ |
|---|---|---|---|---|---|---|
| English (3) | **1.7%** (126/7,285) | 8.4% (106/1,255) | 0.988 | **1.3%** (97/7,285) | 0.990 | **good** |
| Spanish (3) | **3.1%** (267/8,498) | 13.3% (197/1,483) | 0.988 | **2.6%** (220/8,498) | 0.983 | **good** |
| Russian, pre-1918 spelling (3) | 7.8% (459/5,884) | 30.9% (280/907) | 0.932 | 7.4% (434/5,884) | 0.938 | **usable (review)** |
| Hindi (3) | 8.6% (384/4,478) | 25.5% (237/929) | 0.961 | 12.0% (538/4,478) | 0.933 | **usable (review)** |
| Arabic (3) | 22.5% (527/2,338) | 65.9% (280/425) | 0.893 | 15.2% (355/2,338)² | 0.911 | **weak** (Tesseract 22.5%); usable (review) with PP-OCRv5 |
| Greek, polytonic 1916 (4) | 57.8% (1,207/2,090) | 80.1% (278/347) | 0.766 | 27.3% (571/2,090) | 0.838 | **weak** with PP-OCRv5; not reliable with Tesseract |
| Chinese, modern mixed with romanisation (2) | 46.7% (320/685) | 35.3% (101/286) | 0.755 | **4.7%** (32/685) | 0.919 | **not reliable** with Tesseract; good with PP-OCRv5 on 2 pages only — too few to call it working |
| Chinese, 1537 woodblock, vertical (3) | 96.7% (465/481) | 99.4% (460/463) | 0.014 | 98.1% (472/481) | 0.024 | **not reliable** |
| Every other installed language (≈ 110 language and 37 script models) | — | — | — | — | — | **installed, not measured** |

¹ Labels use the better reader's line-ordered CER, which is what a reviewer would see if that
reader were chosen: good ≤ 5%, usable (review) ≤ 15%, weak ≤ 30%, not reliable above. The
label is per language **as measured on these few pages**, not a general claim.
² PP-OCRv5's Arabic recognizer emits each line's characters in visual (left-to-right) order;
scored after reversing each line to logical order (evaluation only; see Limitations).
Its unreversed line-ordered CER is 73.3%.

**PP-OCRv5 is the better reader for modern Chinese, Greek and Arabic** and equal on
English, Spanish and Russian; Tesseract is better on Hindi. Both fail on the woodblock pages
(the vertical Tesseract packs `chi_tra_vert`/`chi_sim_vert` with segmentation modes 3 and 5
find 0–3% of the characters). Tesseract remains the primary reader as specified; see
Decisions.

**Synthetic scans** (books 1, 2, 4 and Statistics; 30 seeded pages per book × 9
degradations = 1,080 cases; text layer removed, figures masked; truth = the native text;
counts in [report_data.json](../experiments/out/step16/report_data.json)):

| Book | clean CER | worst degradation | WER clean |
|---|---|---|---|
| 2 Immigrant children | **0.43%** (324/74,503) | noise 0.59% | 2.3% |
| 4 Medical anatomy | **1.36%** (771/56,712) | blur 1.41% | 5.9% |
| 1 Spanish US history | **2.52%** (2,954/117,199) | 200 dpi 3.26% | 3.3% |
| Statistics | **4.67%** (2,618/56,000) | noise 4.94% | 12.6% |

Orientation: **all rotated pages corrected except 4 of 240 cases**, all on two near-empty
pages. The confidence threshold flags words that are wrong **65% of the time**, while
unflagged words are wrong **1.2%** of the time (held-out pages).

**Downstream** (scan vs native run of the same pages): reading order is kept where the page is
running text (median Kendall tau 1.0 on books 1, 2 and Statistics); paragraph starts are found (recall
0.72–1.0) but OCR over-splits on mixed layouts; **tables are not recovered on scans (0 of
16 native tables)** and list items on book 4 mostly lose their list form.
Details below.

## Scope and baseline

HEAD at start: `8f95184` (Step 15). Baseline: the Step 15 final capture, frozen into
[step16/before](../experiments/out/step16/before/). Only books 1–4 and Statistics were run;
ENT, mideast, the mismatched pair and the math hold-out were not. Gold, reference XML, the
ledger and old projects were not edited. Part of the step (installation, the OCR package and
the eligibility screen) was done in an earlier session by another agent; this session
completed the language-pack provisioning, test data, language choice, measurements, two
fixes found by the measurements, and the gates.

## Part 0 — Step 15 decisions

Recorded in [decisions.md](decisions.md#step-16-owner-decisions-on-the-step-15-gate):
kept Step 9 joins and display equations deferred to Step 17 Part 0; glossary rows across
pages stay unlinked; continuity links are the single source for adapters (`lists.page_links`
audit only); the two Step 15 layout model files are listed in
[dependencies.md](dependencies.md) with immutable revisions, sizes and licences.

## Part 1 — installation

All recorded in [dependencies.md](dependencies.md#step-16-ocr-assets-and-licence-audit).

| Component | Version / pin | Licence | Where |
|---|---|---|---|
| Tesseract | 5.5.3, built from source (Leptonica 1.86/1.87, libpng, zlib; no GPL parts) | Apache-2.0 | `.cache/step16/ocr/tesseract-5.5.3/` (explicit path; no installer, no PATH change, no admin) |
| pytesseract | 0.3.13 | Apache-2.0 | project venv |
| tessdata_best | commit `e12c65a9…`; **162 files, 1,774,547,803 bytes**: every language, all 37 `script/` models, `osd`, vertical CJK | Apache-2.0 | `.cache/step16/ocr/tessdata_best/<commit>/`, each file checked against its Git blob SHA-1 |
| PP-OCRv5 | server detector + server (Chinese/English) recognizer + mobile recognizers for English/Latin, Arabic, Cyrillic, Devanagari, Greek; immutable revisions | Apache-2.0 | `.cache/step16/ocr/ppocr/`, local files only |

The UB Mannheim Windows build was rejected: it ships a GPL-2.0 library (JBIG-KIT).
PaddlePaddle has no wheel for Python 3.14, so PP-OCRv5 runs through the existing
Transformers path. The disk rule held throughout (5 GB reserve; 12.4 GB free before the
packs).

**Runtime model loading fixed (your instruction).** A book run constructed its layout,
table and formula models with network access allowed and, without a model directory, the
user-wide Hugging Face cache. Every model a run constructs is now local-only from the
project cache (`<cache>/huggingface` unless a directory is given). Verified with
`HF_HUB_OFFLINE=1`: all six (Heron, PP-DocLayoutV3, PP-FormulaNet, TATR detection and
structure, TableFormer) load at their pinned revisions
([runtime_model_pins.json](../experiments/out/step16/dependencies/runtime_model_pins.json));
a test fails if a run could construct a model that may fetch.

## Part 2 — which pages need OCR

The screen ([detection](../experiments/out/step16/detection/)) reads the cached native
evidence: text layer, Unicode mapping (unmapped glyphs, private-use characters), invisible
text (render mode 3), and raster coverage of the page. A raster covering the page without
native text is a candidate; an independent visual check (two layout readers agree the area
is text, PP-OCRv5's text detector supports it, neither reader calls it a figure) decides
whether it holds text. Figures are masked and never OCR'd.

| Book | Pages | Native | OCR | Compare only (earlier OCR layer) | Review | Notes |
|---|---|---|---|---|---|---|
| 1 Spanish US history | 758 | 758 | 0 | 0 | 0 | |
| 2 Immigrant children | 331 | 330 | 0 | 0 | **1** | p1, the cover: a full-page image; the visual check finds text on it → **decision for you** |
| 3 Art-therapy index | 9 | 9 | 0 | 0 | 0 | |
| 4 Medical anatomy | 314 | 314 | 0 | 0 | 0 | 14 pages hold isolated unmapped glyphs (353 glyphs, 14 characters, symbols) — native text kept |
| Statistics | 871 | 871 | 0 | 0 | 0 | |

No book has an invisible text layer, so the compare-only path (earlier OCR under a scan)
was exercised only in tests. The render-and-compare check (does the native text match what
is drawn?) was **not run** on these pages; their decision rests on Unicode mapping,
visibility and raster coverage, and each page records the check as unmeasured. The visual
text check ran on the one candidate page (book 2 p1).

## Part 3 — the OCR stage

- **Render** 300 dpi. **Orientation** by `osd` then rotation; **deskew**. **Not measured
  this step:** 400 dpi for small print, and the binarisation, denoise and contrast
  options (they exist in the benchmark but were not run, for time). None is enabled; the
  degradation results (2.2–2.4% CER across all nine) leave little room for them on these
  renders, but real scans may differ.
- **Language choice** (`ocr/language_choice.py`, new this session):
  1. book languages from Lingua's native-text evidence, mapped with the tested table (75
     Lingua languages → tessdata names; 9 have no Tesseract model and are rejected
     explicitly);
  2. no native text: OSD names a script; every major script model (Latin, Cyrillic, Greek,
     Arabic, Hebrew, Devanagari, HanS, HanT, Hangul, Japanese) also reads the page; OSD's
     script is kept unless another beats it by 0.10 mean confidence; with no OSD script, the
     most confident one is used. **The job languages are never assumed for an unknown
     script.** Lingua then reads the result, and a confident language re-reads the page;
  3. mixed pages: the job/region language list (`spa+eng`, …).
- **Two readers.** Tesseract's reading is kept; PP-OCRv5 words are matched by box overlap
  and, where they disagree, recorded as alternatives with lowered confidence. Choosing per
  word by confidence was measured and **not kept** (worse than Tesseract alone on every
  book, below).
- **Output.** OCR words and lines become spans and lines in PDF coordinates with
  `source: "ocr"`, engine, languages, word and line confidence, and font size from line
  height. A page's OCR record and raster are cached under a fingerprint of the native page,
  raster, eligibility, settings, engines and models, packs and runtime. The native ledger
  and native spans are never changed (book 1 ledger 495,751, below).
- **Review status.** With a calibration in the job settings, words below the word threshold
  are `needs_review` and a page below the page threshold is `must_check`; without one, every
  OCR page is `needs_review`. The measured thresholds (below) are not yet written into a
  default configuration (Decisions).
- **Determinism.** One thread per reader (`OMP_THREAD_LIMIT=1` inside the Tesseract call;
  PP on CPU, one thread). **1 vs 2 workers on a scanned book: byte-identical archive (18 of 18
files); re-OCR in a fresh cache: 8 of 8 pages identical (2,128 words; text, boxes and
confidences)** ([workers_immigrant_children.json](../experiments/out/step16/downstream/workers_immigrant_children.json)).

**Two fixes found by the measurements:**
1. Windows: pytesseract keeps literal quotes in `--tessdata-dir "…"`, so OSD could not load.
   The tessdata path is now passed as `TESSDATA_PREFIX` for the duration of the call and
   restored (test added).
2. The first full scanned-book run failed: navigation metadata carried the native
   extractor's identity under the OCR view, and the metadata cache rejected it. The OCR view
   now stamps navigation with its own identity (test added).

A third, found by the test suite: the OCR stage now imports Lingua's wrapper, so
`document_analysis/language.py` joined the OCR cache-key scope (as for paragraphs).

## Part 4 — test data

**Synthetic scans:** 30 seeded pages per book (seed 1600), chosen to include tables, lists,
several columns, an index and (Statistics) equations
([sample_manifest.json](../experiments/out/step16/benchmark/sample_manifest.json)); every
page under clean, 200 dpi, skew ±2°, noise, blur, JPEG 50, rotated 90° and 180°.

**Real scans** ([test_data/step16_real_scans](../experiments/test_data/step16_real_scans/),
read-only): 26 Wikisource pages, each with its scan, the proofread transcription (wikitext,
HTML, text), revision id, proofreading level (3 or 4 only), and the Commons licence
(all public domain); download script `step16_real_data.py`.

| Language | Source (public domain) | Pages |
|---|---|---|
| English | Darwin & Wallace, *On the tendency of species…* (1858) | 3 |
| Spanish | *El ingenioso hidalgo Don Quijote de la Mancha* | 3 |
| Hindi | सरदार पूर्णसिंह अध्यापक के निबन्ध | 3 |
| Arabic | Gibran, الأرواح المتمردة (1908) | 3 |
| Russian | Fet, *Мои воспоминания*, vol. 1 (pre-reform spelling) | 3 |
| Greek | Ραμάς, *13 Σονέττα* (1916), polytonic | 4 (one is an advertisement page) |
| Chinese | 三國史記 (1537 woodblock, vertical) | 3 |
| Chinese | 江南話新概說 (modern, mixed with romanised Wu) | 2 |

Derived ground truth removes the Wikisource CSS and the "本页已校对" status label; the frozen
files are unchanged.

## Part 5 — measurements

### Real scans: language choice before / after (Tesseract, no language given)

Before = OSD script, then Lingua; when OSD names no script, the job languages (spa+eng).
After = the rule kept (OSD script unless another script model is 0.10 more confident;
otherwise the most confident script; then Lingua). Character errors / characters:

| Language | Before | After | Change |
|---|---|---|---|
| English | 1.7% (126/7,285) | 1.7% (126/7,285) | identical |
| Spanish | 3.1% (267/8,498) | 3.1% (267/8,498) | identical |
| Russian | 7.8% (459/5,884) | 7.8% (459/5,884) | identical |
| Hindi | 8.6% (384/4,478) | 8.6% (384/4,478) | identical |
| Arabic | 22.5% (527/2,338) | 22.5% (527/2,338) | identical |
| Greek | 85.1% (1,778/2,090) | **62.4%** (1,305/2,090) | better: p29 84% → 18%, p31 75% → 0% |
| Chinese, modern | 61.6% (422/685) | **48.0%** (329/685) | better |
| Chinese, woodblock | 97.5% (469/481) | 97.1% (467/481) | unreadable either way |

Kept: no language is worse. Greek pages 32 and 33 stay wrong (OSD reads them as Cyrillic
and Greek is not 0.10 more confident; page 33 is an advertisement page that OSD also turns
180°). With the page's language given, Tesseract reaches 57.8% on Greek and 22.5% on
Arabic.

### Real scans: the two readers on the same pages

Same pages, both readers. PP-OCRv5 lines are grouped by vertical overlap, top to
bottom, words by x (evaluation only, single-column pages); "emission" is PP's raw output
order. Counts in [readers_common.json](../experiments/out/step16/real_eval/readers_common.json).

| Language | Tesseract CER | PP-OCRv5 CER, line-ordered | PP-OCRv5 CER, emission order | Order-free F1 Tess. / PP |
|---|---|---|---|---|
| English | 1.7% | **1.3%** | 75.8% | 0.988 / 0.990 |
| Spanish | 3.1% | **2.6%** | 74.0% | 0.988 / 0.983 |
| Russian | 7.8% | **7.4%** | 81.6% | 0.932 / 0.938 |
| Hindi | **8.6%** | 12.0% | 78.5% | 0.961 / 0.933 |
| Arabic | 22.5% | **15.2%** (logical order) | 74.8% | 0.893 / 0.911 |
| Greek | 57.8% | **27.3%** | 79.1% | 0.766 / 0.838 |
| Chinese, modern | 46.7% | **4.7%** | 82.5% | 0.755 / 0.919 |
| Chinese, woodblock | 96.7% | 98.1% | 97.7% | 0.014 / 0.024 |

PP-OCRv5 took 130–400 s per page here (about 20× Tesseract).

### Synthetic scans: per degradation (Tesseract, all four books, 1,080 cases)

| Degradation | CER | WER |
|---|---|---|
| clean | 2.19% (6,667/304,414) | 5.43% (2,683/49,390) |
| 200 dpi | 2.43% (7,384/304,414) | 5.72% (2,824/49,390) |
| skew −2° | 2.23% (6,786/304,414) | 5.39% (2,664/49,390) |
| skew +2° | 2.25% (6,844/304,414) | 5.37% (2,652/49,390) |
| noise | 2.27% (6,925/304,414) | 5.63% (2,779/49,390) |
| blur | 2.37% (7,214/304,414) | 5.51% (2,721/49,390) |
| JPEG 50 | 2.16% (6,566/304,414) | 5.38% (2,657/49,390) |
| rotated 90° | 2.19% (6,667/304,414) | 5.43% (2,683/49,390) |
| rotated 180° | 2.29% (6,957/304,414) | 5.52% (2,725/49,390) |

OCR words are aligned to the native lines by geometry; raw emission-order scores are kept in
each case record. Equations count as text (most of Statistics' error is math). Equivalence:
54 cases cached before a formatting-only producer change were re-read on the frozen producer
and are **identical (54 / 54)**.

### The two readers and the combination (common cases only)

PP-OCRv5 was run on 6 seeded pages per book under clean and 200 dpi only (**scope cut**: it
takes 3–8 minutes per page on this CPU), 52 cases; all readers are compared on exactly those
cases.

| Book | Tesseract | PP-OCRv5 | Combined (kept) | Choose per word by confidence (experiment) |
|---|---|---|---|---|
| 1 Spanish US history | **2.16%** (1,517/70,274) | 5.70% | **2.16%** | 2.91% |
| 2 Immigrant children | **0.20%** (69/33,974) | 0.51% | **0.20%** | 0.43% |
| 4 Medical anatomy | 1.73% (432/25,010) | **1.53%** | 1.73% | 2.09% |
| Statistics | **2.11%** (663/31,428) | 2.65% | **2.11%** | 2.27% |

Combined keeps Tesseract's words, so its error equals Tesseract's; it adds PP alternatives
and lowers confidence where they differ. **Choosing per word by confidence is worse than
Tesseract alone on every book, so it is not kept.** On these born-digital renders Tesseract
is the stronger reader; on the real scans PP-OCRv5 is, for most languages (above).

### Confidence calibration

Fitted on a seeded half of the (book, page) pairs (all degradations of a page together),
evaluated on the other half; 223,839 training words.

| Level | Threshold | Held out: flagged | Wrong among flagged | Unflagged | Wrong among unflagged |
|---|---|---|---|---|---|
| Word `needs_review` | confidence < **0.84** | 6,358 | **65.2%** (4,144) | 209,527 | **1.2%** (2,516) |
| Page `must_check` (page CER > 10%) | mean confidence < **0.773** | 2 | 100% (2) | 538 | 11.0% (59) |

The word threshold works: a flagged word is 54× more likely to be wrong. The page threshold
is precise but **catches only 2 of 61 bad pages**; mean word confidence is a poor page signal
(the bad pages are equation-heavy, with confident wrong words). It is recorded, not trusted
(Decisions). Thresholds belong in the job's calibration settings
(`OcrSettings.calibration`); they are not hard-coded.

### Orientation

| Degradation | Cases | Correct |
|---|---|---|
| clean, 200 dpi, skew ±2°, noise, blur, JPEG 50 | 840 | 840 |
| rotated 90° | 120 | 118 |
| rotated 180° | 120 | 118 |

The 4 misses are two near-empty pages (book 4 p39, 36 characters; book 1 p14, 445
characters), where OSD has too little text and keeps 0°. Book 2 pages 126 and 165 carry
tables printed sideways; OSD turns them to the printed orientation (counted correct). On the
real scans one Greek advertisement page was wrongly turned 180°.

### Downstream (scan vs native of the same pages)

Eight seeded pages per book, preferring pages with tables, lists, columns, an index or
equations; the same pages as a native PDF and as a 300 dpi image-only PDF, both through
`run_book` with production defaults (Tesseract only);
[summary](../experiments/out/step16/downstream/summary.json).

| Book | Order: median Kendall tau / word-order WER | Paragraph starts P / R / F1 | List items matched | Tables native → OCR |
|---|---|---|---|---|
| 1 Spanish US history | 1.0 / 17.6% | 0.61 / 0.92 / **0.73** | 8 of 9 (13 found) | 1 → 0 |
| 2 Immigrant children | 1.0 / 0.6% | 0.98 / 1.00 / **0.99** | 1 of 1 | 3 → 0 |
| 4 Medical anatomy | 0.75 / 86.8% | 0.66 / 0.72 / **0.69** | 20 of 61 (29 found) | 6 → 0 |
| Statistics | 1.0 / 12.2% | 0.94 / 0.82 / **0.87** | 21 of 63 (43 found) | 6 → 0 |

**No OCR text is dropped:** on all four scanned runs every line is owned by exactly one unit
(1,329 lines, 0 unowned, 0 twice) and every one of the 10,703 OCR words lies in a line
([ownership.json](../experiments/out/step16/downstream/ownership.json)).

Running text is fine. Mixed educational layouts over-split paragraphs (boxes and captions
become extra paragraphs). **Tables are lost on scans**: the table stage relies on ruling and
native line evidence and finds none on OCR tokens (TEDS 0); their text becomes paragraphs or
list items and is kept. Book 4's check-box lists lose their markers (low-confidence glyphs).
One sparse table page in books 1 and 4 stayed in `review`: the two layout readers did not
agree it holds text, so nothing on it was OCR'd. It is flagged, not silently dropped.
Equations on scans (Statistics, the same 8 pages): the existing equation stage finds **32
equation regions on the scan against 76 natively** (42%); each goes through the existing
image path (PP-FormulaNet), nothing crashed, and the other math is kept as OCR words in
its paragraphs. Inline math written with ordinary characters is mostly read as
text, which is where most of Statistics' error comes from.

### Time and memory

Measured while other jobs shared the 8-core CPU, so these are upper bounds.

| Reader | Cases | Median s / page | Max s | Median peak memory | Max |
|---|---|---|---|---|---|
| Tesseract (one thread, incl. OSD and deskew) | 1,132 | 23 | 124 | 322 MB | 1,012 MB |
| PP-OCRv5 (detector + recognizer, CPU) | 52 | 300 | 499 | 1,181 MB | 1,568 MB |

A Tesseract page alone takes about 9 s. The no-native-text language choice reads a page with
up to 11 models (about 10× the time of one read).

### Manual check — 20 seeded overlays

[overlays](../experiments/out/step16/benchmark/overlay_previews/) (1,600-pixel previews; full-resolution PNGs and the 1,132 per-case records stay local, rebuildable with `step16_benchmark.py` / `step16_overlays.py`) (words coloured by confidence,
seed 1601, all four books, every degradation type present). On all 20:
- body text is read with high confidence; every rotated page was turned upright;
- low confidence falls where errors are: checkbox and bullet glyphs (book 4), some
  numbered-list markers, math (subscripts such as SS_within, fractions, μ), an accented
  surname in a citation;
- figure areas are blank (masked, never OCR'd);
- printer slug lines and crop-mark text are read as words, as they are in the native text
  (furniture handles them).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **PASS: 1,128 passed** (one cache-closure failure found mid-step and fixed: the OCR scope now covers `document_analysis/language.py`) | [pytest_final.log](../experiments/out/step16/pytest_final.log) |
| 30 source sample pages | **PASS: 0 missing / 0 extra** | [source_gates.log](../experiments/out/step16/final/source_gates.log) |
| Book 1 ledger 495,751 | **PASS** (ledger and final archive) | [full_book.json](../experiments/out/step16/final/full_book.json) |
| Full-book I1–I7 | **PASS: zero on books 1–4**; Statistics I7 = 1 (known) | [after](../experiments/out/step16/final/after/) |
| Every line owned once | **PASS**, every page of the five books | same |
| Byte-identical to Step 15 | **PASS: all five final archives**, file by file | [archive_identity.json](../experiments/out/step16/final/archive_identity.json) |
| Parity development vs production | **PASS**: continuity identical, tables differ on no page, five books | [parity](../experiments/out/step16/final/parity/) |
| 1 vs 2 workers | **PASS**: scanned book byte-identical; OCR repeat identical | [workers](../experiments/out/step16/downstream/workers_immigrant_children.json) |
| Cache closure | **PASS** (cache-key tests, OCR scope included) | tests |
| Ruff | **PASS** (src, tests, Step 16 scripts) | — |
| ENT, mideast, math hold-out | **not run** | — |

## Limitations

1. **Tables on scanned pages are not recovered** (0 of 16 in the downstream set); their text
   is kept as paragraphs or list items, never dropped.
2. **Chinese and Greek are not reliable with Tesseract**; vertical woodblock pages fail with
   every installed model, including the vertical packs.
3. **PP-OCRv5 RTL alternatives are stored in visual order.** For Arabic the second reader's
   alternative text is reversed. It never reaches output (Tesseract's reading is kept), but
   it must be fixed before PP-OCRv5 text is used anywhere.
4. **PP-OCRv5 measurement scope cut:** on the synthetic scans only 6 pages per book, clean
   and 200 dpi (52 cases), because it takes 3–8 minutes per page on CPU. All reader
   comparisons use common cases only. All 24 real scans were read by both readers.
5. **Page-level `must_check` is weak** (2 of 61 bad pages caught).
6. **Sparse scanned pages may stay in `review`** when the two layout readers do not agree the
   area is text.
7. OCR span IDs depend on the cache location: the OCR fingerprint includes the eligibility
   evidence, which names its own file. Moving a cache changes the IDs (the content is
   identical, measured).
8. Deep cache paths can exceed the Windows 260-character limit (the Statistics downstream run
   needed a shorter root). Product caches are shallower; long-path support is not enabled.
9. Real-scan sets are small (2–4 pages per language); the labels describe these pages only.
10. Raster text inside figures is out of scope and not OCR'd (figures are masked); a later
    option.
11. Mean confidence and OSD script confidence are engine scores, not probabilities.
12. Not measured this step: 400 dpi rendering, preprocessing options, and the render-and-
    compare check on born-digital pages.

## Decisions for you

1. **Book 2 cover (p1):** the visual check finds text on the full-page cover image. OCR it,
   or treat covers as figures? Not run; outputs unchanged.
2. **Primary reader per language.** PP-OCRv5 is clearly better on Chinese (4.7% vs 46.7%),
   Greek (27% vs 58%) and Arabic (15% vs 22.5%), equal on English, Spanish and Russian, worse
   on Hindi, and about 20× slower on CPU. Options: (a) keep Tesseract primary everywhere
   (current); (b) make PP-OCRv5 primary for the languages where it measured better, after
   fixing the RTL order (limitation 3) and measuring on more pages; (c) PP-OCRv5 primary only
   when a GPU is present.
3. **Tables on scans:** add a scan table path (for example table-structure recognition on
   the raster with OCR tokens), measured, in a later step?
4. **Page `must_check` signal:** replace mean confidence with the share of `needs_review`
   words, or with equation and table presence, measured first?
5. **OCR fingerprint and cache location** (limitation 7): make the eligibility evidence
   location-independent (a content digest instead of a path)? Changes OCR keys only.
6. **Vertical and historical Chinese print:** accept as unsupported, or evaluate a dedicated
   model later?
7. **Calibration in the default configuration:** write the measured word threshold (0.84)
   into the default OCR settings now, or wait for more real-scan data?
8. **Earlier OCR layers (render mode 3):** none in books 1–4 or Statistics; the compare-only
   path is tested but not measured on real data. Find a sample book?
