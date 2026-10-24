# Step 18 pre-registration: sealed hold-out measurement

Registered on 2026-10-24, before any Step 18 hold-out pipeline run, extraction,
OCR, scoring, or output inspection. This document fixes the metrics and their
interpretation. It contains expectations, not hold-out results. Stop for owner
review after this document's commit. Part 2 is not authorized by this commit.

## Frozen identities and accepted preconditions

- Freeze tag: `holdout-freeze-1` (local lightweight tag).
- Converter commit: `8d6a0b0036db3f28dd8b671a2950ceca9918a680`.
- Default profile: `default`, version `1.0.0`, format `1`.
- Profile SHA-256 of the validated canonical JSON, as computed by
  `ClientProfile.sha256`:
  `cbf9a8369859f4cd43c58370b2db3f5d9988ea21e6544b4cef4a23ddcfb2216d`.
- SHA-256 of `backend/src/book_core/assembly/profiles/default.toml` bytes:
  `85b4d469b6322fcfa086a4a112306c539ea9903fe700c81fda37d26cc200ce2a`.

The profile hash is not the TOML file hash. Both identities are recorded to make
the distinction explicit. Use the unchanged default settings/profile; record
the effective settings, producer and model identities in each eventual manifest.
No threshold, model selection policy, profile, converter or evaluator algorithm
may change after the first run starts. The documentation commit does not move
the freeze tag. Pipeline execution must use the tagged converter, with the
pre-registration commit separately recorded as the measurement protocol.

| Book ID | Source key | PDF SHA-256 | Recorded total pages | Accuracy scope |
|---|---|---|---:|---|
| `ent_textbook` | `ent_textbook_pdf` | `e80efa324b1d877a4c726137827b94090c48b9f32d051cac4c3771b1181c55a0` | 612 | Only the 46 reference-covered pages: 24 front-matter markers and body labels 1-22 |
| `math_holdout` | `math_holdout_pdf` | `7bfd1ff40e044124fb32abada59fb6604f2f412a448a3e417c246f3352fa04bb` | 1,220 | OpenStax Algebra and Trigonometry 1e; only independently reference-supported measures |
| `mideast` | `mideast_pdf` | `3f390515f37342c9d3b7cc9418e3ec903fad51e677627e3009b0fd0fde5c1898` | 317 | Robustness only: no matching reference is registered |

PDF hashes were recomputed as byte streams and matched the existing intake/seal
records. Page counts and coverage above come from those existing records; no PDF
content was examined for this pre-registration. Resolve external paths through
`experiments/references.toml`, its local overlay, or environment overrides. Do not
publish private absolute paths. The math reference is the sealed 1e bundle at
commit `8322d84e2df67cad5ba6616fd306eb22427a50c4` (CC BY 4.0), via
`math_holdout_cnxml`; ENT uses `ent_textbook_xml` and the existing DocBook-4 dialect.
The malformed standalone ENT front file is not substituted for the master.
The mismatched Deanta/Canada XML and the mismatched 48-page pair remain excluded.

Accepted Part 0 ran on the clean frozen commit: Ruff passed, **1,197 tests passed**,
all five development publications passed schema/lossless/contract checks, fresh
every-page invariant/ownership checks completed, and continuity/assembly/table
parity passed. Fresh Spanish I1-I7 was zero on all 758 pages, with no proof reuse.
Statistics retained its previously accepted I7=1. That exception is not an
exemption for a new hold-out. Reference-evaluation records matched Step 17b.
The fresh independent 1-vs-2-worker comparison covered **Art Therapy's 9 pages
only**, not five complete books or either large hold-out.

Local accepted receipts:
[Part 0 report](../.cache/step18_part0/8d6a0b0_run1/part0_review.md) and
[machine-readable review](../.cache/step18_part0/8d6a0b0_run1/part0_review.json).
These ignored local receipts are not newly committed evidence. Earlier wrapper
setup attempts were: a script path dispatched as a module; a sandbox denial when
reading an existing publication; and a new evidence destination missing its
copied epoch metadata after metrics had passed. Corrections affected only local
ignored orchestration/evidence routing. No tracked file, converter rule, cache
payload, profile, permission or Git configuration was changed by those attempts.
All attempts remain preserved and are not counted as passing gates.

## Rules for coverage, scoring and reporting

Report each book separately. Never pool the three books into one accuracy score.
ENT's uncovered pages contribute only to robustness, counts, resource use and
whole-book invariants; they never enter an accuracy denominator. Resolve its 46
covered pages by the existing registration/alignment and reference page labels,
not by assuming they are physical PDF pages 1-46. Freeze and report that mapping,
alignment coverage, failures and ambiguous anchors before computing its scores.

Use the evaluators at the tagged commit, listed below, with the same token rules,
normalization, matching and exclusions as development. Run scored metrics on the
published JSON wherever the development JSON evaluator does so; distinguish
archive-stage results and internal parity from reference accuracy. Report all
reference, aligned, matched, scored, rejected and unlocated counts. Conditional
accuracy on successful matches must retain its coverage denominator beside it.

The CNXML decision in [decisions.md](decisions.md#step-13-part-0-math-reference-books-recorded-before-step-13a)
restricts it to math truth; the later existing table-reference reader also
supports table scoring. It is **not paragraph, heading, list or styling truth**.
Do not turn CNXML into a new structural dialect for this benchmark. No such
independent non-math gold is currently registered for the math hold-out. Those
requested accuracy rows remain visible as unmeasured, with the precise reason;
internal order checks and seeded visual diagnostics are reported separately.

The development experiment drivers contain development book IDs and output paths.
Do not run them verbatim against a hold-out. Invocation/data-routing wrappers may
supply book identity, existing reference data and fresh evidence destinations;
they may not alter scoring algorithms, exclusions or production code. Any
unsupported input bridge is a recorded measurement limitation, not permission
to fit a new scorer after looking at results. Existing gold, references and
source ledgers stay read-only. Any new provisional scoring alignment is a
separate data artifact under `experiments/out/step18/`, never an edit to gold.

Every metric ID and submetric below stays in the results table. Use numeric zero
when a nonempty denominator produces zero, `not_applicable` for a genuinely
absent feature, and `unmeasured` for absent truth, unsupported scoring, unavailable
visual verification or a failed stage. Preserve the frozen evaluator's native
null/undefined values and explain them; do not reinterpret null as perfect or
zero. No metric may be added, dropped, substituted, renormalized or selectively
hidden after results. An unexpected limitation is recorded against the existing
row. Exploratory observations must be labelled outside the registered scores.

## Fixed metric registry

In the scope column, **E** means ENT's 46-page accuracy scope, **A** the math
hold-out, and **M** Mideast. Operational measures use the whole book. A
reference-dependent row with no usable truth remains unmeasured for that book.

| ID | Metric and exact computation | Evaluator/method frozen here | Per-book scope |
|---|---|---|---|
| M01 | Completion, failed stage, exception and completed/total pages; exit status; schema/model error counts; JSON round-trip equality; manifest/assets hash mismatches and contract violations | Existing book runner, assembly schema/model validation and Step 17b metrics/contract gates | E/A/M, whole book; success and zero defects expected |
| M02 | Retained and explicit-TrimBox discard token missing/extra counts, source/store/owner totals; source refs reconstruct the existing ledger tokenization, including furniture and suppression | Existing assembly lossless gate and source-run reconstruction; no new token rule | E/A/M, whole book; required 0/0 in each category |
| M03 | Every-page I1-I7 totals, per-page findings and exact ownership/order-once booleans; no sampling or proof reuse | Existing `step13_run.proof_math_book` invariant/ownership implementation with input identity checks | E/A/M, whole book; zero expected for every invariant; any nonzero recorded as failure |
| M04 | Paragraph boundary precision/recall/F1, exact unit match, split/merge counts, per-page and chained views | `evaluation/paragraphs.py::paragraph_scores`, JSON ownership/chains from `step17_json_eval.py`: adjacent scored reference-token pairs are boundaries when their owners differ; P=TP/(TP+FP), R=TP/(TP+FN), F1 harmonic mean; exact means equal scored token sets. Per-page allows column links, chained also page links | E scored; A unmeasured without independent paragraph truth; M unmeasured |
| M05 | Reference main-flow order agreement, Kendall tau, float-anchor and within-float order; separately JSON-vs-archive adjacent main-unit pair agreement | `evaluation/reading_order.py`, `derived_harness.py`, `step17_json_eval.reading_order/order_agreement`; preserve existing aligned pair/anchor sets and denominators | E reference accuracy; A reference accuracy unmeasured, internal agreement available; M internal agreement only, no accuracy claim |
| M06 | List-item boundary P/R/F1 and exactness; list-boundary P/R/F1; nesting exactness and per-level counts | `evaluation/lists.py::list_item_scores/nesting_scores`, JSON owner/list/chain view from Step 17 evaluator | E where covered lists exist; A unmeasured without independent list gold; M unmeasured |
| M07 | Table detection P/R/F1; mean structure/full-content TEDS and exact share; cell adjacency P/R/F1; header-row exactness, header-token and header-association accuracy | `evaluation/table_scoring.py::match/score`: existing greedy one-to-one same-page token match, overlap at least half the gold tokens and at least half the predicted tokens attributable to gold or its existing allowed-extra set; detected/predicted and detected/reference counts; mean existing normalized tree-edit similarity over scored matches. Keep the existing problem-table exclusion for structural scores and list every excluded case/count | E six reference tables before alignment losses; A only where existing table reference/location machinery supports the sealed source; M no table accuracy |
| M08 | Joined-table structure/full TEDS and whole-only TEDS; number reference/scored/missed; table continuation precision and repeated-header handling | `step15_joined_tables.py` and `step17_json_eval.joined_tables`: preserve column maps, existing repeated-header policy, ordered linked grids and current exclusions | E/A with supported multi-page reference tables; absent feature is N/A, missing usable mapping unmeasured; M unmeasured |
| M09 | Equation detection/missed/split/merged/partial/complete counts, scored coverage; strict and expression-level chosen MathML exactness, symbol accuracy and normalized tree distance; inline/display and review-status splits | Existing `evaluation/math_gold.py`, `math_scoring.py::score/window`, `step13b_evaluate.py`, `step13c_evaluate.py`: strict is one complete region with only that equation's evidence; expression score uses the existing best contiguous expression window. Normalize exactly as development. Symbol accuracy=max(0,1-character edit distance/gold character length); report all incomplete/unscored equations separately | A primary accuracy family, conditional on independently located reference evidence; E reference has no math so no reference MathML score; M unmeasured |
| M10 | Figure detection P/R by PDF-page counts and printed-label/name counts, caption coverage/link precision by rule, linked-name equality, credit coverage and figure anchor agreement | `step12_evaluate.py`: count matches by min(predicted,reference) per page or existing parsed printed label; no IoU replacement. Link correctness uses existing reference caption tokens. Report page and label scores separately, never pick the higher after results | E supported figures/captions on covered pages; A no independent figure-location truth currently registered, so accuracy unmeasured; E/A/M still report exported/converted/embedded/ambiguous figure counts |
| M11 | Continuity correct/wrong/unscored links and precision, by paragraph/list/entry/table and page/column; covered reference continuation recall and missed joins where defined | `step15_measure.py::link_rows/continuation_pairs` and existing table continuation checks. A link is correct when its aligned endpoints share the reference unit or the existing reference continuation pair. P=correct/(correct+wrong); unscored is separate. No Spanish-specific inferred-join proxy is substituted as ENT truth | E within covered reference, with every cross-scope link unscored; A math/table joins only where reference supports them, other joins unmeasured; M counts only |
| M12 | Heading detection P/R/F1, exact/within-one level, role confusion, raw and convention-adjusted precision; separate heading vs ordinary-text typing error counts | `evaluation/structure.py::heading_scores`: at least half the aligned tokens must agree; existing convention-class policy unchanged. Add the fixed page-census visual diagnostic below, reported separately from reference scores | E reference score; A no independent heading gold, visual diagnostic only; M descriptive findings only |
| M13 | Index entry exactness and level accuracy, locator/cross-page entry counts; glossary/definition term and description exactness/boundaries; bibliography F1; footnote/glossary typing and page-number/furniture typing separately | `evaluation/lists.py::index_scores/definition_scores/bibliography_scores/cross_page_scores`, existing `evaluation/furniture.py` label/proxy metrics, plus fixed visual census below. Report body and front labels separately; do not equate a furniture proxy with independent typing truth | E only features in the 46-page reference (full-book index outside it unmeasured); A independent reference scores unmeasured, visual diagnostics separate; M no accuracy claim |
| M14 | OCR pages/regions/reader and granularity counts, flags per OCR word/line/page; CER=sum character Levenshtein errors/sum reference characters, WER analogously, paired page counts; order-free character-multiset F1 as separate diagnostic | `book_core.ocr.evaluation.error_counts/aggregate`: NFKC and collapsed whitespace, existing whitespace/CJK evaluation word rule, as used by `step16_real_eval.py` and `step17_real_summary.py`; use emitted order for production text, identify any existing evaluation line-order variant separately; no engine rerun to choose the best | E/A only if scan and independent transcript both exist; none registered now, so CER/WER unmeasured unless already supported truth is established; M usage/flag rates only, CER unmeasured |
| M15 | Output language shares, script and direction counts including unknown; counts of RTL units/pages, OCR-native/mixed decisions; seeded RTL visual diagnostics where present | Count emitted metadata/unit fields without treating confidence as truth. Compare RTL sequences to rendered logical reading order only on the fixed visual sample; no global x/y sort and no presumption that a Middle East title means Arabic text | E/A/M descriptive robustness; M has no language/RTL accuracy claim |
| M16 | Per-kind reference style P/R over aligned token pairs, whole text and body-only; seeded visible-style correct/wrong/unclear counts and sample correctness by kind/context | `step17_styling_eval.py`, Step 17b all-text enumeration and the deterministic sample below; absent reference markup supplies no precision/recall denominator. Visible styling and reference convention disagreement remain distinct | E supported reference spans plus visual sample; A visual sample only, no CNXML style truth; M descriptive audit only, no accuracy rate |
| M17 | Review items by kind/severity and book/page, per 1,000 content units, items and distinct targets; error capture recall and flagged-item correctness with TP/FP/FN/unscored counts from independent audit | Counts from published `review`; recall=independently found real errors with a relevant flag/all independently found real errors; flagged correctness=sampled flags corresponding to real errors/all adjudicated sampled flags. Use sampling below, never infer recall from flags alone | E/A labelled sampled error families only; M workload/flag rates only, no safety-accuracy estimate without truth |
| M18 | Wall seconds per stage and whole attempt, peak process-tree RSS bytes, source/cache/archive/publication/readable-copy bytes, minimum free bytes, reserve stop and cache hit/miss state | Existing runner/process-tree monitor and byte counts; include child processes, original attempt status and measurement interval. Keep archive and publication timing separate if not one uninterrupted full run | E/A/M, whole book; report measurements, no speed-based accuracy tradeoff |

Metrics used only as robustness or descriptive counts do not become accuracy by
being given a number. The result table must retain all M01-M18 rows and the
listed components, including known unmeasured/non-applicable ones.

## Expected ranges fixed from development evidence

These are planning expectations inferred from development measurements, not
owner-supplied acceptance thresholds, confidence intervals or promised scores.
No separate numeric hold-out targets were supplied by the owner. The observed
development ranges and our prospective bands are both given so they cannot be
replaced after results. Scores use 0-1 units except CER/WER percentages. A band
does not authorize tuning, a retry or selective scoring.

Development JSON scores in [Step 17](step17_report.md#reference-metrics-on-the-json)
were reproduced unchanged by Step 17b and accepted Part 0. Other historical
stage/sample measurements below are explicitly identified; they are not new
population measurements on `8d6a0b0`.

| Metric family | Observed development evidence | ENT prospective expectation | Math hold-out prospective expectation | Mideast prospective expectation |
|---|---|---|---|---|
| M01-M03 | Five books schema/contract/lossless 0 defects; I1-I7 zero except known Statistics I7=1 | Completes all 612 pages; zero defects, lossless 0/0, all invariants zero | Completes 1,220 pages; same requirements; unseen size may expose code/environment failure | Completes 317 pages; same requirements, no accuracy implication |
| M04 paragraphs | Page F1 .854897-.942888, chained .903072-.944556; exact page .680317-.896304, chained .766334-.882864 | Page F1 .85-.95, chained .90-.95; exact .68-.90; medical-publisher similarity may help but front matter is different | No numeric accuracy expectation without independent paragraph truth; retain development band as context only | Unmeasured |
| M05 order | Main flow .962046-.998551; tau .924093-.997102; float anchors .577830-.853532 in the three prose books; within floats .942094-.995577. Nine-page Art Therapy anchor score is 0 | Main flow .96-1, tau .92-1, anchors .55-.90, within .94-1; internal archive agreement 1 expected | Reference accuracy unmeasured; internal agreement 1 expected, with no semantic-order inference | Internal agreement 1 expected; accuracy unmeasured |
| M06 lists | Item F1 .887994-.890553; exact .743559-.796069; list-boundary F1 .517425-.674471; nesting exact .793977-.794349 | Item F1 .85-.92; exact .70-.85; list boundary .50-.70, nesting .75-.85; partial reference contains many lists | Accuracy unmeasured without independent list gold | Unmeasured |
| M07-M08 tables | Step 14a P .885-1, R .648-1; Step 14b structure .803-.982, full .787-.924. Final joined anatomy/Statistics TEDS .9258/.9586, full .8516/.8635, whole-only .9702/.9961 | P .88-1, R .65-1; structure .80-.98, full .78-.95. Only six reference tables: report each count; one miss is large | Where scorable, P .85-1, R .75-.95; structure .90-.98, full .85-.95; joined .92-.97, full .85-.90. Expectations conditional on coverage, not matched-only success | Accuracy unmeasured; table counts remain descriptive |
| M09 math | Step 13c Statistics strict exact .866, symbol .986 (680); expression exact .837, symbol .957 (541); 33 of 1,254 lacked a complete region and were not scored | Reference has no math: no numeric accuracy score; record any detected regions and review workload | Strict exact .80-.90, symbol .95-.99; expression exact .75-.85, symbol .90-.97. One development math book gives weak transfer evidence; coverage may fall on new notation | Accuracy unmeasured |
| M10 figures | Step 12 page-count P/R: Spanish .921/.875, anatomy .515/.607; label-count anatomy .785/.928; caption reference coverage .320/.591 | P .50-.93, R .60-.95 by declared scoring view; caption coverage .30-.65. These are count/location proxies, not box accuracy | No numeric accuracy claim without independent located figure truth; graphs, equations and table drawings may inflate counts | Accuracy unmeasured |
| M11 continuity | Step 15 manually checked added joins: Spanish 44/44, immigrant 20/20, anatomy 2/3, Statistics 17/18; table links 25/25 and 61/61. These are cohorts, not all-link population precision | Desired precision .95-1, but the anatomy cohort shows .667 is possible. Report actual scoped numerator/denominator and missed joins | Same desired .95-1 where truth supports it; no claim from internal parity or CNXML-only prose | Link counts only |
| M12 headings | Historical Step 11b P .598-.969 and R .733-.926 on prose books; exact level .753-.862; Art Therapy 1 on a tiny sample | P .60-.97, R .73-.93; exact level .75-.87. The known single-page typing weakness makes this uncertain | Reference accuracy unmeasured; separately report seeded diagnostic rather than transferring these scores | Descriptive only |
| M13 entries, footnotes, folios | Final index exact .862773-.936015, levels .962480-1; glossary-description exact .966 in Step 15. Historical anatomy body-label .996, all-label .890; no broad footnote typing accuracy baseline | For covered entries only: index exact .85-.95, level .95-1, glossary .90-.98 if present. Body labels .99-1 is tentative; front matter may be materially worse. No defensible numeric footnote typing band | No reference accuracy band; manual typing diagnostic, with known weakness retained | Accuracy unmeasured |
| M14 OCR | Step 17 real scans: horizontal Han CER 5.71-10.66% with PP; Arabic about 24.8%; Greek groups about 2-34%; vertical Chinese near 100%. Scanned tables remain unreliable | Mostly native from intake; no guaranteed OCR page count or CER band without paired transcript | No paired transcript known; native processing expected; any scans may be much worse than native | Intake: 310 text pages, one image-only, six little-text pages; output selection may differ. Usage/flags only |
| M15 language/RTL | Existing language labels changed with job language configuration; no independent full-book language/RTL accuracy baseline | Predominantly English/Latin from intake; unknown values possible, not errors by assumption | English/Latin predominates as a prior, not a scored truth label | Intake sample was English .94; do not infer Arabic/RTL from the title; report actual/unknown outputs |
| M16 styling | Step 17b sampled cells: 13/20-20/20 correct before the underline removals; 148/160 aggregate. Seven sampled Spanish errors removed; five anatomy errors retained. No fresh post-removal population estimate | Tentative visible-style sample correctness .75-1; explicit unclear counts and per-kind results; reference conventions may disagree | Same tentative .75-1 sample band; bold/underline/subscripts need inspection, not blanket trust | Descriptive audit; no accuracy rate |
| M17 review workload/safety | Step 17b reviews/page: Spanish 2684/758=3.54, immigrant 112/331=.34, Art Therapy 0/9, anatomy 1009/314=3.21, Statistics 2906/871=3.34. OCR held-out page-flag recall .7705, precision .6104; pooled precision .3533 on correlated degradation cases | Rough workload .3-4 items/page, not a safety target. No general flag-recall/precision expectation is justified | Rough workload 2-5/page; math/figures may dominate. Safety recall/precision must be measured; OCR figures are not general review-list estimates | Rough workload 0-5/page; counts only, no safety score |
| M18 resources | Step 17 archive .216-9.605 GB peak and 166-4726 s; publication .101-4.427 GB and 6-718 s, with differing cache states | No hard runtime/RAM target; capacity provisioned by page-based plan | Larger than Statistics, so allow more time/storage without lowering accuracy | No crash/resource guarantee from a differently structured book |

Evidence sources: [Step 11b](step11b_report.md), [Step 12](step12_report.md),
[Step 13c](step13c_report.md), [Step 14a](step14a_report.md),
[Step 14b](step14b_report.md), [Step 15](step15_report.md),
[Step 16](step16_report.md), [Step 17](step17_report.md), and
[Step 17b](step17b_report.md). Missing baseline denominators or unsupported truth
must be shown rather than filled with a guessed score.

## Fixed visual samples, error audit and uncertainty

Seed namespace is **`20261024:step18:v1`**. For every sample, enumerate eligible
items first and store the full population IDs. Rank by the hexadecimal SHA-256
of UTF-8 `20261024:step18:v1:<book_id>:<sample_family>:<stable_item_id>` and break
ties by stable ID. Take the first `min(n,population)` without replacement; save
all selected IDs before judging any crop. Page IDs are physical page indices,
unit IDs are source-stable IDs; an ID-less text fragment uses its exact source
refs plus text-range offsets. Record this identity method. No redraw for an
awkward or unreadable target; keep it and mark unscorable/unclear with reason.

- **Styling (M16):** sample 20 detected spans per emitted kind per scored book,
  across all text-bearing locations, including content, table cells, headings,
  captions, index entries and furniture. Do not use content-only enumeration or
  omit weak kinds. ENT candidates must lie in its covered pages. Report the
  population and sampled counts by kind and semantic context. Judge against
  rendered original PDF crops plus enough surrounding page context: correct,
  wrong, unclear. Report correct/(correct+wrong), unclear count and conservative
  correct/all-sampled; a detected-only sample establishes no recall. Mideast's
  corresponding observations are descriptive, without an accuracy percentage.
- **Typing and independent error discovery (M12/M13/M17):** select 20 pages per
  book (ENT from its 46-page scope; the others from the full book), family
  `page_census`. Inspect all headings, footnotes, glossary/definition entries and
  printed page-number occurrences on each selected page against the output.
  Count found/correct/missed/spurious types separately for each class, including
  confusions with paragraph, caption and furniture. Report P/R and a confusion
  table on ENT and the math book as **sampled visual diagnostics**, not full-book
  reference accuracy. No visible feature yields a zero denominator, not 100%.
  Mideast yields descriptive findings only; it has no independent truth set.
- **Safety recall (M17):** use errors independently found in that page census or
  applicable reference-backed census, including unflagged output; deduplicate
  within metric by owning unit/printed occurrence and error class. A captured
  error needs a review target on that unit (or its owning container) with a
  reason relevant to that error family. An unrelated alt-text flag does not
  capture a wrong heading. Keep reference and visual strata separate; do not
  pool overlapping errors across metric families. Report numerator, denominator,
  unclear/unmapped and false negatives. No reference/visual truth means
  unmeasured recall, not an inferred zero or perfect score.
- **Flag correctness (M17):** independently sample 20 review items per
  kind/severity stratum, family `flag:<kind>:<severity>`, and adjudicate whether
  the stated warning corresponds to a real error. Report true/false/unclear and
  all sampled counts. Do not estimate recall from this sample. Distinguish
  genuinely erroneous output from a correct but deliberately cautious review
  suggestion; unresolved alt-text requirements are reported as their own kind.
- **Continuity diagnostics (M11):** for each book and emitted link kind, sample
  20 links, family `continuity:<kind>`, and visually judge both endpoints and
  context. Reference-backed and sampled visual precision are separate. For
  Mideast record only descriptive anomalies, with no accuracy rate.
- **OCR and RTL (M14/M15):** select 20 eligible OCR pages and 20 eligible RTL
  units, families `ocr_page` and `rtl_unit`. Preserve unknown direction. OCR
  visual diagnostics do not manufacture a full transcript or CER; no second
  engine run is chosen to improve a score. No eligible item is N/A; no usable
  independent transcript means unmeasured CER. Mideast remains descriptive.
- **Worse-than-development taxonomy:** for each metric below its registered
  comparable development band, rank all observed errors with family
  `taxonomy:<metric_id>` and inspect 20, or all if fewer. Classify by general
  cause with counts: registration/reference coverage, layout/columns, ownership,
  split/merge, float/anchor, role/typing, continuation, glyph/math recognition,
  style evidence, OCR/script/direction, or environment/scoring limitation. Allow
  `other`/`unclear` with a written explanation. Describe a general rule needed
  for later work; do not implement it or fit a page-specific rule.

A hand-check is verified only after viewing the actual rendered target and its
context. This environment supports local image viewing; no hand-check has been
performed in this pre-registration. Missing/corrupt crops remain unscored and
are reported. Do not count model agreement or the output's own label as truth.

Show raw counts with every proportion. Use Wilson 95% intervals for adjudicated
binomial samples, noting that within-book items and stratified samples are not
independent books. For boundary F1/TEDS/order means, report eligible/scored page
counts and a seeded 1,000-resample page-cluster bootstrap interval where page
contributions exist (seed 20261024); otherwise state why uncertainty was not
estimated. Never reinterpret a development min/max as an interval or significance
test. A generalisation gap is hold-out minus the same comparable development
score/range; reverse the favourable direction for CER, errors and workload.
Report numerical gaps even within the expectation band. Label positive,
negative or mixed using the metric's direction, intervals/counts and coverage;
claim a gap exceeds demonstrated noise only when the available comparison can
support that claim. No comparable truth means no gap/accuracy verdict.

## Known limits registered before results

1. A single-page check already showed weakness in heading, footnote/glossary and
   page-number typing. It is not a population estimate. M12/M13 separate these
   classes so aggregate paragraph or order scores cannot hide them.
2. Worker equality was freshly tested on the **9-page Art Therapy book only**.
   It does not establish equality on ENT, 1,220-page math or Mideast. Do not
   rerun a hold-out with another worker count merely to improve a result.
3. Spanish development table parity used Step 17b's **bounded table-input
   reader**. It verified fingerprints/checksums and table-consumed fields/paths;
   ordinary-reader feature comparisons and largest-page bounded-only stress
   checks have different scope. It is not a replacement native-object proof or
   evidence for unseen inputs. The fresh Part 0 Spanish invariant proof is a
   separate all-page result. Any future use of that existing bounded reader
   must be disclosed and may not change the table algorithm or scoring.
4. ENT has a small same-publisher partial reference, not independent 612-page
   truth. Its six tables and rare footnotes make broad estimates unstable.
   Full-book index/glossary metrics cannot be inferred from uncovered pages.
5. Math has one development analogue; strict/expression MathML scores are
   conditional on successful equation location/completeness. Report failures
   and coverage. CNXML is not general structural/typographic ground truth.
6. Mideast has no matching reference. Schema, ledger, invariants, flags, unknown
   scripts and successful completion do not establish semantic accuracy or RTL
   correctness. No Canada XML, generated XML or output-as-truth substitution.
7. Native text must not be OCRed merely to improve these scores. Installed OCR
   support is not measured accuracy for every language. Vertical Chinese,
   full-line confidence calibration and scanned-page tables remain limitations.
   CER can exceed 100%; no favourable clipping or order-free substitution.
8. Styling reference conventions differ from visible print; detected-only
   samples lack recall. Language confidence is not calibrated accuracy, unknown
   scripts/directions stay unknown, and unspaced-CJK tokenization is not revised.
9. Internal parity and lossless retention do not prove semantic order, heading
   correctness, figure ownership or correct suppression. The image alt-text
   slots and review counts are not independent correctness labels.

## Run ledger, capacity and stop rules

`experiments/holdout_runs.jsonl` starts with exactly three `record_type=template`
rows carrying the source SHA-256, tagged commit, profile ID/version/canonical
hash and profile file hash. `attempt_id`, `start_time` and `end_time` are null;
`outcome=not_run` and `pipeline_started=false`. They are templates, not attempts.
Append real `attempt_started` and `attempt_finished` events with an identical
attempt ID and timezone-aware ISO-8601 times; never edit a template/start row to
fill it in. Record stage, exception, settings/model/producer identities,
pre-registration commit, output identities and reserve receipts. The two event
types together supply start/end/outcome, including interrupted attempts.

Run order, after separate approval: **ENT, math hold-out, Mideast**, serially,
once each on the tagged converter/default profile. A code failure is recorded
without fixing, then proceed to the next book. Only an environmental failure
(disk, power or tool crash) permits another attempt on the identical frozen
commit/settings; append both attempts and the reason. No result-driven reruns,
page exclusions, sample redraws, alternative profiles or model comparisons.

Keep the 5,000,000,000-byte reserve monitor active during every conversion and
evaluation job, watching the actual interpreter/process tree. Stop below the
reserve and report it; delete, move or prune nothing. The accepted Part 0 minimum
was 88.90 GB and completion free space 92.30 GB (decimal). The retained plan is
28,222,579,081 bytes, 33,222,579,081 with reserve, and 39,222,579,081 including
shared transient headroom. These are estimates, not maxima. Recheck actual free
space before any run. The older disk-budget document's insufficient-space
snapshot is historical and was superseded by the accepted Part 0 capacity
receipt; no cleanup is approved. Do not touch or run `frontend_temp/`.

Retain original hash-named outputs and all attempts. Later readable JSON copies
under `experiments/out/step18/<book>/` must parse identically; README identities
and `review_list.json` are evidence copies, with no copied images/crops. Record
what could not be measured and why. No Stage 2, adapter or XML generation work.

This gate commits **only this document**. The new append-only ledger templates
remain outside that docs-only commit for the later evidence commit. Verify the
tag still resolves to the frozen hash, and that neither this commit nor tag
creation changed a tracked `backend/` file. Stop and show this file for review
before running any hold-out book.
