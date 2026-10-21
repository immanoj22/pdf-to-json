# Step 14a — tables: detection and structure

Status: **complete for review.** Step 14b (cell content, captions and notes, model output)
has not started. A new `tables` stage finds table regions from combined evidence, reads each
table's grid (rows, columns, spanning cells, header rows) over line and span ids, and marks
tables continued across pages. Following your instruction during the step, **only tables with
strong evidence take their text** (two learned detectors agree and the geometry is tabular);
weaker candidates are recorded as *possible table, review* and leave their lines in their
units. Earlier stages, the ledger and the lists-stage units are unchanged; the final archive
publishes the table records and a unit view in which text-owning tables hold their lines.

Main results (text-owning tables, final runs):

| Book | Reference segments | Tables | Detection P / R | TEDS (structure) | Cell adjacency F1 | Header rows exact | Paragraph F1 before → after |
|---|---:|---:|---|---:|---:|---:|---|
| 1 Spanish US history | 71 | 52 | **0.885 / 0.648** | 0.80 | 0.84 | 0.89 | 0.9428 → 0.9417 (explained, below) |
| 2 Immigrant children | 12 | 12 | **1.0 / 1.0** | 0.94 | 0.85 | 1.0 | 0.8540 → 0.8546 |
| 3 Art-therapy index | 0 | 1 | — (1 false table) | — | — | — | no paragraph gold |
| 4 Medical anatomy | 94 | 85 | **0.988 / 0.894** | 0.94 | 0.96 | 0.64 | **0.818 → 0.901** |
| Statistics | 537 | 501 | **0.898 / 0.838** | 0.94 | 0.97 | 0.82 | (no paragraph gold) |

Book 4's paragraph boundary recall rises from 0.794 to 0.934 and exact paragraph units from
0.48 to 0.76. Cell order inside reference tables: book 2 **0.75 → 0.99**, book 4 0.87 →
0.9999, book 1 0.87 → 0.999, Statistics 0.99 → 0.9997. A seeded manual check of 30 tables
found 29 real tables, 27 with fully correct structure.

## Scope and baseline

HEAD at start: `14bdaf4` (Step 13c and its gate decisions in; the tracked tree was clean,
the untracked `.vscode/`, one Step 11d output and the Step 13c development files were left
untouched). Baseline: the Step 13c final capture, frozen into
[step14a/before](../experiments/out/step14a/before/). Only books 1–4 and Statistics were run;
ENT, mideast, the mismatched pair and the math hold-out were not. Gold, reference XML, the
ledger and old projects were not edited; new table gold was added in its own folder.

## Part 0

**13c fix.** Text-set equations whose output is their original text, read by the text path
alone, get no review status (`review_status: null`); their own check failures stay flags.
No chosen MathML, LaTeX or output changed in any book
([check](../experiments/out/step14a/final/mathml_13c_fix.json)):

| Book | Records | needs_review → none | must_check → none | needs_review / must_check now |
|---|---:|---:|---:|---|
| Statistics | 6,039 | 3,844 | 106 | **567 / 145** (was 4,411 / 251) |
| 2 Immigrant children | 182 | 120 | 13 | 20 / 4 (was 140 / 17) |
| 4 Medical anatomy | 3 | 2 | 1 | 0 / 0 |
| 1 Spanish US history | 2 | — | — | 0 / 2 (unchanged) |

The 106 + 13 + 1 text-set records that were `must_check` only through their own checks
(mostly brackets cut by a region boundary) keep those check flags and no longer get an image
fallback (their output is their PDF text).

**Frameworks** ([dependencies.md](dependencies.md#step-14a-table-frameworks)): Table
Transformer detection and structure (MIT code and weights), TableFormer accurate/fast (MIT
code; CDLA-Permissive-2.0 + Apache-2.0 weights), Heron and PP-DocLayoutV3 (as before),
pdfplumber 0.11.10 and Camelot 2.0.0 (MIT, comparison only, new `table-comparison` extra).
Camelot runs with the pdfium image backend and no fallback; the Ghostscript backend (AGPL)
is never installed or used. All run on CPython 3.14.8. The `models` extra gains `timm`
(Apache-2.0), which the Table Transformer checkpoints need. Weight revisions and SHA-256 are
recorded.

## Task 1 — table gold and today's measurements

**Gold** ([`backend/tests/gold_derived_tables/`](../backend/tests/gold_derived_tables/),
`human_approved: false`; reader `evaluation/table_gold.py`, vocabulary in the data file
`reference_dialects/table_dialects.json`, driver `step14a_gold.py`): the reference grid (rows
in order, cells placed by column names or the first free column, spans from `colspan` /
`rowspan` / start–end column names / `morerows`, header rows from head rows or header-cell
rows, foot rows as notes) located through tokens already aligned to the PDF — the derived-gold
units for books 1–4, the Step 13a alignment for Statistics. Strays (a page holding under 5% of
a table's tokens) are dropped.

| Book | Tables | Located | Multi-page | Cells (with tokens) | Spanning cells | Header rows | Titles (located) | Notes (located) | Reference cell tokens aligned |
|---|---:|---:|---:|---|---:|---:|---|---|---|
| 1 | 71 | 71 | 0 | 1,196 (644) | 52 | 60 | 4 (4) | 2 (2) | 2,917 / 2,913 |
| 2 | 12 | 12 | 0 | 1,164 (840) | 43 | 12 | 12 (12) | 10 (10) | 1,531 / 1,558 |
| 3 | 0 | — | — | — | — | — | — | — | — |
| 4 | 68 | 68 | 16 | 2,587 (2,517) | 53 | 56 | 54 (49) | 0 | 13,678 / 17,756 |
| Statistics | 478 | 463 | 69 | 12,532 (10,206; 185 math only) | 17 | 420 | 102 (53) | 0 | 16,774 / 17,908 |

Three reference tables have markup that does not describe a grid (overlapping cells); they
are kept, flagged and left out of structure scoring
([backlog](gold_review_backlog.md#table-gold-step-14a)). Book 1's many empty cells are real:
its reference keeps organizer tables with blank answer cells.

**Measured before any change** ([measure/before](../experiments/out/step14a/measure/before/)):

| Book | Reference cell tokens in a table region | Landing (top unit kinds) | Cell-boundary pairs tp / fp / **fn** | Cell order in one stream | Figures overlapping a table |
|---|---:|---|---|---:|---:|
| 1 | 84% | table_text 2,451, paragraph 229, figure_text 155, caption 75 | 43 / 0 / 18 | 0.875 | 8 |
| 2 | 76% | table_text 1,170, paragraph 240, list_item 120 | 38 / 10 / 2 | **0.7495** | 0 |
| 4 | **28%** | paragraph 6,085, table_text 3,864, list_item 3,055, caption 509 | 1,688 / 98 / **1,200** | 0.869 | 36 |
| Statistics | 76% | table_text 12,748, figure_text 2,238, paragraph 813, heading 567 | — | 0.989 | 961 (incl. table pieces) |

This confirms the expected failures: book 4's ~1,200 lost cell boundaries (the ~1,253 of Step
11b), book 2's table order 0.745, figures over tables (book 1 p447 organizer, Statistics
table rules drawn as figures), and 306 Statistics display equations with 0.7 anchors (103
inside reference tables). Top failure classes: undetected light ruled grids (book 4: only the
header row of p16 was a table region), whole cells and lists split into paragraph units, and
rotated tables read row-major line by line.

## What changed

A new stage `book_core.tables` after MathML, its cache scope (`tables`, plus `table_models`
for the model adapters), the final archive view, and the runner. No earlier stage, unit,
order, span or ledger changes.

| Module | Role |
|---|---|
| `rulings.py` | Rules and fills from native drawings: stroked lines and rectangle edges, thin filled rectangles, fills and their edges; white cells count only over a coloured fill; panel fills (a fill around other drawings' fills) and page decoration (rules reaching the content edge) are not structure; free-form strokes (curves, slanted lines) recorded |
| `evidence.py` | One page's evidence: lines, spans, units and streams, rules, fills, Step 4 table regions, final figures, equation records, the detectors' table boxes, the structure stage's navigation kind |
| `detect.py` | Candidates (rule grids, stacks of parallel rules, Step 4 regions, model boxes) merged where they cover each other; look-alike tests |
| `grid.py` | Rows, columns, spans and header rows in the table's reading frame |
| `page.py` | The decision per candidate (families, look-alikes, strong vs possible) |
| `records.py` | Records: cells over line ids and span ranges, cell content units, equations and figures in cells, table pieces, anchors, continuation |
| `recognizers.py`, `detectors.py` | Table Transformer detection (cached like the layout models), structure models for comparison, a per-image reading cache |
| `view.py` | The final unit view; ownership check; figures without table pieces |

### Task 2 — detection

Evidence families (never one alone): **rules** (a connected network of horizontal and
vertical rules enclosing at least 2 × 2 cells *that hold text*, or a stack of at least three
parallel rules of one width for unboxed tables, or a Step 4 ruled region), **alignment**
(text gaps forming at least two columns over two rows in the frame, text in the grid's own
cells, or a Step 4 aligned region), **models** (Heron, PP-DocLayoutV3, Table Transformer table
boxes; beside aligned text alone two must agree). A candidate needs two families.

Look-alikes are rejected with a reason and kept for review:

| Class | Rule (general evidence) |
|---|---|
| Graphic organizer | separate boxes that share no border |
| Figure panel | a raster image fills most of the region, or most lines are figure labels over an image, or free-form strokes (map outlines, diagrams) fill it |
| Timeline | one axis with short ticks |
| Multi-column text | mostly running body text without a ruled grid; labels beside running body text (dialogue) |
| Lists in columns | ≥ 90% bulleted list items (numbered answer grids stay tables) |
| Index / contents | aligned text on a printed navigation page, or mostly entry units |

**Text ownership (your instruction).** A candidate takes its text only when two detectors
agree and its geometry is tabular (ruled grid with text in its cells, unboxed table rules,
or text aligned in columns). On a printed navigation page it is at most a possible table.
Measured before choosing: every reference-matched table in the four scored books has at least
one model supporting it; requiring two keeps 46 of 47 book 1 matches and removes 19 of 25 of
its false tables.

Rotation: the frame is the right-angle rotation shared by 60% of the region's characters; the
grid is read in that frame. Six of book 2's twelve tables are rotated; all twelve are detected.

**Detection per book and per source**
([dev/final](../experiments/out/step14a/dev/final/),
[methods/final](../experiments/out/step14a/methods/final/)) — precision / recall of each
source alone (a source region holds the tokens whose box centre lies inside it):

| Book | **Combined (text-owning)** | Heron | PP-DocLayoutV3 | Table Transformer | Ruled grids | Rule stacks | Step 4 regions |
|---|---|---|---|---|---|---|---|
| 1 Spanish US history | **0.885 / 0.648** (52) | 0.16 / 0.80 (352) | 0.07 / 0.82 (839) | 0.07 / 0.72 (725) | 0.07 / 0.85 (811) | 0.01 / 0.01 (105) | 0.65 / 0.79 (86) |
| 2 Immigrant children | **1.000 / 1.000** (12) | 0.55 / 1.00 (22) | 1.00 / 1.00 (12) | 0.03 / 1.00 (369) | — | 1.00 / 1.00 (12) | 0.91 / 0.83 (11) |
| 4 Medical anatomy | **0.988 / 0.894** (85) | 0.93 / 0.81 (82) | 0.99 / 0.86 (82) | 0.36 / 0.91 (242) | 0.54 / 0.87 (153) | 0.00 / 0.00 (44) | 0.70 / 0.46 (61) |
| Statistics | **0.898 / 0.838** (501) | 0.89 / 0.82 (494) | 0.90 / 0.89 (530) | 0.53 / 0.69 (693) | 0.59 / 0.89 (813) | 0.00 / 0.00 (156) | 0.84 / 0.81 (518) |

A source alone counts each of its regions as a table (score ≥ 0.5 for models); the
parentheses give the number of regions. No source alone is good on every book:
PP-DocLayoutV3 alone is as good as the combination on books 2, 4 and Statistics (on Statistics
its recall is higher, 0.89 vs 0.84) but finds 839 regions in book 1 (precision 0.07); Heron
and Table Transformer also find panels and boxes; Step 4 regions and stacks are incomplete.
The combination is the only setup that stays precise on all four books.

Possible tables (own nothing; for review): book 1 35 (4 match a reference table), book 4 8
(2), Statistics 26 (16).

**False tables, book 1** (classes before the final rules, with counts; examples are
[rendered](../experiments/out/step14a/false_tables/): `b1_*` and `c1_645` single pages, the three
sheets the 29 text-owning false tables left after the figure-panel and navigation rules, before
the two-detector rule):

| Class | Count (approx., of the 79 false tables of the first rules) | Examples (PDF page) | Final |
|---|---:|---|---|
| Map or chart panels in ruled bands (title band, map/chart, question band) | ~44 | 29, 104, 137, 179, 238, 589, 754 | figure-panel rule, then two-detector ownership: all removed |
| Vector maps (state outlines forming a grid) | 2 | 645 | free-form strokes: removed |
| Printed glossary pages (ruled three columns) | 8 | 668–684 | navigation-page rule: possible tables |
| Reading organizers and strategy boxes | ~6 | 145, 389, 409, 519, 739 | two-detector ownership: possible or removed |
| Question callouts | 2 | 36, 110 | removed |
| Remaining text-owning false tables | **6** | 14 (contents box), 145 (reading-strategy organizer), 347 (timeline panel), 389 (perspectives organizer), 684 (last glossary page, not marked navigation by the structure stage), 754 (chart panel beside a data table) | **open** |

Book 3's one table (PDF p3) is an index page the structure stage did not mark as navigation
(it marked pages 1–2 and 6–9); 159 index lines are held by it.

### Task 3 — structure

In the table's frame:

- **Columns**: interior vertical rules covering most of the table height; text gaps that no
  band crosses (one spanning band may cross when there are four or more), wider than a word
  space; inside a ruled column a gap counts only with text on both sides of it. A column of
  list markers only is not a column.
- **Rows**: text bands. Rows are ruled when rules part the bands densely, or when a boxed
  grid (vertical rules) has any full interior rule — then the bands between rules are
  multi-line cells (a lattice). Otherwise every band is a row except a wrapped cell line (no
  text in the first column, close below, only in columns already filled).
- **Spans**: text crossing a column boundary spans those columns; in ruled tables a rule
  segment missing inside a row (column) merges the cells it would separate; a merged area cut
  by another stays single cells (every grid position belongs to exactly one cell).
- **Header rows**: a header fill the body does not share; in an unboxed table, the first
  full-width rule below the top rows (partial rules under group headings stay inside the
  header); else top rows in a style the body does not use.
- **Cells** hold whole lines (`line_ids`) and, where one PDF line carries several cells, span
  ranges (`span_refs`; a span crossing a column boundary is split at the whitespace nearest
  it, character positions estimated by an even share, flagged). Lists-stage units lying wholly
  in a cell are kept as the cell's content (`unit_ids`) — list items in cells stay items.
  Display equation units inside a cell are read in that cell (Statistics: 115 units; of the
  306 display units with 0.7 anchors, 103 lay in reference tables). A figure inside the table made only of the table's rule and
  fill drawings is a **table piece** (absorbed, not exported; Statistics 1,049, book 4 1); a
  real figure inside a cell is read in that cell (book 4: 38).
- **Continuation**: the last table of a page and the first of the next, in the same frame,
  near the content edges, with matching column proportions, are marked `continues_to` /
  `continues_from` (never joined): book 4 25, Statistics 64.

**Structure methods compared on the same detected regions**
([methods/final](../experiments/out/step14a/methods/final/)): structure-only TEDS / cell
adjacency F1 / header rows exact.

| Book | **Our geometry** | TableFormer (accurate) | Table Transformer structure | pdfplumber | Camelot (pdfium) |
|---|---|---|---|---|---|
| 1 Spanish US history | **0.790 / 0.835 / 0.86 (50)** | 0.891 / 0.935 / 0.80 (50) | 0.739 / 0.868 / 0.74 (50) | 0.827 / 0.790 / 0.10 (50) | 0.485 / 0.475 / 0.10 (50) |
| 2 Immigrant children | **0.939 / 0.854 / 1.00 (11)** | 0.883 / 0.866 / 0.91 (11) | 0.863 / 0.779 / 0.91 (11) | 0.424 / 0.148 / 0.00 (11) | 0.906 / 0.481 / 0.00 (6) |
| 4 Medical anatomy | **0.937 / 0.959 / 0.64 (83)** | 0.923 / 0.949 / 0.63 (83) | 0.770 / 0.887 / 0.60 (81) | 0.947 / 0.968 / 0.33 (80) | 0.559 / 0.905 / 0.35 (83) |
| Statistics | **0.941 / 0.971 / 0.82 (466)** | 0.939 / 0.950 / 0.83 (466) | 0.903 / 0.964 / 0.77 (465) | 0.946 / 0.971 / 0.21 (466) | 0.385 / 0.492 / 0.21 (466) |

Cells: TEDS / adjacency F1 / header rows exact (tables scored). Same detected regions for every method (our text-owning and possible tables that match a reference segment). Time per table on CPU: TableFormer ~1.6–8 s, Table Transformer ~0.5 s, pdfplumber ~0.05 s, Camelot ~0.5 s (readings cached).

Decision (measured): **our geometry** in production. It is best or within 0.01 TEDS of the
best on books 2, 4 and Statistics (pdfplumber is 0.006–0.010 higher on the ruled grids of book 4
and Statistics, but gets header rows right on only 0.21–0.33 of tables; our geometry reads
ruled grids as a lattice as pdfplumber does and unruled tables from text gaps, where
pdfplumber fails: book 2 0.42). **Book 1 is the exception: TableFormer reads its tables
clearly better** (TEDS 0.891 vs 0.790, adjacency 0.935 vs 0.835), mainly sidebar and
organizer tables whose cells hold bulleted lists and empty answer cells, where our row and
span reading is weakest. TableFormer is not combined into production in 14a: it costs
~2–8 s per table on CPU and it is only better on one book; a measured combination (for
example TableFormer where our grid's evidence is weak) is a decision below. Table
Transformer structure is weaker everywhere; Camelot finds the regions but splits them.
Table Transformer *detection* is used in production.

## Task 4 — evaluation

### Effect on units (final view vs the lists-stage units)

[effect](../experiments/out/step14a/final/effect/). Page by page, every boundary change is on a
page with a table (`boundary_changes_without_a_table: []` in every book).

| Book | Tables | Lines moved into tables (from unit kind) | Paragraph boundary P / R / F1 | Exact units | Cell order in reference tables |
|---|---:|---|---|---|---|
| 1 | 52 | table_text 830, paragraph 59, list_item 44, figure_text 18, heading 8, caption 2 | 0.918 / 0.968 / 0.9428 → 0.916 / 0.969 / **0.9417** | 0.8949 → 0.8941 | 0.875 → **0.9987** |
| 2 | 12 | table_text 878, paragraph 67, list_item 63 | 0.785 / 0.937 / 0.8540 → 0.786 / 0.937 / **0.8546** | 0.680 → 0.680 | 0.7495 → **0.9946** |
| 3 | 1 | paragraph 159 | — | — | — |
| 4 | 85 | paragraph 2,010, table_text 1,244, list_item 673, caption 90, figure_text 82, heading 15 | 0.843 / 0.794 / 0.818 → 0.871 / **0.934** / **0.901** | **0.482 → 0.765** | 0.869 → **0.9999** |
| Statistics | 501 | table_text 8,505, figure_text 1,307, paragraph 318, caption 109, heading 97 | (no paragraph gold) | — | 0.989 → **0.9997** |

Reference table text held by table cells after: book 4 13,345 of 13,678 tokens (98%; was 28%
in table regions), book 2 1,529 of 1,531, Statistics 16,343 of 16,774 (97%), book 1 2,063 of
2,917 (71%; the rest is in tables we do not own: possible tables and misses).

**Book 1 explained, page by page** (boundary tp / fp / fn change): the small net loss (F1
−0.0011) is three false tables taking text — p347 timeline panel (−1 / +15 / +1), p684
unmarked glossary page (+12 / +25 / −12), p14 contents box (0 / +4 / 0) — plus real tables
whose cells the reference draws differently (p35 −2/0/+2, p743 and p754 −1/0/+1) and gains
(p295 +2/0/−2; p145 and p389 one extra boundary each). Before your two-detector rule and the
navigation fix, book 1 lost 0.012 F1 to 618 glossary lines taken into tables.

### Manual check (30 tables, seeded)

Seed 1414 over the 651 text-owning tables of the five books
([verdicts](../experiments/out/step14a/manual/verdicts.json),
[crops](../experiments/out/step14a/manual/check/)): **29 real tables**; structure fully
correct on **27**. Wrong: book 1 p14 is a contents box (false table); book 4 p15 section rows
("Topic: …") span two of five columns instead of all; book 1 p35 takes the panel's title
paragraph and question band as rows. Statistics 20/20, book 4 5/6, book 1 2/4 fully correct.

### Overlays (8 tables, seeded)

Seed 1415, constrained to include a rotated table, merged cells and a table without ruled
columns ([overlays](../experiments/out/step14a/overlays/), grid red, header cells purple,
spanning cells thick, reference box green):
[book 2 p151, rotated APA table with spanning group headers](../experiments/out/step14a/overlays/table_immigrant_children_p151_1.png)
(two narrow right-hand columns read as one: 9 of 11 columns),
[Statistics p307, merged title row](../experiments/out/step14a/overlays/table_statistics_p307_2.png),
[book 4 p16, competency table: text columns with ruled rows and section rows](../experiments/out/step14a/overlays/table_medical_anatomy_p16_3.png),
[Statistics p713](../experiments/out/step14a/overlays/table_statistics_p713_4.png),
[p575](../experiments/out/step14a/overlays/table_statistics_p575_5.png),
[p702](../experiments/out/step14a/overlays/table_statistics_p702_6.png),
[p254](../experiments/out/step14a/overlays/table_statistics_p254_7.png),
[p141](../experiments/out/step14a/overlays/table_statistics_p141_8.png).

### Time and memory (one worker, CPU; detections cached)

| Book | Tables stage | Peak memory of the stage | Whole run | Peak memory of the run |
|---|---:|---:|---:|---:|
| 1 | 39 min | 10.8 GB | 59 min | 11.7 GB |
| 2 | 14 min | 1.2 GB | 27 min | 1.2 GB |
| 3 | 8 s | 0.2 GB | 2 min | 0.2 GB |
| 4 | 4 min | 1.1 GB | 8 min | 1.1 GB |
| Statistics | 11 min | 0.9 GB | 19 min | 0.9 GB |

The stage reads each page's object analysis and renders it for the cached detector lookups
(book 1's dense vector pages drive its memory). Table Transformer detection, computed once
and cached: 0.8–1.5 s per page (book 1 1.5 s, Statistics 0.8 s), 43 min for all five books
on this CPU.

## Task 5 — tests

`backend/tests/test_tables.py` (16): ruled grid with a spanning header cell; unboxed table
with header rule and one PDF span split between two cells; rotated table read in its frame;
graphic organizer rejected; continuation marked, never joined; **no text lost** (every line
in exactly one final unit or one table, split spans covered exactly once per character);
without model evidence every table is a possible table and takes no text; one detector is not
enough; **1 vs 2 workers and production give identical archives**; **cache closure** (the
`tables` and `table_models` scopes cover their imports; a missing `tables` dependency of
`final` is detected); collinear rules merge only when they meet; gold grid spans and header
rows; TEDS (Zhang–Shasha reference example), adjacency; the unit view cutting units around
table lines. Updated: the 13c text-set review test, the figure tests' warning lists (the
table stage warns without models), the disk-need test's stage layout, the test fixture that
disables real models.

Development safeguards added after two run failures: a pre-run sweep that builds and
validates the records of every page of every book (`step14a_sweep.py`), and a parity check
that the stage's own evidence decides exactly as the development bundles
(`step14a_parity.py`: identical on all pages with a table in all five books).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **1,042 passed, 0 failed** (after the final runs) | [pytest.xml](../experiments/out/step14a/final/pytest.xml) |
| Six-pages-per-book sample + Statistics sample | PASS: 0 missing / 0 extra on 30 pages | [source crosscheck](../experiments/out/step14a/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step14a/final/full_book.json) |
| Full-book I1–I7 on books 1–4 | PASS: all zero on 1,412 pages | `final/after/*_full_gates.json` |
| Every line owned once (five books) | PASS: lists units owned and ordered once on 2,283 pages; final view + tables own every line once, split spans covered once | proofs, [final_outputs.json](../experiments/out/step14a/final/final_outputs.json) |
| Books 1–2 not worse beyond explained changes | PASS: book 2 0.8540 → 0.8546; book 1 −0.0011 F1, explained page by page above | [effect](../experiments/out/step14a/final/effect/) |
| Earlier stages unchanged (books 1–4) | PASS: 0 changed pages in native text, layout, reading order, furniture, paragraphs, lists, structure | comparison |
| Chosen MathML unchanged by the 13c fix | PASS: 0 of 6,226 records | [mathml_13c_fix.json](../experiments/out/step14a/final/mathml_13c_fix.json) |
| Source hashed once per run | PASS: 1 in every book | performance records |
| Ruff (src, tests, Step 14a scripts) | PASS | [ruff_prerun.log](../experiments/out/step14a/ruff_prerun.log) |
| Gold, reference, ledger, old projects untouched | PASS | — |
| ENT, mideast, math hold-out not run | PASS | — |
| Statistics (information) | I1–I6 zero; I7 = 1 (p870 index gutter, backlog); lines owned and ordered once | `final/after/statistics_full_gates.json` |

**Run history (for transparency):** the final runs were made four times. (1) Book 2's
paragraph metric fell (0.854 → 0.839) because cells swallowed the list items inside them;
fixed by keeping units that lie wholly in a cell as its content. (2) Book 1 failed on a grid
whose merged areas overlapped (the record validator caught it; nothing wrong was written);
fixed, and the pre-run sweep was added. (3) Book 1's paragraph metric fell (−0.012) because
the production stage did not receive the structure stage's navigation kinds, so glossary
pages took text; fixed, and the parity check was added. (4) Final, all five books.

## Limitations

1. **Book 1 recall 0.65** for text-owning tables (precision chosen, as instructed); 35 possible
   tables are recorded for review (4 are reference tables).
2. **Six book 1 text-owning false tables** remain (a contents box, two reading organizers, a
   timeline panel, a chart panel and an unmarked glossary page); **book 3** p3 index page is a false
   table. Both glossary/index cases are pages the structure stage did not mark as navigation.
3. **p447 empty organizer** (Step 12 carry-forward): its boxes hold no text, so it is
   rejected as a table and the figure there is not flagged; book 1 flags 7 other
   graphic-organizer pieces.
4. **Header rows**: book 4 0.64 exact (section rows read as headers or not; header style
   equals body style in many of its tables).
5. **Spanning rows**: section rows that span all columns in text-column tables (book 4 p15)
   span only part of the row; two narrow adjacent columns can merge (book 2 p151).
6. **Statistics detection**: precision 0.898 / recall 0.838, partly gold location noise
   (numbers repeated across neighbouring tables aligned to the wrong table); not hand-counted
   beyond the manual check (20/20 Statistics tables correct).
7. **Without the models extra no table owns text** (every table is a possible table; the run
   warns). Table Transformer detection costs ~1–1.6 s per page on CPU (cached).
8. **Span splits** use an even share of the span width (no glyph positions); 342 Statistics,
   106 book 4, 61 book 1, 22 book 2 lines are split over cells.
9. **Book 1 structure** (TEDS 0.80): sidebar and organizer tables with lists and empty cells;
   TableFormer reads them better (0.89) but is not combined in 14a (decision 5).
10. Captions/titles, notes, cell content structure beyond whole units, and joining continued
   tables are Step 14b.

## Decisions for you

1. **Text ownership rule**: two detectors + tabular geometry (chosen to meet your ~0.9
   precision; book 1 0.885, book 4 0.988, Statistics 0.898, book 2 1.0). Keep, or relax for
   ruled grids with one detector (book 1 then 0.81 precision / 0.66 recall)?
2. **Table pieces**: figures made only of a table's rules and fills are absorbed and no longer
   exported (Statistics 1,049, book 4 1). Accept (as for figures converted to equations in
   13b)?
3. **Navigation pages the structure stage misses** (book 1 p684, book 3 p3–5): fix in the
   structure stage (its navigation detection), or add a table-side rule?
4. **13c**: accept that text-set records kept as text carry flags only (no review status, no
   image fallback), including the 120 that were `must_check` through their own checks.
5. **Structure models**: TableFormer is clearly better than our geometry on book 1 (TEDS
   0.891 vs 0.790) and close elsewhere. Combine it (for example where our grid's evidence is
   weak, measured per book first), use it only as a second opinion for review flags, or keep
   it as comparison only? It costs ~2–8 s per table on CPU (cached per image).

**Step 14a is complete; Step 14b has not started.**
