# Step 14b — tables: content, titles, notes, headers and output

Status: **complete for review.** Joining tables continued across pages is Step 15 (not
started). Step 14b fixes the missed navigation pages in the structure stage, reads cell roles
and header references (column headers including spanning group headers, row headers of a
stub column, section rows), lists each cell's content in reading order, links table titles
and notes from evidence learned per book, uses TableFormer only where it measurably helps,
and publishes the full table record in the final archive.

Main results (text-owning tables, final runs; Step 14a final → Step 14b final; development
scoring re-run on evidence rebuilt from the final caches):

| Book | Tables | Structure TEDS | Full TEDS (structure + content) | Cell adjacency F1 | Header rows exact | Header association | Titles found / correct | Notes found / correct |
|---|---:|---|---|---|---|---:|---|---|
| 1 Spanish US history | 51 | 0.803 → 0.803 | 0.787 | 0.840 | 0.891 → **0.978** | 0.892 | 0 / 1 (no table numbering) | 0 / 1 |
| 2 Immigrant children | 12 | 0.939 → **0.982** | 0.875 → **0.927** | 0.854 → **0.901** | 1.0 | 0.933 | **12 / 12**, 12 correct | **9 / 10**, 9 correct |
| 3 Art-therapy index | **0** (was 1 false table) | — | — | — | — | — | — | — |
| 4 Medical anatomy | 85 | 0.942 → 0.945 | 0.909 → 0.911 | 0.960 → **0.971** | 0.642 | 0.942 | **44 / 48**, 44 correct | (none in reference) |
| Statistics | 502 | 0.944 → 0.944 | 0.924 | 0.972 | 0.822 → **0.851** | 0.932 | **48 / 50**, all correct (1 gold noise) | (none in reference) |

Paragraph boundary F1 (books 1–2 must not be worse): book 1 **0.9417 → 0.9422**, book 2
**0.8546 → 0.8549**, book 4 0.9010 → 0.9014. Headings, unit kinds and cell order are unchanged
except where explained below. Manual checks: **30 / 30 real tables, 28 fully correct**;
title/note links **60 / 60 correct** (20 per book in books 2, 4 and Statistics; books 1 and 3
have no links).

## Scope and baseline

HEAD at start: `d590e9d` (Step 14a and its gate decisions in; tracked tree clean; the
untracked `.vscode/`, one Step 11d output and Step 13c/14a development files left untouched).
Baseline: the Step 14a final capture, frozen into
[step14b/before](../experiments/out/step14b/before/). Only books 1–4 and Statistics were run;
ENT, mideast, the mismatched pair and the math hold-out were not. Gold, reference XML, the
ledger and old projects were not edited.

## Task 1 — navigation pages (14a decision 3)

Cause, measured on the structure evidence: book 1 p684 sets its glossary entries in a region
the layout typed as a table, whose units the entry statistics skipped (1 entry counted);
book 3 pp. 3–5 are each one or two Step 9 units of ~150 lines, so alphabetical order could not
be read from units.

Fix (structure stage, general evidence; `structure/features.py`, `structure/navigation.py`):

- The pass-1 evidence records, for units of several lines, each line's start and the head
  and tail of its text (`line_entries`).
- A unit holding several entries is read **line by line**: lines at its column's base
  indent open entries (deeper lines are sub-entries and wrapped lines); the unit is replaced
  by those entries only when they are themselves in alphabetical order (a body paragraph is
  never split: its line starts are not ordered).
- A run of an index or glossary also **continues onto a neighbouring page whose entries the
  layout set in a table region**, with the same entry tests; a table page alone never starts
  a run.

Before/after on all books ([navigation](../experiments/out/step14b/navigation/),
[effect](../experiments/out/step14b/final/effect/), driver
[comparison](../experiments/out/step14b/final/comparison.json)):

| Book | Navigation pages | Kinds changed | Headings | Lists | Index / glossary entries | Paragraphs |
|---|---|---|---|---|---|---|
| 1 | 69 → 70 | p684 none → glossary | 581 → 581 (p684: the column label "ENGLISH" is no longer a heading; the divider "U" is one, as on every other glossary page) | p684 only | definition entries 1,292 → 1,293; the table region's units stay `table_text` units (81 → 88), now in no table | F1 +0.0005 |
| 2 | 81 → 81 | none | 231 → 231 | unchanged | unchanged | F1 +0.0003 |
| 3 | 6 → **9** | pp. 3–5 none → index | 2 → 2 | pp. 3–5 | index entries **602 → 899** (3 merged paragraphs split into entries) | no paragraph gold |
| 4 | 13 → 13 | none | 672 → 672 | unchanged | unchanged | F1 +0.0004 |
| Statistics | 2 → 2 | none | 1,347 → 1,347 | unchanged | unchanged | — |

On other index/glossary pages (book 1 pp. 664–722, book 2 pp. 324–327, book 4 pp. 305–314)
only the recorded entry statistics, reasons and confidence change (more entries read line by
line); kinds, headings and units are identical. Tables: book 1 p684's glossary table and book
3's index table are now possible tables only, so book 1's text-owning false tables drop from 6 to 5
(precision 0.885 → 0.902) and book 3 has no table.

## Task 2 — TableFormer (14a decision 5)

TableFormer (accurate) reads every text-owning table that matches a reference segment, from
the crop the stage itself makes (`tables/opinion.py`: page rendered through the Extractor,
region cut out and turned upright by exact quarter turns; readings cached per image). Policies
scored per book ([tableformer/final](../experiments/out/step14b/tableformer/final/)):

| Use | Book 1 | Book 2 | Book 4 | Statistics | Kept |
|---|---|---|---|---|---|
| Our geometry (TEDS / header rows exact) | 0.803 / 0.891 | 0.982 / 1.0 | 0.945 / 0.642 | 0.944 / 0.822 | — |
| (a) Its grid where our evidence is weak — lists in cells | 0.830 | = | **0.934 ✗** | = | no |
| (a) — empty cells (≥ 30% of body) | 0.860 | **0.978 ✗** | **0.942 ✗** | 0.945 | no |
| (a) — organizer-like (ruled lattice, long cells) | 0.857 | = | **0.940 ✗** | = | no |
| (a) — uncertain spans | 0.808 | 0.984 | 0.946 | **0.943 ✗** | no |
| (a) — any of them | 0.914 | 0.984 | **0.931 ✗** | 0.945 | no |
| (b) Its header rows always | header 0.804 ✗ | 0.909 ✗ | 0.630 ✗ | 0.838 | no |
| (b) Its header rows **only where our grid found no header evidence** | **0.978** | 1.0 | 0.642 | **0.851** | **yes** |
| (c) Second opinion: flag where structures disagree (similarity < 0.8) | flags 15, precision 1.0, recall 0.83 | 2, 0.5, 1.0 | 5, 0.8, 0.31 | 13, 0.46, 0.07 | **yes (review flag only)** |

(a) improves book 1 strongly but makes book 4 worse in every variant (and book 2 or
Statistics in some), so by your rule it is not used. (b) improves books 1 and Statistics and
changes nothing elsewhere: kept. (c) changes no output and its flags are precise where our
structure is weakest (book 1: 15 of 15 flagged tables are wrong ones): kept as a review flag.
Final runs: header rows from TableFormer on 4 (book 1) and 49 (Statistics) tables;
disagreement flags 19 / 2 / 5 / 16. Time on CPU: ~3–5 s per table (book 2's 23 s per table
includes loading the model), cached per image. TableFormer is in the `accuracy-models` extra:
`structure_reader = "auto"` uses it when installed and the learned detectors run, and warns
otherwise.

## Task 3 — cell content and headers

`tables/grid.py`, `tables/records.py`:

- **Section rows** — a row whose only text is one continuous line crossing a column boundary
  spans the whole row (except across a rule that parts it). Book 4 p15: the five "Topic: …"
  rows now span 5 of 5 columns (were 2 of 5, or split over two cells).
- **Narrow adjacent columns** — sparse bands (at most half as many text pieces as the fullest
  band: group headers, centred counts, section labels) may cross a column gap that at least
  half of all bands leave clear. Book 2 p151 now reads **11 of 11** columns (was 9).
- **Group headers** — a cell of an upper header row widens over the empty positions of the
  sub-columns it groups (rightward to the midpoint to the next group header, leftward as far
  as its centre makes symmetric), never into a stub column. Book 2 p124 "Externalizing",
  "Alcohol Use", "Risky Sexual Behavior" now span their 4 sub-columns each, as in the
  reference.
- **Cell roles** — column header (header rows), section (a body row of one cell spanning the
  table), row header (the first column when its cells are text beside mostly numeric data, or
  when the header rows leave its head empty above text), data.
- **Header association** — each cell lists the header cells that label it: column headers
  above it sharing its columns (group headers first), the row header of its row, the nearest
  section row above. Scored against the column headers implied by the reference grid: 0.89 /
  0.93 / 0.94 / 0.93 (books 1, 2, 4, Statistics). The references mark no row headers; stub
  columns were checked by hand in the samples (e.g. Statistics "Race 1 … Race 20").
- **Content** — each cell lists its content in reading order, by reference: whole lists-stage
  units (paragraphs, list items), remaining lines and span ranges as text, display equation
  units and figures where they sit. Final archives: book 4 cells hold 328 list items, 330
  paragraphs and 38 figures; Statistics 115 equations. The record validates that a cell's
  content holds its lines and span ranges exactly once.

Effect of Task 3 alone in development (books 2/4): TEDS 0.939 → 0.982 / 0.942 → 0.945,
adjacency 0.854 → 0.901 / 0.960 → 0.971; books 1 and Statistics unchanged.

## Task 4 — titles and notes

`tables/captions.py`. For each text-owning table, units of the final view next to it in its
own frame (above/below, overlapping its columns, nearest first, each further one close to the
previous), and its own top/bottom rows when they are one cell spanning the table:

- **Table labels** are learned per book: words opening the nearest neighbour of at least two
  tables before a number ("Table 4.1", "TABLE 2.1:", "Table C2" in appendices), never the
  figure stage's caption labels. The **title side** is where most of them sit. Learned: book 2
  `table`/above, book 4 `table`/above, Statistics `table`/below; books 1 and 3 none.
- A **title** is the nearest unit on the title side opening with a table label and a number
  (else on the other side, flagged); each unit titles one table only.
- **Note labels** are learned the same way from units below tables ("Note." in book 2), and
  need text after them ("Contd..." continuation marks under book 4 tables are not notes).
  **Notes** are the units below the table that open with a note label or with a footnote
  marker the table itself uses (`*`, `†`, raised letters); the first other unit ends them.
- Not linked, with the reason (review): caption units next to a table without the book's
  numbered label (or in a book without table numbering), units opening with a marker the
  table does not use, a note word the book uses only once, numbered titles nearer to another
  table, and units a figure has linked as its caption or credit. Text that a figure region
  merely contains does not block a numbered title (Statistics: 364 titles also lie inside
  figure regions drawn over table parts; they are linked and flagged for review of the
  figure).

Links against the reference titles and notes (a link is correct when it holds at least half
of the reference title's tokens; [dev/final](../experiments/out/step14b/dev/final/)):

| Book | Links | Reference titles found | Wrong (gold) | Reference notes found | Unlinked candidates |
|---|---:|---|---:|---|---:|
| 1 | 0 | 0 / 1 (an unnumbered title row inside the table) | 0 | 0 / 1 (a source row inside the table) | 0 |
| 2 | 21 | **12 / 12** | 0 | **9 / 10** (the miss: the book's only "Source:" line; not learned from one table) | 1 |
| 4 | 49 | **44 / 48** (misses: titles Step 9 merged into the paragraph above them) | 0 | — | 9 |
| Statistics | 502 | **48 / 50** | 1* | — | 0 |

\* p61: two tables with identical cells; the gold matched its "Researcher A" table to our
second table. Our links are right ("Table 1.31 Researcher A" under the first, "Table 1.32
Researcher B" under the second; [render](../experiments/out/step14b/manual/p61_titles.png)).

**Manual check, 20 links per book** (seed 1426, [verdicts](../experiments/out/step14b/manual/verdicts.json),
[renders](../experiments/out/step14b/manual/links/)): book 2 **20 / 20** correct (titles and
notes of rotated APA tables), book 4 **20 / 20** (including pages with two or three tables,
each title over its own table), Statistics **20 / 20** (one title unit also holds the next
sentence, merged by Step 9). Books 1 and 3 have no links to check.

## Task 5 — model output

`tables/models.py`. Every table record (text-owning or possible) carries: `id`, `page`,
`page_label` and `label_source`, `bbox`, `rotation` (its reading frame), `rows`, `columns`,
`header_rows`, `row_header_columns`, `cells` (row/column, row/column span, `header`,
`role`, `header_cell_ids`, `content`, `unit_ids`, `line_ids`, `span_refs`,
`equation_unit_ids`, `figure_ids`, `bbox`), `title` and `notes` (unit id or inside lines,
rule, numbered, confidence), `unlinked_texts` (with reasons), `continues_from` /
`continues_to`, `review_flags`, `evidence`, `families`, `structure_evidence`,
`absorbed_figure_ids`, `anchor`, `confidence`, `reasons` and `provenance`. No tag names; no
text is copied. Possible tables keep their review records. The book record adds the learned
labels, title side, link and TableFormer counts, and role/content counts.

## Task 6 — evaluation

Detection is unchanged except the navigation fix (book 1 P/R 0.902 / 0.648, book 2 1.0 /
1.0, book 4 0.988 / 0.894, Statistics 0.896 / 0.838). Structure, headers and links: tables
above.

**Effect on units, page by page** (Step 14a final → Step 14b final; every boundary change is
on a page with a table or a changed navigation kind, `changes_without_a_table_or_navigation_change: []`):

| Book | Page | Boundary tp / fp / fn change | Cause |
|---|---|---|---|
| 1 | 684 | −12 / −25 / +12 | glossary page: no longer a table; its entries are back in units (net gain: 25 fewer false boundaries) |
| 1 | 35, 743, 754 | +1–2 / 0 / −1–2 | finer grids (cells now match reference paragraphs) |
| 1 | 347 | 0 / −1 / 0 | timeline false table, finer grid |
| 2 | 44 | −1 / −2 / +1 | Table 3.1 regrouped (section rows) |
| 4 | 15, 16 | 0 / −3–4 / 0 | section rows read as one cell each |

Cell order inside reference tables: unchanged (book 1 0.9987, book 2 0.9946, book 4 0.9999,
Statistics 0.9997). Reading order of earlier stages: unchanged (native text, layout, reading
order, furniture, paragraphs identical on books 1–4; lists change only on book 1 p684 and book
3 pp. 3–5).

**Manual check, 30 tables** (seed 1424 over the 650 text-owning tables;
[verdicts](../experiments/out/step14b/manual/verdicts.json),
[crops](../experiments/out/step14b/manual/check/)): **30 real tables, 28 fully correct**.
Wrong: book 1 p743 (a panel's title band read as the header row); Statistics p722 (two empty
cells under a missing rule segment merged into a row span).

**Overlays** (seed 1425, constrained to a rotated table, merged cells, unruled columns, a
title and notes; grid red, column headers purple, row headers cyan, section rows orange,
title blue, notes orange, reference green; [overlays](../experiments/out/step14b/overlays/)):
[book 2 p165, rotated, title, note, group headers, stub](../experiments/out/step14b/overlays/table_immigrant_children_p165_1.png),
[book 1 p35](../experiments/out/step14b/overlays/table_spanish_us_history_p35_2.png),
[book 1 p347 (timeline false table, open since 14a)](../experiments/out/step14b/overlays/table_spanish_us_history_p347_3.png),
[Statistics p276](../experiments/out/step14b/overlays/table_statistics_p276_4.png),
[book 2 p123](../experiments/out/step14b/overlays/table_immigrant_children_p123_5.png),
[Statistics p468](../experiments/out/step14b/overlays/table_statistics_p468_6.png),
[p76](../experiments/out/step14b/overlays/table_statistics_p76_7.png),
[p159](../experiments/out/step14b/overlays/table_statistics_p159_8.png).

**Time and memory** (one worker, CPU; the structure change invalidated every later stage of
books 1 and 3, so they recomputed characters, figures, equations, MathML and tables):

| Book | Tables stage | Peak memory of the stage | Whole run | Peak memory of the run |
|---|---:|---:|---:|---:|
| 1 | 37 min | 13.1 GB | 2 h 48 min | 14.1 GB (equations) |
| 2 | 12 min | 1.4 GB | 50 min | 1.4 GB |
| 3 | 6 s | 0.2 GB | 2 min | 0.2 GB |
| 4 | 5 min | 1.3 GB | 24 min | 1.3 GB |
| Statistics | 11 min | 1.5 GB | 60 min | 1.5 GB |

## Task 7 — tests

`backend/tests/test_tables_14b.py` (17): header references with group headers, row
headers and sections; group headers widen over sub-columns, never into the stub; section
lines kept whole; sparse bands crossing a gap; cell content kinds in reading order (and the
validator rejecting uncovered content); titles need the learned label, notes the learned note
label or a table marker, unnumbered captions and foreign markers stay unlinked with reasons,
figure caption claims block a title; no numbering → nothing linked, captions flagged; note
labels need text after them; the navigation fix (a merged index unit read line by line, a
body paragraph not split; a glossary continuing onto a table-region page, a table page alone
not starting a run); cache closure of the new modules; the upright crop maps pixels back to
the page in all four frames; TableFormer header rows only without header evidence and the
disagreement flag; and a small book with numbered titles, notes (`Note.` and a `*` footnote),
group headers and a stub column, **1 vs 2 workers byte-identical**.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **1,059 passed, 0 failed** | full suite before the final runs |
| Six-pages-per-book sample + Statistics sample | PASS: 0 missing / 0 extra on 30 pages | [source crosscheck](../experiments/out/step14b/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step14b/final/full_book.json) |
| Full-book I1–I7 on books 1–4 | PASS: all zero | `final/after/*_full_gates.json` |
| Every line owned once (five books) | PASS: lists units and order once on every page; final view + tables own every line once; split spans once; inside titles/notes outside cells; linked units' lines exact | [final_outputs.json](../experiments/out/step14b/final/final_outputs.json) |
| Books 1–2 not worse | PASS: book 1 0.9417 → 0.9422, book 2 0.8546 → 0.8549; every change explained above | [effect](../experiments/out/step14b/final/effect/) |
| Parity (stage vs development) | PASS: **identical on every page of all five books** (tables, grids, roles, header references, content kinds, titles, notes, possible tables) | [parity](../experiments/out/step14b/final/parity/) |
| Pre-run sweep | PASS: 0 failures on all five books | [sweep_prerun.log](../experiments/out/step14b/sweep_prerun.log) |
| Ruff (src, tests, Step 14b scripts) | PASS | [ruff_prerun.log](../experiments/out/step14b/ruff_prerun.log) |
| Gold, reference, ledger, old projects untouched | PASS | — |
| ENT, mideast, math hold-out not run | PASS | — |
| Statistics (information) | I1–I6 zero; I7 = 1 (p870 index gutter, backlog); lines owned once | `final/after/statistics_full_gates.json` |

**Run notes.** (1) The first full test run had 29 failures because I edited a table module
while it ran (the producer guard); rerun untouched: 1,059 pass. (2) Proofs recompute every
page now (Step 14a's per-page proof checkpoints hold the old lists keys). (3) The Statistics
run was refused by the disk check (8.8 GB needed, 12.8 GB free, 5 GB reserve); with your
approval the 27 entries of a dry-run list were deleted (3.39 GB: 26 superseded final archives
of Steps 13–14a that no final capture or tracked file uses, and the Step 14a development
bundles; [list](../experiments/out/step14b/cache_prune_dry_run.json)), then it ran.

## Limitations

1. **Book 1 structure** stays at TEDS 0.80: its sidebar and organizer tables with lists and
   empty answer cells. TableFormer reads them better (0.91) but makes book 4 worse, so it is
   only a review flag there (15 flags, all on wrong tables).
2. **Book 1 titles and notes**: the book numbers no tables, and its titles and source lines
   sit inside table regions as rows; nothing is linked there.
3. **Titles merged into paragraphs** by Step 9 (book 4: 4 of 48; Statistics: a title unit
   holding the next sentence) are unlinked or over-long.
4. **Header rows in book 4** stay 0.64 exact (header style equals body style in many tables;
   TableFormer does not help there).
5. **Row headers** are not in the references; detected stub columns (Statistics: 152 tables;
   row-header cells: book 2 110, book 4 25, book 1 4) were checked only in samples.
6. **Book 1 false tables**: 5 remain (contents box p14, two organizers, timeline p347, chart
   panel p754); the p743 panel title band is read as a header row.
7. **Notes** are learned only from labels used under at least two tables (book 2's single
   "Source:" line stays unlinked, flagged).
8. **Disagreement flags** are weak in Statistics (precision 0.46, recall 0.07).
9. Book 1 p684's entries stay `table_text` units: the lists stage does not re-read a glossary
   page the layout typed as a table region.

## Decisions for you

1. **TableFormer**: keep (b) header rows only where our grid has no header evidence and (c)
   disagreement as a review flag; (a) not used (book 4 worse in every variant). Accept?
2. **Titles inside figure regions** (Statistics 364): numbered titles are linked although
   the text lies inside a figure region drawn over table parts; the figure is flagged. Should
   such figures (table drawing fragments that also hold the title) be treated as table pieces
   in a later step?
3. **Single-use note labels** ("Source:" once in book 2): keep the two-table rule (unlinked,
   flagged), or accept a label next to one table when it opens with a word followed by a colon
   and the unit sits directly under the table?
4. **Book 1 p684**: the page is a glossary, but its entries stay `table_text` units. Re-read
   such pages as entries in the lists stage (Step 15 or later)?

**Step 14b is complete; Step 15 has not started.**
