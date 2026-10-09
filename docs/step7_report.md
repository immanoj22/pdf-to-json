# Step 7: reading order

Every page now has an ordered reading sequence over the Step 4 lines: one main flow, float
streams (sidebar, callout, figure, table, card, credit, note) each anchored in the main flow, and
side streams (furniture, artifact, invisible). Order is a NetworkX graph with typed edges. No
paragraphs, headings, furniture removal or zones are decided. Step 4 layouts, the text ledger,
the span store and all gold are unchanged. Old projects were not touched.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **703 passed**, 0 failed / 0 skipped (644 earlier + 59 new) | [JUnit](../experiments/out/step7/pytest.xml), [log](../experiments/out/step7/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** on all 24 | [cross-check](../experiments/out/step7/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens; 758 pages; line counts exact; passing | [full_book.json](../experiments/out/step7/full_book.json) |
| I1-I7 on 24 pages | **0 each** | [invariants.json](../experiments/out/step7/invariants.json) |
| Every line ordered exactly once | 24 pages, and all pages of all 3 books (84,085 + 14,396 + 1,231 lines); graph checks 0 problems | same, plus per-book summaries |
| Ruff check / format, from backend/ | pass | [ruff.log](../experiments/out/step7/ruff.log) |

Gold (hand-made and derived) and the ledger are byte-unchanged (`git status`). The full-book
gate is written to step7/ instead of rewriting the Step 4a output.

## Part 0

- **Decision recorded** ([decisions.md](decisions.md)): GPL WITH the GCC Runtime Library
  Exception (NumPy/SciPy wheels) is allowed. scikit-learn, LightGBM and UniMERNet move to allowed.
- **scikit-learn 1.9.1 and LightGBM 4.7.0** are installed as the optional `classical-ml` extra
  (with SciPy 1.18.1, joblib, threadpoolctl, narwhals, cloudpickle; all permissive, binary
  wheels, `pip check` passes). Both synthetic CPU smokes pass. They are unused by the pipeline.
  [Smoke](../experiments/out/step7/smoke_classical_ml.json), [lock](../backend/requirements-classical-ml-lock.txt).
- **UniMERNet: deferred, per your decision.** It is allowed but blocked on CPython 3.14: upstream
  pins `transformers==4.42.4`, which needs `numpy<2` (no 3.14 wheel; source build fails without
  a compiler). With transformers 5.19 it installs but cannot import
  (`apply_chunking_to_forward` was removed). Exact errors are in [dependencies.md](dependencies.md).
  The temporary environments and the briefly installed Python 3.12 were removed. The main venv
  remains CPython 3.14.8. PP-FormulaNet-L remains the formula candidate.
- **Atomic cache writes** ([atomic.py](../backend/src/book_core/atomic.py)): all three writers
  retry the final rename on a Windows `PermissionError` (8 attempts, at most about 3.6 s,
  each retry logged). Off Windows, for other errors and when the retries run out, the error is
  raised unchanged. Covered by [tests](../backend/tests/test_atomic_retry.py). This edits
  COMMON producer files, so every derived cache key changed once (by design).

## Model and rules (brief)

[reading_order/](../backend/src/book_core/reading_order/): models, frames, continuation
evidence, builder, graph and cache. The cache is keyed on the layout fingerprint, the producer
source, the version and the vocabulary digest.

- **Edges:** next_in_lane, next_lane_in_band, next_band, continues_across_column,
  next_in_stream (inside figures, tables and side streams), belongs_to_figure, belongs_to_table,
  caption_of, anchored_after. continues_across_page is a cross-page *candidate* only; it is
  stored per book and never applied.
- **Scopes:** bands are read along the stacking axis. Rotated scopes are read in their own frame.
  A callout that forms a band by itself is an in-flow section, read in place inside its own
  scope. Other boxes are floats.
- **Bands and lanes:** lanes are read in writing direction (rtl right to left; vertical writing
  right to left). Within a lane, lines are read by baseline; lines sharing a baseline form a row
  read inline.
- **Floats:** a float in a text lane is anchored at its centre. A gutter-bridging inset uses the
  first lane it touches. A float that has its own lane is read in lane order; band-level floats
  are read at the end of their band. Card lanes are one card each, in lane order.
- **Continuation evidence** (rules only, no model) uses Unicode sentence terminals, letter case,
  line-break hyphens and the Step 6 vocabulary. It types lane transitions and decides whether
  columns continue across a band holding only floats. Layout-model (Heron/PP) evidence is not used.
- **Book-1 tuning added three general rules,** each needed because Step 4 mis-segments columns:
  1. Sub-lanes: text columns that Step 4 left in one lane are split at gutters crossed by at
     most 5% of lines, and only if the columns stand side by side.
  2. Row-synchronised lanes: lanes whose block starts align (at least 75%) are read block row by
     block row (the bilingual glossary).
  3. Adjacent bands with the same aligned columns, no gap and no rule or banner between them are
     read as one column flow (index columns split across bands; insets).

Every decision carries confidence and reasons. Confidence below 0.6 is flagged for review.

## Evaluation (harness `reading_order` metric, per book, no overall score)

Units are reference (derived-gold) units. A unit belongs to the stream holding most of its
tokens. Main flow is scored by pairwise agreement and Kendall tau between main units, plus
adjacent-pair agreement. A float anchor is correct when the main unit just before the anchor
equals the reference's last main unit before the float (anchoring inside the right paragraph
counts as correct, since paragraphs are not decided yet). Floats are scored separately.

| | Book 1 (development) | Book 2 (hold-out, once) | Book 3 (hold-out, anecdotal, once) |
|---|---:|---:|---:|
| Lines ordered once | 84,085 / 84,085 | 14,396 / 14,396 | 1,231 / 1,231 |
| Main units | 14,157 | 2,265 | 926 |
| Main pairwise agreement, pooled | **0.946** | **0.968** | **0.991** |
| Kendall tau, pooled | 0.891 | 0.936 | 0.981 |
| Adjacent-pair agreement | 0.977 | 0.973 | 0.993 |
| Page mean / perfect pages | 0.983 / 584 of 718 | 0.977 / 265 of 294 | 0.991 / 5 of 9 |
| Float anchor accuracy | **0.899** (1,509 streams) | 0.375 (16 streams) | 0 / 1 |
| Within-float pairwise order | 0.921 | 0.745 (mostly table cells) | 1.0 |
| Low-confidence decisions | 263 | 2 | 1 |

Book 1 anchors by kind: callout 0.949, credit 0.950, table 0.941, note 0.910, sidebar 0.890,
figure 0.768, card 4/4. Book 1's first full run (before the three rules) scored 0.900 pooled,
538 perfect pages and anchors 0.888.

Hold-out discipline: the producer was frozen at `32dcffa0…`. Books 2 and 3 each ran once after
that, as logged in [holdout_runs.jsonl](../experiments/out/step7/holdout_runs.jsonl). Nothing
was tuned after those runs. Book 3 remains anecdotal.

Per book: summaries for [book 1](../experiments/out/step7/spanish_us_history/summary.json),
[book 2](../experiments/out/step7/immigrant_children/summary.json) and
[book 3](../experiments/out/step7/art_therapy_index/summary.json), each with per-page metrics,
anchor misses, the low-confidence list and cross-page candidates in the same folder.

### Reference conventions found (book 1)

Position of each stream's first reference unit relative to the page's main units:

| Stream kind | Before main | Interleaved | After main | Reading of the convention |
|---|---:|---:|---:|---|
| callout | 75 | 68 | 171 | Boxes are read where they sit; full-width boxes after the text above them |
| figure (+captions) | 63 | 127 | 110 | Image groups sit near the paragraph they illustrate; editor placement varies |
| note (glossary bar) | 0 | 110 | 215 | Definitions follow the text; often after all main text |
| credit | 0 | 1 | 364 | Credits at the end of the page |
| sidebar | 3 | 55 | 15 | Pull quotes go into the paragraph they interrupt (p26: inside "Al inicio…") |
| furniture | 36 | 32 | 129 | Running heads first; CONÉCTATE and folios at the end |

The repeated **CONÉCTATE** box is kept as content after the main text on every page, as a
paragraph or a sidebar. Step 4 types it either `header_footer_candidate` (→ furniture stream) or
`footnote_candidate` (→ note float). Both are anchored or placed after the main flow, so its
position agrees with the reference either way. Sidebar/chart boxes at the top of a column are
read first (p100). Cards are read after the summary text (p465).

## Regression targets

All are asserted in [test_reading_order.py](../backend/tests/test_reading_order.py) and pass.

| Target | Result |
|---|---|
| column_26 | Left column wholly before right; pull quote is an `inset` float anchored in the left lane, inside the paragraph it interrupts; quote lines read `“Nuestros`, `sabios…` |
| column_100 | Left before right; top-right "de la guerra de Independencia" follows the left prose "…después" with a `continues_across_column` edge; chart box and figure anchored at page start |
| complex_cards | Two columns, then the in-flow "El desafío" box, then cards CORE, NAACP, SCLC, SNCC; NAACP reads 1909 < 1954 < 1955–1956 |
| complex_map | Map figure anchored before the two-column body; left column before right |
| complex_sidebar / background_worksheet | Section by section (C then D; A then B); the worksheet's photo box and table anchored inside their own sections |
| u07 | Rotated scope read in its frame: title, then table (anchored after the title), then note |
| u01 / u02 | Three index columns read column by column |
| Synthetic | 1/2/3/4 columns; spanning title mid-page; pull quote (circle, and a framed box that makes Step 4 split bands); sidebar; card grid; rtl two columns and rtl rows; vertical lines; rotated block; column flow across a float band only on evidence; every-line-once invariant on all 24 pages |

## Overlays

Numbered blue arrows show the main flow (thick at lane or band changes). Floats are coloured
boxes with `F<n> kind @<anchor>` and a dashed arrow to the anchor. Furniture is grey. Red marks
low confidence. All eight were inspected visually. [Index](../experiments/out/step7/overlays/overlays.json).

| Page | What it shows | Main pairwise / anchors |
|---|---|---|
| [p26](../experiments/out/step7/overlays/reading_order_p26.png) | Two columns, pull-quote inset; Step 4 merged line flagged | 1.0 / 1.0 |
| [p100](../experiments/out/step7/overlays/reading_order_p100.png) | Column continuation; chart box and figure at page start | 1.0 / 0.75 |
| [p465](../experiments/out/step7/overlays/reading_order_p465.png) | Two columns, then cards in order | 1.0 / 1.0 |
| [p669](../experiments/out/step7/overlays/reading_order_p669.png) | Bilingual glossary read row by row | 1.0 / – |
| [p696](../experiments/out/step7/overlays/reading_order_p696.png) | Index: sub-lanes plus the band split; 3 merged lines flagged | 0.990 / – |
| [p245](../experiments/out/step7/overlays/reading_order_p245.png) | Unseen: two panels, painting anchored in panel E | 0.952 / 1.0 |
| [p732](../experiments/out/step7/overlays/reading_order_p732.png) | Unseen: columns, box, table float, glossary note | 1.0 / 1.0 |
| [p47](../experiments/out/step7/overlays/reading_order_p47.png) | Unseen: two columns | 1.0 / – |

The unseen pages are a seeded draw (seed 7) from pages never inspected during tuning.

## Low-confidence list (book 1: 263)

- **211 `caption_link` / not_linked:** a caption candidate with no adjacent figure or table in
  its scope is read in place. Often this is body text typed as a caption by Step 4, as on the
  worksheet.
- **43 `scope_boundary` / assigned_by_start:** a line crosses a sub-lane gutter. Step 4 merged
  text of two index columns into one visual line.
- **9 `scope_boundary` / kept_in_scope:** a line extends 25% or more beyond its box (p26's
  merged quote line).

The full list with page, subject IDs and text is in
[low_confidence.jsonl.gz](../experiments/out/step7/spanish_us_history/low_confidence.jsonl.gz).
No direction decision needed a default in book 1, and no line was unplaced.

## Limitations

1. **Figure anchors are weakest (0.768).** Misses split evenly early and late, mostly off by one
   or two units. The reference places image groups by editorial choice, not geometry. Not tuned.
2. **Book 2 floats (hold-out):** anchors are 0.375 on only 16 streams, and within-float order is
   0.745. The rotated regression tables read row-major line by line, and multi-line cells
   interleave. Table structure is deferred.
3. **Step 4 defects are inherited, not repaired.** Lines merged across texts (p26 quote, index
   gutters) stay whole and are flagged. Banner rows such as p245's "E" and "F" section letters
   are read together before the panels.
4. **No continuation model** (none passed in Step 6b). Text evidence ties on index pages, so the
   band-merge rule relies on geometry (no gap, no rule or banner) rather than text.
5. **Cross-page continuation** is candidates only. Book 1: 117 continue, 80 neutral, 514 break.
6. Right-to-left and vertical ordering are tested on synthetic layouts only; the books are
   left-to-right.
7. Rule confidences are heuristics, not calibrated probabilities.

## Decisions for you

1. Accept the three book-1 rules (sub-lanes, row-synchronised lanes, same-structure band merge),
   which compensate for Step 4 column segmentation. Alternatively, ask Step 4 to fix them at the
   source later.
2. Float anchoring at the float's centre inside a text lane: keep, or anchor at paragraph
   boundaries once paragraphs exist (Step 8+)?
3. Captions without an adjacent figure stay in the main flow (211 flagged). Keep this, or make
   them caption floats?
4. CONÉCTATE and other repeated boxes: final policy remains yours. Reading order already places
   them after the main flow, matching the reference.

## Reproduce

From the project root: `python experiments/step7_smoke.py`;
`python experiments/step7_layouts.py --book spanish_us_history`;
`python experiments/step7_run.py --book spanish_us_history`; then for the hold-outs (once)
`python experiments/step7_layouts.py --book <book> --holdout` and
`python experiments/step7_run.py --book <book> --holdout --reason "…"`;
`python experiments/step7_overlays.py`; `python experiments/step7_gates.py`. Pytest and Ruff
run from `backend/`.

**Step 7 stops here for owner review. Step 8 has not started.**
