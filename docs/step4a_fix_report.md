# Step 4a-fix: layout invariants and root-cause fixes

Seven layout invariants (I1–I7) are now enforced by model validation, a shared checker and tests. Violations on the 24 measured pages (9 gold fixtures plus 15 unseen pages) went from 275 to 0. The gold band gates and text gates still pass. Two pages got worse in a way that needs your decision (see **Worse**). Step 4b has not started.

## Gate

| Gate | Result |
|---|---|
| pytest | **156 passed** (121 earlier + 35 new), 0 skipped; [junit](../experiments/out/step4afix/pytest.xml) |
| Ruff check / format (backend) | Pass |
| 9 fixtures: bands and columns vs gold, certain items | **9 / 9 pass** ([evaluation](../experiments/out/step4afix/layout_evaluation.json)) |
| Text gates, 9 fixtures + 15 unseen | **0 missing / 0 extra on all 24**; unseen pages also 0/0 against the original source page ([pages.json](../experiments/out/step4afix/pages.json)) |
| Full 758-page book | **495,751** retained tokens, 0 / 0 ([full_book.json](../experiments/out/step4afix/full_book.json)) |
| Device | auto; resolved to CPU on all pages |

No gold file, gate or threshold of an existing check was edited. Text spans, the span store and the ledger are unchanged. The layout version moved to `layout-proposals-2`, so old layout caches are not reused.

## Part 0: repository hygiene

- `experiments/fixtures_unseen/u11_spanish_fullpage_map.pdf` (47.7 MB) is untracked and listed in `.gitignore`. `experiments/recreate_unseen_fixtures.py` recreates any missing fixture from the manifest. It checks the source SHA-256 before cutting and the fixture SHA-256 after, and refuses on any mismatch.
- Recreation must be byte-exact, so the cut now saves without a random trailer `/ID`. All 15 fixtures were re-cut that way and the manifest updated. Their bands, lanes and regions are identical; only digests and ID-derived ordering changed.
- Tests that use unseen fixtures skip with an explicit message when the file is absent (`test_layout_invariants.py::real`).
- `fa7365f` was amended to **`a694aff`**; the u11 blob is in no reachable object (`git rev-list --all --objects` finds none).
- Repository size (`git count-objects -vH`): **127.56 MiB before** (446 loose objects, `.git` 129 MB) → **79.72 MiB after** amend, reflog expiry and `gc --prune=now` (one pack, `.git` 80 MB). Packing compression accounts for part of the reduction.

## Part 1: invariants and tests

The checker is `book_core.layout.invariants.check(layout, analysis)`. It reads a layout or its serialised dict, so the layout-proposals-1 JSON from Steps 4a and 4a-v is measured with the same code. It never repairs anything.

| Invariant | Definition used | Tests |
|---|---|---|
| I1 lane width | `Lane` requires `x0 < x1` (model validator) | `test_i1_lane_rejects_non_positive_width`, plus I1 in every page test |
| I2 band overlap | Bands of one scope may overlap along the scope's stacking axis by at most half the median font size (ascender/descender contact). Nested callout scopes and rotated scopes are separate scopes. Checked in `PageLayout` validation. | `test_i2_bands_of_one_scope_must_not_overlap`, `test_i7_edge_strip_opens_no_lane` |
| I3 figure text | No **paragraph-like** line is embedded in a figure. Paragraph-like means ≥ 5 letter-bearing words AND either (a) the page body style, or (b) a wrapped sequence: ≥ 3 stacked same-style lines sharing a left or right edge, or a justified pair. | `test_i3_running_text_over_a_faded_picture_stays_in_the_flow`, `test_i3_flat_backdrop_is_not_a_figure` |
| I4 content frame | The figure box stays inside the content (TrimBox) frame. No line in the furniture zone (top/bottom 7% of content height, the existing `EDGE_ZONE`) is embedded. | `test_i4_figure_stays_in_content_and_never_takes_furniture` |
| I5 rotated structure | At least 3 lines sharing a right-angle rotation must belong to a band. Cells of such a group are credits only if small, isolated and within 4 font sizes of a figure edge. | `test_i5_rotated_cells_build_structure_not_credits` |
| I6 tables | Aligned numeric cells without rules are a table candidate. Ruled grids that share ≥ 2 interior column rules within one row height are one table. | `test_i6_aligned_numeric_cells_are_a_table_candidate`, `test_i6_a_ruled_grid_is_not_split_at_a_heavy_rule`, `test_i6_multi_column_prose_is_not_a_table` (negative control) |
| I7 edges and locators | A page band at least half the content height has no text-free lane ≤ 10% of content width at the content edge. A lane of ≥ 3 short locator cells (≤ 3 tokens, digits) row-aligned with a neighbouring lane is not a column. | `test_i7_edge_strip_opens_no_lane`, `test_i7_locator_column_is_not_a_text_column` |
| All, real pages | Every invariant holds | `test_invariants_hold_on_gold_fixtures[*]` (9), `test_invariants_hold_on_unseen_pages[*]` (15) |

**Tests first.** The tests ran against the unchanged pipeline before any fix ([before-fix run](../experiments/out/step4afix/tests_before_fix.txt)): **21 failed**.
- All 10 synthetic invariant tests failed. Four synthetic pages (backdrop, edge strip, glossary, split grid) had to be rebuilt before they reproduced the real failure: the first versions did not trigger the old rule (for example, a uniform raster got no Step 3 role).
- The prose negative control passed, as intended.
- On real pages, 11 failed (worksheet, fission and u06–u09, u11–u15) and 13 passed.

**Interpretations to confirm:**
1. The I5 credit clause applies to cells of a structural rotated group ("rotated cells"). A single isolated rotated line (the margin credits on 7 pages) keeps the earlier credit rule.
2. I6 uses alignment only with numeric-column evidence. Short-text alignment also matched the unframed cards on u09, so text-only unruled tables are not detected.

## Part 2: fixes and the evidence each uses

All thresholds are relative: font size, line height, content-frame share, or dimensionless rendered-edge fractions. No page numbers, coordinates or fonts.

- **C1, figures do not grow over text** (`blocks.py`, `pipeline.ownership`):
  - *Textured extent.* A raster seed is measured on the rendered page with text masked out (lines dilated by 0.3 font size). Border rows or columns whose edge fraction is ≤ 0.01 are flat (a fade or empty border) and are trimmed. Example: the u15 photo bbox ran to y=360 while its texture ends at 282.
  - *Backdrop.* A raster with ≤ 0.02 edge fraction outside text and ≥ 3 lines painted on it is a flat field, not a picture. Example: the u09 grey panel at 0.008, against ≥ 0.05 for every real picture measured.
  - *Unknown visible extent.* An image placement with > 10% of its native box outside the page is a clipped view of a larger raster (the u06 sprite sheet, placed 16 times), so it seeds nothing.
  - *Content frame.* Figure bounds are clipped to the content frame (I4).
  - *Ownership.* Paragraph-like lines (I3) and furniture-zone lines (I4) are never embedded, including through label chaining.
- **C2, rotated structure** (`frames.py`, `pipeline.analyse_frame`): lines sharing a right-angle rotation, at least 3 of them, are transformed into their own reading frame. The transform is orthonormal, so distances are preserved. The same table, band, lane and region rules run there, and boxes map back to the page. These lines form a scope of kind `rotated`:
  - Band boxes are in page coordinates. Lane and gutter x positions are in the frame, documented on `Scope`, and the overlay maps them back.
  - Rotated frames have no furniture edge zones.
  - Single regions with credit evidence become credits.
- **C3, tables** (`tables.py`, `blocks.py`):
  - *Aligned cells.* Rows are lines sharing a baseline band with ≥ 2 cells at least one font size apart. A run has ≥ 3 rows less than 3 line heights apart. Columns are cells that overlap or share an edge or centre (0.75 font size), and must recur in ≥ 60% of rows. A run is a table only if ≥ 1 column is ≥ 70% numeric cells and no cell is paragraph-like.
  - *Ruled grids.* Grids sharing ≥ 2 interior column rules within one row height are merged. Outer edges alone are not evidence: the worksheet's section frame shares them with its inner table. A sparse ruled strip, such as a header row, may join a table it continues, but never the table it encloses.
- **C4, edges, locators, overlaps** (`blocks.py`, `bands.py`):
  - *Edge strips.* Narrow (≤ 10% of content width), tall (≥ 50% of content height), text-free artwork touching the left or right content edge (within 5%) is decoration, not a figure.
  - *Locators.* A lane made only of locator cells that sit on the rows of a neighbouring text lane joins that lane: the narrower of its gutters is dropped.
  - *Overlaps (I2).* Overlapping band groups merge. Only gutters that no member bridges are kept (a line past both gutter edges, or a block over the gutter's central half). Gutters overlapping in x are merged to their common part.
- **C5, positive lanes** (`models.py`, `bands.py`): `Lane` validation enforces I1. The root cause was a gutter with no band member on one side (the inverted `unknown` lanes on u09, u12 and u14), so a gutter now separates lanes only when non-inset members lie wholly on both of its sides.

## Part 3: before / after per invariant

Violations per invariant (before → after). The text gate is ledger missing/extra.

| Page | I1 | I2 | I3 | I4 | I5 | I6 | I7 | Text | Overlay |
|---|---|---|---|---|---|---|---|---|---|
| background_worksheet | 0 | 0 | 4 → 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/background_worksheet_regions.png) |
| colored_box | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/colored_box_regions.png) |
| column_100 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/column_100_regions.png) |
| column_26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/column_26_regions.png) |
| complex_cards | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/complex_cards_regions.png) |
| complex_map | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/complex_map_regions.png) |
| complex_sidebar | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/complex_sidebar_regions.png) |
| science_dissolving | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/science_dissolving_regions.png) |
| science_fission | 0 | 0 | 0 | 1 → 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/science_fission_regions.png) |
| u01 art index | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u01_art_index_3col_regions.png) |
| u02 science index | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u02_science_index_regions.png) |
| u03 Spanish index (check) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u03_spanish_index_4col_regions.png) |
| u04 Canadian scan | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u04_canadian_scanned_regions.png) |
| u05 image only | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u05_immigrant_image_only_regions.png) |
| u06 ruled table | 0 | 3 → 0 | 19 → 0 | 1 → 0 | 0 | 3 → 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u06_science_ruled_table_regions.png) |
| u07 rotated table | 0 | 0 | 0 | 0 | 218 → 0 | 1 → 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u07_immigrant_rotated_table_regions.png) |
| u08 unruled table | 0 | 0 | 0 | 0 | 0 | 1 → 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u08_immigrant_unruled_table_regions.png) |
| u09 unframed cards | 1 → 0 | 1 → 0 | 3 → 0 | 1 → 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u09_science_unframed_cards_regions.png) |
| u10 full-width figure | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u10_science_fullwidth_figure_regions.png) |
| u11 full-page map | 0 | 0 | 0 | 2 → 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u11_spanish_fullpage_map_regions.png) |
| u12 Spanish glossary | 4 → 0 | 4 → 0 | 0 | 1 → 0 | 0 | 0 | 2 → 0 | 0/0 | [png](../experiments/out/step4afix/u12_spanish_bilingual_glossary_regions.png) |
| u13 science glossary (check) | 0 | 1 → 0 | 0 | 1 → 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u13_science_bilingual_glossary_regions.png) |
| u14 sidebar (check) | 1 → 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u14_spanish_sidebar_regions.png) |
| u15 narrow + wide | 0 | 0 | 2 → 0 | 0 | 0 | 0 | 0 | 0/0 | [png](../experiments/out/step4afix/u15_science_narrow_wide_regions.png) |
| **Total** | **6 → 0** | **9 → 0** | **28 → 0** | **7 → 0** | **218 → 0** | **5 → 0** | **2 → 0** | | |

Bands, lanes, region counts and grouped review-flag causes for every page, before and after, are in [pages.json](../experiments/out/step4afix/pages.json). OCR was not run. u04's invisible layer is still `scan_layer` with 337 spans and 448 tokens, all `unknown` for review. u05 has no native text.

### Untouched checks

- **u03:** no change. Same bands (1 / 3 / 4 columns), regions and flags. Its 4a-v defect remains: the first two index rows are split into a separate 3-column band. The two bands overlap by 2.3 pt, which is within the I2 tolerance, so it is not counted as a violation.
- **u13:** changed.
  - The figure band (banner art plus side tab) overlapped the first two-column band and is now merged into it. The result is still 2 columns, with confidence .85 → .75.
  - Guide word "half-life/inertia": `caption_candidate` → `main_text`. Letter "H": `title_candidate` → `heading_candidate`.
  - The figure box is now clipped to the content frame.
  - An intermediate version of the overlap merge made this band 1 column, because the centred letter "H" sits inside the gutter. The merge was corrected generally: a gutter is now dropped only by a line that bridges both of its edges. It was not tuned to this page.
- **u14:** changed.
  - The chart-legend band lost its inverted `unknown` lane (the I1 violation). It is now **2 columns** [column, column] at 0.65, where it was 1 column [unknown, column, margin] at 0.40.
  - The right legend half went from `sidebar` to `main_text`.
  - Everything else is unchanged: the sidebar lane, the callouts, the table inside the strategy box, and the headings.

## Worse

Per your rule, I stopped here and did not adjust anything to hide these.

1. **science_fission (gold fixture) vs u11.** The I4 rule as specified ("furniture-zone lines are never embedded") takes the diagram label "Energy" (y 92–104, inside the top 7% zone) out of the top figure. It is now a `header_footer_candidate`. The same rule moves u11's CONÉCTATE footer bar out of the map figure, which is correct. Gold bands still pass.
   - **Decision needed:** how to define the furniture zone. For example, use detected running-furniture bands, or exempt lines painted over figure artwork.
2. **u14 (check page).** The legend is now counted as 2 text columns, where it was 1 column plus an invalid lane. The cause is C5: a gutter needs members on both sides, so the remaining gutter splits the two legend halves. The underlying defect is unchanged: the legend lies outside the chart's figure block.

**Changed, mixed, not counted as worse:**
- **background_worksheet:** the photo card's instruction text is in the flow now (I3). But the figure box still covers the text area, and the card's band lane went from [figure] to [column]. The worksheet A body gold is uncertain; the certain gold still passes.
- **u15:** the heading below the figure is no longer embedded. It is typed `caption_candidate`, because the caption rule runs before the heading rule. The narrow column's lines are now captions.
- **u12:** a band holding a single "(pág. 448)" gets a margin lane, typed `sidebar`. The locator rule needs ≥ 2 locator lines in a lane.

**Improvements to review on the overlays** (not claimed correct):
- u06: one table including its header row, plus the separate legend table. The banner art is a small figure.
- u07: a rotated scope with one table candidate, its title band and a note.
- u08: the table is a table candidate. The running head and folio are still `main_text`.
- u09: the reviewer panel is a callout scope with its own bands. The cards still read as 4 columns, the known limitation.
- u11: the footer bar is a header/footer candidate.
- u12: no page-height band; the locator lane is merged.

## Notes

- The layout cache key covers the source, the Step 3 analysis, `LAYOUT_VERSION` and dependencies, but not code. During development the stale `layout-proposals-2` entries were cleared before every reported run.
- Reproduce with `cd experiments; python recreate_unseen_fixtures.py; python step4afix_run.py`.
- New modules:
  - `layout/evidence.py`: script-agnostic text evidence.
  - `layout/frames.py`: reading-frame transforms.
  - `layout/tables.py`: aligned cells and grid continuity.
  - `layout/invariants.py`: the checker.

**Step 4a-fix stops here.**
