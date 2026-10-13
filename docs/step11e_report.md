# Step 11e — layout credit classification

Status: **FAILED-FOR-REVIEW — accuracy regression**. The five layout violations are corrected,
but page 724 acquires a deterministic paragraph/order regression. This checkpoint
is for review, not an accuracy pass. All other required checks pass.
Step 11d remains on hold. Step 12 has not started.

## Scope and baseline

This step changes only the layout fallback for rotated credit candidates. The
baseline is the frozen Step 11d capture at diagnostic checkpoint `90a544a`; its
page identities, native/analysis model digests and metrics match Step 11c. The
initial tracked checkout was clean. `.vscode/settings.json` remains untouched and
untracked, as explicitly authorized; its SHA-256 is recorded. The diagnosis script
was the first new task file. The provenance probe was rerun before the producer
edit, so its inventory also includes that script and its initial diagnostic outputs;
these are task-created files, not pre-existing exceptions.

Only the approved Spanish US history, immigrant children, art-therapy index and
medical anatomy books are run or scored. Sealed ENT, `deanta_pdf_mideast`, the
mismatched reference pair and unregistered originals are not run. Existing tests
also use their registered historical fixtures and synthetic PDFs; these are
separate from the four-book measurements. Reference XML, gold and old projects
remain read-only. There are no instruction conflicts requiring a scope change.

Before full runs, free disk was 40,215,089,152 bytes. The Step 11c estimate is
1,412 × 12 MiB = 17,767,071,744 bytes, leaving 22,448,017,408 bytes, above the
10 GB stop threshold. Each book run checks capacity again. Evidence:
[baseline](../experiments/out/step11e/baseline.json).

On resumption, HEAD was still `90a544a29b371e1a31548781003663afa75e90e9`
with no Step 11e commit. The existing layout edit, its new test and the Step 11e
diagnostic/measurement files were retained. Two previously started Python jobs
were still running: the Spanish full-book proof and immigrant-children run.
They were allowed to finish without duplicating their work. Free disk was
39,722,946,560 bytes. Every current producer-scope file matched the saved producer
identity, including the complete raw pipeline hash below; no product edit was
made during resumption. [Resume inventory](../experiments/out/step11e/resume_state.json).

The historical Step 11d manifest and frozen evidence are retained. `.gitattributes`
adds only the Step 11e comment and `experiments/out/step11e/** -text` rule (with the
same whitespace attributes used for Step 11d), preserving exact measured bytes
when Git stages the evidence, including CRLF summaries. Because `.gitattributes`
is covered by the historical manifest, this is an explicit extension exception:
the auditor checks that all original attribute bytes remain intact and only those
two Step 11e lines are appended. The other 83 historical manifest entries remain
byte-identical. This exception does not modify the historical manifest or
authorize changing old evidence.

## Diagnosis before implementation

The exact definition in `layout/invariants.py` is:

```text
I5  Rotated lines that share a right-angle rotation take part in structure; rotated text is
    a credit only when small, isolated and beside a figure edge.
```

The Step 4a-fix report spells out its scope:

> At least 3 lines sharing a right-angle rotation must belong to a band. Cells of such a group are credits only if small, isolated and within 4 font sizes of a figure edge.

It also explicitly preserves the earlier rule for a single isolated rotated line.
Consequently, extending the strict group test to every lone margin line would be
an additional rule change. This step retains that documented interpretation.

The unchanged checker is:

```python
rotated = [line for line in texts if not line.horizontal]
groups = defaultdict(list)
for line in rotated:
    groups[rotation_key(line)].append(line)
figure_boxes = [block.bbox for block in figures]
for key, members in groups.items():
    if len(members) < ROTATED_STRUCTURE_LINES or right_angle(key) is None:
        continue
    for line in members:
        region = region_of.get(line.id)
        if region is None or region.get("band_id") is None:
            result["I5"].append(
                f"rotated line outside structure ({key} deg): {line_text(line, store)[:40]!r}"
            )
        # Cells of a rotated structure are credits only with full credit evidence.
        if region and region["type"] == "credit_candidate":
            if credit_like(line, lines, figure_boxes, body_size):
                continue
            result["I5"].append(
                f"rotated text labelled credit without credit evidence: "
                f"{line_text(line, store)[:40]!r}"
            )
```

`texts` means nonblank, visible, inside-content lines with positive font size.
`credit_like` requires size ≤ 1.05 times the dominant horizontal page-body size
(or no body size), no other nonblank line of the same rotation within two font
sizes, and a figure box within four font sizes. Distance is the Euclidean minimum
box gap, zero for touching/overlapping boxes. Rotation is rounded modulo 360.

The old fallback, quoted before editing, was:

```python
small = body_style is None or line.font_size <= 1.05 * body_style[1]
spec = (
    ("credit_candidate", 0.75, ["Rotated small text outside figures"])
    if small
    else ("unknown", 0.45, ["Rotated text that is not small; review"])
)
```

`git blame` attributes this exact fallback to `900d743c`, Step 4a,
2026-10-08 15:40:29 +0530. The exact checker and shared credit evidence date to
`370bc295`, Step 4a-fix, 2026-10-08 17:07:05 +0530. Later file changes in Steps 4b
and 11c did not change these clauses. This is an old producer/checker disagreement,
not a regression introduced by Step 11c or the Step 11d diagnostic work.
[History and blame](../experiments/out/step11e/diagnosis/history.json).

All five lines are small and already have band membership. They fail the second
checker branch (credit evidence), not the first branch (missing structure).
The first three pages have three eligible lines of the same rotation; page 724
has four. Figure-owned rotated labels count toward those totals. Ownership removes
those labels before deciding whether enough free lines remain for a rotated frame,
so these leftover lines reached the older size-only fallback.

| Spanish physical page and line | Font/body ratio | Isolated | Nearest figure gap / font size | Failed evidence |
|---|---:|---|---:|---|
| 324: “A People’s History of the United States: 1492 - Present by Howard Zinn…” | 0.612245 | yes | 48.519496 | figure proximity |
| 350: “Second Day, Wednesday, 11/21/1945, Part 04…” | 0.612245 | yes | 10.940765 | figure proximity |
| 361: “Recommendation for Assistance to Greece and Turkey: Address of the President…” | 0.612245 | yes | 67.615399 | figure proximity |
| 724: “PHOTO: (tl)U.S. News & World Report Magazine Photograph Collection…” | 0.375000 | no | 0 | isolation |
| 724: “Confucius. Quoted by Zhang Haihua and Geoff Baker. Think Like Chinese…” | 0.375000 | no | 0 | isolation |

The complete line texts, stable IDs, relative measurements and reference witnesses
are in the [complete fallback inventory](../experiments/out/step11e/diagnosis/fallback_credits.json).
All five complete normalized texts occur in the registered Spanish reference,
inside `span class="credit"` within paragraphs. None is omitted. The matching
printed markers are 300, 326, 337 and HT2 respectively; the Nuremberg citation also
occurs in a combined credit at marker 318. Both page-724 lines match the same
combined credit at HT2. These are reference marker labels, not physical PDF pages.
[Deepest containers and all matches](../experiments/out/step11e/diagnosis/reference_contexts.json).

A subsequent reference audit corrected the initial parent-only reading: selecting
the shortest text container had selected `p` when its text length tied its child
credit span. The corrected diagnostic explicitly selects deepest matching
containers. This correction happened after the isolated producer measurement;
no further producer edit followed. The reference therefore confirms a semantic
credit interpretation, while the written I5 layout-candidate rule remains narrower.
This distinction is a limitation of the existing rule, not permission to weaken
its gate or invent a semantic role from geometry. The downgrade to `unknown` means
the layout evidence is insufficient; it does not assert that the text is not a
citation or credit. No gold or production rule is derived from the XML tags.

| Book | All fallback credit lines | Pass I5 | Also meet full credit evidence | Fail I5 |
|---|---:|---:|---:|---:|
| Spanish US history | 523 | 518 | 58 | 5 |
| Immigrant children | 2 | 2 | 0 | 0 |
| Art-therapy index | 0 | 0 | 0 | 0 |
| Medical anatomy | 0 | 0 | 0 | 0 |

All 520 passing fallback lines lie outside I5's structural-group scope. Of these,
58 meet the full evidence test independently; the other 462 pass because the
group clause does not apply. “Pass I5” is therefore not a claim that each line's
semantic credit role has been independently validated. Every inventory entry is
retained for checking that the correction preserves these existing labels.

The fallback is too liberal **inside the existing I5 scope**. The checker agrees
with the written Step 4a-fix definition. The supported recommendation is to apply
the existing `credit_like` evidence to fallback lines belonging to an eligible
page-wide group, including figure-owned lines in the group count, and retain
unsupported text as `unknown` for review. No checker or decision-definition change
is justified.

## Implementation and isolated measurement

`build_regions` now counts eligible rotated lines across the page using the same
rotation key, right-angle test and minimum group size as I5. Within that scope,
the fallback additionally requires the existing full credit evidence, using the
same page-body size as the checker. An unsupported small line becomes `unknown`
at confidence 0.45 with an explicit reason and review flag. Its source text,
stable line/region IDs, geometry, ownership and band membership are preserved.

Only `layout/pipeline.py` is changed in the product. The I5 checker, evidence
thresholds, model schema, native extraction, analysis, hidden-text handling,
character repair, reading-order rules, paragraphs, lists, ledger, worker selection
and hash-once implementation are unchanged. There are no dependencies, adapters,
XML output, OCR, book/page/font/publisher rules or absolute geometry thresholds.

Before any further producer edit, the four affected pages were actually rerun
through `analyze_layout`. All seven invariants were zero on each. The complete
field differences show only the five labels' confidence, type, proposed type,
reasons, review-required state and resulting review flags. Lines, blocks, scopes,
bands and text were identical. No further producer edit was made.
[Isolated measurement](../experiments/out/step11e/isolated.json).

Twelve new cases cover the figure-owned-label cause, a true isolated credit near
a figure, a distant margin citation, adjacent margin notes, preserved solitary
behavior and exact line ownership, at three geometric scales. Existing synthetic
rotated-table tests protect headers and cells and retain a true figure credit;
the new cases also protect embedded figure labels.

## Page 724: exact downstream regression

Reference paragraph 832 (`.../blockquote[2]/p[1]`, PDF token ordinals 62–88)
previously matched one four-line paragraph exactly:

```text
[ “ No solo nos arriesgamos a repetir la historia cuando la barremos debajo de la alfombra,
  también nos arriesgamos a tener una visión miope [cortoplacista] sobre nuestro presente”. ]
```

After the layout change it is two two-line paragraphs:

```text
[ “ No solo nos arriesgamos a repetir la historia cuando la barremos debajo de la alfombra, ]
[ también nos arriesgamos a tener una visión miope [cortoplacista] sobre nuestro presente”. ]
```

The exact chain is **layout → reading order → paragraphs**. The two rotated
credit lines become `unknown`. The unchanged reading-order producer puts them
in the main stream between the quote's second and third lines. The unchanged
Step 9 paragraph producer therefore no longer sees those quote lines as adjacent.
Its new boundary before “también” is evaluated against the intervening credit's
terminal ending, style change and different Step 4 block: score 0.5, boundary
confidence 0.6. The original cross-line join from `70d3a022…` to `bc6aff26…`
disappears. The first unit retains ID `1c5ac2db…`; the second starts a new unit
`b534d346…`. The list stage preserves the split; it did not introduce it.

This is a real regression, not noise. In each of the four paragraph evaluations,
exact reference units decrease by one and units split increase by one. Reference
credit unit 839 also changes from three pieces to two and remains inexact; that
offsets the extra piece in the aggregate `split_errors` count. An unchanged total
split-error count therefore does not establish unchanged paragraph accuracy.

The reading-order comparison also exposes two additional discordant reference-unit
pairs on page 724. The first three affected pages instead move one credit stream
each into main flow. Three correctly anchored streams leave the float denominator,
with no new anchor miss. On page 724 six concordant within-float pairs leave that
denominator: the four-page subset changes from 41/44 to 35/38. Changes in pooled
main-flow ratios mix added comparisons and actual order errors and are not a
uniform accuracy improvement. All four reading-order views are recorded.

Full before/after unit texts, line IDs, boundaries, join evidence, reference token
ownership and order scores are preserved in
[effects.json](../experiments/out/step11e/effects.json). This diagnosis adds no
product rule. Per the user's subsequent instruction, the regression and the
interaction between `unknown` layout text and main-flow placement are recorded
for later review, with no attempted follow-up fix.

The owner explicitly chose to keep `unknown` plus `needs_review` as the contract.
Routing unknown rotated lines near figures to a separate review stream in reading
order was rejected for this step and deferred for consideration in Step 12. This
accepts page 724 as a known limitation; it does not convert the accuracy gate to a
pass. Any additional regression still requires stopping and reporting it.

## Producer identity

The complete current layout producer digest is
`2ef089e343cd44acbf2c9a7f336c021f425d073a36adbd4cb9d87127c02afeb6`.
The raw pipeline SHA-256 is
`eb32cdd38828a20c1b92210de132c8b6f0ae68f38233640e674c056a328649db`.
The layout key calculated in a fresh process from the final producer is
`6f58a1909f6a42bd9faa39fdc043de338d081cebd72c0e17873a558b4cab12fa`:
exactly the isolated measurement, the recorded Spanish run key and the Spanish
identity capture key. The metrics' paragraph and structure keys are checked against
that capture. Tests are outside the layout producer scope. File modification
times are not used as proof of producer equality; the evidence retains each
producer-scope file's measured raw SHA-256. Every current working-tree scope file
matches those measured raw bytes, including the exact pipeline SHA-256 above.

The committed-byte audit uses the existing producer's canonicalization:
`cache_identity.producer_digest` normalizes CRLF to LF before hashing. Twelve
unchanged layout-scope files have CRLF working-tree bytes but LF Git bytes; their
raw hashes therefore differ, while their canonical bytes and producer identity
are equal. The changed pipeline already has LF bytes and matches its measured
raw hash exactly. The audit retains raw and canonical per-file hashes and
reconstructs the committed producer digest. This is only an existing newline
normalization difference; no source behavior or cache key changed and no
measurement rerun is needed on that account.
[Producer identity](../experiments/out/step11e/producer_identity.json).

## Full measurements and gates

All four real full-book runs, identity captures, metric comparisons, I1–I7/
line-ownership proofs, source sample/ledger checks and consolidated audit are
complete. The [verifier](../experiments/out/step11e/verification.json) records
`FAILED-FOR-REVIEW` with every other required check passing.

### Per-book identities and reported metrics

| Book | Pages | Layout and downstream identities vs Step 11d | Reported metrics vs Step 11d |
|---|---:|---|---|
| [Spanish US history](../experiments/out/step11e/metrics/spanish_us_history/summary.json) | 758 | Layout/order/furniture/paragraphs/lists change only on 324, 350, 361, 724; structure projection changes on 350, 724 | All measured changes listed below |
| [Immigrant children](../experiments/out/step11e/metrics/immigrant_children/summary.json) | 331 | Every page and whole-book semantic digest identical | All accuracy/count fields identical; three propagated keys and elapsed seconds change |
| [Art-therapy index](../experiments/out/step11e/metrics/art_therapy_index/summary.json) (anecdotal) | 9 | Every page and whole-book semantic digest identical | All accuracy/count fields identical; three propagated keys and elapsed seconds change |
| [Medical anatomy](../experiments/out/step11e/metrics/medical_anatomy/summary.json) (development) | 314 | Every page and whole-book semantic digest identical | All accuracy/count fields identical; three propagated keys and elapsed seconds change |

The Spanish native-text identity is unchanged on all 758 pages. Whole-book
paragraph, structure-evidence and structure digests change; furniture and list
book decisions are identical. Semantic page/book comparisons use the established
canonical digest convention; cache keys are compared separately.
[Identity comparison](../experiments/out/step11e/spanish_identity_comparison.json),
[full field changes](../experiments/out/step11e/page_changes_spanish_us_history.json).

| Spanish page | Direct layout change | Downstream cause |
|---|---|---|
| 324 | One distant small rotated credit candidate becomes unknown with review | Its credit stream joins main flow; associated order evidence, paragraph/list placement and carried order change |
| 350 | One distant small rotated credit candidate becomes unknown with review | Its credit stream joins main flow; associated order evidence and paragraph/list placement change; caption unit `14d70007…` adds a rejected heading candidate at score 0.35 |
| 361 | One distant small rotated credit candidate becomes unknown with review | Its credit stream joins main flow; associated order evidence, paragraph/list placement and carried order change |
| 724 | Two non-isolated small rotated credit candidates become unknown with review | The two lines enter main flow inside quote 832, creating the paragraph/order regression described above; structure also adds a non-heading styled-text overlay to the first quote fragment |

The page 724 structure addition is a `display_title` styled-text overlay on unit
`1c5ac2db…`, confidence 0.686, `review_required: false`; its paragraph/list kind
remains `paragraph`. The profile display-title count changes from 1,259 to 1,260.
This is a deterministic, currently unscored downstream consequence. The Step 10
owner policy explicitly permits non-heading styled roles for text that the
reference treats as a paragraph, so this overlay alone does not establish another
accuracy regression. It does not erase the independently demonstrated quote split.
The page 350 candidate remains rejected. Heading, zone and list accuracy scores
are unchanged.

Pages 324, 350 and 361 add or remove no paragraph units: each moved credit unit
keeps its identity and line membership, with its stream and boundary evidence
updated for main flow. Page 724 adds the second quote-fragment unit and removes
one old separate credit unit as the two moved credit lines join; eight surviving
units have changed fields. The net unit count is therefore unchanged despite the
quote split. [Unit-level changes](../experiments/out/step11e/unit_changes_spanish.json).

Every reported Spanish paragraph score that changes is listed here. Each cell is
Step 11d → Step 11e. The four views all lose exactly one exact unit and gain one
split reference paragraph because of quote 832 on page 724; the credit-unit 839
piece-count reduction masks this in the total split-error count. Boundary recall
and all unlisted paragraph fields are identical.

| Paragraph metric | Step 9 per page | Step 9 with chains | Step 11 per page | Step 11 with chains |
|---|---|---|---|---|
| Boundary precision | 0.916507 → 0.916444 | 0.916924 → 0.916861 | 0.918497 → 0.918440 | 0.919323 → 0.919265 |
| Boundary F1 | 0.898114 → 0.898084 | 0.897423 → 0.897393 | 0.942797 → 0.942767 | 0.943013 → 0.942982 |
| Exact unit match | 0.753076 → 0.753010 | 0.742483 → 0.742417 | 0.894927 → 0.894862 | 0.885256 → 0.885190 |
| Exact units | 11,446 → 11,445 | 11,285 → 11,284 | 13,602 → 13,601 | 13,455 → 13,454 |
| Units split | 1,002 → 1,003 | 998 → 999 | 791 → 792 | 783 → 784 |
| Paragraph-kind exact | 0.895803 → 0.895682 | 0.877244 → 0.877123 | 0.898472 → 0.898350 | 0.879913 → 0.879791 |
| Paragraph-kind split | 380 → 381 | 380 → 381 | 394 → 395 | 394 → 395 |

Every reported Spanish reading-order score that changes is listed below. The
credit-anchor and float-anchor ratios decrease because three correctly anchored
credit streams (324, 350, 361) leave their denominators. No new anchor miss is
introduced. Within-float agreement decreases because six concordant pairs leave
the comparison on page 724. Main-flow/tau changes combine new comparisons from
the moved lines with two additional reversed pairs on page 724; the pooled ratio
increase does not establish improved accuracy.

| Reading-order metric | Step 9 | Step 11 | Nearest paragraph boundary | End paragraph boundary |
|---|---|---|---|---|
| Credit anchors | 0.949868 → 0.949468 | 0.949868 → 0.949468 | 0.949868 → 0.949468 | 0.949868 → 0.949468 |
| Float anchors | 0.900670 → 0.900488 | 0.900670 → 0.900488 | 0.891530 → 0.891331 | 0.895186 → 0.894994 |
| Within floats | 0.921773 → 0.921729 | 0.921773 → 0.921729 | 0.921773 → 0.921729 | 0.921773 → 0.921729 |
| Kendall tau | 0.891362 → 0.891366 | 0.908957 → 0.908958 | 0.908957 → 0.908958 | 0.908957 → 0.908958 |
| Main flow | 0.945681 → 0.945683 | identical | identical | identical |

The Spanish metric comparison contains 49 changed fields: the 45 score/count
fields above, three propagated cache-key fields, and elapsed evaluation seconds
413.0 → 331.4. All other reported fields, including heading/list accuracy, page
labels and confidence totals, are unchanged. Runtime reflects separate executions
and is not an accuracy result. Cache identity changes are explained below.
[Complete metric changes](../experiments/out/step11e/spanish_metric_changes.json).

Books 2–4 each have exactly four changed summary fields: the propagated paragraph
book key in `cache_key_inputs` and `gates`, the propagated structure-decision key,
and elapsed evaluation seconds. Those seconds change 24.4 → 34.1 for immigrant
children, 6.1 → 9.6 for art-therapy index, and 57.7 → 81.1 for medical anatomy.
The keys change because the shared layout producer changed, even though these
books' semantic outputs did not. Every summary field was compared, with no metric
exclusions; all 61 changed fields across the four books have explicit reasons in
[the full metric-change ledger](../experiments/out/step11e/metric_changes.md) and
[machine-readable explanations](../experiments/out/step11e/metric_explanations.json).
[Four-book identity and metric comparison](../experiments/out/step11e/comparison.json).

### Full-book invariants and ownership

These are measurements from the actual full runs, not synthetic fixtures. Each
page's unchanged I1–I7 checker was evaluated, and final unit/order ownership was
checked for every visual line, including furniture and artifact streams.

| Book / complete proof | Pages | Visual lines | I1–I7 totals | Exactly one unit / exactly once in order |
|---|---:|---:|---|---|
| [Spanish US history](../experiments/out/step11e/after/spanish_us_history_full_gates.json) | 758 | 84,085 | all zero | PASS / PASS |
| [Immigrant children](../experiments/out/step11e/after/immigrant_children_full_gates.json) | 331 | 14,396 | all zero | PASS / PASS |
| [Art-therapy index](../experiments/out/step11e/after/art_therapy_index_full_gates.json) | 9 | 1,231 | all zero | PASS / PASS |
| [Medical anatomy](../experiments/out/step11e/after/medical_anatomy_full_gates.json) | 314 | 20,142 | all zero | PASS / PASS |
| **Total** | **1,412** | **119,854** | **all zero** | **PASS / PASS** |

All **520** previously passing fallback credit labels are preserved: 518 in
Spanish history and two in immigrant children. No other fallback credit is
downgraded. The exact native-object and analysis-model digests, as well as their
cache keys, are unchanged for all 1,412 pages.

### Source sample, ledger and final archives

The source check reuses the frozen **Step 11d six-pages-per-book sample**, not the
historical driver that opens additional books. Fresh PyMuPDF extraction through
the Extractor interface is compared with the final source archives using the
unchanged TrimBox-centre, case-sensitive NFKC token Counter.

| Book | Physical pages in the frozen sample | Missing / extra tokens |
|---|---|---|
| Spanish US history | 33, 283, 435, 441, 535, 626 | 0 / 0 |
| Immigrant children | 153, 198, 203, 209, 282, 330 | 0 / 0 |
| Art-therapy index | 2, 3, 4, 5, 6, 7 | 0 / 0 |
| Medical anatomy | 65, 69, 78, 203, 207, 232 | 0 / 0 |

The full Spanish ledger contains exactly **495,751 retained/node tokens** from
529,911 source tokens; 34,160 tokens remain assigned to the existing explicit
TrimBox exclusions. Missing and extra counts are zero. The ledger and its
tokenizer were not edited; ledger completeness does not assert semantic order.
The separate full-book ownership proof above checks line coverage and order
multiplicity, while the accuracy failure concerns the order itself.

All four final archives pass file-checksum, source/unit digest and span-reference
resolution checks on every page. Their retained-token counts are 495,751,
124,017, 4,249 and 95,957 for books 1–4 respectively. These archives agree with
the measured runs and identity captures.
[Source crosscheck](../experiments/out/step11e/source_crosscheck.json),
[full Spanish ledger](../experiments/out/step11e/full_book.json),
[final archive proofs](../experiments/out/step11e/final_outputs.json).

### Cache identity and runtime behavior

Only the layout producer scope changes. Native extraction and analysis producer
digests and cache keys are unchanged across all four books. The Spanish layout
key changes from `9b82a910…f2e4` to
`6f58a190…b12fa`; reading order, furniture, paragraphs, structure evidence,
structure decisions and lists re-key through their upstream dependency closure.
Their own producers are unchanged. The complete keys are retained in the
[identity comparison](../experiments/out/step11e/spanish_identity_comparison.json)
and [producer audit](../experiments/out/step11e/producer_identity.json).
All four books have the same set of re-keyed stages, as recorded in
[comparison.json](../experiments/out/step11e/comparison.json).

The one-worker automatic default, source hash-once behavior, cache formats and
dependency registry are unchanged. Passing `test_step11c.py` cases cover byte
equality across worker counts and production mode with one source hash, the
memory-safe worker default, and a deliberately missing upstream dependency being
detected. Existing producer import-closure tests also pass.

The actual four full runs each used **one worker and one source hash**. Their
pipeline wall times were 2,845.4, 1,112.0, 24.8 and 475.6 seconds respectively for
books 1–4. These are separate from the evaluation seconds above. Per-stage timing,
cache sizes and memory measurements remain in the complete
[performance records](../experiments/out/step11e/performance/).

The complete test inventory is **881 passing cases = 869 baseline + 12 new**:
876 core cases in 321.37 seconds and five furniture cases in 21.13 seconds. The
handoff's 876 expectation described the core run. The additional run emitted one
pytest cache-directory creation warning and no failures. The fresh furniture run used
`--basetemp=../.cache/step11e/tc`. Ruff was run from `backend/` over `src`, `tests` and all
six Step 11e scripts: checks pass and 207 files are already formatted.
[Core results](../experiments/out/step11e/pytest_core.xml),
[furniture results](../experiments/out/step11e/pytest_furniture.xml),
[lint results](../experiments/out/step11e/lint.json).

### Gate table

| Gate | Result | Evidence / remaining verification |
|---|---|---|
| Accuracy preservation | **FAILED-FOR-REVIEW** | Deterministic page 724 quote split and two added reversed pairs; no threshold relaxed |
| Four isolated affected pages, unchanged I1–I7 checker | PASS | All seven zero after rerunning those pages; isolated evidence linked above |
| Full-book I1–I7 on all 1,412 pages | PASS | All seven zero on every real full-book page |
| Every line in exactly one unit and ordered exactly once | PASS | All 119,854 visual lines across all four full books |
| Book 1 ledger exactly 495,751 tokens | PASS | Full 758-page ledger and final retained source archive agree; zero missing/extra |
| 24-page source comparison | PASS | Frozen Step 11d six-pages-per-book sample; zero missing/extra on all 24 pages |
| Books 2–4 layout and downstream identity | PASS | Every page/book semantic digest identical to Step 11d |
| All four books' metric differences explained | PASS | 49 Spanish fields and four per other book; no metric excluded or noise exception applied |
| Producer equality with measured Spanish result | PASS | Raw pipeline and all scoped producer bytes match the recorded identity |
| Full tests and Ruff | PASS | 881 tests; worker equivalence/hash-once/default and deliberately missing-dependency closure included; Ruff checks and formatting pass |
| Native/analysis keys unchanged; downstream closure respected | PASS | All four books; layout and its dependent stages re-keyed |
| Native/analysis exact model digests unchanged | PASS | All 1,412 pages identical to the frozen Step 11d capture |
| Existing passing fallback credit labels retained | PASS | All 520 preserved |
| Final archive provenance and reference integrity | PASS | All files checksum correctly; source/unit digests and span references match all four runs |
| Historical evidence and local settings preserved | PASS | Original Step 11d manifest and its 83 covered files other than attributes unchanged; documented append-only attributes exception; settings untouched and untracked |
| Approved-source scope | PASS | Only books 1–4 measured; sealed ENT and mideast robustness books not run |

Step 11c's “I1–I7 zero” was a fixture-level result. Step 11d first measured the
full four books and found these five I5 failures. **Step 11e is the first verified
zero-violation I1–I7 result across all 1,412 real full-book pages.**

## Reproduction and commit audit

From the repository root, with the existing registered read-only references:

```powershell
$step11eBooks = 'spanish_us_history', 'immigrant_children', 'art_therapy_index', 'medical_anatomy'
foreach ($step11eBook in $step11eBooks) {
    .venv\Scripts\python.exe experiments\step11e_run.py run --book $step11eBook
    .venv\Scripts\python.exe experiments\step11e_run.py proof --book $step11eBook --fresh
}
.venv\Scripts\python.exe experiments\step11e_source_gates.py
.venv\Scripts\python.exe experiments\step11e_run.py compare
.venv\Scripts\python.exe experiments\step11e_compare_audit.py
.venv\Scripts\python.exe experiments\step11e_verify.py --manifest
```

The normal verifier's expected exit code is **1**: it records
`FAILED-FOR-REVIEW` because the accuracy regression remains, even when every other
required check passes. Manifest creation does not turn that failure into success.
After the one Step 11e commit, run:

```powershell
.venv\Scripts\python.exe experiments\step11e_verify.py --committed
```

The committed-byte audit's expected exit code is **0**. That command checks only
that manifested file bytes and the canonical layout producer identity match the
commit; it is not an accuracy pass. Test and Ruff results are recorded separately
above, with Ruff invoked from `backend/`.

## Limitations and carry-forward

The page 724 paragraph/order regression is retained for review under the owner's
decision. The semantic credit role of these lines cannot be rejected from the
layout evidence alone. I5's preserved solitary-line exception also means that
“pass I5” is weaker than “all credit evidence present” for the 462 other fallback
lines noted above. No hidden-text or character-repair result from Step 11d is
implemented here, and book 3 remains anecdotal.

The Step 12 and Step 17/adapter prompts must carry forward **`unknown` plus
`needs_review`** as the contract. Preserve the source and review state. Step 12
(figures and credits) is the natural place to evaluate a review stream or another
supported resolution of the page 724 interaction. That candidate is deferred;
this report does not start Step 12 or authorize adapter/XML work.

**Step 11d remains on hold. Step 12 has not started.**
