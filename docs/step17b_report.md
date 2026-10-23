# Step 17b — pre-freeze checks

The visual investigation found three general publication defects: letter dividers
were being overridden by generic headings; explicitly cell-owned text retained an
obsolete figure-text role; and shallow map paths and box borders could be mistaken
for underlines. These are corrected in assembly. All five new publications have
exactly **0 missing / 0 extra** retained and discarded tokens, zero schema/contract
defects, identical JSON round trips and verified manifests. Every content-unit ID,
text, source run, source reference and geometry is unchanged. Fresh every-page checks
pass on books 2–5: I1–I7 are zero on books 2–4; Statistics retains the allowed I7 = 1.
Spanish's fresh invariant pass hit the disk reserve. With explicit user approval,
its unchanged Step 17 proof is reused after checking all 3,032 input cache
fingerprints/payload checksums and rechecking every file's exact bytes. Its receipt
explicitly records `fresh_every_page: false`. Final freeze acceptance is
authoritative only in `experiments/out/step17b/final/validation_record.json`.

The weakest reference styling cells do not all indicate incorrect visible styling.
Of 160 sampled detected spans across content and furniture, **148 were correct,
12 wrong and none unclear**. Five
anatomy heading separators remain a documented ambiguity; no rule fitted to their
colour, column width or font has been introduced.

| Book | Dividers before / after | Figure-text paragraphs before / after | Underline spans before / after | Reviews before / after |
|---|---:|---:|---:|---:|
| Spanish history | 1 / 44 | 0 / 0 | 1,942 / 1,351 | 2,686 / 2,684 |
| Immigrant children | 0 / 0 | 0 / 0 | 0 / 0 | 112 / 112 |
| Art therapy | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Medical anatomy | 1 / 26 | 56 / 0 | 58 / 58 | 1,065 / 1,009 |
| Statistics | 1 / 21 | 934 / 204 | 1,104 / 1,104 | 3,636 / 2,906 |

Spanish's 44 dividers comprise 25 index and 19 glossary letters. All 15 inspected
pages now match the hand-counted divider letters exactly. Published heading counts
change 555→512, 232→232, 2→2, 649→624 and 1,223→1,203 in the table's book order.
Table-text paragraph counts change 156→156, 17→17, 0→0, 14→70 and 313→1,043.
The 56/730 relabelled cell paragraphs keep their existing ownership and text.
The two removed Spanish heading reviews belonged to newly classified dividers;
the 56/730 removed figure reviews were the obsolete cell-text warnings.

All **148 correct** sampled spans are retained in full. All seven sampled Spanish
false underlines are removed; the five wrong anatomy separators remain.
An unclear bold panel letter in the superseded content-only sample also remains
unchanged, with its original judgment retained. The 591-span Spanish underline reduction is a full population
count, not a new precision estimate. All non-underline style decisions are exactly
unchanged on all five books, including every furniture field. Complete
per-kind/context/type/role/review counts and sample character coverage are in
`all_text_style_census.json`, `final/changes`, `final/all_text_sample_after.json`
and the initial cohort's `final/sample_after` under
`experiments/out/step17b`. Step 17's old reference styling scores remain historical
measurements of that producer; this audit does not claim new population precision.

| Book | New local publication |
|---|---|
| Spanish history | [book.json](../.cache/step11d2/final_books/step13/book-f3269459838bbee02da0b569340cc7a571609eec280316e1b052cd0f7d9836f7/book.json) |
| Immigrant children | [book.json](../.cache/step11d2/final_books/step13/book-488f93069c75f931fe846f20a37becaf4d8978b52778a508e075e6231aca6f5d/book.json) |
| Art therapy | [book.json](../.cache/step11d2/final_books/step13/book-e8a58f200fc854b221defde1b584eda2746f64fe185379752883ed3c5abeee87/book.json) |
| Medical anatomy | [book.json](../.cache/step11d2/final_books/step13/book-6f3258562703950360b40be509c1e2c82eb908994ba980fbd531f6c13714ff4d/book.json) |
| Statistics | [book.json](../.cache/step13/final_books/final/book-c93a655da73ebae222152f221bb7a4670d75264e1c16136a6f70bc68f52da5f9/book.json) |

The original Step 17 publications remain unchanged at the paths and hashes in
`experiments/out/step17b/inputs.json`. Each new folder also contains its verified
manifest, images and review crops. Publication times and peak memory are recorded
separately from the unchanged archive measurements in `final/performance`.

## Rendered styling audit

The population is the frozen Step 17 publication, not an earlier experiment's
candidate set. Seed **17023**, with an independent `Random("17023:<book>-<kind>")`
stream per cell, selects 20 spans uniformly across the full book's content and
furniture. Population order is content traversal followed by the furniture array.
Headings are eligible, but are not the only eligible context. Bold-italic counts in both kinds.
All 160 targets have a source box and were compared with rendered PDF crops.

| Book / detected kind | Population | Correct | Wrong | Unclear |
|---|---:|---:|---:|---:|
| Statistics bold | 10,504 | 20 | 0 | 0 |
| Statistics underline | 1,104 | 20 | 0 | 0 |
| Statistics subscript | 185 | 20 | 0 | 0 |
| Immigrant children bold | 296 | 20 | 0 | 0 |
| Anatomy bold | 3,514 | 20 | 0 | 0 |
| Anatomy italic | 2,776 | 20 | 0 | 0 |
| Anatomy underline | 58 | 15 | 5 | 0 |
| Spanish underline | 1,942 | 13 | 7 | 0 |

Population counts by serialized semantic context (overlapping, so columns need
not sum to the population):

| Book / kind | Headings | Table headers | Captions | Index entries | Furniture | On index pages |
|---|---:|---:|---:|---:|---:|---:|
| Statistics bold | 1,316 | 2,062 | 916 | 0 | 1,292 | 25 |
| Statistics underline | 243 | 0 | 15 | 191 | 0 | 191 |
| Statistics subscript | 2 | 11 | 1 | 0 | 0 | 0 |
| Immigrant children bold | 196 | 2 | 12 | 0 | 0 | 2 |
| Anatomy bold | 670 | 212 | 325 | 0 | 418 | 36 |
| Anatomy italic | 168 | 58 | 122 | 350 | 17 | 350 |
| Anatomy underline | 50 | 0 | 0 | 0 | 0 | 0 |
| Spanish underline | 10 | 1 | 136 | 0 | 0 | 0 |

Table headers include row and column headers. “Index” here means content in a
serialized index list; the printed index letter headings are audited separately.
“On index pages” also includes title/letter headings outside those lists, using
each content unit's first source page or the furniture page. This is a separate
overlapping page context. The explicit page sets are in
`index_page_style_census.json`.
These context labels are not an independent visual annotation of every detected
span. Counts are detected spans, not aligned reference tokens or recall estimates.

The initial audit accidentally excluded furniture. Its 160 targets and original
147 correct / 12 wrong / one unclear judgments are preserved in `style_verdicts.json`.
The correction adds 1,292 Statistics bold, 418 anatomy bold and 17 anatomy italic
spans to those cells' populations, then resamples and visually reviews all 20
targets in each affected cell. The other five cells have no relevant furniture
and keep exactly the same seeded samples. The new cohorts include three Statistics
and five anatomy bold furniture targets; the anatomy italic seed selects none.
The 60 new cohort targets have 12 contact sheets and explicit per-target visual
notes. These are additional cohort reviews, not independent double annotation.
The original unclear panel D is outside the replacement sample, not resolved by it.

The wrong anatomy underlines (samples 5, 7, 8, 9, 11; physical pages 128, 157,
284, 271, 175) are magenta column-wide heading separators. Their straight strokes
are real, but interpreting them as a text style is wrong in these crops. A new
universal distinction from intentional heading underlining was not established.
This remains backlog. The initial cohort's unclear anatomy bold target is a single panel letter D.

Spanish wrong samples 5, 6 and 12 (pages 562, 596, 342) are checkmark glyphs over
the bottom edge of filled label boxes. Samples 15 and 17 (page 663) intersect river
paths; sample 16 (page 90) intersects a map border; sample 19 (page 746) intersects
a curved graticule. The source primitives confirm these causes. Shallow bounding
boxes alone had admitted these drawings as underlines.

The Statistics samples include visibly bold table labels, caption labels and
exercise numbers; visible hyperlink underlines; and actual mathematical
subscripts. Immigrant bold and anatomy italic samples are also printed styles.
Disagreement with reference emphasis markup alone does not prove these detections
wrong. The small sample establishes neither full-book precision nor recall.
The published JSON does contain bold/italic spans in headings; Step 17's statement
that the default avoids those spans does not describe these publications.

The final 160 judgments, text ranges, page numbers and crop paths are in
`experiments/out/step17b/all_text_style_verdicts.json`; summaries and complete
before/after populations are in `all_text_hand_check_summary.json` and
`all_text_style_census.json`. The 32 initial five-target contact sheets and 12
additional cohort sheets are under `sheets`. This is a single visual review.
Some new targets use their owner's broader crop when reconstructed text differs;
the actual target was identified manually, including cross-column crops. These
fallbacks are explicit in each row's `box_method` and visual note.
Three repeated strings in ID-less table fragments needed exact source-reference
disambiguation. Two original crop locations were correct; the Statistics subscript
sample 11 crop pointed to another occurrence of `2` on the same page. Its corrected
source-reference crop shows the lowered `2` in CO2 and was reviewed again as correct.
The original crop is retained. `target_disambiguation.json`, `target_recheck/` and
`target_visual_recheck.json` record this correction; no judgment count changes.

## Printed index letter dividers

Three leaves per book were inspected at full-page size. Spanish, immigrant,
art and anatomy use the first, middle and last index pages. Statistics has only
two populated index leaves; its third printed Index leaf is blank apart from the
running head and was also inspected. Physical PDF page numbers are used below.

| Book | Pages | Printed dividers per page | Step 17 JSON per page |
|---|---|---|---|
| Spanish | 685 / 702 / 719 | 1 (A) / 0 / 3 (W,Y,Z) | 0 / 0 / 0 |
| Immigrant children | 308 / 318 / 327 | 0 / 0 / 0 | 0 / 0 / 0 |
| Art therapy | 1 / 5 / 9 | 0 / 0 / 0 | 0 / 0 / 0 |
| Anatomy | 305 / 310 / 314 | 2 (A,B) / 2 (M,N) / 4 (W,X,Y,Z) | 0 / 0 / 1 (X) |
| Statistics | 869 / 870 / 871 | 17 / 4 (T,U,V,Z) / 0 | 1 (A) / 0 / 0 |

Statistics page 869 prints A,B,C,D,E,F,G,H,I,L,M,N,O,P,Q,R,S.
Immigrant and art samples use spacing between alphabetic groups and print no
letter dividers. Detection is weak in Spanish, anatomy and Statistics: the letters
are present as generic headings, but assembly had required `heading is None`
before making an `index_divider`. The original Spanish single divider J is in
the glossary, not the index. Across all relevant navigation pages the newly
eligible heading candidates are 43 Spanish (25 index, 18 glossary), 25 anatomy
and 20 Statistics; all are single letters. Other short body headings are excluded
by the existing navigation context. Page images and explicit hand counts are in
`index` and `index_hand_count.json`.

## Statistics figure-text audit

Thirty paragraphs were selected uniformly from the **934** published paragraphs
with role `figure_text`, using seed `17023:figure_text`.

| Visual cause | Sample count |
|---|---:|
| Axis labels | 0 |
| Table fragments, including formulas inside cells | 24 |
| Equation parts outside that category | 1 |
| Complete prose paragraphs | 0 |
| Exercise enumeration numbers | 4 |
| Prose fragment introducing an inline formula | 1 |

This classification does not assign every fragment to a figure. A complete JSON
ownership trace finds **730 of the 934 already inside explicit table cells**;
204 are outside cells. All **56** similarly flagged anatomy paragraphs are also
inside cells. Spanish, immigrant and art have none. Step 17's description of
all 934/56 as unresolved figure ownership therefore overstates that workload.
The cell nesting and text are already present; publication was carrying forward
an earlier `figure_text` role and adding an inappropriate missing-figure warning.
The remaining 204 Statistics fragments have insufficient evidence for a general
new ownership assignment. The sample is not an estimate of their distribution.

See `figure_verdicts.json`, the ten three-target contact sheets, and the complete
`figure_ownership_trace.json` under `experiments/out/step17b`.

## Rotated map labels

The relevant equation rule is `equations.text.line_runs`: `_split_at_scripts`
is called only for `line.horizontal`. Rotated label letters with different sizes
or baseline offsets must not be split into an equation base and its script.
Projection in `line_characters` uses the line's own writing direction.

The separate assembly safeguard `assembly.text._source_grouped` reunites spans
when layout pieces interleave original source lines. It uses explicit native
source-line sequences, not `(y,x)` or serialized dictionary-key order. A complete
Spanish archive trace finds this safeguard changes two table-text units; that
trace is not evidence that this assembly rule fixed the rotated map labels.

Step 17 had no dedicated label regression at 90°, 270° and an arbitrary angle.
Its extraction page-rotation test and rotated-math test do not establish that
coverage. `backend/tests/test_step17b.py` now adds both
`test_rotated_label_letters_are_not_equation_scripts` and
`test_interleaved_rotated_source_lines_reconstruct_without_split_tokens`, each at
90°, 270° and **37°**. The former uses a mixed-size, offset two-letter label;
removing the horizontal-only guard causes a false equation. The latter verifies
whole label text and exact 0/0 ledger reconstruction after interleaving and cache
key sorting. These are synthetic regression cases, not new full-book accuracy
measurements. No rotated-label production rule changed in Step 17b.

## General fixes and validation

1. A standalone alphabetic label on an established index/glossary page, without
   locators and occupying one line, can become a divider even if the structure
   stage called it a heading. Table-cell content is excluded from this rule.
   Outline and section heading targets must still name published heading nodes.
2. Explicit table-cell content supersedes the earlier figure-text paragraph role.
   The node becomes `table_text`, records table provenance and loses only the
   obsolete missing-figure warning. Other review flags, text, IDs, geometry,
   references and cell ownership remain intact. Outside-cell fragments retain
   their warnings.
3. An underline candidate must be an actual horizontal straight stroke or a thin
   filled rectangle. A shallow curve/polyline box is insufficient. A stroke
   coincident with a larger rectangle edge is a border. Tolerance comes from
   coordinate rounding and stroke width, with no book, page, colour or font rule.

Five regression tests first reproduced the publication defects; all 11 publication
regressions pass after correction. All 56 focused assembly/regression tests pass.
Three additional audit-reader regressions preserve ordinary table evidence and
reject changed cache identities. The final
production source and test hashes are frozen in `final/epoch.json` under
`experiments/out/step17b`; the two-letter rotation case was strengthened before
the full suite, with an explicit hash revision receipt. Only assembly is rebuilt.
The semantic archives, Step 15/16 baselines and Step 17 publications are retained.

An initial full-suite attempt used an excessively long audit temporary path. The
equation worker test reproduced a Windows file-open failure at a 260-character
temporary filename, then passed unchanged under `.s17bt/eq`. That invalid suite
was interrupted and its log retained. The final full suite uses a new short
directory; no converter workaround for this test-path issue was added.

Concurrent publication/proof work also temporarily reduced measured free space
below the reserve. Both jobs were stopped; free space returned to 8.45 GB without
deletion. The audit's test directories accounted for about 126 MB. Temporary
system allocation pressure is suspected; this is not a measured attribution to a
specific paging mechanism. A later long-lived sequential queue also hit 4.51 GB
during the Spanish invariant pass, after completing all five JSON checks. Its
monitor stopped it; space returned to 7.77 GB without deletion. The remaining
gates run in a fresh process per book/phase, monitored individually. The available
memory/pagefile counters do not establish the spike's cause. The interrupted
proof has no final receipt and is not accepted as a passing gate. See
`space_audit.json`, `space_retry_audit.json` and `test_path_failure.json`.
The isolated Spanish retry also stopped after its page-650 progress message,
at 3.97 GB free, then recovered to 7.77 GB. Process isolation did not resolve this
particular gate. Its preserved Step 17 proof matches the committed bytes, the four
input cache keys and all non-assembly producer hashes. A separate fingerprint/payload
checksum closure passes for all **3,032** native/analysis/layout/list cache files,
with at least 7.77 GB free. The proof hash is
`696e8e7e038563559cb0d02a91e9e707e301f0e0a2b4bc944a119c1b074b06f1`.
This establishes input closure, not a fresh invariant calculation. The user explicitly
approved only this proof reuse in `proof_reuse_approval.json`. The guarded `reuse_proof`
action rechecked every closed file's byte hash and passed, with `fresh_every_page`
false and at least 7.75 GB free. Books 2–5 completed fresh invariant checks with at
least 7.77 GB free. The approval does not replace assembly, table, continuity,
lossless, schema, reference evaluation, worker or final test checks.

The initial independent Spanish parity attempt completed both assembly passes,
then hit the reserve while rebuilding table evidence; its equality result was not
checkpointed and is not accepted. The interrupted monitor is retained. One native
cache envelope expands to 727 MB before typed construction. The audit-only bounded
reader verifies cache fingerprints/checksums, validates table-consumed object fields
and path items, and leaves paths re-iterable without retaining every typed vertex.
Unused native render glyphs and paint commands are not table inputs; this is not a
fresh native-object invariant calculation. The original table evidence, ruling,
freeform and comparison algorithms are unchanged. Three synthetic regressions and
**20 real-page comparisons across all five books** preserve all consumed features
and paths against the ordinary reader. Each book's largest native cache also passes
a bounded-only stress check, explicitly distinguished from those ordinary-reader
comparisons. Spanish's largest page has 30,214 objects and 2,168,771 path items;
its successful check kept at least 7.75 GB free. The ordinary-reader comparisons
select three seeded pages plus the largest eligible page under a 1 MB compressed
cache cap, so they do not claim ordinary full-model equality on the largest Spanish page.
See `final/table_input_checks` and the `parity_bounded` execution receipt for the
completed checks. All five input comparisons and fresh Spanish assembly, continuity
and table parity pass; the bounded parity run took 5,609.65 seconds and kept at least
7.74 GB free. No converter source or publication changes accompany this audit fix.
Full native-model loading of very large vector pages remains a resource limitation;
the bounded audit helper does not change production cache loading.

The first worker attempt also stopped because the queue's Windows `cp1252` stdout
could not print a Unicode model-loader progress character. Its interrupted monitor
and log are preserved. The audit queue explicitly uses UTF-8 for its retry. This
console failure is not a passing worker gate and required no converter change.
The inherited worker helper also used one extraction-cache directory for both worker
counts. Its passing byte comparison is retained as `workers_shared_cache_book3.json`.
The final gate overrides only the audit's cache directories: one-worker and two-worker
runs started with separate, absent caches and independently reproduced the same
JSON/manifest bytes and development output in 205.57 seconds, with at least 7.74 GB
free. `workers_book3.json` records both paths
and the independence assertions; cached model weights and learned profiles remain shared.

Two initial JSON comparison attempts also stopped on an audit-helper assumption
that nested text always has a `type` discriminator. `TextFragment` and `FigureText`
allow no such field. Optional lookups now follow the schema; the corrected JSON
checks pass all five books. No converter/publication change was needed. Both
failed logs and `audit_helper_correction.json` are retained.

The final records are under `experiments/out/step17b/final`: `changes`, `lossless`,
`contracts`, `sample_after`, `after`, `source_crosscheck.json`, `parity`,
`json_eval` and `workers_book3.json`. A page proof is accepted only with its new
`validation/proof_<book>.json` receipt, not merely the initially copied gate file.
The fresh native-source audit covers 30 pages with 0 missing/extra; archive asset,
reference and manifest checks pass. The cache-closure selection passes 40 tests.
All 259 Python files, the JSON Schema and the default profile in the built wheel
match the frozen source bytes.

All five complete JSON reference-evaluation records are identical to Step 17's
records: paragraph/list/index/bibliography scores, reading order and joined tables
are unchanged. Anatomy retains 15/15 joined reference tables and TEDS .9258;
Statistics retains 65/69 scored tables and .9586. See `json_eval` and
`reference_evaluation_comparison.json`. These fixes correct publication roles,
divider typing and false inline styles; no new structural accuracy gain is claimed.

The final full-suite command and outcome are in `validation/full_suite_final.json`
and its checksummed log. Collection contains **1,197** tests (1,183 existing plus
11 publication and three audit-reader regressions). Before that run,
`final_suite_inputs.json` freezes this report,
the evidence README, helpers and all backend sources/tests. Final acceptance requires
a passing full suite, no edit to any frozen file after its start, passing Ruff,
all five current publication checks, every required page/parity/worker receipt,
and valid reserve monitors for the accepted runs. Interrupted reserve records are
retained separately and do not become passing gates. `validation_record.json`
records the actual test count, duration, proof methods, checksums and final free space.

No hold-out run, cache cleanup, gold/reference/ledger edit, Git configuration
change or adapter work is included. One commit will be made after the gates pass,
then this step stops for review.
