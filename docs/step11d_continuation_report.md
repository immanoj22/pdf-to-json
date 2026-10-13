# Step 11d continuation — opaque covers and character evidence

Status: **complete for review.** Hidden text is recorded as diagnosis-only evidence after
its applied form regressed four visible-only units on Spanish page 215. Character evidence
is a new flags-only stage. In the final combined run every semantic output equals the
frozen Step 11e baseline. Step 12 has not started.

Sections up to the page 215 counterfactual are the earlier diagnosis; their candidate and
decision counts (72 invisible, 306 already excluded and 23 review spans in Spanish; 18
invisible in medical) were re-confirmed from the layout evidence of both full runs.

## Scope and frozen baseline

The baseline is `ad1acfcd2ebe7108bd717bb3a74be832ed10f473` (Step 11e).
Its known page 724 accuracy regression remains part of the frozen baseline;
this continuation does not change the I5 credit fallback or unknown-line ordering.
Only Spanish US history, immigrant children, art-therapy index and medical anatomy
are run. The sealed ENT hold-out, the mideast robustness book, the mismatched pair
and unregistered originals are not run. References, gold and old projects remain
read-only. `.vscode/settings.json` remains untouched and untracked.

The initial tracked tree was clean. Free space was 39,468,625,920 bytes; the
11c estimate of 1,412 × 12 MiB leaves more than 10 GB. Capacity is checked again
before full variant runs. The baseline was captured before any backend edit.
All four books reproduce every prior metric except measured elapsed time.
Per-page native, analysis and downstream identities match the frozen 11e outputs.
All 1,412 pages pass I1–I7 and exact line assignment/order. The unchanged six-pages-
per-book sample has zero missing/extra tokens. Book 1 has exactly 495,751 retained
tokens; its original ledger and TrimBox discard accounting remain unchanged.

Evidence: [provenance](../experiments/out/step11d2/before/provenance.json),
[completion](../experiments/out/step11d2/before/complete.json),
[sample](../experiments/out/step11d2/before/source_crosscheck.json),
[ledger](../experiments/out/step11d2/before/full_book.json), and the four per-book
identity, full-gate and metric files in [the baseline directory](../experiments/out/step11d2/before/).

## Diagnosis before implementation

The supported evidence class is an exactly attributed glyph occurrence, fully
inside the inscribed core of a later opaque fill with supported effective context,
whose suppression changes no pixels at 144 and 288 dpi. Attribution uses decoded
Unicode, font identity, exact glyph origins, multiplicity and occurrence order.
Nonprinting native controls may match an empty space glyph only at the exact
origin/font. Ambiguous occurrences remain unproven. Native text is never replaced.

MuPDF executes nested forms and their resource/transform state. The diagnostic
records the form invoker graph and device state at each paint: clip/mask lifetime,
group alpha/blend/knockout, optional layers and pattern tiles. Unsupported contexts
are review observations. Supported paths are exact rectangles or verified
inscribed rounded-rectangle cores, not arbitrary path bounding boxes.

Suppression rebuilds only the exact selected glyph items, preserving the remaining
text matrices, glyph IDs, advances, bidi state, writing mode and language. The
renderer follows PyMuPDF's display-list path. Every tested crop first requires
byte-for-byte agreement with ordinary `Page.get_pixmap`; a mismatch invalidates
the test. The comparison covers the glyph union plus a relative one-em border.
Earlier direct-device rendering was rejected because it differed from PyMuPDF on
some pages. No visibility result from a failing passthrough check was accepted.

| Book | Evidence class | Candidate spans | Render-confirmed | Visible controls | False positives |
|---|---|---:|---:|---:|---:|
| Spanish US history | Opaque cover | 378 | 378 | 320 | 0 |
| Immigrant children | Opaque cover | 0 | 0 | 293 | 0 |
| Art-therapy index | Opaque cover | 0 | 0 | 318 | 0 |
| Medical anatomy | Opaque cover | 18 | 18 | 271 | 0 |

All 396 candidates passed both resolutions. All 1,202 controls were independently
visible under suppression, and none was selected by the screen. This is a measured
sample false-positive rate of zero, not an exhaustive guarantee for arbitrary PDFs.
Twenty-three additional Spanish cover observations have unsupported context and
remain visible. Zero candidates in another book is not proof of exhaustive visibility.

Of the Spanish candidates, 306 spans are exactly the already excluded 170 lines /
476 tokens from the earlier TrimBox group. They are counted separately. Newly
confirmed retained text is 72 spans / 56 source lines / 173 distinct ledger tokens
in Spanish and 18 spans / 6 lines / 35 tokens in medical anatomy. No token is
partially hidden across a mixture of confirmed and unconfirmed owner spans.

Reference checks are whole-document normalized substring checks, not independent
occurrence alignment: 45 Spanish candidate-span phrases occur somewhere in the
reference and 333 do not; medical counts are 11 and 7. Short labels and numbers can
occur elsewhere. Reference presence is never used to decide visibility.

Evidence: [diagnosis and ledger/reference context](../experiments/out/step11d2/diagnosis.json),
the per-book `*_validated.json` files in [hidden evidence](../experiments/out/step11d2/hidden/),
and [synthetic guards](../experiments/out/step11d2/diagnostic_guards.json).

## Page 215 and heading counterfactual

The ordinary visible-mode English lesson paints are genuinely covered. A page-level
soft-mask resource does not mean the later covering fill is inside an active mask.
The per-operation state and independent render tests establish opacity for these
specific occurrences.

The earlier 48 uncertain lines / 174 tokens resolve into 40 hidden lines / 126
tokens and eight visible Spanish lines / 48 tokens. Every one of those eight lines
changes pixels under suppression and has complete nonblank attribution. The new
screen also finds four previously omitted hidden lines / eight tokens. Thus the
page's total is 60 confirmed spans / 44 lines / 134 tokens.

The read-only counterfactual projects confirmed spans into the existing invisible
mechanism in memory, rebuilds layout/order/furniture view/paragraphs/page evidence,
and re-runs the whole-book heading decision with other pages and book context fixed.
The baseline page paragraphs and whole-book headings were reproduced exactly first.
The original span store is unchanged.

| Mixed-language heading before | Before | Counterfactual after |
|---|---|---|
| LEARN + Spanish lesson title | Level 2 | No longer a heading |
| INQUIRY + Spanish activity title | Level 2 | Spanish title, level 1 |
| REVIEW + Spanish review title | Level 2 | Spanish title, level 1 |

For this single-page counterfactual, heading precision changes from 0.736111 to
0.737391 and F1 from 0.789699 to 0.790435. Recall and measured level accuracy stay
identical. This does not substitute for the full hidden-only production measurement.

Evidence: [visibility resolution](../experiments/out/step11d2/page215_resolution.json),
[counterfactual](../experiments/out/step11d2/counterfactual_spanish_us_history_215.json),
[heading scores](../experiments/out/step11d2/counterfactual_heading_scores.json).

## Resumption and safety copy

Codex stopped at a usage limit with the hidden-only run measured but not analysed, no
character-flag product code, and no commit. Before any edit, the tracked diff, the full list
of untracked files and copies of every untracked source, test, script and document file were
saved to the git-ignored `.cache/step11d2_backup/` with SHA-256 sums. Large outputs were
listed, not copied. The executed hidden-only producer bytes were confirmed identical to the
snapshot in [tools/hidden_only](../experiments/out/step11d2/tools/hidden_only/sources.json),
so the hidden-only measurement describes the code it claims to describe.

The final archive folders written by the earlier Codex sessions deny read access to this
session's Windows identity (Python creates them through a private temporary directory).
No evidence below depends on them: the hidden-only analysis reads the per-page caches, and
the combined run wrote new archives.

## Hidden text alone: measured, then withdrawn

The hidden-only variant hid every render-confirmed span before line building. All four
books ran fully with one worker and one source hash. All 1,412 pages had I1–I7 zero and
every line in exactly one unit and ordered once. Native and analysis models and keys were
unchanged. Layout changed on every page by the new evidence field; outside the pages below,
a field-by-field audit found no other layout difference.
[Layout/furniture audits](../experiments/out/step11d2/hidden/).

### Book 1: every changed unit

Units are matched by kind, stream kind, list membership, level and stable span IDs. Each
unmatched unit is judged against the derived reference with the benchmark's own definitions:
paragraph exactness, pieces and merges; list-item kind agreement; heading matching; and
page-restricted reading order. "Hidden" means the unit holds a render-confirmed span.
Complete rows, reference outcomes and order pairs are in
[unit_table_spanish_us_history.json](../experiments/out/step11d2/hidden/unit_table_spanish_us_history.json).

| Page | Changed units | Contain a hidden line | Worse | Reason |
|---:|---:|---:|---|---|
| 90 | 3 | 2 | none | Hidden duplicate map label `20° N` leaves a figure-text unit |
| 118 | 6 | 2 | none | Hidden duplicate `La.` leaves; two visible figure labels merge into one figure-text unit; reference figure 3459 unchanged |
| 215 | 47 | 35 | **4 visible-only units** | See below |
| 330 | 4 | 3 | none | Hidden duplicate `SAUDI`/`ARABIA` map labels leave a figure-text unit |
| 435 | 3 | 2 | none | A hidden copy of the CONÉCTATE callout text leaves; the visible callout unit is unchanged against the reference |
| 662 | 13 | 11 | none (heading better) | Hidden map title/legend duplicates leave; the false heading `EL MUNDO` disappears |

Page 215 detail. Removing the hidden English lesson labels leaves the visible Spanish table
of contents. The unchanged table detector then reads entries 04–07 as an aligned table.

| Unit after the change | Hidden line | Verdict | Reason |
|---|---|---|---|
| `04 Una economía en crecimiento 207` (table text) | no | worse | Reference list item 5280 loses list-kind agreement |
| `05 Política y cultura afroamericanas 213` (table text) | no | worse | Reference list item 5281 loses list-kind agreement |
| `06 Análisis de fuentes: El Renacimiento Harlem 217` (table text) | no | worse | Reference item 5285 loses list-kind agreement (it also becomes one exact piece instead of two) |
| `07 Un choque de valores 223` (table text) | no | worse | Reference list item 5282 loses list-kind agreement |
| Entries 02, 03, 08; three Spanish lesson headings; caption; figure text | no | same | Only hidden English copies left them |
| 25 `invisible` units | yes | same | Hidden English labels and page-number placeholders |

The new table stream also adds one table anchor that misses (expected after reference unit
5279, predicted after 5284), moves four units out of the main flow (30 correctly ordered
main-flow pairs leave the comparison) and adds one discordant within-float pair. The three
mixed English/Spanish headings disappear; two Spanish headings appear, both still unmatched
by the reference. Eight further pages change only heading evidence counts ("recurring title
on 10 pages" becomes 11), with no heading decision change.

Under the owner's rule, four visible-only units getting worse is a **regression**. Its cause
is the table detector's reaction to the remaining visible text, not a wrong visibility proof.
No general narrowing of the hiding rule targets that reaction without also dropping the
page's legitimate hidden text, so the behaviour change is withdrawn: **hidden text is
diagnosis only** (see Implementation).

Hidden-only book 1 metric changes, for the record: list-kind agreement 0.874878 → 0.872931,
list-boundary F1 0.686001 → 0.684856, table anchors 0.941176 → 0.927536, float anchors
0.900488 → 0.899878, within floats 0.921729 → 0.92168, Kendall tau 0.908958 → 0.908949,
heading precision 0.736111 → 0.738676 and F1 0.789699 → 0.791173, paragraph exact units
13,601 → 13,602. Lines rise 84,085 → 84,116 because hidden spans split from mixed lines.
[Comparison](../experiments/out/step11d2/hidden/comparison_spanish_us_history.json).

### Books 2–4

| Book | Downstream pages changed | Result |
|---|---:|---|
| Immigrant children | 0 | Identical except the empty evidence field and elapsed seconds |
| Art-therapy index | 0 | Identical except the empty evidence field and elapsed seconds |
| Medical anatomy | 6 (74, 92, 166, 184, 198, 226) | Exactly the 18 expected spans: one hidden chapter running head per chapter-opener page |

On each medical page the whole running-head line is render-confirmed hidden. Its caption
unit becomes `invisible` (captions 379 → 373). Each was a correctly anchored callout float,
so leaving the score lowers callout anchors 0.738095 → 0.725 and float anchors
0.606 → 0.601215. Book-wide furniture repetition evidence shifts on 287 pages ("recurs on
287 pages" becomes 281), with no role change outside the six pages. Every changed medical
unit contains a hidden line and none is worse, so this is accepted under the rule and
documented. [Medical unit table](../experiments/out/step11d2/hidden/unit_table_medical_anatomy.json).

## Character evidence alone

A flags-only stage after lists reads native spans, layout lines, final list units and the
source PDF for glyph names. It attributes glyphs with the paint audit's exact matching. Two
general tests use only Unicode properties and the font's own glyph names; there is no
code-point, font, book or page list.

1. **Name disagreement.** A glyph name that the strict glyph list reads as one character,
   compared after NFKC and case folding with what the PDF decodes. Decodings to format
   characters (soft hyphen) are exempt. A glyph decoding to several characters agrees when
   the name denotes the whole sequence (ligature) or its first character.
2. **Repeated marker.** A letter, number or control/unassigned character set off as a list
   marker (an accepted unpunctuated bullet marker, or a set-off glyph opening a visual line),
   whose glyph has no readable name or a disagreeing one, when the same glyph of the same font
   is such a marker at least twice in the book.

Flags carry span and line IDs, reasons, a rule-strength confidence (0.7–0.9, not a calibrated
probability) and glyph evidence as code points. Original and NFKC text are never changed;
the driver asserts the span store is byte-identical before and after every page.

Measured on the frozen baseline inputs. Flags feed no stage, so every other output is the
baseline by construction. [Flags per book](../experiments/out/step11d2/flags/).

| Book | Flagged spans | False positives | Strict initial comparison (glyphs) |
|---|---:|---:|---:|
| Spanish US history | 0 | 0 | 291 |
| Immigrant children | 0 | 0 | 0 |
| Art-therapy index | 0 | 0 | 0 |
| Medical anatomy | 677 | 0 (all in the two diagnosed classes) | 1,013 |

Medical flags cover all 538 cube markers decoded as `Ǌ` (519 by both tests, 19 by name only)
and 139 of 142 arrowhead markers decoded as `¾` (repeated-marker test). Three isolated `¾`
remain unflagged. The strict initial comparison flags small capitals (`H.smcp` → `h`), soft
hyphens and, in Spanish, 219 table-of-contents dot-leader glyphs (a `space` glyph decoding to
` .`). The first measurement of this stage flagged 10 Spanish leader spans; that led to the
first-character agreement clause, before any final run. The six beta-shaped `b` in book 2 are
not detectable by these tests, because their misleading name agrees with their misleading
Unicode. "Zero false positives" means none among the flags raised on books 1–3; recall
outside the medical witnesses is unverified.

## Rejected marker experiment: one statement

Removing the Unicode-category veto for set-off markers **hurt Spanish US history and
immigrant children and changed nothing on art-therapy index or medical anatomy.** Spanish
(pages 349, 427): exact paragraphs 13,601 → 13,600, merges 720 → 721, boundary F1
0.942767 → 0.942733. Immigrant children (pages 69, 256): exact paragraphs 515 → 511,
merges 57 → 60, boundary F1 0.854041 → 0.849910. Art-therapy index and medical anatomy have
no changed pages and no changed accuracy field. This was recomputed from the
[marker metric summaries](../experiments/out/step11d2/markers/metrics/). List classification
is unchanged in the product.

## Implementation

- `paint/`: occurrence-level paint evidence as its own cached stage. One comment was
  reworded for the schema-vocabulary guard, which re-keys paint.
- `layout/pipeline.py` records the evidence on each page and adds a span review flag for
  every `invisible` or `review` decision. **Lines keep native visibility**;
  `layout/lines.py` is back to its committed form.
- `characters/` is the new flags-only stage: models, glyph names, rules and cache. It is
  registered with dependencies on lists and paint, and the final stage depends on it.
- `book_run.py` runs the character stage after lists. Final pages carry
  `visibility_evidence` and `character_evidence`, and the final-archive key includes the
  character key.
- Tests: paint tests follow the diagnosis-only contract. Six character tests cover the
  rules, book-level repetition, text preservation on a synthetic PDF whose ToUnicode maps a
  bullet glyph to `Ǌ`, the final archive and a missing dependency.

## Combined run (final product)

All four books ran fully with the final producer, one worker and one source hash.

| Book | Pages | Downstream digests vs baseline | I1–I7 | Every line in one unit, ordered once | Span review flags | Character flags |
|---|---:|---|---|---|---:|---:|
| Spanish US history | 758 | identical | all zero | PASS (84,085 lines) | 95 | 0 |
| Immigrant children | 331 | identical | all zero | PASS | 0 | 0 |
| Art-therapy index | 9 | identical | all zero | PASS | 0 | 0 |
| Medical anatomy | 314 | identical | all zero | PASS | 18 | 677 |

Layout pages differ from the baseline only by the added evidence and span review flags,
checked field by field on every page. Reading order, furniture, paragraphs, structure and
lists are identical on every page and book-wide. The only changed metric field in any book
is elapsed evaluation seconds. Every accuracy and count field is identical, including the
inherited Step 11e page 724 limitation.
[Combined comparisons, audits and gates](../experiments/out/step11d2/combined/).

Cache keys: native and analysis are unchanged in all books. Paint and character keys are new.
Layout re-keys because its producer and the paint key changed. Reading order, furniture,
paragraphs, structure evidence, structure decisions and lists re-key through their
dependency closure with unchanged producers.

Source and ledger, from the combined final archives: the frozen Step 11d six-pages-per-book
sample (Spanish 33, 283, 435, 441, 535, 626; immigrant 153, 198, 203, 209, 282, 330;
art-therapy 2–7; medical 65, 69, 78, 203, 207, 232) has 0 missing and 0 extra tokens on all 24
pages. The full Spanish ledger has exactly 495,751 node tokens with every ledger gate true.
Final-archive retained tokens are 495,751, 124,017, 4,249 and 95,957 for books 1–4. Every
archive file checksum, source and unit digest, line/span reference, visibility proof and
character flag resolves; the archives hold 677 character flags for medical anatomy and none
elsewhere, identical to the flags-alone measurement.
[Source crosscheck](../experiments/out/step11d2/combined/source_crosscheck.json),
[ledger](../experiments/out/step11d2/combined/full_book.json).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| Hidden text alone, book 1: every changed unit classified | Done; **regression found** on page 215 (4 visible-only units) | Unit table above |
| Response to the regression | Behaviour withdrawn: diagnosis only, no behaviour change | Combined run identical to baseline |
| Hidden text alone, books 2–4 | Medical only (6 pages, 18 spans), accepted; books 2–3 unchanged | Comparisons and medical unit table |
| Character flags alone | Books 1–3: 0 flags, 0 false positives; medical 677 | Flag files |
| Character flags general and flag-only | PASS: no code-point/font/book list; span store byte-identical | Rules module; driver assertion |
| Combined run, all four books | PASS: all downstream digests and accuracy fields identical | Combined comparisons |
| Full-book I1–I7, 1,412 real pages | PASS: all zero | `combined/after/*_full_gates.json` |
| Every line in exactly one unit and ordered once | PASS on every page of all four books | Same files |
| Spanish ledger 495,751 | PASS | Ledger file |
| Six-pages-per-book sample | PASS: 0 missing / 0 extra on 24 pages | Source crosscheck |
| Full tests | PASS: 902 passed, 0 failed (881 Step 11e + 11 paint + 6 character + 4 new cache-scope cases) | `pytest_final_core.xml` |
| 1 vs 2 workers byte-identical, PDF hashed once | PASS (`test_workers_and_production_are_byte_identical_and_hash_pdf_once`) | Same |
| Cache closure with a missing dependency | PASS (`test_missing_upstream_dependency_is_detected`, paint and character variants) | Same |
| Ruff from `backend/` | PASS: checks and format on src, tests and all `step11d2_*` scripts | `lint_final.log` |
| Native and analysis keys unchanged | PASS in all four books | Combined performance records |
| One-worker default, single source hash in real runs | PASS: all four runs used one worker and one source hash | Same |
| Rejected marker experiment | Hurt Spanish and immigrant only | Marker statement above |

The five furniture-book tests read Step 8 caches for the current layout key, so they run after
the combined runs; they are included in the 902. The 58 MB field-level page diff of the
rejected hidden-only variant is not committed; regenerate it with
`step11d2_run.py details --book spanish_us_history --variant hidden`.

Not run: the sealed ENT hold-out, the mideast robustness book, the mismatched pair and any
unregistered file. References, gold, the ledger and old projects were not edited.
`.vscode/settings.json` remains untouched and untracked. **Step 12 has not started.**
