# Step 13b — math ownership and boundaries

Status: **complete for review.** Step 13c (MathML) has not started. Every equation region
has an owner, figures that hold only equation evidence are converted, boundaries follow
general native and typographic evidence, mixed expressions (text-set and drawn parts) are one
region, and text-set notation (`f(x)`, `P(A)`, `Hₐ`) is detected. Text, units, lines and order
are unchanged; equation units hold drawn objects only. In books 1–4 every page, book record,
cache key and accuracy metric is identical to the Step 13a baseline. All required gates pass.

## Scope and baseline

HEAD at start: `47604aa` (Step 13a). The Step 13a gate decisions were recorded first as their
own commit `bc0e3bf`. Baseline for books 1–4: the Step 13a final capture, copied to
[step13b/before](../experiments/out/step13b/before/); Statistics is compared with the Step 13a
final records. Only books 1–4 and Statistics were run; ENT, mideast, the mismatched pair and
the sealed math hold-out were not. Gold, reference XML, the ledger and old projects were not
edited.

Development used per-page bundles of the stage inputs (`step13b_bundles.py`, git-ignored) so
a rule could be scored on all 871 Statistics pages in seconds (`step13b_dev.py`); numbers
below are from the final runs unless marked "dev".

## What changed

All in the equations stage (`book_core.equations`), the final archive view and the disk
check; no earlier stage, unit, line, order, ledger or span changes.

### Rules (general evidence, relative to the book)

| Rule | Evidence |
|---|---|
| Drawing groups | A clip that holds no text and lies within one text size around its marks is one native drawing: its marks join; marks of two different groups never join by proximity. Without such clips proximity alone decides. |
| Operator bars, dots, parts | A thin bar on a glyph's band (a minus), a dot below glyph height, and a filled outline at glyph scale that is not a glyph (a wide radical, an overline piece) join the cluster beside, touching or sharing a group with them; none starts a cluster. |
| Fraction rows | A bar takes only the nearest row above and below, not the next line. |
| Lines | Glyphs set inside a text line stack only at accent distance (0.25 size) and never across two text lines' bands. |
| Display rows | Display rows closer than one text line pitch of the book (median baseline distance in its units; 11.55 pt in Statistics), overlapping, with no text or other group between, are one display. |
| Reversed lettering | A cluster lighter than the fill painted right behind it, when no fill of that colour holds text of its colour, is not typeset math (a logo); reversed math in table header cells is kept. |
| Text runs | A comma, semicolon or colon at bracket depth 0 before a space ends an expression; a spaced dash is a minus only in a run holding a relation (else a range: `1933 - 1944`, `A – G`); a glued modifier symbol between operands is an operator (`e^(x)`). |
| Function application | A standalone letter applied with no space to a bracket holding an operand is math (`f(x)`, `P(A)`); words inside a bracket applied to a single letter or a closing bracket belong to the expression (`P(A AND B)`, `(1.5)(IQR)`). |
| Scripts | On horizontal lines, a standalone letter followed by a short (≤ 3 characters) raised or lowered span is base + script, not a word (`Hₐ`, `sₓ`, `pA`). |
| Mixed expressions | Text parts without evidence of their own (`f(x) =`, a lone `=`) join a drawn part on the same line band when they meet through an operator, a bracket or touching with no space; a list separator between a text part and a drawn part keeps them apart; parts that join nothing are dropped. |
| Character boxes | Character ranges use the rendered glyph boxes of the native text objects; the even share of the span is a fallback. |

No font, book, page, word or code-point list.

### Ownership (Task 1) and figures (Task 2)

Every region gets one owner (`equations/ownership.py`):

- spans (text, mixed): the text unit holding them; the text stays text and the equation is
  recorded beside it (decision 1); drawn parts of a mixed region get an inline place;
- drawn inline: read inside the unit of the line beside it at an **inline place** (before
  the first character whose glyph centre follows the objects along the line's reading
  direction);
- drawn display: an **equation unit** anchored after a line of a reading-order stream (the
  nearest line above in its column, or before the nearest below; never a page sort);
- figures: a figure whose own content is only equation evidence (no caption, no drawing or
  image of its own apart from fills painted behind the equations) is **converted**: its
  equations replace it and its image is not exported. A **real figure** owns only equations
  drawn within its own drawn or raster content; text-flow math that a figure region merely
  overlaps is owned by the text flow;
- `review`: a display region with no line to anchor it (never read as an equation).

The figure stage's records are unchanged; the final archive shows figures without the
converted ones (reading indexes renumbered, credit proposals filtered) and does not copy their
images.

## Results

### Ownership: nothing vanishes (Task 1)

[Ownership](../experiments/out/step13b/ownership/).

| Statistics | Step 13a | Step 13b |
|---|---:|---:|
| Drawn objects of equation regions | 25,254 | 26,546 |
| … held by nothing (no unit, no figure) | **9,597** | **0** |
| … held only as pixels of an exported figure | 15,657 | 74 (2 real figures) |
| … read inside text units (inline place) | — | 16,513 |
| … in display equation units | — | 9,959 (435 units) |
| … for review | — | 0 |
| Gold drawn objects in no region | 516 | 21 |

| Book | Drawn objects before: held by nothing / only in an image | After: unowned | Owners |
|---|---|---:|---|
| 1 Spanish US history | 4 / 19 | 0 | p653 map fragment: its real map figure; p652 map fragment: review (not read) |
| 2 Immigrant children | text only | 0 | 182 text units |
| 3 Art-therapy index | — | 0 | — |
| 4 Medical anatomy | text only | 0 | 3 text units |

Display units on Statistics: 129 between consecutive lines of their stream (confidence 0.9),
306 after the nearest line above or before the nearest below (0.7, `review_required`; mostly
equations in table cells, Step 14). Inline placement against the gold's own anchor tokens
(within the place's stream): **974 of 987 comparable placed between them (98.7%)**.
[Placement](../experiments/out/step13b/evaluation/final/placement.json).

### Figures (Task 2)

| Book | Figures before → after | Converted | Kept with math | Images no longer exported |
|---|---|---:|---:|---:|
| 1 | 507 → 507 | 0 | 1 (p653 map) | 0 |
| 2 | 1 → 1 | 0 | 0 | 0 |
| 3 | 0 → 0 | 0 | 0 | 0 |
| 4 | 330 → 330 | 0 | 0 | 0 |
| Statistics | 2,393 → 2,013 | 380 | 2 | 380 |

Books 1–4: figure records and images unchanged. Book 1's four Step 13a drawn false positives:
the two publisher logos (pp. 3–4) are no longer equations (reversed lettering on a dark shape);
p653 is owned by its real map figure; p652 is kept for review. None enters reading order.
Statistics' two kept: p450 (a radical wider than the mark limits reads as the figure's own
drawing) and p864 (text lines that layout put inside a figure of calculator-key images). A
review of the 51 figures that held math before the own-content rule found solution boxes with a
check-mark icon and graphs whose region covered the worked equation above the plot; they now
read that math in the text flow
([review](../experiments/out/step13b/review/statistics_kept_figures/)).

### Boundaries (Task 3)

[Boundaries](../experiments/out/step13b/boundaries/boundaries.json),
[mixed view](../experiments/out/step13b/mixed/final.json),
[sample changes](../experiments/out/step13b/boundaries/sample_changes_final.json).

The Step 13a classifier, unchanged (drawn objects decide; complete = one region holds ≥ 95% of
the equation's objects and ≤ 20% other objects). The reference sets the text parts of an
expression (`f(x) =`, `P(A) =`, a `=` between two fractions) as text and only the drawn parts
as MathML, so when the mixed rule makes one region of `f(x) = 1/(23 − 8) = 1/15`, the strict
label of each fraction is "merged". **Expression level** counts such a region as complete for
each of its equations.

| All 1,254 verified | 13a | 13b before the mixed rules | **13b final** |
|---|---:|---:|---:|
| Exactly one complete region (strict) | 779 (62.1%) | 1,074 (85.6%) | **975 (77.8%)** |
| Merged through text-set operators on one line (one expression) | — | — | 99 |
| **Expression level complete** | 779 | 1,074 | **1,074 (85.6%)** |
| Complete, region also holds other material | 78 | 93 | 92 |
| Merged otherwise | 139 | 52 | 55 |
| Partial | 131 | 5 | 5 |
| Split | 104 | 9 | 7 |
| Missed | 23 | 21 | 21 |

**Seeded sample of 200 (seed 13):**

| | 13a | 13b before mixed rules | **13b final, strict** | **13b final, expression level** |
|---|---:|---:|---:|---:|
| Exactly one complete region | 131 | 177 | **159** | **177** |
| Merged through text on one line | — | — | 18 | 0 |
| Complete with extra / merged otherwise / split / missed | 8 / 19 / 18 / 3 (+21 partial) | 11 / 7 / 2 / 3 | 11 / 7 / 2 / 3 | 11 / 7 / 2 / 3 |

**Why 177 → 159 strict:** the only label changes between the two final record sets are 18
"complete → merged" on the sample, and every one is a single expression chained through
text-set operators on one line: `f(x) = 1/(23 − 8) = 1/15` (p320), `z = (y − μ)/σ =
(4 − 2)/1 = 2` (p364), `σ = √(npq) = √(15(.281)(.719)) = 1.7409` (p309), `μ = (a + b)/2 =
(15 + 0)/2 = 7.5` (p321), `P(B) = (outcomes in B)/(outcomes in S) = 6/19` (p185), the
`P(being a female musician)…` chains (p239) and others. The first version of the mixed rule
also had **two real regressions** (p184, p185: a text `, P(B) =` after a drawn fraction joined
two expressions across a comma); a separator between a text part and a drawn part now keeps
them apart, and both are fixed. No other label moved: no split, partial or miss.

Without drawing-group (clip) evidence the geometric rules alone give 985 exactly complete (dev,
before the mixed rules; clips add 89), so books without clipped drawings still gain.

Region accounting (6,039 regions): 1,163 on a verified equation (+6 fragments of a split one),
420 on located but unverified equations, 4,450 on no located equation (3,949 text, 170 mixed,
331 vector) — mainly math set as text, which the reference keeps as text. "Merged otherwise"
are mostly gold artefacts (several located gold rows on the same few objects, e.g. p425
`1 4`, `1 2`, `3 4` in one 5×13 pt box).

**Manual check of 40 labels** (seed 14 of the sample; green gold, red regions;
[check](../experiments/out/step13b/boundaries/manual_check.json)): 38 labels right (2 of them
on gold errors — an icon and an answer-letter column, where "missed" is correct), 2 gold
artefacts (the `x̄` gold lacks the overline pieces the region correctly holds).

### Mixed expressions, text-set math and edges

Before = 13b records just before these rules; after = final. Seeded line samples are drawn from
input evidence, not from the regions judged.
[Samples](../experiments/out/step13b/samples/manual_review.json).

**1. Mixed expressions.** The gold has 16 verified equations with drawn objects and PDF text
tokens and 15 text-only ones, but their "text tokens" are mostly stray answer letters and list
numbers the gold locator attached (1 of 16 and 0 of 15 complete before and after), so the gold
cannot measure this. Seeded sample (seed 101) of 40 of the 905 lines holding a drawn equation
object and a math operator, relation or applied bracket: **the whole expression is one region
in 36 of 40 lines after, 1 of 40 before.** Remaining failures: `P(T < 2) = 1 - …` cut at the
line end; `binompdf(…)` (word-named calculator call); a long `P(R on 1st) P(B on 2nd) + …`
chain split in three; a 13a short-name rule takes `and` before a drawn `α/2`. Mixed regions
on Statistics: 167 → 663.

**2. Text-set math (`f(x)`, `P(A)`, `Hₐ`).**

| | Before | After |
|---|---:|---:|
| Seeded sample (seed 102) of 40 of the 3,799 lines with no drawn math whose text holds an operator or an applied bracket: math expressions one complete region (of 35) | 15 | **26** |
| False positives in that sample | 1 | 1 (`5−10 percent`, a range with a minus sign, from 13a) |
| Precision of added regions, seed 103 (40 of 435) and seed 104 (40 of 223) | — | **80/80 math** (70 complete, 10 start or end inside an expression) |
| Recall on verified gold (Step 13a scorer) | 0.963 (13a) | **0.983** |
| Region precision against the gold (lower bound; the reference keeps text-set math as text) | 0.225 (13a) | 0.184 |

New hits include `P(Y)`, `P(Person obtained the disease through method C)`, `P(O OR H)`,
`x = 2` / `y = 6.2` (split at the comma), `151 – 160 = –9`, `pF < pM`, `pW > pA` and `Hₐ`
(its lowered `a` is a separate span; read as the word "Ha" before the script rule). Still
missed: hyphenated or multi-letter names (`p-value = 0.0095`, `y = mx + b`) and a leading
sign after a figure number.

**Books 1–4 false positives from these rules: none.** Two candidate rules that produced them
were rejected during development: an unrestricted spaced-dash minus (`1933 - 1944`,
`01/20/1981 - 01/20/1989`, `A – G`, `1 – 22`) and an unrestricted script split (rotated map
lettering `oH`, `nR`, `cN`; a table note `1.78bc`). The regions of books 1–4 differ from Step
13a only where explained below.

**3. Clipped edges.** On book page 308 (PDF p320) no characters were lost: the ranges held all
of `8 < x < 23` and `(x > 12)`; only the drawn box was an even-share estimate. Across all text
and mixed regions:

| | Before | After |
|---|---:|---:|
| Region box cuts an edge glyph (< 50% of its rendered box) | 860 of 3,701 checked | **0** of 5,258 |
| Character really outside the range (an operand, operator or closing bracket glued to the edge) | 24 | **5** |

The 5 left have a space before an applied bracket (`Q₃ + 1.5 (IQR)`, `X ~ G (…)`) or are
calculator syntax.

### Detection on Statistics

[Evaluation](../experiments/out/step13b/evaluation/final/statistics.json).

| | 13a | 13b |
|---|---:|---:|
| Regions | 5,334 | 6,039 |
| Recall (verified gold) | 0.963 | **0.983** |
| Gold drawn objects in some region | 0.957 | 0.998 |
| Measured precision (lower bound) | 0.225 | 0.184 |

Manual precision on seeded samples: before the text and mixed rules (seeds 91–93) vector 40/40
math (36 complete), text 20/20 (11), mixed 10/10 (5); every display joined over rows (11) is
math (8 one multi-row display, 3 two stacked statements); after them the added-region samples
above (80/80). [Reviews](../experiments/out/step13b/review/).

### Books 1–4 (Task 4)

[Comparison](../experiments/out/step13b/final/comparison.json),
[inventories](../experiments/out/step13b/inventory/).

Against the Step 13a baseline: **0 changed pages** in native text, layout, reading order,
furniture, paragraphs, lists and structure; 0 book-record changes; 0 cache-key changes (native
through lists); 0 changed accuracy metrics (only elapsed seconds differ); figure records and
images unchanged. Equation records change only as follows, each intended:

| Book | Regions 13a → 13b | Change | Reason |
|---|---|---|---|
| 1 | 4 → 2 | publisher logo (pp. 3, 4) removed | reversed-lettering rule |
| 1 | — | p653 owned by its map figure, p652 for review | ownership |
| 2 | 174 → 182 | 36 regions split at list separators, e.g. `F(1, 147) = 16.87, p < .001` → `F(1, 147) = 16.87` + `p < .001`; `η2 = .13, .06` → `η2 = .13` | separator rule (owner decision below) |
| 2 | — | all 182 owned by their text units | ownership |
| 3 | 0 → 0 | — | — |
| 4 | 3 → 3 | `21, 22 + Y` → `22 + Y` (still the Step 13a karyotype false positive) | separator rule |

### Overlays

Six Statistics pages by seeded draw (seed 131 over the 613 pages with an equation region;
[draw](../experiments/out/step13b/overlays/draw.json)). Blue text-unit owner with an orange caret
at the inline place, green display unit with its reading index and a link to its anchor line,
purple real figure, red dashed converted figure, thin red Step 13a regions, grey verified gold:
[p213](../experiments/out/step13b/overlays/ownership_statistics_p213.png) (answer options as
separate display units, set notation),
[p443](../experiments/out/step13b/overlays/ownership_statistics_p443.png) (inline `x̄`, a display
unit, mixed `σ = 0.337`),
[p477](../experiments/out/step13b/overlays/ownership_statistics_p477.png),
[p548](../experiments/out/step13b/overlays/ownership_statistics_p548.png),
[p571](../experiments/out/step13b/overlays/ownership_statistics_p571.png) (`H₀`, `Hₐ`),
[p736](../experiments/out/step13b/overlays/ownership_statistics_p736.png) (a table-header figure
converted; `x̄ =` and `s² =` read inline).

### Disk check (owner instruction during 13b)

The fixed four-book disk estimate stopped books 2–4. Now permanent (decisions.md):
`cache_admin.disk_need` counts only stages this book has not cached under the current
producers, plus the final archive; each costs at least an even share of the per-page estimate
(more if measured larger); an uncached book needs the full estimate; the 5 GB reserve stays.
Final runs: needs 34 MB – 2.6 GB against full estimates of 0.1–11 GB (Statistics: only the
final archive, 2.6 GB budgeted; the archive written is 67 MB). Tests cover empty, fully cached,
one changed stage and another book. Three superseded 13b Statistics archives (3 × 67 MB) were
deleted after a dry-run list. The cleanup dry run (nothing deleted;
[report](../experiments/out/step13b/cache_cleanup_dry_run.json)) finds **1.41 GB** of
superseded registered stage caches from earlier steps (figures 0.89 GB, layout 149 MB, lists
104 MB, paragraphs 91 MB, furniture 73 MB, …); unregistered folders (old final archives,
per-step folders) are listed by size without a reclaim figure.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **986 passed, 0 failed** (after the final runs) | `pytest.xml` |
| Six-pages-per-book sample + Statistics sample | PASS: 0 missing / 0 extra on 30 pages | [source crosscheck](../experiments/out/step13b/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step13b/final/full_book.json) |
| Full-book I1–I7 on books 1–4 | PASS: all zero on 1,412 pages | `final/after/*_full_gates.json` |
| Every line in exactly one unit, ordered once (five books) | PASS: 158,127 lines | same |
| Books 1–2 not worse; books 1–4 identical | PASS: identical on every page, key and metric | comparison |
| Final archives (checksums, line/span references, figures, equation owners, anchors, conversions, images) | PASS | [final_outputs.json](../experiments/out/step13b/final/final_outputs.json) |
| No unowned typeset glyph | PASS: 0 in all five books | ownership |
| Text untouched, no invention | PASS: regions hold ranges and object ids only | tests, archive checks |
| 1 vs 2 workers and production equal | PASS | `test_workers_and_production_give_identical_equations` |
| Cache closure (equations reads figures; final reads equations) | PASS | `test_equations_cache_closure_covers_its_imports` |
| Source hashed once per run | PASS: 1 in every book | performance records |
| Ruff from `backend/` before the long runs and final | PASS | `ruff_prerun.log` |
| ENT, mideast and the math hold-out not run | PASS | — |
| Statistics (information) | I1–I6 zero; I7 = 1 (p870 index gutter, backlog); lines owned and ordered once | `final/after/statistics_full_gates.json` |

Equations stage cost (one worker, CPU): Statistics 12 min, book 2 24 min, book 4 4 min, book 3
6 s (book 1's records were cached from the run before the disk-rule change; 13a: 30 min).
Peak memory of a run is in the native-object page jobs (book 1 10.2 GB; 13a 11.5 GB).

**Development history (for transparency):** the final runs were repeated as reviews found
general problems: text-flow math under over-extended figure regions (p320 example; then all 51
kept figures reviewed), the owner's follow-up on mixed expressions, missed text-set math and
clipped edges, two cross-comma regressions and the `Hₐ` miss found while explaining the sample
drop, and the disk rule. Each change was general, re-scored on Statistics and re-checked on
books 1–4.

## Limitations

1. **Mixed rule vs the reference:** expressions joined through text-set operators count as
   "merged" against the gold (99); reported strict and expression level.
2. **Text-set names:** hyphenated or multi-letter names (`p-value`, `mx`) and word-named calls
   (`binompdf`) are not read as math; a 13a short-name rule can take a short word before a
   drawn operand (`and α/2`); `5−10 percent` (a range written with a minus) stays a false
   positive.
3. **Display anchors in tables:** 306 display units have confidence 0.7 (table cells; Step 14).
4. **Real figures with math:** 2 kept on Statistics are layout edge cases (p450, p864).
5. **Drawing groups** help only where a producer clips each expression; the geometric rules
   carry books without clips (985 vs 1,074 complete, dev).
6. **Scripts on rotated lines:** letter-on-letter scripts are read on horizontal lines only.
7. **Inline place** follows the line direction and reverses for right-to-left lines; no
   right-to-left math was available to test.
8. **Disk need** is conservative for the final archive (budgeted at the measured stage sum).
9. **Statistics I7 = 1** (p870 index gutter, backlog). Book 4's karyotype `22 + Y` remains.

## Decisions for the owner

1. Accept that text-set parts of an expression join its drawn parts in one region (the
   reference keeps them as text around separate MathML); for 13c: emit one expression (text
   parts as MathML tokens) or keep the text and emit only the drawn parts — a client option.
2. Accept list separators (`, ; :` at bracket depth 0 before a space) as expression boundaries
   (book 2's statistic lists split; `F(1, 147)` stays whole).
3. Accept the 380 converted Statistics figures (equation evidence only) as no longer exported
   images.
4. Accept 0.7-confidence display anchors in table cells for review until Step 14.
5. Superseded caches: 1.41 GB registered stage caches reclaimable (dry run); decide whether to
   prune.

**Step 13c has not started.**
