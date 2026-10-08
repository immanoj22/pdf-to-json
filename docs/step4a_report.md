# Step 4a gate: lines, bands, per-band columns, region proposals

Built visual lines, band segmentation with columns decided per band, typed region proposals from own geometry, column gold for the nine fixtures, and a region overlay. No reading order, paragraphs, furniture-text decisions, table structure or learned models were added. Step 4b has not started.

## Gate

| Gate | Result |
|---|---|
| pytest (all earlier tests included) | **121 passed**, 0 skips/failures (Step 3: 93); [junit](../experiments/out/step4a/pytest.xml) |
| Ruff check / format | Pass |
| 9 fixtures + 2 image-boundary regressions | **0 missing / 0 extra** on all 11 ([fixtures](../experiments/out/step4a/fixture_gate.json), [regressions](../experiments/out/step4a/regression_gate.json)) |
| Full 758-page book | **495,751 retained tokens**, 92,228 − 7,194 = 85,034 lines, 0 / 0 vs frozen cache ([full book](../experiments/out/step4a/full_book.json)) |
| Bands and column counts vs gold, certain items | **9 / 9 fixtures pass**: every certain band matched with the same column count, 0 unexcused extra bands ([evaluation](../experiments/out/step4a/layout_evaluation.json)) |

The token benchmark definition is unchanged: case-sensitive NFKC, Unicode letter/mark/number runs, Counter multisets, order unchecked; measured after TrimBox exclusion and before furniture removal. The text ledger and span store were not modified.

## Part 0

- Git was not installed on this machine; Git for Windows 2.55 was installed (winget) with your approval. Step 3 commit `35c2465` confirmed; working tree clean before work began.
- Gold-role corrections: none supplied (prompt placeholder unfilled); by your choice the `roles_*.json` files are **unchanged and still `human_approved: false`**.
- Unknown-object policy implemented: unknown visual objects never block processing; each gets a non-blocking `ReviewFlag` in `PageLayout.review_flags` (tested: the flagged set equals the Step 3 unknown set).

## What was built

- **Span geometry evidence.** The extractor now also records each span's baseline origin, direction and writing mode, keyed by the existing span IDs, on the native object page. Span IDs, object IDs, the span store and the ledger are unchanged (Step 3 gold object IDs still resolve). Only the native-object cache version moved.
- **Visual lines** (`layout/lines.py`). Spans are grouped along their own writing direction by shared baseline; native lines split at large gaps and tab stops and join across native lines on one baseline (justified word fragments, drop quotes, sub/superscripts). Lines reference spans only, keep native span order, and carry baseline, rotation, writing mode and `text_direction` from Unicode bidi classes (`None` when no strong characters; never assumed). Rotated credits stay separate rotated lines.
- **Visual blocks** (`layout/blocks.py`) from Step 3 roles: backgrounds are never blocks; containers become callouts unless they hold artwork with only short labels (figure panels) or match their ground colour (frames); figure parts, images and adjacent unresolved local artwork cluster into figure candidates; ruled grids with text become table candidates; broad bands are obstacles only; thin long strokes are rules.
- **Scopes and bands** (`layout/bands.py`). Each scope (page content frame, or a callout interior, recursively) is rasterised from free lines and blocks. Gutter seeds are empty strips found by OpenCV opening with a text lane on both sides; each seed extends along its own strip until text, a rule or a block's central half crosses it. Callouts/figures crossing a gutter while text continues on both sides are bridged as insets. Bands are maximal vertical intervals with one gutter set; wide blocks without gutters form their own bands. Lanes are typed column / sidebar / figure / callout / table / card / caption / margin; **column count = column lanes only**. Rendered ink (Canny) inside each gutter and vertical rules are recorded as evidence.
- **Regions** (`layout/regions.py`, `layout/pipeline.py`). Every visual line is a direct member of exactly one region (validated). Types are proposed from combined cues (position, rules, adjacent figures, style contrast with the scope's body style, isolation, lane kind); headings need style difference plus at least two further cues, never size alone. Confidence below 0.6 becomes `unknown` with the proposal kept and a review flag.
- **Cache**: layout results are cached per page with a fingerprint chained from the object-analysis fingerprint plus layout version, dependency versions and resolved device. Execution is CPU (OpenCV/NumPy); provenance records both devices.
- **Overlay/CLI**: `book-core overlay <pdf> --page N --regions --out file.png` draws page bands (tinted), callout-scope bands (thin), gutters (magenta), lane kinds, region types with confidence, and review flags (red, `!`). The JSON sidecar is the complete `PageLayout`.

## Bands per fixture: expected vs found

Gold was written before any Step 4a output existed, from rendered pages and native line coordinates; it is an assistant annotation, `human_approved: false`. **U** = explicitly uncertain gold. Columns count text-column lanes only.

| Fixture | Band (scope) | Expected cols, lanes | Found cols, lanes | Band conf. |
|---|---|---|---|---:|
| column_26 | title | 1 | 1 | .85 |
| | body (pull quote inset) | 2 | 2, inset bridged | .60 ⚑ |
| | bottom | 1 | 1 | .70 |
| column_100 | body (chart panel in left column) | 2 | 2 | .75 |
| | bottom | 1 | 1 | .70 |
| complex_map | panel title **U** | 1 | 1 | .70 |
| | map | 0 [figure] | 0 [figure] | .80 |
| | questions | 1 | 1 | .85 |
| | body | 2 | 2 | .85 |
| | bottom glossary + folio **U** | 2 | 1 | .85 |
| complex_cards | title | 1 | 1 | .70 |
| | body | 2 | 2 | .85 |
| | card-panel header | 0 [callout] | 0 [callout] | .80 |
| | cards | 0 [4 cards] | 0 [4 cards] | .65 ⚑ |
| | footer | 1 | 1 | .70 |
| colored_box | title | 1 | 1 | .70 |
| | body | 1 [sidebar, column] | 1 [sidebar, column] | .75 |
| | footer | 1 | 1 | .70 |
| complex_sidebar | panel C / panel D / folio (page) | 0 / 0 / 1 | 0 / 0 / 1 | .80/.80/.70 |
| | C text / C photo / D text | 2 / 0 [figure, caption] / 2 | 2 / 0 [figure, caption] / 2 | .85/.70/.85 |
| background_worksheet | banner **U** / title / A / B / footer (page) | 1 / 1 / 0 / 0 / 1 | 1 / 1 / 0 / 0 / 1 | .70–.80 |
| | A body **U** | 1 [column, figure] | 1 [column, sidebar] | .80 |
| | B heading / B body (with table) | 1 / 2 | 1 / 2 | .70/.75 |
| science_dissolving | body | 1 [column, figure] | 1 [column, figure] | .75 |
| | footer bar **U** | 1 | 1 (y-overlap 0.49) | .70 |
| science_fission | upper | 1 [column, figure] | 1 [column, figure] | .80 |
| | lower (spanning Figure 9) | 0 [figure, caption] | 0 [figure] | .80 |
| | footer bar **U** | 1 | 1 (y-overlap 0.49) | .70 |

⚑ = band review flag. The figure lanes on both science pages and the card lanes are not counted as columns. Synthetic tests also check 1-, 2- and 3-column pages and a title / 2-column / spanning-image / 2-column page (`[1, 2, 0, 2]`).

## Region-type agreement (reported only; no overall score)

Certain gold regions agreeing / total: column_26 8/8, column_100 12/12, complex_map 7/7, complex_cards 15/16, colored_box 9/9, complex_sidebar 12/12, background_worksheet 12/13, science_dissolving 15/15, science_fission 8/8. Uncertain samples (14) are listed separately in the evaluation file. Misses:

- complex_cards: the CONECTATE bar is proposed as `footnote_candidate` because the card panel's bottom rule sits directly above it.
- background_worksheet: the astronaut photo is inside a dark activity card that is proposed as a callout; the figure region is nested in it and the evaluator picks the card.

## Overlays to review

1. [column_26_regions.png](../experiments/out/step4a/column_26_regions.png) — two columns, pull quote bridged as an inset.
2. [complex_map_regions.png](../experiments/out/step4a/complex_map_regions.png) — spanning map band above two columns; 200+ map labels embedded in the figure.
3. [complex_cards_regions.png](../experiments/out/step4a/complex_cards_regions.png) — two columns, header callout, four framed card lanes.
4. [complex_sidebar_regions.png](../experiments/out/step4a/complex_sidebar_regions.png) — per-panel bands inside two callout scopes.
5. [colored_box_regions.png](../experiments/out/step4a/colored_box_regions.png) — sidebar lane beside one main column.
6. [science_fission_regions.png](../experiments/out/step4a/science_fission_regions.png) — figure lane not counted; spanning Figure 9 band.

All nine fixtures have overlays and complete JSON sidecars in `experiments/out/step4a/`.

## Review-flag list

[review_flags.json](../experiments/out/step4a/review_flags.json). Visual-object flags (Step 3 unknowns, non-blocking): worksheet 288, colored_box 264, column_100 32, column_26 256, cards 263, map 1,396, sidebar 263, dissolving 881, fission 1,066 — mostly clip/group state and unresolved artwork primitives. Band flags: column_26 body (inset bridge plus few items lowers confidence) and complex_cards cards band (card frames put rendered ink inside the gutters). No region fell below the unknown threshold on these fixtures.

## Limitations

- Geometry is still bounding-box based; the pull quote works because the inset is bridged, not because the circle's outline is used.
- Figure grouping is proximity-based: Figure 9's legend icon is a separate small figure; Figure 8's caption is not linked to it. Semantic figure/caption pairing is not attempted.
- Header/footer/page-number/footnote types are single-page geometric proposals; cross-page repetition is not used yet.
- Card detection needs each lane to have its own drawn frame; unframed card grids would read as columns.
- Thresholds are relative to page size and median font size but were tuned on these nine fixtures only; no unseen-book validation yet.
- CJK/vertical and right-to-left handling is tested only on synthetic lines.

## Decisions for you

1. Review the column gold (`backend/tests/gold/columns_*.json`), especially the uncertain items: worksheet section A (1 or 2 columns?), complex_map glossary/folio rows, banner and footer-bar bands.
2. Supply the gold-role corrections when ready; they remain unreviewed.
3. Confirm the taxonomy choices: a box whose content is a full section (complex_sidebar, worksheet) is a callout scope with its own bands; caption boxes are callouts with a caption child; card text is proposed as `sidebar`.
4. Choose the next validation set: unseen pages from the 758-page book and the science book before tuning anything further.

**Step 4a stops here.**
