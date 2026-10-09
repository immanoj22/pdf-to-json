# Step 3 gate: page objects

Built the native object graph, transparent asset roles, asset ledger and reusable overlay CLI. No region grouping, reading order, paragraphs, headings, tables, furniture-text detection, OCR or adapters were added.

## Gate

**93 tests passed; Ruff passed; pip check passed.** All earlier tests remain included. The nine Phase 0 fixtures and two earlier image-boundary regressions have **0 missing / 0 extra** tokens.

The 758-page book reproduces **495,751 retained tokens**: 92,228 nonblank source lines minus 7,194 explicit TrimBox exclusions = 85,034 retained lines. This is **after TrimBox exclusions, before removing headers/footers/page numbers**. The tokenizer and ledger accounting implementation are unchanged: case-sensitive NFKC, Unicode letter/mark/number runs, Counter multisets, order unchecked. See [full gate](../experiments/out/step3/full_book.json), [fixture gates](../experiments/out/step3/fixture_gate.json), [earlier regressions](../experiments/out/step3/regression_gate.json) and [pytest results](../experiments/out/step3/pytest.xml).

Old-project audit: **1,309 protected files unchanged**, old Git HEAD/status preserved within the documented Step 2b audit scope. External Spanish PDF also matches the frozen benchmark fingerprint. [Audit evidence](../experiments/out/step3/old_project_verification.json).

## Product structure

- Extractor/ObjectExtractor contracts expose native page objects, raster rendering and document image repetition. PDF parsing/rendering stays behind PyMuPDF.
- Text objects reuse span-store IDs. Images/shadings, every drawing path, clips/groups, native paint commands and text traces (including invisible text) remain available. CompoundVisual members stay individually addressable.
- Shapely STRtree indexes object bounds; NetworkX DiGraph records paint/containment/overlap/touch/member relations. These are **bounding-box relations**, not exact curved-path intersections. Relation safety limits mark an incomplete graph explicitly; no asset is dropped. All nine fixture graphs are complete.
- Consolidation joins adjacent same-style primitives inside an uninterrupted paint run; text/image paints break runs. It creates primitive compounds, never complete figures.
- Native and derived caches are separate, atomic and checksum-validated. Fingerprints include source, extractor/configuration, dependency/rule versions, repetition evidence and resolved device. IDs do not depend on resolved device.
- Settings.device defaults to auto; probing and GPU-operation failures recover to CPU. Provenance records resolved and execution devices. This environment resolved **CPU**; native extraction/geometry execute on CPU. GPU recovery is tested with injected failures; actual CUDA hardware was not tested.
- SpanRef now supports optional half-open original Unicode character offsets, JSON round-trip and source-range validation. Existing full-span ledger ownership stays unchanged; splitting token ownership across ranged references is deferred. Optional visual_refs prepare existing callout/nodes for object references.

Run from the new repository root:

    .venv\Scripts\book-core overlay experiments\fixtures\colored_box.pdf --page 1 --out experiments\out\review.png

Default overlays suppress ambiguous drawing primitives/state records for readability; JSON sidecars retain every object, role, reason and link. Use --all-objects for exhaustive primitive/text bounds.

## Fixtures

All asset ledgers have 0 missing/extra. Unknown totals include retained clip/group state and unassociated/empty paint records. CPU analysis times below reuse native caches; they include derived analysis and omit final overlay rendering.

| Fixture | Raster / shading / drawings | Compounds (largest membership) | Unknown / assets | Retained tokens | Analysis s |
|---|---:|---:|---:|---:|---:|
| background_worksheet | 3 / 1 / 407 | 11 (94) | 288 / 453 | 453 | 5.15 |
| colored_box | 1 / 2 / 331 | 13 (26) | 264 / 364 | 420 | 1.49 |
| column_100 | 0 / 0 / 89 | 12 (8) | 32 / 105 | 779 | 0.35 |
| column_26 | 1 / 0 / 439 | 11 (146) | 256 / 460 | 564 | 2.64 |
| complex_cards | 4 / 0 / 310 | 13 (5) | 263 / 337 | 676 | 1.19 |
| complex_map | 1 / 0 / 1,668 | 25 (8) | 1,396 / 1,887 | 619 | 5.06 |
| complex_sidebar | 1 / 1 / 300 | 10 (4) | 263 / 327 | 401 | 4.00 |
| science_dissolving | 0 / 811 / 225 | 47 (249) | 881 / 1,904 | 410 | 2.54 |
| science_fission | 0 / 853 / 206 | 50 (150) | 1,066 / 2,158 | 364 | 2.35 |

The dense map preserves **100,496 drawing/clip path items**, indexes drawing groups instead of those individual items, and checks 20,543 spatial candidates. Science labels remain in the text ledger. Seven Spanish fixtures use frozen old-cache Counters; science totals match Phase 0 extraction evidence and their ledger checks conserve the rawdict tokens. The two earlier regressions retain 713 and 768 tokens.

## Provisional visual gold

Nine files in [tests/gold](../backend/tests/gold) were written after viewing rendered overlays. They are **assistant visual annotations awaiting human review**, selected main objects rather than exhaustive independent production truth. Uncertain annotations are explicit and excluded from the per-fixture sample denominator. [Object-level results](../experiments/out/step3/role_evaluation.json).

| Fixture | Expected main roles | Found roles and confidence | Matched / certain samples; uncertain |
|---|---|---|---:|
| background_worksheet | 2 backgrounds, photo | background .93; content_image .80 | 3/3; 1 |
| colored_box | 2 containers, photo, banner background | container .82; content_image .83; banner unknown .60 | 3/4; 1 |
| column_100 | container, 3 chart bars as figure_part | container .88; bars unknown .35 | 1/4; 1 |
| column_26 | quote container, decorative strip, banner background | container .88; decorative .82; banner unknown .60 | 2/3; 0 |
| complex_cards | 4 portraits, container | content_image .80; container .88 | 5/5; 1 |
| complex_map | map image, legend container | content_image .83; container .88 | 2/2; 1 |
| complex_sidebar | background, photo, container | background .93; content_image .80; container .88 | 3/3; 0 |
| science_dissolving | 3 molecular compounds as figure_part | figure_part .77 | 3/3; 1 |
| science_fission | 3 nuclear compounds as figure_part | figure_part .77-.80 | 3/3; 1 |

These are separate fixture review results; no overall accuracy score is claimed. Background/callout protection, scan-layer detection and member/text conservation are strict tests. Exact digest repetition is verified on a synthetic four-page document including rotated pages; single-page fixtures cannot establish original-book repetition. The CLI prepares repetition across its input document.

## Important limitations/review cases

- Chart bars and broad banners remain unknown. Dense clipped vector fragments, line grids and some colored visual panels require review. No table/figure grouping is inferred to fill these gaps.
- Substantially overpainted raster placements become unknown .55; crop texture measures the composited page, not isolated asset pixels. Clip/blend/opacity information unavailable from native APIs is explicitly marked unavailable.
- Native shading paint bounds can be unbounded: finite placement bounds come from get_image_info. Empty paints can offset drawing counters; geometry/type checks reconcile 148 worksheet and 53 sidebar drawings. Six remaining unassociated/empty paint commands are explicit unknown assets. Three dissolving-page traces without rawdict-span matches remain render evidence; they do not invent additional ledger tokens.
- Bounding-box overlap and rule confidences are diagnostic evidence, not calibrated probabilities. Conservative unknowns are intentional.

## Dependencies/install

All requested wheels installed/imported on **Python 3.14.8 / Windows x64** without workarounds. Full pins and notices are in [dependencies](dependencies.md) and [CPU lock](../backend/requirements-lock.txt).

| Added package | Pin | License |
|---|---|---|
| Shapely | 2.2.0 | BSD-3-Clause; GEOS LGPL-2.1 |
| NetworkX | 3.7 | BSD-3-Clause |
| NumPy | 2.5.3 | BSD/0BSD/MIT/Zlib/CC0; bundled **GCC GPL-3.0 with runtime exception** |
| OpenCV headless | 5.0.0.93 | Apache-2.0; wrapper MIT; bundled FFmpeg LGPL-2.1 |
| torch, optional gpu extra | 2.14.1 | BSD-3-Clause source; CP314 Windows wheel dry-run succeeds; not installed |

PyMuPDF remains AGPL/commercial under the accepted internal-use decision. imagehash is unnecessary because native exact image digests are available. No weights or models were installed. Optional GPU binary/runtime licenses and real CUDA operation remain unverified until that distribution is selected. [Installed evidence](../experiments/out/step3/dependencies.json), [GPU wheel resolution](../experiments/out/step3/gpu_extra_resolution.json).

## Six overlays to review

1. [background_worksheet_overlay.png](../experiments/out/step3/background_worksheet_overlay.png)
2. [colored_box_overlay.png](../experiments/out/step3/colored_box_overlay.png)
3. [column_100_overlay.png](../experiments/out/step3/column_100_overlay.png)
4. [complex_map_overlay.png](../experiments/out/step3/complex_map_overlay.png)
5. [science_dissolving_overlay.png](../experiments/out/step3/science_dissolving_overlay.png)
6. [science_fission_overlay.png](../experiments/out/step3/science_fission_overlay.png)

Each path has a complete adjacent JSON sidecar; overlays for all nine fixtures are present.

## Decisions for review

1. Approve/correct the provisional gold roles, especially banners, chart primitives, hidden raster placements and colored panels inside illustrations.
2. Decide whether unknown visual objects should block later processing or continue with a mandatory review flag; decide when exact path/clip geometry becomes required beyond this bounding-box graph.
3. Select a GPU binary distribution only if needed; then validate its runtime/licenses and CUDA recovery on real hardware. The CPU-default gate is complete.

Step 3 stops here. Step 4 has not started.
