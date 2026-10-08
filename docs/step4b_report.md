# Step 4b: learned layout detectors as evidence

Both models run on all **24 measured pages** in the main Python **3.14.8** environment.
All gates pass. Fusion preserves own geometry, types, memberships, bands, lanes and
text exactly; only confidence and review annotations change. **K1-K8 remain unchanged**
in own/fused output, with useful model evidence for several corrections. Step 5 has not started.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| Part 0, earlier tests after derived-cache clearing | **156 passed** | [junit](../experiments/out/step4b/part0_pytest.xml) |
| Part 0, 24 pages vs 4a-fix | **No band/lane/type/block changes; text 0/0; I1-I7 all 0** | [comparison](../experiments/out/step4b/part0_comparison.json) |
| Final tests, optional models installed | **215 passed**, 0 skipped (156 earlier + 59 new) | [junit](../experiments/out/step4b/pytest.xml) |
| Final text ledger, all 24 pages | **0 missing / 0 extra**; ledger and span-store payloads unchanged by detection/fusion | [manifest](../experiments/out/step4b/manifest.json) |
| All 24 fixtures vs original source pages | **0 missing / 0 extra** | [source cross-check](../experiments/out/step4b/original_source_crosscheck.json) |
| Full 758-page book | **495,751 retained tokens**, 0/0; 92,228 - 7,194 = 85,034 retained lines | [full book](../experiments/out/step4b/full_book.json) |
| Certain gold bands/columns | **9/9 fixtures pass**, own and fused | per-page gold evaluations in manifest |
| I1-I7 after fusion | **0 each**, all 24 pages | manifest |
| Bands/lanes vs 4a-fix | **Exact equality**, all 24; no accuracy reduction | manifest |
| CPU model repeats, nine gold fixtures x two models | **18/18 tolerance gates pass**, 0 boundary-unmatched regions | manifest and `*_repeat.json` |
| Ruff check / format | Pass, run from `backend/` | [checks](../experiments/out/step4b/final_checks.log) |

The benchmark remains case-sensitive NFKC Unicode token Counters after explicit
TrimBox exclusions and before furniture removal. Native text order remains evidence,
without a semantic reading-order or paragraph claim. The runner retains its 22 existing
external counter comparisons; the separate original-source cross-check covers all 24,
including both science fixtures. No gold, existing gate, own rule
or old project was edited. No additional owner overlay notes were supplied.

## Cache correctness

Every producing Python file contributes to a SHA-256 key, including transitive native,
object, layout and detector producers. Keys include chained source/configuration,
versions/dependencies (including Python/Unicode), `LAYOUT_VERSION`, render identity,
model revision, threshold and actual resolved device where applicable. Model revision
and learned threshold are inapplicable to own-only geometry; its rule constants are
source-hashed. A changed producer requires a worker restart, preventing old loaded code
from writing new-source keys. GPU recovery is stored under CPU, never the failed CUDA key.

Project-local derived analysis/layout/repetition and legacy derived caches were cleared
before the Part 0 run. Native extraction caches remained read-only inputs unless their
new fingerprints required regeneration. Weights are immutable download assets, separate
from derived outputs. Source-edit, producer-closure, runtime/configuration, corruption,
and CPU-recovery regressions pass. See [caching.md](caching.md).

## Installation and execution

| Adapter | Official inference path | Main project result | Weight size / license |
|---|---|---|---|
| Docling Heron | Transformers AutoImageProcessor + AutoModelForObjectDetection | Installs and runs on CPython 3.14.8 | 171,658,996 bytes; Apache-2.0 |
| PP-DocLayoutV3 | Same official Transformers path, with official PP postprocessing | Installs and runs on CPython 3.14.8 | 133,270,468 bytes; Apache-2.0 |

Pinned revisions match Phase 0: Heron `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`,
PP `e4f489dc536556fc1be02b973ba06756e0d4a2ac`. Optional `universal-book-core[models]`
uses Torch **2.14.1+cpu**, torchvision **0.29.1+cpu**, Transformers **5.19.0**,
Pillow **12.3.0**, safetensors **0.8.0** in this audited installation. Default dependencies
and their lock are unchanged. Weights/caches are git-ignored. No install failure or
compatibility workaround; `pip check` passes. Versions, licenses, weight digests and
install logs are linked in [dependencies.md](dependencies.md).

Gold and repeat runs explicitly use CPU. Auto smokes resolved and executed CPU because
CUDA is unavailable. GPU fallback and fresh CPU reload are tested; real CUDA inference
could not be measured on this hardware. Model renders use Phase 0's **1 pixel/point
(72 dpi)**, including the full unrotated crop frame. Own geometry retains its earlier
2x render. All extraction/rendering goes through the Extractor interface; OCR is not run.

## Fusion policy and thresholds

`RegionDetector` consumes rendered pixels and returns boxes/types/raw labels and provenance,
without text, span ownership or a ledger argument. Fusion keeps the complete model results
beside the copied own layout. A type-compatible match with IoU >= **0.5** increases confidence;
other overlaps/unmatched regions are review evidence with both sources retained.
Heading/title and furniture/folio are explicitly compatible coarse type pairs; `unknown`
never corroborates a type. Confidence gain **0.1** is a heuristic, not a calibrated probability.

A composite candidate stays intact if a model proposes fragments. Own geometry and all
I1-I7 outputs are protected by exact checks; model figures leaving the content frame are
flagged. Persist the full `FusionResult`, including model-only comparisons, rather than
only its `PageLayout`. Model reading order is ignored.

**Threshold changes: none.** Detection 0.5 -> 0.5; fusion IoU 0.5 throughout;
CPU repeat tolerance is IoU >= 0.95, score delta <= 0.02, explicitly reported threshold-edge
margin 0.02 (unused in these 18 repeats). No earlier threshold was changed.

## Region-type agreement with existing gold

Certain items only; the existing evaluator is unchanged. Gold remains
`human_approved: false`. Model labels map conservatively to candidate types (a generic
`number` remains `unknown`). Different box granularity and taxonomy affect these counts;
they are descriptive, with no combined score.

| Fixture | Own | Heron | PP | Fused |
|---|---:|---:|---:|---:|
| background_worksheet | 12/13 | 7/13 | 9/13 | 12/13 |
| colored_box | 9/9 | 3/9 | 5/9 | 9/9 |
| column_100 | 12/12 | 7/12 | 8/12 | 12/12 |
| column_26 | 8/8 | 2/8 | 4/8 | 8/8 |
| complex_cards | 15/16 | 11/16 | 13/16 | 15/16 |
| complex_map | 7/7 | 4/7 | 4/7 | 7/7 |
| complex_sidebar | 12/12 | 7/12 | 7/12 | 12/12 |
| science_dissolving | 15/15 | 13/15 | 13/15 | 15/15 |
| science_fission | 8/8 | 7/8 | 6/8 | 8/8 |

## Columns, lanes and disagreements per page

Own/fused entries are **scope + columns/total lanes per band**: p = page, c = callout,
r = rotated scope. Their sequences are identical to 4a-fix, in stored pipeline order
(not semantic order). Model entries are **spatial text components / existing own lanes
with text support**, aligned to those same bands. Models predict no bands or semantic
columns: those metrics are **N/A**, rather than invented from their box count. A model
box enters this diagnostic only when >= half its area lies in a band; overlapping x
intervals form components. Full band bounds, lane kinds and support counts are in manifest.

Disagreements count comparison records (type/geometry mismatches, unmatched regions or
figure fragments), not missing tokens. Granularity, production marks and invisible-layer
regions contribute; for example Heron's u02 index boxes produce many unmatched fragments.

| Page | Own = fused columns/lanes | Heron components/support | PP components/support | H disagreements | PP disagreements |
|---|---|---|---|---:|---:|
| background_worksheet | p1/1, p0/1, p0/1, p1/1, p1/1, c1/2, c1/1, c2/2, c1/1 | 0/0, 2/1, 2/1, 0/0, 2/1, 2/2, 0/0, 2/2, 1/1 | 0/0, 2/1, 2/1, 0/0, 0/0, 2/2, 0/0, 2/2, 1/1 | 25 | 19 |
| colored_box | p1/1, p1/2, p1/1, c0/1, c1/1, c1/1 | 1/1, 2/2, 2/1, 0/0, 1/1, 1/1 | 0/0, 2/2, 0/0, 0/0, 1/1, 1/1 | 22 | 16 |
| column_100 | p2/2, p1/1, c1/1 | 2/2, 1/1, 1/1 | 2/2, 0/0, 0/0 | 23 | 24 |
| column_26 | p1/1, p2/2, p1/1, c1/1 | 1/1, 3/2, 1/1, 2/1 | 1/1, 3/2, 0/0, 2/1 | 36 | 25 |
| complex_cards | p1/1, p2/2, p0/1, p0/4, p1/1, c1/1 | 1/1, 2/2, 1/1, 4/4, 3/1, 1/1 | 1/1, 2/2, 1/1, 4/4, 0/0, 1/1 | 48 | 34 |
| complex_map | p1/1, p0/1, p1/1, p2/2, p1/1 | 1/1, 0/0, 1/1, 2/2, 2/1 | 0/0, 0/0, 1/1, 2/2, 0/0 | 23 | 20 |
| complex_sidebar | p0/1, p0/1, p1/1, c2/2, c0/2, c2/2 | 2/1, 2/1, 1/1, 2/2, 1/1, 2/2 | 2/1, 2/1, 0/0, 2/2, 0/0, 2/2 | 16 | 15 |
| science_dissolving | p1/2, p1/1, c1/1 | 1/1, 1/1, 1/1 | 1/1, 0/0, 1/1 | 12 | 10 |
| science_fission | p1/2, p1/1, p0/1 | 2/2, 0/0, 0/0 | 1/1, 0/0, 0/0 | 12 | 12 |
| u01 | p1/1, p3/3 | 0/0, 3/3 | 0/0, 3/3 | 12 | 27 |
| u02 | p1/1, p3/3 | 0/0, 3/3 | 0/0, 3/3 | 178 | 27 |
| u03 | p1/1, p3/3, p4/4 | 0/0, 1/1, 4/4 | 0/0, 1/1, 4/4 | 76 | 51 |
| u04 | N/A | - | N/A | 45 | 44 |
| u05 | N/A | - | N/A | 9 | 6 |
| u06 | p0/1, p0/1, p0/1, p1/1, p1/1 | 0/0, 5/1, 0/0, 1/1, 2/1 | 0/0, 1/1, 1/1, 1/1, 0/0 | 36 | 27 |
| u07 | p1/1, r0/1, r1/1, r1/1 | 0/0, 0/0, 0/0, 0/0 | 0/0, 0/0, 0/0, 0/0 | 81 | 80 |
| u08 | p0/1, p1/1, p1/1 | 0/0, 0/0, 1/1 | 0/0, 0/0, 1/1 | 10 | 9 |
| u09 | p0/1, p3/3, p1/1, p1/1, p4/4, p1/1, p4/4, p1/1, c1/1, c4/4 | 1/1, 3/3, 0/0, 1/1, 4/4, 1/1, 4/4, 1/1, 1/1, 4/4 | 1/1, 3/3, 0/0, 1/1, 4/4, 1/1, 4/4, 1/1, 1/1, 4/4 | 68 | 23 |
| u10 | p1/1, p0/1, p0/1, p1/1, p0/1, p1/1, p1/1, c1/1, c1/1 | 1/1, 1/1, 1/1, 1/1, 0/0, 1/1, 1/1, 1/1, 1/1 | 0/0, 1/1, 1/1, 0/0, 0/0, 1/1, 1/1, 1/1, 1/1 | 25 | 22 |
| u11 | p0/1 | 0/0 | 0/0 | 105 | 103 |
| u12 | p1/1, p2/2, p2/2, p2/3, p2/2, p1/1 | 0/0, 0/0, 0/0, 0/0, 0/0, 2/1 | 0/0, 0/0, 0/0, 0/0, 0/0, 0/0 | 40 | 34 |
| u13 | p2/2, p1/1, p2/2, p1/1 | 2/2, 0/0, 2/2, 1/1 | 3/2, 0/0, 2/2, 0/0 | 64 | 58 |
| u14 | p1/2, p2/2, p1/1, c0/1, c1/1, c1/1 | 2/2, 0/0, 2/1, 0/0, 1/1, 1/1 | 2/2, 0/0, 1/1, 0/0, 1/1, 0/0 | 30 | 18 |
| u15 | p1/1, p0/1, p0/1, p1/1, p1/1, c1/1 | 1/1, 1/1, 1/1, 1/1, 1/1, 1/1 | 0/0, 1/1, 0/0, 1/1, 1/1, 1/1 | 13 | 13 |

## Pages without gold: review evidence

No new gold was written. T/G/O/M/F = type disagreement / geometry disagreement /
own-only / model-only / fragmented figure. Unseen IDs and source details remain the
approved Step 4a-v set. Every page retains both model outputs in its `_fused.json` sidecar.

| Page | Heron T/G/O/M/F | PP T/G/O/M/F | Disagreement overlay |
|---|---|---|---|
| u01 | 1/1/0/10/0 | 1/3/0/23/0 | [png](../experiments/out/step4b/u01_art_index_3col_disagreements.png) |
| u02 | 8/5/0/165/0 | 3/4/5/15/0 | [png](../experiments/out/step4b/u02_science_index_disagreements.png) |
| u03 | 6/9/4/57/0 | 3/9/5/34/0 | [png](../experiments/out/step4b/u03_spanish_index_4col_disagreements.png) |
| u04 | 5/19/21/0/0 | 4/20/20/0/0 | [png](../experiments/out/step4b/u04_canadian_scanned_disagreements.png) |
| u05 | 0/0/0/9/0 | 0/0/0/6/0 | [png](../experiments/out/step4b/u05_immigrant_image_only_disagreements.png) |
| u06 | 6/5/2/22/1 | 2/5/5/15/0 | [png](../experiments/out/step4b/u06_science_ruled_table_disagreements.png) |
| u07 | 3/1/77/0/0 | 3/0/77/0/0 | [png](../experiments/out/step4b/u07_immigrant_rotated_table_disagreements.png) |
| u08 | 4/0/4/2/0 | 4/0/4/1/0 | [png](../experiments/out/step4b/u08_immigrant_unruled_table_disagreements.png) |
| u09 | 7/8/0/53/0 | 3/8/3/9/0 | [png](../experiments/out/step4b/u09_science_unframed_cards_disagreements.png) |
| u10 | 11/5/1/7/1 | 4/5/3/9/1 | [png](../experiments/out/step4b/u10_science_fullwidth_figure_disagreements.png) |
| u11 | 4/1/98/2/0 | 2/1/100/0/0 | [png](../experiments/out/step4b/u11_spanish_fullpage_map_disagreements.png) |
| u12 | 6/2/27/5/0 | 4/2/28/0/0 | [png](../experiments/out/step4b/u12_spanish_bilingual_glossary_disagreements.png) |
| u13 | 8/8/0/48/0 | 4/6/6/42/0 | [png](../experiments/out/step4b/u13_science_bilingual_glossary_disagreements.png) |
| u14 | 15/4/2/9/0 | 5/2/11/0/0 | [png](../experiments/out/step4b/u14_spanish_sidebar_disagreements.png) |
| u15 | 6/1/6/0/0 | 5/1/4/3/0 | [png](../experiments/out/step4b/u15_science_narrow_wide_disagreements.png) |

u04's 448 invisible-layer tokens remain retained/unknown; models can propose visual
regions without owning that layer. u05 has zero native tokens; model text boxes do not
create text. Their disagreements remain review evidence.

## K1-K8 before / after

All statuses below concern **own -> fused output**. Model evidence is advisory; it does
not silently retype content, transfer text or repair geometry.

| Issue | Before (4a-fix) -> after (4b) | Status | Heron / PP evidence |
|---|---|---|---|
| K1 fission Energy / u11 footer | `header_footer_candidate` / `header_footer_candidate` -> same | Unchanged | Both diagram boxes fully cover Energy (H .966, PP .957); both map boxes exclude u11's footer. They separate the geometry. H calls the footer caption at .501; PP has no footer box at .5. Furniture taxonomy still needs Step 8 repetition. |
| K2 u14 legend | Outside own chart; 2-column band -> same | Unchanged | PP's chart .918 includes both legend columns. Heron's plot-only .729 excludes them; its broad .613 picture also covers surrounding text, so that alternative is ambiguous. |
| K3 u03 index rows | First two rows in separate 3-column band, then 4 columns -> same | Unchanged | Both models show four lower text components, but provide no band decisions. Their first-row boxes do not authorize a band merge. |
| K4 u09 cards | Unframed cards counted as 4 columns -> same | Unchanged | Both produce four text components in card rows; neither establishes card scopes. H emits 88 total regions vs PP 40, largely finer text/heading fragments. |
| K5 u08 furniture/table | Running head and folio `main_text`; numeric table already detected -> same | Unchanged | H/PP identify head as furniture (.950/.871); H folio is header (.929), PP generic number is unknown (.780). Both detect the existing unruled numeric table (.990/.965). General text-only unruled tables remain unproven. |
| K6 u12 locator | Lone `(pág. 448)` band is `sidebar` -> same | Unchanged | Both cover that locator inside a whole glossary table (H .989, PP .972), rather than a sidebar. No band/ownership change; native text remains preserved. |
| K7 u15 heading | Heading below figure is `caption_candidate` -> same | Unchanged | Both propose a heading: H section_header .940, PP paragraph_title .850. The separate narrow figure caption has mixed model taxonomy. |
| K8 worksheet photo card | Own figure box covers instruction area; instruction remains in flow -> same | Unchanged | Both photo boxes exclude instruction text (H .972, PP .953); both classify instruction as text (.969/.922). Strong narrower-extent evidence, with own bounds preserved. |

Exact native line/span IDs, model boxes and scores are in each `_line_evidence.json`;
those files are diagnostic reports, not core text copies or gold. No K issue is made
worse by fusion because own protected fields are identical.

## Phase 0 failures

| Failure | Heron now | PP now | Fusion effect |
|---|---|---|---|
| Figure 16 split into three panels | Reproduces: three picture boxes, .979-.982 | Reproduces: three image boxes, .950-.971 | Preserves all existing own candidates. **4a-fix itself already has three panel candidates**, so no new semantic composite parent is claimed. Synthetic fragment tests show that a supplied single own candidate cannot be split. |
| complex_map right glossary definition omitted | Covers it as text, .832 | Reproduces omission at .5 | Definition remains retained as own footnote candidate; no token loss. |
| complex_cards NAACP text sequence | Raw positions are diagnostic only; no native reading-order claim | Reproduces: later 1955-1956 box emitted at zero-based 24 before 1954 box 25 | Sequence ignored. Text stays in native span order; semantic reading order remains Step 7. |

## Eight focused overlays

Three panels show own / Heron / PP. `!` and thick outlines mark disagreement; thin
outlines mark agreement. Numbers identify regions for review, never reading order.

- [science_fission_disagreements.png](../experiments/out/step4b/science_fission_disagreements.png) - K1 Energy.
- [science_dissolving_disagreements.png](../experiments/out/step4b/science_dissolving_disagreements.png) - three-panel split.
- [complex_map_disagreements.png](../experiments/out/step4b/complex_map_disagreements.png) - missing definition.
- [background_worksheet_disagreements.png](../experiments/out/step4b/background_worksheet_disagreements.png) - K8 instruction/photo.
- [u08_immigrant_unruled_table_disagreements.png](../experiments/out/step4b/u08_immigrant_unruled_table_disagreements.png) - unseen K5.
- [u11_spanish_fullpage_map_disagreements.png](../experiments/out/step4b/u11_spanish_fullpage_map_disagreements.png) - unseen K1 footer.
- [u14_spanish_sidebar_disagreements.png](../experiments/out/step4b/u14_spanish_sidebar_disagreements.png) - unseen K2 legend.
- [u15_science_narrow_wide_disagreements.png](../experiments/out/step4b/u15_science_narrow_wide_disagreements.png) - unseen K7 heading.

## Decisions for review

1. Review PP's u14 legend extent, both worksheet photo extents and the u15 heading evidence
   as proposals for a separately authorized correction gate.
2. Keep K1's furniture decision pending whole-book repetition (Step 8), despite useful
   model geometry; decide how that evidence should interact with I4.
3. Review a future Figure 16 composite parent and the unresolved card/text-only-table scopes.
   They are not repaired or annotated as new gold here.

Reproduce: install the optional extra as in dependencies.md, then run
`python experiments/step4b_run.py --device cpu` (all 24, with nine-gold CPU repeats),
`python experiments/step4b_source_crosscheck.py`, and `python experiments/step4b_summary.py`.
Run pytest and Ruff only after `cd backend`. Per-page derived detections are cached in
`.cache/models/`; full review artifacts are in `experiments/out/step4b/`.

**Step 4b stops here for owner review. No Step 5 work.**
