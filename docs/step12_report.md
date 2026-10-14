# Step 12 — figures, captions and credits

Status: **complete for review.** Every required gate passes on the real four-book runs. The
pipeline changes exactly one page (book 1 p724, where the Step 11e regression is reversed);
everything else Step 12 adds is a new `figures` stage whose records, links, flags and images
are published in the final archive. Step 13 has not started.

## Scope and baseline

HEAD at start: `9b249fc` (clean apart from the untracked `.vscode/` and one 11d output file,
both left untouched). The frozen baseline is the Step 11d continuation combined capture,
copied to [step12/before](../experiments/out/step12/before/). Only books 1–4 were run; the
sealed ENT hold-out, the mideast robustness book, the mismatched pair and unregistered files
were not. Gold, reference XML, the ledger and old projects were not edited. Disk before the
final run: 31.2 GB free; the 1,412 × 12 MiB estimate leaves more than 10 GB; images add
435 MB (estimate before export: 600 figures × 4 MB = 2.4 GB).

Measured runs: the final evidence set is [step12/final](../experiments/out/step12/final/).
Two earlier attempts were stopped and archived, not used: the first before any measurement
(its producer record is kept), the second after a visual audit showed the photo/drawing
statistic misread black-and-white photographs
([aborted](../experiments/out/step12/aborted/)). A third, completed run from before the review of caption/credit rules and model evidence is kept in [step12/run](../experiments/out/step12/run/) for reference; it is not the evidence set.

## Part 0 decisions

Recorded in [decisions.md](decisions.md) (Step 12 Part 0): naming pattern
`page_{label}_{n}` (configurable, file-safe, unique, inferred/unlabelled flagged), JPG/PNG
from measured evidence only, alt-text slot option B with an optional SmolVLM-256M generator
(Apache-2.0, CPython 3.14.8 smoke test passed, **off by default**), no new dependency.
Figure records live in the new `figures` stage rather than `model/` (editing `model/` would
re-key native extraction for every page). Dependencies note:
[dependencies.md](dependencies.md).

## Task 1 — measurement before any change

Reference inventory ([step12_reference.py](../experiments/step12_reference.py)) and our
outputs at HEAD ([measure/before](../experiments/out/step12/measure/before/)).

| Book | Reference figures / page images | Captions (reference) | Credits (reference) | Our figures | Figure detection P / R (page counts) |
|---|---:|---:|---:|---:|---|
| 1 Spanish US history | 441 groups / 534 images | 435 | 468 | 507 | 0.921 / 0.875 |
| 2 Immigrant children | 3 | 0 | 0 | 1 | 0 / 0 (page-marker offset, see below) |
| 3 Art-therapy index | 0 (2 metadata file references) | 0 | 0 | 0 | — |
| 4 Medical anatomy | 280 (216 titled) | 24 + 216 titles | 0 | 330 | 0.515 / 0.607 |

Current figure placement (float anchors by kind, figure): book 1 0.768, book 4 0.487 (all
floats: 0.900 / 0.375 / 0.606). Figure-internal text in paragraph-like units: book 1 1,954 of
8,677 reference image-description tokens (22.5%), mostly infographic text in sidebars with
no figure region; lines inside figure boxes not embedded by the layout are mostly real
paragraphs (book 4: 80 of 82 units). Top failure classes before: book 1 captions read as
callout paragraphs (164, caption boxes), credits in separate credit streams (377, mostly
>16 font sizes from any figure), unknown rotated text in the main flow beside a figure (2, the
p724 case); book 4 page-count mismatches (108 over, 50 under pages). Examples:
[diagnosis](../experiments/out/step12/diagnosis/).

## What changed

### Reading order (one rule, fixes p724 generally)

Rotated `unknown` text within the existing credit reach (4 font sizes) of a figure is read
with that figure's float stream; its region stays `unknown` and the decision is
`needs_review`. Pages 324/350/361 (credits 11–67 font sizes away) are unchanged. This is the
only change upstream of the new stage.

### The figures stage (`book_core.figures`)

- **Regions (Task 2):** one figure per layout figure region; the layout already groups
  rasters, vector artwork and panels into composites and keeps distinct blocks apart.
  **Spreads** are detected only from evidence: facing content edges, vertical alignment and
  pixel continuity across the gutter (book 1: one spread, pp. 664–665, verified visually).
- **Captions (Task 3)**, each rule measured for precision and inspected by hand (below):
  caption box (callout) within the figure's span; reading-order attachment only with the
  book's own caption numbering (label learned from the book's linked captions, never a word
  list); numbered caption (label must open the text). Everything else stays text, listed as
  an unlinked caption with a reason, for review.
- **Credits (Task 3):** credit lines are page-level records with the figure(s) their rule
  proposes, explicit confidence, always `review_required` — never linked to a figure (see
  the credit decision below).
- **Figure text (Task 4):** units of the figure's embedded lines are linked as
  `internal_text` with their rule; no unit or token moves or disappears.
- **Export (Task 5):** crop at 300 dpi through the Extractor render; JPG for photographs,
  PNG for drawings; mixed evidence → PNG with a flag. Grey-tone statistics (8-bit levels) sit
  next to quantized colour statistics, so black-and-white photographs are not read as
  drawings (the reason for the second-attempt stop).
- **Model (Task 6):** `FigureRecord`: id, name, page label (+ source and inferred flag), bbox,
  content-area share, kind, image (file, format, dpi, size, sha256), measured evidence,
  caption / credit / internal-text links (unit ids, line ids, rule, confidence), anchor
  (stream, after-line, position, reading index), alt-text slot `{text, status, source}`,
  model support, spread partner, provenance and review flags. No tag names.
- **Layout-model evidence:** `model_evidence` defaults to `auto` — on whenever the models
  extra is installed, a clear warning (in the log and the run statistics) when it is not,
  an error if forced `on` without it. A figure that not both models find gets
  "model disagrees" (must-check); nothing is ever dropped.
- **Small artwork:** `small_figure_share` (client profile, default 2% of the content area)
  marks icons/logos as information for the adapter; never a drop.

## Task 7 — results

### Pipeline effect: only book 1 p724 changes

| Book | Changed pages | Changed metric fields (excluding keys/seconds) |
|---|---|---|
| 1 | p724 (reading order, furniture, paragraphs, lists, structure) | 40, all improvements |
| 2, 3, 4 | none | none |

Book 1, Step 11 per page: paragraph boundary F1 0.942767 → 0.942797, exact units 13,601 →
13,602, units split 792 → 791; main flow 0.954479 → 0.954485, Kendall τ 0.908958 → 0.908971,
within floats 0.921729 → 0.921773 (the exact pre-11e value). Headings, lists, zones, page
labels and float anchors are identical in every book. Quote 832 is one paragraph again.
[Comparison](../experiments/out/step12/final/comparison.json),
[p724 field details](../experiments/out/step12/final/page_changes_spanish_us_history.json).

### Figures per book (final run)

| | Book 1 | Book 2 | Book 3 | Book 4 |
|---|---:|---:|---:|---:|
| Figures / image files | 507 / 506 | 1 / 1 | 0 | 330 / 330 |
| Photos (JPG) / drawings (PNG) | 247 / 260 | 0 / 1 | — | 49 / 281 |
| Mixed evidence → PNG (flag) | 34 | 0 | — | 24 |
| Spreads | 1 | 0 | 0 | 0 |
| Image bytes | 316 MB | 0.18 MB | 0 | 118 MB |
| Figures stage time / peak memory | 50 min / 11.9 GB | 0.1 min | 0 | 6.8 min / 1.3 GB |
| Detection P / R by PDF page | 0.921 / 0.875 | 0 / 0 | — | 0.515 / 0.607 |
| Detection P / R by printed label (reference image names) | 0.693 / 0.791 | 1 / 0.333 | — | **0.785 / 0.928** |
| Captions linked / reference captions linked | 151 / 0.320 | — | — | 150 / 0.591 |
| Linked figure's name = reference image name (label + index) | 0.849 | 1 of 1 | — | 0.883 |
| Credits: page-level records / reference credits covered | 328 / 0.896 | — | — | — |
| Page credits with exactly one proposed figure | 310 (285 of the covered) | — | — | — |
| Figure anchors (unchanged reading order) | 0.768 | — | — | 0.487 |

By-page counts depend on the reference's page markers; by-label scoring compares our names
with the reference's own image names (`p{label}_{n}`, `pg{label}_{n}`, `page{label}-{n}`) and
is the better detection measure for books 2 and 4. Book 2's single figure is `page_32_1`; the
reference names it `pg32_1.jpg` (its marker sits one page later). Figure-internal text: book
1 4,753 of 8,677 reference image-description tokens are owned by internal-text links (54.8%).
[Evaluation](../experiments/out/step12/evaluation/final/).

### Link rules: precision and manual review

Twenty seeded random links per rule per book were judged on contact sheets (figure blue,
unit green): [links_review.json](../experiments/out/step12/links_review.json),
[sheets](../experiments/out/step12/links_v3/sheets/). Precision "with title evidence" also
counts a link correct when its text is a reference figure title/caption.

| Book | Rule | Links | Precision (reference) | Manual sample (correct / wrong / unclear) | Decision |
|---|---|---:|---:|---|---|
| 1 | reading-order caption attachment | 417 | 0.28 | 3 / 17 / 0 | disabled (no caption numbering) |
| 1 | caption box within the figure's span | 151 | 0.927 | 20 / 0 / 0 | kept |
| 1 | credit within reach of a figure | 76 | 0.947 | 7 / 5 / 8 | page-level records only |
| 1 | credit on a page with one figure | 232 | 1.0 | 13 / 1 / 6 | page-level records only |
| 1 | page credit to every figure | 43 | 1.0 | 4 / 5 / 11 | page-level records only |
| 4 | reading-order caption with the book's label | 139 | 0.70 (0.978 with title evidence) | 20 / 0 / 0 | kept |
| 4 | numbered caption | 11 | 0.33 (1.0 with title evidence) | 11 / 1 / 0 (the 1 fixed: label must open the text) | kept |
| 4 | caption box (before the within-span fix) | 3 | 0.0 | 0 / 3 / 0 | none remain |

**Credit decision.** Credit lines mix picture credits with citations for quoted text
("PHOTO: …; TEXT: …"); telling them apart needs vocabulary, which is not allowed, and the
manual review falls below 0.9. So no credit is linked to a figure. This matches the
reference: in book 1, 467 of 468 credits are their own paragraph at section/page level (151
next to an image group, never inside it), one sits in a caption. Books 2–4 have no credit
markup.

**p724.** The two rotated lines read with the figure (keeping quote 832 whole) are page
credits: one is a photo credit, the other a citation of the quote. The page's figure region
covers most of the page (portraits, ornaments and quote marks grouped); "01" is now an
unlinked caption and the region carries "page-scale figure region" (must-check).

### Layout models as evidence

Heron and PP-DocLayoutV3 ran on every page of books 1–4 (CPU, cached, 72 dpi, threshold 0.5;
evidence only). [Model evidence](../experiments/out/step12/model_evidence/).

| Use | Book 1 | Book 4 | Decision |
|---|---|---|---|
| Reject caption candidates the model calls header/text/table/heading | no gain over the final rules | no change | not used |
| Rescue captions the model calls captions (Heron) | +49 links at ≈0.92 | +49 at ≈0.67 | not general: not used |
| Flag figures not both models find ("model disagrees") | 56 flagged; precision flagged 0.48 vs unflagged 0.976 (page) | 67 flagged; 0.13 vs 0.951 (label) | **on, flag only** |
| Flag only when neither model finds it | 3 flagged | 31 flagged | weaker; not chosen |
| Add model-only figures (both models, none of ours) | 100, precision 0.31 | 18, precision 0.22 / 0.0 (label) | not added (limitation) |

Book 2: 5 model-only figures (precision 0.2 by label), no flags. Detection time (full books,
information): book 1 50.0 + 55.3 min, book 2 14.6 + 18.5, book 3 0.6 + 0.6, book 4 12.1 + 20.9
(Heron + PP). In production the models run only on pages with our figures: estimated
≈59 min (book 1, 425 pages), ≈22 min (book 4, 207 pages), <1 min (book 2).

**False figures in book 1 and the flag.** Every figure on a page where we exceed the reference
(67 suspects) was classified by eye
([classes](../experiments/out/step12/final/false_figures/spanish_us_history_classes.json)):

| Class | Figures | Flagged |
|---|---:|---:|
| Contents boxes on unit-opener pages (incl. p257, p723) | 24 | 24 |
| Cover art p1 (reference has no figure there) | 2 | 2 |
| Decorative title lettering (p38, p60) | 2 | 2 |
| Header banner (p24) | 1 | 1 |
| Strip / legend inset beside a map (p656, p659) | 2 | 0 |
| Graphic-organizer pieces (p329, p335) | 4 | 0 |
| Multi-panel art the reference keeps as one image | 15 | 0 |
| True figures (13 opener photos, 2 on p24, 2 maps) | 17 | 3 |

The empty organizer table on p447 (`page_423_1`) is not flagged: both models report a region
there.

### Review flags by severity

[review_flags.json](../experiments/out/step12/final/review_flags.json). Alt-text slots are
counted separately: every figure has an empty slot, `needs_review` (507 / 1 / 0 / 330).

| Flag | Severity | Book 1 | Book 4 |
|---|---|---:|---:|
| model disagrees | must-check | 56 | 67 |
| page-scale figure region | must-check | 21 | 5 |
| page credit proposing several figures | must-check | 18 | 0 |
| unit mixes figure roles | must-check | 1 | 0 |
| unlinked caption | quick-confirm | 611 | 241 |
| page credit with one proposed figure | quick-confirm | 310 | 0 |
| inferred page label | quick-confirm | 26 | 39 |
| no page label (named by PDF page) | quick-confirm | 3 | 0 |
| mixed evidence → PNG | info-only | 34 | 24 |
| small artwork | info-only | 37 | 14 |
| **must-check per 100 pages** | | **12.7** | **22.9** |

Book 2: no flags (one figure, alt-text slot only); book 3: none.

### Overlays

[Index](../experiments/out/step12/overlays/overlays.json) (figure blue with its name, captions
green, page credits orange dashed, internal text purple, unlinked captions red):
[composite / timeline, book 1 p30](../experiments/out/step12/overlays/figures_spanish_us_history_p30.png),
[map with labels, p125](../experiments/out/step12/overlays/figures_spanish_us_history_p125.png),
[captioned photo, p123](../experiments/out/step12/overlays/figures_spanish_us_history_p123.png),
[rotated credit, p724](../experiments/out/step12/overlays/figures_spanish_us_history_p724.png),
[book 2 figure, p43](../experiments/out/step12/overlays/figures_immigrant_children_p43.png),
[book 4 anatomy diagram, p264](../experiments/out/step12/overlays/figures_medical_anatomy_p264.png).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: 946 passed, 0 failed | `final/pytest.xml` |
| Six-pages-per-book sample | PASS: 0 missing / 0 extra on 24 pages | [source crosscheck](../experiments/out/step12/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step12/final/full_book.json) |
| Full-book I1–I7 on 1,412 real pages | PASS: all zero | `final/after/*_full_gates.json` |
| Every line in exactly one unit, ordered once | PASS: 119,854 lines | same |
| Books 1–2 not worse | PASS: book 1 improves on p724 only; book 2 identical | comparison |
| Final archives | PASS: every file checksum, digest, line/span reference, link and image resolves | [final_outputs.json](../experiments/out/step12/final/final_outputs.json) |
| 1 vs 2 workers equal (with images and model evidence) | PASS | `test_workers_and_production_give_identical_figures`, `test_workers_equal_with_model_evidence` |
| Source hashed once per run | PASS: 1 in every book | performance records |
| Cache closure (figures in final, missing dependency detected) | PASS | figure tests |
| Ruff from `backend/` | PASS (src, tests, all step12 scripts) | — |
| ENT and mideast not run | PASS | — |

Tests: **946 passed, 0 failed** (902 before Step 12 + 44 figure tests; 513 s), run after the final runs so the furniture-book tests read current caches.

## Limitations

1. **Book 1 caption coverage ≈32%.** With the reading-order caption rule disabled (book 1
   has no caption numbering; precision 0.28), 151 captions are linked (caption boxes) and
   611 caption candidates stay text as unlinked captions for review; 0.320 of reference
   captions are linked.
2. **Figure-internal text not removed from paragraph units.** The stage records embedded
   figure text as internal-text links (3,548 units in book 1), but text the layout did not
   embed (sidebar infographics, timelines: 1,954 reference description tokens in book 1) stays
   in paragraph units; paragraph metrics change only on p724. A geometric "inside the box"
   rule was measured and rejected (book 4: 80 of 82 such units are real paragraphs). Carry to
   Step 17.
3. **Book 4 figure placement not improved:** figure anchors 0.487 (reading order unchanged).
4. **Book 2 rotated thin-line diagrams missed:** `pg129_1` (PDF p140, Figure 7.1) and
   `pg175_1` (p186, Figure 9.1) are landscape diagrams of unfilled strokes whose rotated labels
   form a rotated text scope; no figure region forms. Both models find p186, neither p140.
   Neither page is scanned (no missed figure in books 1, 2 or 4 is on a scanned page).
5. **False figures not flagged:** the p447 empty organizer table, graphic-organizer pieces
   (4), map strips/insets (2) and 15 multi-panel granularity cases (models support them).
   Model-only figures are not added (precision 0.31 / 0.22).
6. **Derived-gold caption misalignment:** 84 book 4 caption links whose text is a reference
   figure title are tagged non-caption by the derived gold (the tokens are aligned to nearby
   `para` units). For a later gold review; gold was not edited.
7. Other: the figures stage reads the object analysis per figure page (book 1 peak 11.9 GB);
   book 4 over-detection by printed label is 55 labels (10 on the advert page), merged
   panels under-detect 10 labels; the photo/drawing thresholds were calibrated on books 1 and
   4 by visual audit with no hold-out.

## Decisions for the owner

1. Accept credits as page-level records (never figure links) — consistent with the reference.
2. Accept "model disagrees" (not both models) as the default must-check flag, with the models
   extra in the production install.
3. Book 1 captions: keep the reading-order caption rule disabled for unnumbered books, or fund
   a supervised caption classifier (Heron rescue reached 0.92 in book 1 but 0.67 in book 4).
4. Schedule limitation 2 (non-embedded figure text) for Step 17 and the derived-gold caption
   review (limitation 6).

**Step 13 has not started.**
