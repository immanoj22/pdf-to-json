# Step 13c — equations to MathML

Status: **complete for review.** A new `mathml` stage gives every equation region an equation
record: MathML, LaTeX, the text/drawn/image readings, checks, agreement, confidence, review
status and the default output. On Statistics the chosen MathML matches the verified gold
exactly on **86.6%** of strict equations (98.6% symbol accuracy) and **83.7%** at expression
level; equations whose two paths agree are **97.2%** exact. Books 1–4 are identical to Step
13b except for the new records. All gates pass. UniMERNet was measured and is **not kept**.

## Scope and baseline

HEAD at start: `a7abb81` (Step 13b and its gate decisions in; the tree was clean apart from
the untracked `.vscode/` and one Step 11d output file, both left untouched). Baseline for
books 1–4: the Step 13b final capture, copied to
[step13c/before](../experiments/out/step13c/before/). Only books 1–4 and Statistics were
run; ENT, mideast, the mismatched pair and the sealed math hold-out were not. Gold, reference
XML, the ledger and old projects were not edited.

## Part 0 — frameworks

Recorded in [dependencies.md](dependencies.md) (Step 13c).

| Framework | Licence | CPython 3.14 | Decision |
|---|---|---|---|
| lxml 6.1.3 | BSD-3-Clause | cp314 wheel | **Added as a core dependency**: writes and validates every MathML string |
| PP-FormulaNet-L @ `69869f28` | Apache-2.0 | yes | Image path and isolated shape readings (optional `models` extra, unchanged) |
| latex2mathml 3.81.1 | MIT | pure Python | LaTeX → tree (optional `math-conversion` extra, unchanged) |
| SymPy 1.14.0 | BSD-3-Clause | pure Python | Parse and arithmetic checks (added to the `math-conversion` extra; already installed through Torch) |
| fontTools 4.66.1 | MIT | pure Python | Core (unchanged; not used by 13c) |
| UniMERNet 0.2.3, tiny weights @ `3f09ac4b` | Apache-2.0 | **no** | (a) throwaway venv, `--no-deps`, current NumPy: **fails** at import (`apply_chunking_to_forward` removed in Transformers 5.x); (b) side CPython 3.12 environment as a subprocess: **works**. Comparison below. |

The main environment was never altered for UniMERNet: (a) read the project packages through
a `.pth` file in a deleted throwaway venv; (b) is a self-contained CPython 3.12.10 (official
NuGet package) with its own venv under the git-ignored `.cache/side_envs/`, with UniMERNet's
own pins; the checkpoint is loaded with `torch.load(weights_only=True)`.
[Logs](../experiments/out/step13c/dependencies/).

## What changed

A new **`mathml` stage** (`book_core.mathml`) after `equations`. It reads the equation
regions (unchanged) and writes one equation record per region; no earlier stage, unit,
line, order, span or key changes, and the span store is never changed. The final archive
adds the records (page and book) and the equation image fallbacks.

| Module | Role |
|---|---|
| `tree.py` | Neutral expression tree (tokens by Unicode category; structures: row, fraction, radical, root, scripts, over/under, table) and its comparison form |
| `markup.py` | MathML 3 writer (lxml), reader and structure validator; bracket balance |
| `latex.py` | LaTeX of a tree; recognizer LaTeX → tree through latex2mathml |
| `symbols.py` | Positioned symbols: real characters (rendered glyph boxes and origins, rotated lines in their own frame) and drawn glyphs (shape table) |
| `layout.py` | Structure from positions (text and drawn paths) |
| `shapes.py` | Drawn shape table: isolated readings, context votes, learned unit height and descent |
| `recognition.py` | `PPFormulaNet` behind a recognizer interface; per-image reading cache |
| `images.py` | Region images through the Extractor, own marks only, turned upright |
| `paths.py` / `checks.py` / `decide.py` | The three paths; validation; agreement, confidence, review, output |
| `settings.py` / `models.py` / `cache.py` | Client options; records; the book passes |

### Task 1 — recognition paths

Every region is read by up to three paths (`paths.py`); a path that cannot read a symbol
gives no reading (never a guessed character).

- **Text path** (text-set math): the region's characters with their rendered glyph boxes and
  baseline origins (a span whose glyphs do not match its characters falls back to an even
  share of its box and the span's own baseline, with a note). A rotated line is laid out in
  its own frame (writing direction to the right).
- **Drawn path** (vector glyphs): every drawn object of the region becomes a symbol — a thin
  bar or rectangular rule is a *bar*, every other outline takes the character of its *shape*
  (see below), its size from the shape's learned unit height and its baseline from the
  shape's learned descent. Text parts of a mixed region enter as real characters (text path).
- **Image path**: the region rendered through the Extractor at 300 dpi with only its own marks
  (other ink inside the box painted white), turned upright, read by PP-FormulaNet-L, LaTeX →
  latex2mathml → tree.

**Layout from positions** (`layout.py`, text and drawn paths): bars drawn in pieces merge;
radicals (a radical sign with the bar at its top, or a wide radical outline) take what lies
under the bar; fractions take the symbols stacked right above and below a bar inside its
extent (widest first, recursively); remaining bars with symbols just below are overlines;
small symbols centred over one symbol are accents; symbols centred above/below an operator
taller than a line (or smaller symbols centred under any operator) are limits; distinct
baselines of full-size symbols are rows of a table; along a row, digits with decimal or group
marks between them form numbers and upright letters of one word form a word; scripts are
smaller symbols raised (bottom above the base's baseline, top no lower than the base's top)
or lowered (bottom below the baseline) with their centre clearly off the base's axis; a
script on a closing bracket belongs to the bracketed group; a bar high above the base opens
an exponent; a bar that is none of these is a minus. All tests are relative to the symbols'
own sizes; no character, font, page or book is named.

**Drawn shapes, once per book** (`shapes.py`): a drawn font repeats one outline per
character, so each scale-free shape is recognised once:

1. *isolated reading*: the outline rasterized alone (its own path, 64 px high) and read by
   PP-FormulaNet-L; upright markup (`\mathrm`, `\mathbf`, …) marks an upright letter;
2. *context votes*: in every equation whose image reading has exactly as many characters as
   the provisional drawn reading, aligned characters vote for the shapes they fall on, per
   vertical position (baseline / axis / raised), so one dot can be a decimal point on the
   baseline and a product dot on the axis.

A shape takes the votes when at least three agree by 60%, otherwise its isolated reading
(lower confidence, flagged when the votes disagree). Unit height = the tallest size cluster
holding ≥15% of its occurrences; descent = the median offset of its bottom from the baseline
of the glyphs beside it. (A joint calibration of sizes across shapes was tried and rejected:
relations such as `=` were tied to superscript digits whose bottoms coincide, which made
`=` look like a script — strict exact fell from 81.8% to 64.6% in development.)

### Task 2 — validation and confidence

Every reading is checked (`checks.py`): lxml well-formedness and MathML 3 presentation
structure (allowed elements, fixed child counts, token contents, table structure); the
character count against the region's evidence (position paths: every character symbol used
exactly once; image path: as many characters as the position reading); bracket balance per
row; a SymPy parse where the expression is made of numbers, single-letter names, arithmetic,
relations, fractions, powers and roots, and — when every side of a relation is numeric —
whether the written arithmetic holds within the rounding of its result.

`decide.py` compares the position reading with the image reading in comparison form (tokens
split into characters, dash/dot/bar/prime variants unified, sentence punctuation at the ends
ignored — a crop can take in the full stop after an expression):

| Case | Confidence | Review status |
|---|---|---|
| position and image readings agree, checks pass | 0.95 | `paths_agree` |
| both read, disagree | 0.45 + 0.35 × tree similarity (capped by doubtful shape labels) | `needs_review` ≥ 0.7, else `must_check` |
| position reading only | 0.75 text / 0.70 drawn (capped by shape label confidence) | `needs_review` |
| image reading only | 0.5 | `must_check` |
| no reading | 0 | `must_check` |
| failed checks | −0.2 characters, −0.1 brackets, −0.15 arithmetic, −0.1 radical extent | — |

The chosen MathML is the position reading's when it is valid (its characters come from the
PDF), else the image reading's (always `must_check`). `paths_agree` is never set without two
agreeing paths. A `must_check` equation keeps its original text or objects, gets an image
fallback (`page_{label}_eq_{n}`, client pattern; `n` = position among the page's equation
records, physical page when no label) and is never output as MathML. Each record carries
MathML, LaTeX, path, every path's reading with its checks, agreement, similarity,
confidence, review status, output, flags and `sources` (each character of the chosen
position reading traced to its span character or drawn object).

### Task 3 — decisions applied

Client settings (`MathSettings`, recorded in the book record; they enter only this stage's
key): `text_set_math = "text"` (default: text-set math stays text, MathML stored, output
`text`; `"mathml"` outputs it), `mixed_expressions = "whole"` (default: one MathML per
expression; `"reference"`: text parts stay text and each drawn part gets its own MathML,
output `mathml_parts`), fallback name patterns, recognition and fallback dpi,
`min_confidence = 0.7`, `image_recognition = "auto"` (on when the models and
math-conversion extras are installed, otherwise a warning and image fallbacks for drawn
equations).

## Task 4 — evaluation

### Statistics against the verified gold (1,254 equations)

Scoring (`evaluation/math_scoring.py`, driver `step13c_evaluate.py`): both sides normalised
(tokens split into characters; dash, dot, bar and prime variants unified; limits scored like
scripts; sentence punctuation at the very end dropped). **Strict** = the equation has exactly
one complete region holding only its own evidence (680); **expression level** = complete
regions that also hold text-set parts or other equations, scored against the best contiguous
run of the expression's top-level items (541). 33 equations have no complete region (Step 13b
boundary: missed, split or partial) and are not scored.
[Evaluation](../experiments/out/step13c/final/evaluation.json).

| Reading | Level | n | Exact | Symbol accuracy | Tree edit distance / gold size |
|---|---|---:|---:|---:|---:|
| **Chosen (output)** | strict, all | 680 | **86.6%** | **98.6%** | 0.029 |
| | strict, inline | 614 | 87.3% | 98.6% | 0.028 |
| | strict, display | 66 | 80.3% | 98.7% | 0.032 |
| | expression, all | 541 | **83.7%** | 95.7% | 0.079 |
| | expression, inline / display | 521 / 20 | 84.8% / 55.0% | 96.1% / 85.4% | 0.068 / 0.379 |
| Drawn path | strict / expression | 680 / 541 | 86.6% / 83.7% | 98.1% / 95.7% | 0.028 / 0.079 |
| Image path, PP-FormulaNet-L | strict / expression | 680 / 541 | 64.9% / 45.8% | 94.4% / 67.6% | 0.085 / 0.701 |
| Image path, UniMERNet (side env.) | strict / expression | 680 / 541 | 65.6% / 50.5% | 94.3% / 73.0% | 0.088 / 0.538 |

The chosen reading is the drawn path on every scored equation (the verified gold is drawn
math; the text path is measured on book 2 and in the manual check). Image readings score low
at expression level because a region image also holds the text-set parts of the expression,
which the recognizer often reads as words in `\mathrm`/`\text`.

**By review status** (chosen reading, strict): `paths_agree` 427 equations, **97.2% exact**,
99.1% symbol accuracy; `needs_review` 171, 71.9%; `must_check` 82, 62.2%. Expression level:
`paths_agree` 195, 91.3%; `needs_review` 282, 80.1%; `must_check` 64, 76.6%.

**Development history:** the same scorer on development runs moved strict exact from 64% (first
layout) to 77% (context votes), 82–85% (bracket groups, baseline rows, geometric scripts) and
86.6% (final). One idea was rejected: a joint size calibration across shapes (64.6%, see Task 1).

### Records

| Book | Records | Text / drawn / mixed | Paths agree | Needs review | Must check | Output text / MathML / image | Image fallbacks |
|---|---:|---|---:|---:|---:|---|---:|
| Statistics | 6,039 | 3,950 / 1,426 / 663 | 3,171 | 1,538 | 1,330 | 3,950 / 1,807 / 282 | 1,330 |
| 1 Spanish US history | 2 | 0 / 2 / 0 | 0 | 0 | 2 | 0 / 0 / 2 | 2 |
| 2 Immigrant children | 182 | 182 / 0 / 0 | 127 | 34 | 21 | 182 / 0 / 0 | 21 |
| 3 Art-therapy index | 0 | — | — | — | — | — | — |
| 4 Medical anatomy | 3 | 3 / 0 / 0 | 0 | 3 | 0 | 3 / 0 / 0 | 0 |

Statistics by source (agree / review / must check): text 2,162 / 740 / 1,048, drawn 776 /
419 / 231, mixed 233 / 379 / 51. Flags: paths disagree 2,752, brackets unbalanced 113,
written arithmetic does not hold 34, image reading only 8, character count 7. Drawn shapes:
210; 152 labelled by agreeing context votes (confidence ≥ 0.85), 13 where the votes overrule
the isolated reading, 1 with a position-specific reading (a dot: decimal point on the
baseline, product dot on the axis), 2 unread.

A defect found at the gate was fixed before the final runs: a rule drawn in pieces and a
radical sign were counted as unused symbols, which penalised 725 correct drawn readings.
`must_check` fell from 1,752 to 1,330; accuracy did not change.

### PP-FormulaNet-L vs UniMERNet (Part 0 comparison)

**How UniMERNet was installed.** (a) A throwaway venv with `unimernet 0.2.3 --no-deps` on the
current NumPy 2.5.3 / Transformers 5.19.0 (read through a `.pth` file, never written): it
**fails at import** (`apply_chunking_to_forward` was removed from Transformers 5.x); the venv
was deleted. (b) **A side CPython 3.12 environment, called as a subprocess** (CPython 3.12.10
from the official NuGet package, its own venv under the git-ignored `.cache/side_envs/`, with
UniMERNet's pins: Transformers 4.42.4, NumPy 1.26.4, timm 0.9.16, Torch 2.5.1+cpu): **works**.
Weights `wanderkid/unimernet_tiny` @ `3f09ac4b`, loaded with `torch.load(weights_only=True)`.
[Logs](../experiments/out/step13c/dependencies/).

**The main environment is unchanged except for lxml.** No `pip freeze` was saved before the
step, so the proof is: (1) the main environment's `pip freeze` after the step
([main_env_freeze_after.txt](../experiments/out/step13c/dependencies/main_env_freeze_after.txt),
63 packages) matches the committed lock files exactly (no package outside them, no differing
version); (2) the install times of every package
([main_env_dist_info_times.txt](../experiments/out/step13c/dependencies/main_env_dist_info_times.txt))
show one install since the step began: lxml 6.1.3 (2026-10-15 16:20, the requested
dependency); (3) none of UniMERNet's packages or pins is present; `pip check` passes.

**Measured on the gold, not on a few images.** (My earlier "comparable" was an impression from
24 sample crops; these are the measurements.) Both models read the same region images (same
renderer, same masks) on every scored gold equation:

| | Strict (680) | Expression level (541) | All scored (1,221) |
|---|---:|---:|---:|
| Read by both | 680 | 535 | 1,215 |
| PP-FormulaNet-L: exact / symbol accuracy | 64.9% / 94.4% | 46.2% / 68.2% | 56.6% / 82.8% |
| UniMERNet: exact / symbol accuracy | 65.6% / 94.3% | 50.7% / 73.3% | 59.0% / 85.0% |
| **Agreement rate** (normalised readings equal) | **87.4%** | 66.4% | **78.1%** |
| When they agree: n, exact | 594, 70.0% | 355, 52.4% | 949, 63.4% |
| When they disagree: n | 86 | 180 | 266 |
| … PP exact / UniMERNet exact / either exact | 29.1% / 34.9% / 64.0% | 34.4% / 47.8% / 63.9% | 32.7% / 43.6% / 63.9% |

Agreement between the two image models is weak evidence on its own (agreeing readings are
only 63–70% exact: both models misread the same glyph styles and both take in text-set
parts). **The pipeline with UniMERNet as its image path** (development harness, same code,
UniMERNet readings for the image path and the context votes): strict 86.3% exact (PP: 86.6%),
expression 83.7% (PP: 83.7%), `paths_agree` subset 96.5% exact (PP: 97.2%), 1,415
`must_check` (PP: 1,330). **Decision: UniMERNet is not kept.** The model alone is slightly
better (+0.7 to +2.4 points exact) but the system is not, and it needs a second interpreter.
Speed on this CPU: UniMERNet tiny ~1.0 s per image alone (2.7 s while sharing the CPU), PP-FormulaNet-L ~6.5–7.2 s.

### Seeded manual check (40 equations, render vs MathML)

40 records drawn from all 6,039 Statistics records (seed 1340), each rendered from the PDF
(region, own marks only) beside the chosen reading (LaTeX serialized from the same tree as
the MathML). [Sheets and verdicts](../experiments/out/step13c/manual/).

| Review status | Sample | Correct |
|---|---:|---:|
| `paths_agree` | 23 | **23** |
| `needs_review` | 12 | 10 |
| `must_check` | 5 | 5 |
| **All** | 40 | **38** |

Wrong: a subscript fraction read as a following fraction (`t \frac{α}{2}` for `t_{α/2}`) and
two superscripts missed in `χ² = (Z₁)² + (Z₂)²` (`χ 2`, `(Z₂) 2`). No character was wrong.
Five correct readings are of regions whose Step 13b boundary cuts the expression (a function
name left outside, a closing bracket outside, a region starting or ending mid-expression):
the MathML matches its region; the boundary is the 13b limitation.

### Books 1–4

Against the Step 13b baseline ([comparisons](../experiments/out/step13c/final/)): **0 changed
pages** in native text, layout, reading order, furniture, paragraphs, lists and structure;
0 book-record changes; 0 cache-key changes; 0 changed accuracy metrics (only elapsed seconds).
The final archives add the MathML records (page and book) and the equation image fallbacks.

New equation records:

- **Book 1** (2): the two Step 13b drawn non-math objects (p652 map fragment with a `review`
  owner; p653 inside its map figure). Their drawn shapes have no confident reading
  (`f f x x`, `u r i`); both are `must_check`, output an image fallback and keep their
  objects — no math is invented.
- **Book 2** (182, all text-set statistics: `F(1, 147) = 16.87`, `p < .001`, `(M = 45.08,
  SD = 16.37)`, `β = –.30`, `α = .77`, `η² = .13`, `X²(18) = 55.76`, `(n = 194)`, the rotated
  table notes `*p < .05`): the text and image paths agree on **157**; `paths_agree` 127,
  `needs_review` 34, `must_check` 21. In each of the 25 disagreements the text reading is
  right and the image reading carries a crop artefact (a neighbouring note asterisk read as
  `^{\circ}`, a following letter, a tiny rotated `R²`). Output: text for all 182 (default);
  21 image fallbacks. Rotated table notes are read in their own frame (`p < .05`, not
  `p^{< .05}`) and their crops are turned upright for the image path.
  [Records](../experiments/out/step13c/final/evaluation.json) (`immigrant_children.records_list`).
- **Book 3**: no equations.
- **Book 4** (3, text): `m²)` and the two Step 13a karyotype false positives (`22 + Y`,
  `12 + X`); `needs_review`, output text.

### Time and memory (one worker, CPU; readings cached)

| Book | MathML stage | Peak memory of the stage | Whole run (cached stages verified) | Peak memory of the run |
|---|---:|---:|---:|---:|
| Statistics | 14.5 min (39 min with the 214 shape readings uncached) | 1.5 GB | 24 min | 1.5 GB |
| 1 Spanish US history | 3.9 min | 3.3 GB | 30 min | 10.8 GB (native page jobs, as in 13b) |
| 2 Immigrant children | 3.7 min | 1.2 GB | 18 min | 1.2 GB |
| 3 Art-therapy index | 3 s | 0.1 GB | 2.3 min | 0.2 GB |
| 4 Medical anatomy | 44 s | 0.5 GB | 5.7 min | 0.7 GB |

The image readings were computed once and cached per image: PP-FormulaNet-L read the 5,754
Statistics images in 11.4 h (about 7 s each) plus 182 + 3 + 2 for books 2, 4 and 1 and the
214 shape images; UniMERNet (side environment) read the same 5,754 images in 4.3 h of model
time. Each run hashed its source once.

## Task 5 — tests

`backend/tests/test_mathml.py` (31 tests): scripts, subscripts, bracket groups, fractions,
radicals, overlines (also in pieces), tables; an unknown glyph never gets a character; every
symbol is used once (including rules in pieces and radical signs); shape decisions (votes,
position classes, isolated readings) and learned geometry; image path readings and failures;
MathML 3 validation, brackets, SymPy and arithmetic; agreement, disagreement, image-only and
no-reading cases (`must_check`, original kept, never `paths_agree` without agreement);
invalid reading markup is not recorded; text-set math stays text unless the client asks; the
fallback image is required on the page; naming patterns are validated; comparison folding;
rotated lines and upright crops; the stage end to end without models (image fallbacks,
warning) and with a supplied reader (reference-style parts); **1 vs 2 workers give identical
archives**; **cache closure** (the `mathml` and `formula` scopes cover their imports; a
missing `mathml` dependency of `final` is detected).

Existing tests updated: the stage layout helper of `test_step11c` (knows the new paged
stage), the warning lists of two figure tests (the MathML stage also warns when the test run
has no formula models), and the schema-vocabulary test of `test_boundaries` (MathML element
names are allowed only in `mathml/markup.py`, which writes and reads MathML; DTBook/NIMAS
names stay forbidden everywhere).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **1,021 passed, 0 failed** | [pytest.xml](../experiments/out/step13c/pytest.xml) |
| Six-pages-per-book sample + Statistics sample | PASS: 0 missing / 0 extra on 30 pages | [source crosscheck](../experiments/out/step13c/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step13c/final/full_book.json) |
| I1–I7 on books 1–4 | PASS: all zero on 1,412 pages | `final/after/*_full_gates.json` |
| Every line once (five books) | PASS: owned and ordered once on 2,283 pages | same |
| Books 1–4 identical except the new records | PASS: no page, key, book record or metric changed | comparisons |
| Final archives | PASS: checksums; every region has one MathML record; every output MathML validates (6 invalid image readings carry no MathML, only their problems); `paths_agree` only with agreement; every `must_check` keeps its evidence and has its checksummed fallback image; every traced source resolves | [final_outputs.json](../experiments/out/step13c/final/final_outputs.json) |
| Never invent | PASS: an unreadable glyph gives no reading; image-only readings are `must_check` | tests, archives |
| Ruff (src, tests, Step 13c scripts) | PASS | [ruff_final.log](../experiments/out/step13c/ruff_final.log) |
| Gold, reference, ledger, old projects untouched | PASS | — |
| ENT, mideast, math hold-out not run | PASS | — |
| Statistics (information) | I1–I6 zero; I7 = 1 (p870 index gutter, backlog) | `final/after/statistics_full_gates.json` |

**Run history (for transparency):** the final runs were made twice. The first set passed the
proofs and comparisons; the archive gate then failed on 6 image readings with empty markup,
and the record review found the unused-symbol defect. Both were fixed (invalid reading markup
is no longer recorded; rules in pieces and radical signs count as used), the driver's
producer record was reset because the code had changed, and all five books were rerun.

## Limitations

1. **Image recognition cost on CPU.** PP-FormulaNet-L takes ~6.5–7.2 s per region image on
   this laptop (no GPU); the first Statistics pass read 5,754 distinct images in 11.4 h. The
   readings are cached per image, so reruns cost minutes. The image path runs on every region
   (as specified), including 3,950 text-set expressions whose text path already holds the
   real characters.
2. **Review load.** On Statistics 1,330 of 6,039 records are `must_check` (1,048 of them
   text-set math that stays text; their image reading disagrees, mostly through crop
   artefacts: a neighbouring asterisk, comma or word taken in) and 1,538 `needs_review`.
3. **Structure errors that remain** (development samples and the manual check): subscripts
   after a base whose descent was not learned (`Q₂`), a subscript fraction after a short
   letter (`t_{α/2}`), superscripts at the minimum script size in some numerators, limits
   under a capital-sigma shape read as a letter (`Σ_{(i·j)}`), stretchy radicals drawn from
   pieces, and words in drawn math read letter by letter (`b e t ween`).
4. **Shape labels.** 2 of 210 shapes have no reading (`\hat{y}` composites: 8 occurrences);
   13 take their character from the context votes against the isolated reading (decimal
   point and comma read as bullet and 9 in isolation, upright o/s/v/w read as capitals, a
   prime read as `l`); a few low-vote shapes keep a doubtful isolated reading (colon read
   as `∴`).
5. **The text path is not scored against gold** (the verified gold is drawn math); it is
   measured by path agreement (book 2: 157 of 182 agree) and the manual check.
6. **Gold conventions.** Primes are scored as written in the reference (`p ′`, not a
   superscript); some verified gold rows are themselves wrong (`∝` for `α`). Gold was not
   edited.
7. **Six image readings were empty** (`<msup><mrow/><mrow/></msup>`). The final records keep
   no MathML for an invalid reading (only its problems); none was ever chosen.
8. **Rotated drawn math** is laid out in page orientation (text-set rotated lines are
   turned upright; no rotated drawn equation occurs in these books).

## Decisions for the owner

1. **Image path on text-set math.** It accounts for most of the review load (1,048
   Statistics text-set equations are `must_check`, almost all through crop artefacts) and
   most of the model time; the text path already holds the PDF characters. Keep it (as now),
   or run the image path only on drawn and mixed equations (about one third of the model time)?
2. **Review threshold.** `min_confidence = 0.7` gives 1,330 `must_check` on Statistics; the
   manual check found 5 of 5 sampled `must_check` readings correct. Keep it, or lower it?
3. **UniMERNet is not kept** (the system does not improve and it needs a second
   interpreter). The side environment stays in the git-ignored cache for later comparisons;
   delete it?
4. **Gold conventions** (primes written `p ′`, a few wrong verified rows such as `∝` for
   `α`): accept for further scoring as is, or review the gold first?

Carry-forwards: limits under a letter-shaped sigma, subscript fractions after short letters,
stretchy radicals drawn in pieces, drawn words read as words, and the Step 13b boundary cuts
seen in the manual check.

**Step 13c is complete; nothing beyond it has started.**
