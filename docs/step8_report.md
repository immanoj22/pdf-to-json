# Step 8: page furniture and printed page numbers

Each retained line now has a whole-book furniture role: running_head, running_foot, folio,
production_mark, repeated_box or content. A fitted folio sequence gives every physical page a
printed label, a source (printed, metadata, inferred or none) and a confidence. Nothing is
deleted. Furniture lines are read in their own streams (one stream per role) and still count
in the ledger. Repeated boxes stay content.

The Step 4 layouts, the Step 7 builder, the text ledger, the span store and all gold are
unchanged. Old projects were not touched.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **744 passed**, 0 failed / 0 skipped (703 earlier + 41 new) | [JUnit](../experiments/out/step8/pytest.xml), [log](../experiments/out/step8/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** on all 24 | [cross-check](../experiments/out/step8/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; line counts exact; passing | [full_book.json](../experiments/out/step8/full_book.json) |
| I1-I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step8/invariants.json) |
| Every line ordered exactly once, with furniture applied | 24 pages ([report](../experiments/out/step8/furniture_every_line_once.json)), and all lines of the three books (84,085 + 14,396 + 1,231); graph checks: 0 problems | per-book summaries |
| Reading-order metric, book 1 | **not worse**: main flow 0.945681 vs 0.945588; anchors 0.9007 vs 0.8993; no Step 7 stream lost its anchor | [summary](../experiments/out/step8/spanish_us_history/summary.json) |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step8/ruff.log) |

## Part 0 and owner conditions

The following are recorded in [decisions.md](decisions.md):

- The general reference-convention policy.
- Acceptance of the Step 7 rules, with a backlog item for narrow index gutters in Step 4.
- Float anchors stay at their centre until Step 9.
- Unlinked captions stay in the main flow.
- Repeated designed boxes are content, tagged `repeated_box`, and are never dropped by the
  converter.

The Step 8 cache key was accepted on two conditions, and both are met:

1. **The key covers what it must.** [furniture/keys.py](../backend/src/book_core/furniture/keys.py)
   binds these named components:
   - the furniture package, the Step 7 reading-order scope, `settings.py` and the Step 6
     metadata producer;
   - the reading-order producer digest;
   - the layout and order fingerprints;
   - a Step 6 evidence digest (book vocabulary plus native document metadata, which includes
     PDF page labels);
   - the settings digest, the configuration and `FURNITURE_VERSION`.

   The components are stored on each decision as `cache_key_inputs`.
2. **A closure test guards it.** [test_furniture_cache.py](../backend/tests/test_furniture_cache.py)
   fails when the entry points import a module that the scope does not cover. It also fails
   when editing or adding a scope file leaves the digest unchanged, and when changing any one
   of the eight components leaves the key unchanged.

**Backlog (recorded): per-stage cache keys.** Every scope includes `caching.py`, so registering
a new scope re-keys every derived cache. A rebuild needs about 25 GB, and only 18 GB is free.

Current cache disk use (project `.cache`, 35 GB total):

| Folder | Size | Content |
|---|---:|---|
| step7 | 26 GB | analysis 16 GB, native 9.0 GB, layout 172 MB, reading order 116 MB |
| objects | 4.9 GB | object caches used by tests and gates |
| step6b | 2.9 GB | science-book math evidence |
| step5 | 600 MB | alignments (Step 8 reads the recall-proxy causes from here) |
| huggingface | 291 MB | model files |
| step6 | 274 MB | document evidence (Step 8 reads navigation entries from here) |
| step8 | 203 MB | furniture 182 MB (includes superseded development keys), metadata 22 MB |
| pip, pytest, other | about 110 MB | |

During this step, 13 leftover test caches and the Step 7 development cache were deleted (about
1 GB). Disk: 221 GB used, 18 GB free.

## Model and rules (brief)

[furniture/](../backend/src/book_core/furniture/) contains:

- per-line evidence ([features](../backend/src/book_core/furniture/features.py));
- label parsing ([labels](../backend/src/book_core/furniture/labels.py));
- the folio sequence ([sequence](../backend/src/book_core/furniture/sequence.py));
- the whole-book classifier ([classify](../backend/src/book_core/furniture/classify.py));
- page application ([apply](../backend/src/book_core/furniture/apply.py));
- neutral models ([models](../backend/src/book_core/furniture/models.py));
- the cache ([cache](../backend/src/book_core/furniture/cache.py), [keys](../backend/src/book_core/furniture/keys.py)).

The model contains no XML names.

- **Model output:**
  - `LineRole` per line: role, confidence, reasons, group id, evidence and a review flag.
  - `PageMarker` per physical page: label, kind, source, confidence, folio line ids, run,
    metadata label and reasons.
  - `FolioRun` and `FurnitureGroup` for the book.
  - `PageFurniture` holds the roles, the marker and the rebuilt order, plus `furniture_streams`
    (role → stream id). Validators enforce one role per ordered line and role-pure furniture
    streams.
- **Positions:** measured in the content frame along each line's own block axis. Horizontal
  lines use the top and bottom edges; rotated and vertical lines use the side edges. Label
  digits from any Unicode script are accepted. No page number, coordinate, font or book rule
  is used.
- **Folio sequence:** label-like edge lines (arabic, roman, prefixed; overprint repeats such as
  `438438438` are read both as written and as their unit) imply a state of series and offset.
  A Viterbi pass picks one state per page. Staying in a state is free, and switching costs a
  penalty, which handles resets and unnumbered inserts. Candidates are then re-weighted by the
  dominant folio style and refitted.
- **Labels for pages without a printed folio:**
  - Pages between printed folios of one run are interpolated.
  - Up to 2 pages beyond a run are extrapolated, flagged for review.
  - A new run that would restart at 1 inside a gap takes the gap from that page on.
  - An extrapolated label never repeats a printed label of a neighbouring run.
  - PDF page-label metadata is trusted only when it agrees with at least 90% of printed folios
    over at least 5 pages; it then becomes the source for unnumbered pages.
- **Running head and foot slots:** lines that share an edge, a style (colour excluded, since
  feet change colour on dark pages) and a narrow edge depth. A slot needs joint evidence:
  - local coverage of at least 40% (or 40% of one parity);
  - outermost text, not counting folios;
  - whitespace inward;
  - text no larger than 1.25 × body size;
  - at most 12 tokens;
  - side alternation by parity, or constant text, as a bonus.

  Lines inside figures, tables, credits or cards never found a slot. Edge map labels stay
  content.
- **Production marks:** text whose centre lies outside the TrimBox, or tiny repeated edge text
  with a file-name or date shape.
- **Repeated boxes:** constant digit-masked text on 3 or more pages with more than 12 tokens.
  Content, tagged.
- **Low confidence:** furniture with confidence below 0.6 stays content and is flagged.
- **Application:** regions are re-typed in a view; the cached Step 4 layout is never modified.
  The unchanged Step 7 builder re-orders 248 book-1 pages, and the other pages keep their
  cached Step 7 order. Content lines that Step 4 took for furniture rejoin the block they
  continue (an adjacent block within 1.5 font sizes) or the text region of their lane (within
  3 font sizes). Repeated boxes become sidebar floats.

## Evaluation (per book, no overall score)

Book 1 is the development book. Books 2 and 3 are hold-outs: the producer was frozen at
`a5d57582…`, and each hold-out ran once
([log](../experiments/out/step8/holdout_runs.jsonl)). Nothing was tuned after those runs. Book 3
remains anecdotal, and its page markers are excluded from gates.

| | Book 1 (development) | Book 2 (hold-out, once) | Book 3 (hold-out, anecdotal) |
|---|---:|---:|---:|
| Lines: content / repeated_box | 77,664 / 141 | 13,669 / 117 | 1,215 / 0 |
| Lines: folio / running_head / running_foot | 695 / 52 / 246 | 312 / 295 / 3 | 9 / 7 / 0 |
| Lines: production_mark | 5,287 (all outside the TrimBox; 0 retained tokens) | 0 | 0 |
| **Page-marker label accuracy** | **1.000** (751 / 751) | **0.990** (291 / 294) | excluded |
| **Placement accuracy** | **1.000** | **0.990** | excluded |
| Gold markers not scored | 7 non-label placeholders (front, special) | 15 unplaced in gold | 9 excluded |
| Marker sources | printed 709, inferred 46, none 3 | printed 312, metadata 19 | printed 9 |
| **Furniture precision proxy** (tokens not aligned to reference units) | **0.989** (2,222 tokens, 24 aligned) | 0.981 (1,318 tokens, 24 aligned) | 0.936 (47 tokens, 3 aligned) |
| Folio / running head / running foot precision | 1.000 / 0.956 / 0.991 | 0.949 / 0.995 / 0.0 (3 tokens) | 0.667 / 1.0 / – |
| Flagged lines / flagged markers | 0 / 2 | 0 / 0 | 0 / 0 |
| Main-flow pairwise, Step 7 → Step 8 | 0.945588 → **0.945681** | 0.968030 → **0.972635** | 0.990615 → 0.990615 |
| Float anchors, Step 7 → Step 8 | 0.8993 (1,509) → **0.9007** (1,641) | 0.375 → 0.375 (16) | 0 → 0 (1) |
| Within-float pairwise, Step 7 → Step 8 | 0.92116 → 0.92177 | 0.7448 → 0.7448 | 1.0 → 1.0 |

The book 1 reading-order details:

- **Kendall tau:** 0.891176 → 0.891362. Perfect pages are unchanged at 584.
- **No Step 7 float stream lost its anchor.** The 11 new anchor misses all belong to the 137 new
  CONÉCTATE sidebar floats (126 correct, 0.92).
- **More main units:** 14,157 → 14,255. These are content lines that Step 4 had put in the
  furniture stream.

### Folio sequence summary

| Book | Run | Pages | Labels | Printed | Inferred pages |
|---|---|---|---|---:|---|
| 1 | roman | 5–24 | iii–xxii | 11 | 3, 4 (before the run), and even pages 6–22 (unnumbered versos) |
| 1 | arabic, offset 24 | 25–719 | 1–695 | 662 | 26, 27, 112, 113, 176, 177, 216, 217, 258, 259, 300, 301, 352, 353, 392, 393, 430, 431, 470, 471, 502, 503, 540, 541, 582, 583 (unit openers); 652–664 even (atlas); 720, 721 (extrapolated, review) |
| 1 | prefixed "HT", offset 722 | 723–758 | HT1–HT36 | 36 | none |
| 1 | no label | 1, 2, 722 | | | covers and the page before the HT block |
| 2 | arabic, offset 11 | 12–330 | 1–319 | 312 | none; 19 pages labelled from trusted metadata (front matter 1–11 and 17, 61, 109, 203, 223, 249, 307, 331) |
| 3 | arabic, offset −279 | 1–9 | 280–288 | 9 | none |

- **Book 1:** has no PDF page labels. The HT block (PDF pages 723–758), which the reference
  moves after page xxii, is placed correctly.
- **Book 2:** its metadata agrees with all 312 printed folios. The roman front-matter folios
  did not form a printed run, so pages 1–11 carry metadata labels.
- **Book 2 marker misses, 3:**
  - Gold places "i" on p5; our p5 label is "iv". Gold markers on blank front pages are
    unreliable (Step 5).
  - Gold places 146 and 147 on p158 and p159. The printed folios read 147 and 148, and the
    metadata agrees with the printed folios, so these look like a one-page shift in gold
    placement.

### TOC target resolution

| Book | Printed TOC entries | Resolved before (PDF labels) | Resolved after (page markers) | Title + target correct, before → after |
|---|---:|---:|---:|---|
| 1 | 1,790 | 0 | **1,645** (145 unresolved) | 0 → **117** of 126 title matches (0.929) |
| 2 | 1,245 | 1,244 | 1,244, all agree with before | 6 → 6 |
| 3 | 0 | – | – | – |

The 145 unresolved book-1 entries cite labels that no page carries, mostly index-style numbers
from the Step 6 geometry-only TOC candidates.

### Top false-furniture groups (furniture tokens aligned to reference units)

| Book | Role | Tokens | Reference kinds | Example (page) | Reading |
|---|---|---:|---|---|---|
| 1 | running_head | 13 | list_item 11, definition 2 | `anualidad • baby boom` (667) | Guide words repeat the first and last entry; the aligner matched some duplicates to the head |
| 1 | running_foot | 10 | paragraph 6, image_description 4 | `Tabla de contenido` slot (29, 105, 183, 251, 479, 653, 659) | Chapter feet whose words the reference also contains nearby |
| 1 | running_foot | 1 | caption | `Las herramientas del historiador HT3` (757) | Same |
| 2 | folio | 16 | other 16 | folio on chapter openers (18, 38, 62, …) | Matched to reference label elements, not body text |
| 2 | running_head | 5 | paragraph 4, other 1 | `Contents` (13, 66, …) | Duplicate words |
| 2 | running_foot | 3 | other 3 | `v` (6, 8, 10) | Roman front-matter folios read as a foot slot (see limitations) |
| 3 | folio | 3 | other 3 | `280` (1, 5, 6) | Matched to index labels |

### Recall proxy (aligner diagnostics, never a gate)

| Book | folio_candidate tokens → classified furniture | furniture_candidate tokens → classified furniture |
|---|---|---|
| 1 | 2,642 → 747 (the other 1,895 are mainly numbers in indexes, tables and lists) | 3,937 → 1,139 (2,397 of the rest are the CONÉCTATE box, kept as content) |
| 2 | 322 → 275 | 1,013 → 973 |
| 3 | 6 → 6 | 36 → 36 |

As found in Step 5, the aligner's folio cause over-reports: it labels any single-number token.

### Repeated boxes

- **Book 1:** CONÉCTATE, 141 lines on 141 pages (8–743). In the order: 132 sidebar floats, 8 in
  notes, 1 in the main flow. None are in a furniture stream, so it stays content.
- **Book 2:** one false tag. A bibliography entry repeated on 3 pages is tagged repeated_box,
  but it remains content in the main flow.
- **Book 3:** none.

## Regression targets

| Target | Result |
|---|---|
| Book 2 p124: table numbers are not folios | Pass: number-only table cells are content |
| Book 1 glossary and index guide words (`casa de vecindad • conservadurismo dinámico`, `ejecuciones hipotecarias • …`) | Pass: running_head, in the furniture stream |
| Book 1 index entry Step 4 took for furniture (`entente cordiale, 167`) | Pass: content, in the main flow |
| Book 1 slug lines | Pass: production_mark |
| CONÉCTATE | Pass: repeated_box, never in a furniture stream |
| Synthetic | Pass: odd and even heads with alternating sides; roman then arabic folios; a reset to 1; a blank page; a missing folio; a number-only table cell; a map label at the top edge (in a figure); a right-to-left page; metadata trusted only on agreement; no duplicate inferred labels; a repeated box re-typed as content; low-confidence evidence kept as content |

Real-book targets are in [test_furniture_books.py](../backend/tests/test_furniture_books.py).
They read the cached decisions of the single runs, so they never start a new hold-out run.
Synthetic targets are in [test_furniture.py](../backend/tests/test_furniture.py).

## Overlays

The overlays show each furniture class as a filled colour with a tag: RH, RF, F=label, PM and
RB. Flagged lines get a red frame. A banner shows the page marker. All six were inspected
visually. [Index](../experiments/out/step8/overlays/overlays.json).

| Page | What it shows | Marker |
|---|---|---|
| [p669](../experiments/out/step8/overlays/furniture_p669.png) | Glossary: guide-word head, `Glosario/Glossary` foot, folio, slug lines | 645, printed, 0.99 |
| [p696](../experiments/out/step8/overlays/furniture_p696.png) | Index: guide-word head, folio; `entente cordiale, 167` back in the text | 672, printed, 0.99 |
| [p25](../experiments/out/step8/overlays/furniture_p25.png) | Chapter opener: folio 1 starts the arabic run; CONÉCTATE as a repeated box | 1, printed, 0.99 |
| [p662](../experiments/out/step8/overlays/furniture_p662.png) | Atlas map: edge map labels (`PRIMER MERIDIANO`) stay content | 638, inferred, 0.85 |
| [p279](../experiments/out/step8/overlays/furniture_p279.png) | Unseen: running foot, folio | 255, printed, 0.99 |
| [p437](../experiments/out/step8/overlays/furniture_p437.png) | Unseen: running foot, folio; vertical photo credit stays content | 413, printed, 0.99 |

The unseen pages are a seeded draw (seed 8) from printed-folio pages never inspected during
development.

## Limitations

1. **Book 2 front matter (hold-out, not tuned).** Its roman folios formed no printed run, so
   their labels come from trusted metadata. Three `v`-style folios were classified as a
   running-foot slot instead of folios.
2. **Repeated-box rule.** Book 2 has one false repeated_box tag (a repeated bibliography entry).
   The tag is harmless to order and retention, but the rule uses only repetition and length,
   with no box geometry.
3. **Guide-word heads.** These overlap index and glossary entry text, and the aligner sometimes
   matches the duplicate to the head (13 tokens in book 1).
4. **Credit-shaped vertical text** at page edges is excluded from slots because Step 7 typed it
   as a credit. A real rotated running head inside a credit-typed region would be missed.
5. **Rotated and vertical furniture** and right-to-left books are tested on synthetic pages
   only; all three books are horizontal left-to-right.
6. **Inferred labels.** Book 1 pages 720–721 are extrapolated beyond the arabic run (flagged
   for review). The reference gives them no label.
7. **Confidence** values are rule heuristics, not calibrated probabilities.
8. **Disk.** The furniture cache keeps superseded development entries (about 150 MB), which
   have no automatic clean-up.

## Decisions for you

1. **Repeated boxes in the order.** CONÉCTATE is now a sidebar float (anchored about 0.92
   correct). The alternative, reading it in place in the main flow, breaks credit anchors
   (0.43 vs 0.95 on the affected pages). Keep it as a sidebar float?
2. **Front-matter folios on hold-out book 2** came from trusted metadata. Should the
   folio-run threshold (a minimum of 2 printed folios and a switch penalty of 2.5) be revisited
   on development data in a later step, or is metadata acceptable where it is trusted?
3. **Book 2 gold page markers 146/147** look shifted by one page against both the printed
   folios and the metadata. Should a logged label fix to the derived gold be made, or should
   it stay as is?
4. **Repeated-box evidence.** Should repeated_box additionally require box geometry (a fill or
   frame behind the text) to avoid tagging repeated prose such as citations?

## Reproduce

From the project root:

- `python experiments/step8_run.py --book spanish_us_history`
- Hold-outs, once each: `python experiments/step8_run.py --book <book> --holdout --reason "…"`
- `python experiments/step8_overlays.py`
- `python experiments/step8_gates.py`

Pytest and Ruff run from `backend/`. Caches are in `.cache/step8`. The script reuses the
`.cache/step7` layouts and orders.

**Step 8 stops here for owner review. Step 9 has not started.**
