# Step 13a — math: reference books, math gold, detection and character evidence

Status: **complete for review.** Step 13b (MathML) has not started. A new `equations` stage
records equation regions and a character-repair layer beside unchanged units. In books 1–4
every page, book record, cache key and accuracy metric is identical to the Step 12 baseline;
their final archives only gain the new records. All required gates pass (below).

## Scope and baseline

HEAD at start: `a2781fb` (Step 12 and its decisions commit in; the tree was clean apart from
the untracked `.vscode/` and one Step 11d output file, both left untouched). The frozen
baseline for books 1–4 is the Step 12 final capture, copied to
[step13/before](../experiments/out/step13/before/). Only books 1–4 and the math development
book were run; the sealed ENT hold-out, the mideast robustness book, the mismatched pair and
the sealed math hold-out were not. Gold, reference XML, the ledger and old projects were not
edited (new math gold was added in its own folder).

## Part 0 — math reference books

Recorded in [decisions.md](decisions.md) (Step 13 Part 0).

| Item | Result |
|---|---|
| Development book | OpenStax *Statistics*, CC BY 4.0 (CMS record, `LICENSE`, collection). `Downloads/math_book` did not exist: official PDF downloaded (871 pages, SHA-256 `6aef489a…8def`). |
| Source | `osbooks-statistics` @ `7dea80a`, git-ignored clone; its 101 modules inherit the collection's CC BY 4.0 |
| Same edition | **Yes**: title, all 13 chapter titles, sample equations. The one source commit after the PDF build rewords a preface paragraph (no math). |
| **Math hold-out** | **Found and sealed: OpenStax *Algebra and Trigonometry* 1e** — seeded draw (seed 20261014) between the two CC BY 4.0 first editions named (College Algebra; Algebra and Trigonometry), branch `1e` of `osbooks-college-algebra-bundle` @ `8322d84` (all four collections CC BY 4.0). Official PDF, 1,220 pages, SHA-256 `7bfd1ff4…04bb`, in `Downloads/math_book/holdout/`. Edition identity: title and all 13 chapters (a first check that compared punctuation logged `edition_mismatch` over one serial comma; the corrected check logged `sealed`; both records are kept). **Never run.** [Log](../experiments/out/step13/holdout_runs.jsonl) |
| NC / NC-SA books | none used |
| CNXML | own data file `reference_dialects/math_dialects.json` (math scoring only; never merged into `dialects.json`); the gold records its digest |
| UniMERNet | licence passes (Apache-2.0); **not added**: its pins pull NumPy 1.26.4, which has no CPython 3.14 wheel ([dry run](../experiments/out/step13/dependencies/unimernet_dry_run.log)) |
| New dependency | fontTools 4.66.1 (MIT, pure Python) becomes a core dependency (font-program evidence) |

## Task 1 — math gold (derived, `human_approved: false`)

[`backend/tests/gold_derived_math/statistics/`](../backend/tests/gold_derived_math/statistics/) —
reader and locator in `evaluation/math_gold.py`, driver `step13_gold.py`.

The collection is read in module order with each MathML equation replaced by a *slot*
between reference text tokens; the reference text is aligned to the retained PDF tokens with
the unchanged reference aligner (91.2% of 290,596 reference tokens aligned). An equation is
located between its nearest aligned neighbours: the native drawn objects and unaligned PDF
tokens that lie, in PDF order, between them (objects are placed by the visual band they sit
on). A gap is located only when its objects form as many connected groups as it has
equations.

| | Equations | Inline | Display |
|---|---:|---:|---:|
| Reference (MathML) | 2,374 | 2,116 | 258 |
| Located | 1,744 (73.5%) | 1,569 | 175 |
| **Verified (scoring set)** | **1,254 (52.8%)** | 1,167 | 87 |

Unlocated: anchor tokens unaligned (228), anchors on non-adjacent pages (161), scattered gap
(130), nothing in the gap (78), others (33). Weakest contexts: notes (118 of 281 located) and
glossary entries (23 of 50).

**Verified** = located and drawn with as many glyphs as the equation has leaf characters
(±25%). A seeded manual check (40 located rows, seed 14) found count-consistent rows **26 of
28 correct (93%)** and the rest 6 of 12 (50%), so detection is scored against the verified set
only; the other located rows stay in the gold, marked unverified.
[Coverage](../experiments/out/step13/gold/coverage.json),
[manual check](../experiments/out/step13/gold/manual_check_seed14.json).

## Task 2 — measurement before any change

Baseline caches only (books 1–4: Step 12 final; Statistics: a HEAD run into
[step13/before](../experiments/out/step13/before/)). [Measurements](../experiments/out/step13/measure/).

**The math book draws every equation as filled vector paths** (Prince/MathJax): no text, no
images; 23,955 recurring glyph outlines (213 shapes) on 871 pages.

| Book | How math appears | Where it lands today |
|---|---|---|
| Statistics | vector glyphs; plus arithmetic and notation set as text (`.15 + .25 = .40`, `H0: μ = 6`): 3,264 operator runs | **9,310 glyphs lie in no layout region: no unit holds them — the math is lost from the text.** 14,645 lie in layout figure regions; 456 inline and 127 display located equations sit inside exported Step 12 figure images. Text runs: paragraphs 1,666, list items 1,336, tables 134 |
| 1 Spanish US history | no math; 10 lines with an operator; 12,067 recurring vector shapes (map symbols, compass roses, icons) | — |
| 2 Immigrant children | statistics in prose and table notes: 175 operator runs; one embedded font with math coverage (its Greek) | paragraphs 156, table text 16, list items 3 |
| 3 Art-therapy index | none | — |
| 4 Medical anatomy | 269 lines with an operator — etymology glosses (`Axilla = armpit`), phone numbers, `<35 years`; 3 runs | paragraph 1, table text 2 |

No embedded font in books 1, 3, 4 or Statistics is a math font; book 2 has one.

## What changed

Only additions: the `equations` stage (`book_core.equations`) after figures, its records in
the final archive, the stage registration (cache scope and cache index) and evaluation code.
No earlier stage, unit, order, ledger or span changes.

### Detection (Task 3) — general evidence only

- **Vector equations.** A drawn glyph is a filled outline at the book's text size that holds
  no text. A shape (scale- and position-free signature) counts as a character when it recurs
  on at least two pages and is set **beside a glyph of another shape** in at least 30% of its
  occurrences (characters are set in words and expressions; ornaments repeat beside copies of
  themselves, icon parts nest, a logo stays on one page). Glyphs join by proximity, never
  across text between them; thin bars join as fraction bars or overlines. A cluster must look
  **typeset**: one colour, a colour the page's own text uses, not drawn over an image.
- **Text equations.** Runs of operands (numbers, single or Greek letters, scripts) and Unicode
  math operators (Sm), with no word inside: an operator between operands, a raised/lowered
  script on an operand, or a span in a math font (font-program evidence). Not equations: a
  raised number after a word (note reference), a raised letter on a bare number (table note
  mark, ordinal), items separated by commas (`83, 83+, 84`), one-sided prose comparisons
  (`>35 years`). A short name before a symmetric relation and a number is a quantity
  (`SD = 3.1`); a dash before a number after an operator is a sign; a run left open at a line
  end joins the run opening the unit's next line. Lines of any rotation are read in native
  order. Region boxes cover the characters of the run, not whole spans.
- **Inline / display** from the visual band; **where it lands** is the unit holding the line
  (inline) or followed (display), with its kind and layout region type.
- **Layout models** (Heron, PP-DocLayoutV3 formula boxes, cached) are support only.

No font, book, page, word or code-point list; no change to units, order or text.

### Character repair layer (Task 4)

A glyph whose name the strict glyph list reads as one character while the PDF decodes it to
another (Step 11d evidence) becomes a **repair** only when the embedded font program's own
character map assigns that character to that glyph (fontTools): two independent sources
against the decoding. A repair records original, corrected, evidence, confidence 0.95 and
review status `needs_review`; the span store is never changed. Anything less is a **flag**
that keeps the original.

## Task 5 — results

### Detection, math book

| | Regions | Recall (verified gold) | Measured precision (lower bound) |
|---|---:|---:|---:|
| All | 5,334 | **0.963** (1,207 / 1,254) | 0.225 |
| Inline | 4,481 | 0.966 | 0.206 |
| Display | 853 | 0.920 | 0.325 |
| Drawn glyphs (object level) | 25,254 | 0.957 of gold glyphs | 0.450 |
| Layout models alone: either / both / PP / Heron | 2,922 / 661 / 2,101 / 821 | 0.652 / 0.222 / 0.606 / 0.255 | 0.350 / 0.409 / 0.341 / 0.374 |

**Manual precision** on seeded samples of the final records, drawn per source (seeds 81–83):

| Source | Population | Sample | Math | complete | partial / merged | False positive |
|---|---:|---:|---:|---:|---:|---:|
| Vector | 2,085 | 40 | **40** | 30 | 10 | 0 |
| Text | 3,095 | 20 | **20** | 16 | 4 | 0 |
| Mixed | 154 | 10 | **10** | 4 | 6 | 0 |

Earlier samples during development (seeds 21–33, 51–53) found the false positives that led to
the general rules above (section icons, chevrons, list commas). [Reviews](../experiments/out/step13/review/),
[evaluation](../experiments/out/step13/evaluation/final/).

### Region boundaries (main input for 13b)

[Boundaries](../experiments/out/step13/boundaries/boundaries.json), script `step13_boundaries.py`.

**Why 5,334 regions for 1,254 verified equations.** Every region is accounted for:

| Regions | Count | What they are |
|---|---:|---|
| On a verified equation (one per equation) | 1,142 | the regions scored above |
| Extra fragments of a split verified equation | 131 | boundary defects |
| On a located but unverified equation | 403 | reference MathML outside the scoring set |
| Vector / mixed, on no located equation | 540 / 23 | the 630 reference equations the gold could not locate, and equations' unlocated parts (manual samples: all math) |
| Text, on no located equation | 3,095 | **math set as text** (`.15 + .25 = .40`, `P(x = 40) = 0.33`, `H0: μ = 6`) — not MathML in the reference (manual sample: 20/20 math) |

So the excess is mainly **gold coverage** (only 53% of reference equations are verified, and
the reference marks text-set math as text), then **fragments** (131); the manual samples found
no non-math region among the final records.

**Per verified equation** — every one (1,254), and the seeded sample of 200 (seed 13):

| Label | All verified | Sample of 200 | Inline (186) | Display (14) |
|---|---:|---:|---:|---:|
| **Exactly one complete region** | 779 (62.1%) | **131 (65.5%)** | 128 | 3 |
| Complete, region also holds other material | 78 (6.2%) | 8 (4.0%) | 8 | 0 |
| Merged with another equation | 139 (11.1%) | 19 (9.5%) | 19 | 0 |
| Partial (one region holds part) | 131 (10.4%) | 21 (10.5%) | 18 | 3 |
| Split over several regions | 104 (8.3%) | 18 (9.0%) | 10 | 8 |
| Missed | 23 (1.8%) | 3 (1.5%) | 3 | 0 |

Complete = one region holds ≥ 95% of the equation's glyphs, and ≤ 20% of the region is other
material. A manual check of 40 sampled labels (seed 14; green gold, red regions) found **36
correct**, 2 labelled complete that hold neighbouring material (should be "with extra"), and 2
gold errors (an icon and answer letters as gold; "missed" is correct there).
[Manual check](../experiments/out/step13/boundaries/manual_check.json).

**For 13b:** two thirds of equations get exactly one complete region; inline merges (two
equations in one region, across a full stop or a list of answer options) and display splits
(8 of 14 sampled display equations; wide spacing around `=` and between lines of a multi-line
display) are the boundary work 13b must do while reading glyph positions.

### Detection, books 1–4 (no math in their references; every region reviewed)

| Book | Regions | Math (notation) | False positives | Recall review: candidate lines without a region |
|---|---:|---:|---:|---|
| 1 Spanish US history | 4 (vector) | 0 | 4: publisher logo twice (white letters on pages that also have white text), two map fragments | 10 lines: photo credits, URLs, `LGTBIQ+`, an abbreviation legend — no math missed |
| 2 Immigrant children | 174 (text) | **174** (126 complete; 48 partial: start inside an expression or unbalanced bracket) | 0 | 16 lines: URLs and query strings, scale anchors (`1 = extremely poor`), and 4 real misses: expressions wrapped after `(SD =` (2), `X²(df=2)` without spaces, `= 2302 and 863` |
| 3 Art-therapy index | 0 | — | — | none |
| 4 Medical anatomy | 3 (text) | 1 (`m²`, partial) | 2: karyotype notation `12 + X`, `21, 22 + Y` | 278 lines: etymology glosses, phone numbers, `μ` units; not detected by design: 9 one-sided comparisons (`<35 years`); 1 word formula missed (`No. of X-chromosomes − 1`) |

[Inventories](../experiments/out/step13/evaluation/step12/),
[recall reviews](../experiments/out/step13/evaluation/recall_review/).

### Book 2 statistics lines: detected, text unchanged

All 174 regions in book 2 are statistical notation, detected as **inline text equations** on
30 pages: `F(1, 147) = 16.87, p < .001`, `(M = 45.08, SD = 16.37)`, `(β = –.30, p < .001)`
(wrapped over two lines, joined), `α = .77`, `η2 = .13, .06`, `X2(18) = 55.76`, `(n = 194)`,
and the significance notes of rotated tables (`*p < .05; ** p < .01; ***p < .001`, pages 71,
73, 124, 126, 147, 152). Rule combinations: operator between operands 113; with a math
font 44; script only 8; operator and script 4; math font only 3; all three 1; math font and
script 1. No table note mark (`3.38ᵇ`) and no URL query (`pubid=2008016`) is an
equation.

**The text is unchanged:** a region holds character ranges into the span store and copies no
text. Book 2's native text, units, lists, structure and every metric are identical to the
Step 12 baseline on all 331 pages (comparison below), the final archive's text equals a fresh
extraction on its six sample pages (0 missing / 0 extra), and no repair touches book 2.
[Overlay p117](../experiments/out/step13/overlays/equations_immigrant_children_p117.png),
[rotated notes p73](../experiments/out/step13/overlays/equations_immigrant_children_p73.png).

### Character repairs and flags (Task 4)

[Records](../experiments/out/step13/final/character_repairs.json).

| Book | Glyphs whose name disagrees | Repairs | Flags (original kept) | False positives |
|---|---:|---:|---:|---:|
| 1 Spanish US history | 0 | 0 | 0 | 0 |
| 2 Immigrant children | 0 | 0 | 0 | 0 |
| 3 Art-therapy index | 0 | 0 | 0 | 0 |
| 4 Medical anatomy | 538 | **0** | 538 | 0 |
| Statistics | 0 | 0 | 0 | 0 |

Example (book 4, page 41 and 537 others): a list marker decoded as `Ǌ` (U+01CA) whose glyph
is named `bullet.034`, so the name proposes `•`. The embedded font program (UtopiaStd) does
not map U+2022 to that glyph, so it is a flag, not a repair — and rightly: Step 11d showed the
painted glyph is a cube, not a bullet. (The 139 Wingdings `¾` markers have no readable name
and keep their Step 11d flags.) No book of the five sets Greek in a symbol font extracted as
Latin, so **repair precision has no positive case here: 0 repairs, 0 false repairs**. The rule
is covered by tests (a repair needs both sources; unnamed or unconfirmed glyphs are only
flagged; the original is kept; a repair must change the character). The sealed hold-out (an
InDesign PDF with font-set math) is where it will first meet real cases.

### Effect on books 1–4

**None outside the new records.** Against the Step 12 baseline, in all four books: 0 changed
pages in native text, layout, reading order, furniture, paragraphs, lists and structure; 0
book-record changes; 0 cache-key changes (native through lists); 0 changed accuracy metrics
(only elapsed seconds differ). Paragraphs, lists and headings are therefore unchanged by
construction. The final archive key changes (it now includes the equations key).
[Comparison](../experiments/out/step13/final/comparison.json).

Equations stage cost (one worker, CPU, layout-model detections cached): book 1 30 min,
book 2 22 min, book 3 6 s, book 4 6 min, Statistics 12 min; peak memory ≤ 1.3 GB. Each run
hashed its source once.

### Overlays

[Index](../experiments/out/step13/overlays/overlays.json) — inline blue, display green,
text/mixed regions with an orange outline, layout-model-only boxes red dashed, verified gold
grey: [inline fractions in prose, Statistics p19](../experiments/out/step13/overlays/equations_statistics_p19.png),
[display formulas, p183](../experiments/out/step13/overlays/equations_statistics_p183.png),
[fractions, p204](../experiments/out/step13/overlays/equations_statistics_p204.png),
[subscripts, p728](../experiments/out/step13/overlays/equations_statistics_p728.png),
[table of computations (matrix-like), p251](../experiments/out/step13/overlays/equations_statistics_p251.png),
[book 2 statistics line, p117](../experiments/out/step13/overlays/equations_immigrant_children_p117.png).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **962 passed, 0 failed** (run after the final runs) | `final/pytest.xml` |
| Six-pages-per-book sample | PASS: 0 missing / 0 extra on 30 pages (books 1–4 and six seeded Statistics pages) | [source crosscheck](../experiments/out/step13/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step13/final/full_book.json) |
| Full-book I1–I7 on books 1–4 (real run) | PASS: all zero on 1,412 pages | `final/after/*_full_gates.json` |
| Every line in exactly one unit, ordered once | PASS: books 1–4 (119,854 lines) and Statistics (38,273 lines) | same |
| Books 1–2 not worse | PASS: identical on every page and metric (books 3–4 too) | comparison |
| Final archives | PASS: every file checksum, digest, line/span reference, figure and equation record resolves | [final_outputs.json](../experiments/out/step13/final/final_outputs.json) |
| No invention, text untouched | PASS: regions hold span ranges only, no text/MathML; repairs are separate records; span store unchanged | tests, archive checks |
| 1 vs 2 workers and production equal (with equations) | PASS | `test_workers_and_production_give_identical_equations` |
| Cache closure (equations in final, missing dependency detected) | PASS | `test_equations_cache_closure_covers_its_imports`, `test_missing_equations_dependency_is_detected` |
| Source hashed once per run | PASS: 1 in every book | performance records |
| Ruff from `backend/` (before long runs and final) | PASS (src, tests, all step13 scripts) | `final/ruff.log` |
| ENT, mideast and the math hold-out not run | PASS | — |
| Statistics (new book, information) | I1–I6 zero; **I7 = 1** (page 870, existing index behaviour); lines owned and ordered once | `final/after/statistics_full_gates.json` |

Disk: the four-book cache estimate (1,412 × 12 MiB) is checked against free space minus 5 GB
(the owner's Step 10b rule); the inherited Step 11d driver's stricter 10 GB margin was
replaced in the Step 13 driver because every upstream cache already existed.

**Development history (for transparency):** the final runs were repeated four times as
reviews found general problems — rotated table notes skipped, significance stars hiding
expressions, map symbols and logos drawn as glyphs (typeset test), table note marks, and
text-region boxes covering whole spans. Each change was general (no book rule), was re-scored
on Statistics, and re-ran all five books; superseded producer records are kept in
`final/producers_superseded_*.json`.

## Limitations

1. **Gold coverage:** 52.8% of reference equations are verified; notes and glossary entries
   are under-represented; verified gold is ~93% correct by the manual check.
2. **Boundaries:** see the table above — 65.5% exactly one complete region; merges (inline)
   and splits (display) are the main defects; function words (`invNorm`) are left out of text
   runs.
3. **Text-set math vs reference markup:** found as equations; the references keep it as text.
4. **Rotated pages:** text runs are read at any rotation; inline/display for drawn glyphs uses
   horizontal bands.
5. **Book 1:** four drawn non-math objects pass every test. **Book 4:** karyotype notation.
6. **Not detected:** one-sided comparisons, word formulas, `X²(df=2)` without spaces, an
   expression whose first line ends with a bare name (`(SD =` / `2.1)`).
7. **Presentation:** an equation alone in a table cell is reported display (143 cases).
8. **Statistics I7 = 1** (page 870, index: locator column counted as text) is existing layout
   behaviour on a new book (index-gutter backlog), not a Step 13 change.
9. **Character repair** has no positive case in these books.
10. Character boxes inside a span are proportional (characters taken as equally wide).

## Decisions for the owner

1. **Text-set math** (`p < .001`, `.15 + .25 = .40`): in 13b keep it as text with an equation
   record (as the references do), or convert to MathML? A client option could do either.
2. **Equations inside Step 12 figures:** 583 located Statistics equations lie inside exported
   figure images (Statistics exports 2,393 figure images; the layout grouped vector glyphs as
   figures). In 13b, should equation regions take precedence over figure regions?
3. Accept the **verified gold** (1,254 equations) as the 13b MathML scoring set,
   `human_approved: false`.
4. Accept **layout-model formula boxes as support only** (alone they reach 0.65 recall).
5. Accept the boundary table as the 13b starting point (merges and display splits first).

**Step 13b has not started.**
