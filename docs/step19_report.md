# Step 19 — fix what the hold-out benchmark found (general fixes only)

Status: **complete for review.** One commit; Stage 2 not started.

## Summary

**What was broken.** The Step 18 hold-out books showed:
- a crash on the math book;
- extra list-number tokens on ENT;
- I7 layout violations;
- weak headings, footnotes and review flags;
- anatomy labels typed as math;
- reversed text inside table cells.

Several small Step 17b leftovers were also open, and the Spanish book needed 15 GB of memory.

**What changed.** Every fix is general: no page, coordinate, font, book or word rules.
- Region identities are unique. A failing page writes a clear failure record.
- List numbers stay bound to their own glyphs.
- Edge strips and number columns no longer break I7.
- Running heads, footnote markers, folios and heading review flags are handled better.
- Math needs real evidence. A letter drawn slanted by the PDF counts as slanted.
- Table cells read their lines in their own order. A separate in-cell order score was added to the evaluator.
- Separators are not underlines, and OCR settings cannot change native pages.
- Review items are de-duplicated.
- Memory use on huge vector pages is lower.
- Cache paths are short and portable, and a stopped run leaves a stop record.

**Before → after on the development books** (frozen code `final3`, digest `86174f9e…`; books other than Spanish have byte-identical layout to `final2` and reuse its results):

| Book | What moved | Before | After |
|---|---|---|---|
| Book 4, medical anatomy | Paragraphs exactly right | 0.766 | **0.782** |
| | List items exactly right | 0.744 | **0.775** |
| | Headings F1 | 0.658 | **0.726** |
| | Heading levels exactly right | 0.847 | **0.874** |
| | Main text order | 0.962 | **0.965** |
| | Figure/table anchors | 0.578 | **0.613** |
| | Text order inside table cells | 0.964 | **0.978** |
| | Table structure (TEDS) | 0.911 | 0.911 |
| Book 2, immigrant children | Paragraph boundary F1 | 0.855 | 0.856 |
| | Heading review flags: recall / precision | 0.30 / 0.56 | **0.34 / 0.59** |
| | Order, tables, headings | — | unchanged |
| Statistics | I7 (page 870) | 1 | **0** |
| | Review items | 2,906 | **2,735** |
| | MathML strict / symbol (gold) | 87.35% / 98.61% | 87.35% / 98.61% |
| Art therapy | everything | — | unchanged |
| Spanish | Paragraphs exactly right | 0.896 | 0.897 |
| | Glossary definitions: term / description | 0.849 / 0.835 | 0.849 / 0.835 |
| | Headings F1 | 0.792 | 0.791 |
| | Main text order / Kendall tau | 0.979 / 0.957 | 0.979 / 0.957 |
| | Text order inside table cells | 0.944 | **0.945** |
| | Table detection precision | 0.902 | 0.902 |

On every development book these hold:
- **Lossless:** 0 missing / 0 extra tokens.
- **Layout invariants:** I1–I7 = 0, Spanish included.
- **Ownership:** every line is owned once.
- **Review list:** no duplicate review items.

**Seeded hand checks on the final output.** I judged each item against the printed page.

| Check | Book 4 | Book 2 | Statistics |
|---|---|---|---|
| Headings right | 29/40 | 39/40 | 38/40 |
| Page links right | 31/32 (all links) | 40/40 | 38/40 |
| Underline spans right | 20/20 | — | 20/20 |
| Inline math right | — | — | 31/40 |

**Still broken** (the Step 20 list in `decisions.md`):
- Narrow two-column gutters: lines join across the columns. This is the main cause of the book 4 link and heading problems.
- The table of contents is used as the whole outline, so deeper titles become display titles.
- Reading order inside column groups, and float anchors.
- Bold bullet lead-ins typed as headings, and two-line headings split in two.
- Inline math sometimes starts or stops inside the expression, and "math" is found in URLs.
- Problems from the owner's test books: a rear zone set by abstract labels, citations typed as footnotes, in-cell line order, titles inside chapter-opener images, and empty TOC entries.

**Hold-out books** (burned; not unseen scores):

| Book | Result |
|---|---|
| Math book (post-fix, more exposed) | **Stopped in the MathML stage; no MathML score.** On `final3` every stage up to MathML completed on all 1,220 pages (the `final2` run crashed in layout at page 987, fixed). Reading 41,056 equation images on CPU needed about 240 h, so the owner stopped it after 8 h. Layout-only check on the whole book: 0 failures, I6 = 12, I7 = 4. |
| ENT, confirmation run (`final2`) | Completed. Missing / extra **0 / 0** (Step 18: 0 / 10). I1–I7 all 0 (Step 18: I7 = 42). Every line owned once. Review items 1,785 (Step 18: 1,918). |
| Mideast, confirmation run (`final2`) | Completed. 0 / 0, I1–I7 all 0, as in Step 18. Review items 871 (Step 18: 698): 180 are the new "heading-like, not a heading" flag. Heading census on Step 18's 20 pages: running heads typed as headings 20 → 1; standalone headings found 1 of 17, as before, but 15 of the other 16 are now flagged. |

ENT and Mideast ran on `final2`. The `final3` changes (locator labels, touching gutters)
did not run on them, by owner decision; no code changed after their results. The append-only
log is [holdout_runs.jsonl](../experiments/holdout_runs.jsonl).

## Part status

| Part | Status | Final number |
|---|---|---|
| 0 Start clean | Done | Tree clean. HEAD is 4 non-step commits after Step 18. 175 GB free. |
| 1 Math crash | Done | Synthetic page-348 collision fails before and passes after. Every region identity change on books 2 and 4 comes from changed content (10 and 190). |
| 2 Extra list-marker tokens | Done | 0 / 0 on all five development books. ENT is checked in its confirmation run. |
| 3 I7 | Done | I7 = 0 on all five development books. Statistics page 870 went from 1 to 0. The `final2` Spanish glossary regression (I7 = 5, definitions damaged) is fixed in `final3`: page labels such as "HT19" count as locators. |
| 4 Reading order / joins | Partly (owner decision) | No new order rule. Order moved only through the line fixes (book 4 main 0.962 → 0.965, anchors 0.578 → 0.613). Page-link precision by hand: 31/32, 40/40, 38/40. |
| 5 Headings / footnotes / folios / flags | Partly | Running heads, footnote split, folios as furniture and flags are done. Book 4 flag recall 0.16 → 0.24, precision 0.55. The joint hierarchy redesign is deferred. |
| 6 False math / cell order | Done | Labels need evidence. Slanted (sheared) variables count as math. In-cell order 0.964 → 0.978 (book 4). Statistics math not lower. |
| 6b.1 Separators | Done | Book 4 separator pages are no longer underlined. Underline 20/20 and 20/20. |
| 6b.2 Native language labels | Done | OCR settings never reach native stages. Book 2 native pages are identical. Step 16 archive not on this machine (see Skips). |
| 6b.3 Statistics figure-text fragments | Kept flagged | 204 stay flagged and nothing is dropped. Their owner needs a reading-order change (deferred). |
| 6b.4 Review dedupe | Done | 0 duplicates on every book. |
| 6b.5 Memory | Done | Spanish heavy page 10.18 → 4.29 GB. Full Spanish run peak 15 GB → 6.90 GB on `final3` (other jobs running). |
| 7 Paths / sleep / math rerun | Done; math stopped | Longest output path 103 characters, longest cache path 121. A stop record is written. The math rerun passed page 348 and every stage to MathML, then was stopped for time (see Hold-out books). |

## The line-split change, measured separately

Step 19 splits two fragments on one baseline in two cases:
- the font size changes by ×1.2 or more across a gap of 0.75 of the larger size, with letters or digits on both sides;
- a list marker follows a gap of one font size.

It changes lines on 59 book 4 pages and 17 Spanish pages. It changes none on books 2, 3 or Statistics.

Book 4 was run twice on the frozen code: as frozen, and with only these two split rules
removed. All other Step 19 changes are in both runs.

| Book 4 | Before Step 19 | Step 19, split reverted | Step 19 (frozen) |
|---|---|---|---|
| Paragraphs exactly right | 0.766 | 0.766 | **0.782** |
| Paragraph boundary F1 | 0.901 | 0.901 | **0.906** |
| List items exactly right | 0.744 | 0.744 | **0.775** |
| List boundary F1 | 0.517 | 0.517 | **0.538** |
| Main text order | 0.962 | 0.962 | **0.965** |
| Figure/table anchors | 0.578 | 0.578 | **0.613** |
| Kendall tau | 0.924 | 0.924 | **0.931** |
| Headings F1 | 0.658 | 0.658 | **0.726** |
| Heading levels exactly right | 0.847 | 0.847 | **0.874** |
| Heading flag recall / precision | 0.16 / — | 0.20 / 0.52 | **0.24 / 0.55** |
| In-cell order / TEDS | 0.964 / 0.911 | 0.978 / 0.911 | 0.978 / 0.911 |
| Lossless, I1–I7, owned once | 0/0, 0, yes | 0/0, 0, yes | 0/0, 0, yes |

So on book 4 the split change accounts for **all** of the paragraph, list, order and heading
gains. The other Step 19 changes leave those scores exactly where they were. They improve
in-cell order and part of the flag recall. The split makes no book 4 measure worse, so it is
kept.

Spanish, the same comparison on `final2` (before the glossary fix, which the split does not
touch): the split changes 30 pages' output, and the scores barely move (paragraphs exactly
right 0.879 reverted → 0.880 with the split; headings F1 0.773 both; definitions and tables
the same).

## Known limits

- **Formula reading is far too slow for a math textbook** (math hold-out). The image reader
  managed about 170 equations an hour on CPU. The run used about 2 of 8 cores: the run
  script set `OMP_NUM_THREADS=2`, and the OCR engine calls `torch.set_num_threads(1)` in the
  same process. So the math book's MathML is unscored. Step 20 item 14.
- **The math run's cache is kept for a MathML-only rerun (owner decision).** `.cache/s19/math_holdout/`
  (694 MB) holds every stage up to MathML for all 1,220 pages, plus the 542 formula
  readings already done, under the `final3` freeze. It is not deleted. The MathML stage will
  be rerun later on the GPU machine. Layout keys include the resolved device, so that rerun
  must run the page stages with `device: cpu` (or accept recomputing them) to hit this cache.
- **Math hold-out layout flags** (layout-only check, not fixed: hold-out): I6 on 12 pages,
  I7 on 4 pages. No page fails.
- **Narrow columns.** A gap of up to 1.25 × the font size joins fragments on one baseline. So on pages with 6 or more columns, or a gutter under about one font size, two columns read as one line. Lines under 4× the font size are also affected.
- **Found after the benchmark, on a new book, both older than Step 19.** On the IAP MEC book (not sealed; the Step 20 development book), the Step 18 freeze shows both:
  - left and right lines are joined across a narrow gutter, so paragraphs interleave on pages 27 and 210;
  - about 720 section titles are display titles. The table of contents is used as the outline below the depth it lists.

  These are Step 20 items 1 and 2.

## Events during the step

- **Spanish tables crash after the first freeze.**
  - **Crash:** the frozen code (digest `1092c54c…`) stopped Spanish in the tables stage after 8.6 h. A cell held one paragraph twice.
  - **Cause:** cells are now read row by row. A paragraph with another line between its lines was met twice. 22 cells on 17 pages were affected.
  - **Fix:** each unit is listed once, at its first line. Synthetic tests cover a loose line and a second paragraph between its lines.
  - **Cell check:** tables stage only, on all books. 1,203 + 2,707 + 2,197 cells are correct, and no previously correct cell changed order.
  - **Reruns:** a new freeze (`0ad2d184…`). Equations onward were rerun on every book, because the slant fix also changed equations. Spanish was rerun from a clean state, not from the crashed run.
- **Production fallback (owner decision).** A cell that fails the uniqueness check stops a development or test run. In production it is read in source order, and its table gets a `must_check` flag naming the cell. This is the only exception to "table flags are `needs_review`". Tests cover both modes.
- **Statistics slant fix.**
  - **What the check found:** the Statistics math check before the second freeze found 234 lost equations. Examples are H₀, Hₐ, Q₁, z₀.₀₅ and F₃,₁₆. A hand check of 30 found 29 were real math.
  - **Cause:** the book sets variables in an upright font, sheared by the text matrix. Font name and flags say "upright", so the Step 18 label rule treated them like anatomy labels.
  - **Fix:** slant is read per glyph from its drawn matrix (shared with assembly italic). An upright "C5" stays a label.
  - **Result:** all 234 return, and 4 boundary changes are restored. These were hypothesis lines that had lost their H₀/Hₐ prefix, on pages 729, 752 and 818 ×2. The only change from before Step 19 is L₁–L₄ on page 725, now labels.
  - **Unaffected:** books 2, 4, Spanish and art therapy have unchanged equations.

- **Spanish glossary regression, found by scoring Spanish (`final3` freeze).**
  - **What scoring showed:** the Part 3 locator-cell rule damaged the whole Spanish glossary (pages 653–680), not only the five I7 lines. Inside the glossary: paragraphs exactly right 0.969 → 0.548; definition terms / descriptions 0.998 / 0.985 → 0.653 / 0.526; six false tables. Outside it nothing moved.
  - **Not the line split:** the split-reverted Spanish run scored the same as `final2`.
  - **Fix (owner decision, Step 19):** a short page label, up to four letters joined to digits ("HT19", "A-12"), is a locator. A word beside a number ("variable 7", "anatomy 12a") still is not. Unit tests cover both.
- **Math hold-out crash on `final2`.**
  - **Crash:** layout stage, page 987, after 986 pages: "Lane requires x0 < x1, got 441.50 and 441.50". Two gutters that only touch opened a lane of zero width. The bug predates Step 19. The Step 18 crash at page 348 was a different check (duplicate region IDs, fixed in Part 1), and that run never reached page 987.
  - **Fix:** gutters that touch merge like overlapping ones, into one cut. A synthetic band with touching gutters reproduces the exact error on `final2` and passes on `final3`.
- **Whole-book layout check before the rerun (owner request).** Layout alone on all 1,220 math pages with the fixed code, in a scratch cache: 0 failures in 810 s. I6 = 12 and I7 = 4 are left as found (hold-out).
- **`final3` freeze and layout reuse (owner decision).**
  - **What changed:** `final3` (digest `86174f9e…`) differs from `final2` only in `layout/bands.py` and `layout/evidence.py` (plus tests). Of 27 producer digests only `layout` changed.
  - **Reuse rule:** each development book's `final3` layout was compared page by page with its `final2` layout. Art therapy 9/9, book 2 331/331, book 4 314/314 and Statistics 871/871 are byte-identical, with I1–I7 = 0. Their `final2` results are reused, with a hash proof in `final3/reuse/`.
  - **Rerun:** Spanish's layout changed, so it was fully rerun on `final3`.
- **Math hold-out stopped in the MathML stage (owner decision).** The `final3` math run completed every earlier stage on all 1,220 pages. From 13:39 it read equation images at about 170 an hour: 542 of 41,056 in about 3 h. It was stopped at 16:35 after 8 h 01 min and logged as stopped, with no MathML score.
- **Test-suite collision.** A side pytest, run while the full suite ran, removed the shared `.cache/pytest` and failed one resume test. Rerun alone, the suite passed.

## Memory

| Run | Peak |
|---|---|
| Spanish heaviest page (2.1 M paths), load | 10.18 → 4.29 GB |
| Spanish full run, before Step 19 | 15 GB |
| Spanish full run, Step 19 (first freeze, two other runs alongside) | 6.95 GB |
| Spanish full run, `final2` (alongside the hold-out runs) | 7.00 GB |
| Spanish full run, `final3` (alongside the math run) | 6.90 GB |
| Math hold-out, `final3`, to the MathML stop | 4.27 GB; machine minimum free 2.5 GB |

Concurrency: the Step 19 runs shared the 18 GB machine with up to two other conversions. The machine-wide free-memory minimum (3.6 GB) and per-run peaks are not clean single-run numbers.

## Skips

- **Step 16 byte comparison for book 2's native language labels.** The Step 16 archive is only on the old Windows cache. Native pages are identical before and after the Step 19 fix, and the language share is the same.
- **Hold-out reference scoring (M04–M16) for ENT and Mideast.** Owner agreed. Step 18 scored them with Windows-bound orchestration tools that were not ported. Machine checks only.
- **Science PDF.** Sealed; not run or read.
- **Math hold-out MathML scoring.** The run was stopped in the MathML stage for time (owner decision), so there is no MathML output to score. The scorer `tools/math_holdout_score.py` is ready, and the run's cache is kept for a MathML-only rerun on the GPU machine.
- **Joint heading-hierarchy redesign and column-group / float-anchor ordering.** Deferred by owner decision.

## Later steps

- **Docker.** The target platform is a Linux Docker image used through Docker Desktop on Windows. Building and testing it (Tesseract with all packs, pinned models, optional GPU, volumes, identical rerun from cache) is a later step. It replaces the former Windows check.
- **Step 20:** items 1–12 in `docs/decisions.md`.

## Gates

| Gate | Result |
|---|---|
| Full test suite | 1,275 passed, 0 failed, 2 warnings (PyTorch ONNX exporter deprecation, from `test_directml`). The 5 furniture-book tests need caches rebuilt for the new layout code (`step19_furniture_caches.py`, from `final3`): with `BOOK_CONVERTER_FURNITURE_CACHE` set, **all 5 pass**, so 0 skipped in total. (Spanish rebuild 8,229 s.) |
| Source sample pages, fresh extraction | **30/30 at 0 missing / 0 extra**: the frozen Step 11d sample of 24 plus 6 seeded Statistics pages ([source_sample_pages.json](../experiments/out/step19/final2/source_sample_pages.json)) |
| Book 1 ledger | 495,751 (full-book test in the suite) |
| I1–I7 = 0, every line owned once | all five development books: yes (Spanish fresh on `final3`; the others' layout is byte-identical to `final2`, and I1–I7 was recomputed on it) |
| Spanish lossless / ledger | 0 missing / 0 extra; 495,751 |
| Not worse beyond explained changes | see the summary table and the appendix |
| Development vs production | byte-identical (art therapy, 13/13 files) |
| 1 vs 2 workers | Pass. Art therapy 13/13 files identical; book 4 fresh with 2 workers 1,942/1,942 files identical (5,878 s; I1–I7 = 0; every line owned once) |
| Cache closure | tests pass |
| Ruff | lint clean (backend and the Step 19 tools). 11 files have format-only differences: 10 already exist at HEAD, and one is a list literal in the new `test_layout_edges.py` test. All are left untouched to keep the freeze. |

## Appendix

### A. Hand checks

Seeded samples drawn from the frozen publications: `step19_handcheck.py`, seed 19, plus the
inline-math sampler with the same seed. Each crop was judged against the rendered source
page. The judgments are by the agent and have not been independently verified. Item numbers
and reasons are in [judgments.json](../experiments/out/step19/final2/handcheck/judgments.json)
and [inline_math/judgments.json](../experiments/out/step19/final2/handcheck/statistics/inline_math/judgments.json).

| Book | Headings: right / errors / errors flagged | Links right (population) | Underline | Notes |
|---|---|---|---|---|
| Book 4 | 29 / 11 / 10 | 31/32 (32) | 20/20 | The errors are 7 false headings (6 bullet lead-ins, 1 quiz question) and 4 missed headings, all flagged. 4 correct headings are split at a line break. 13 correct links carry a line of the other column (narrow gutter). |
| Book 2 | 39 / 1 / 1 | 40/40 (161) | — (none in book) | 2 contents entries are rightly not headings but are flagged heading-like. |
| Statistics | 38 / 2 / 1 | 38/40 (107) | 20/20 | The unflagged error is a run-in label typed as a heading. The 2 wrong links: a bullet list joined to an answer list across a figure, and a sentence joined to a "Reminder" box line. |

Inline math, Statistics (40 of 5,118 inline marks):

| Result | Count |
|---|---|
| Right | 31 |
| Partly right (starts or stops inside the expression) | 4 |
| Wrong structure (binomial coefficient flattened, parentheses lost, χ² superscript lost; 2 flagged) | 3 |
| Not math ("t = 50" in a URL; "X = a" from "Let X = a score") | 2 |

The Statistics gold covers only drawn (vector) equations, so these text-set inline
expressions are outside it. "Inline-math gold" is in the evaluator backlog
(`gold_review_backlog.md`).

**Hand-check tool fix.** `step19_handcheck.py` names a sheet by item number ÷ 8. A page-link
item makes two crops, so every second link sheet overwrote the one before it, and half
the link items were never shown. The link sheets were regenerated with a copy that numbers
sheets by a counter: same seed, same items
([tools/handcheck_links_fixed.py](../experiments/out/step19/tools/handcheck_links_fixed.py)).
The frozen script is unchanged, to keep the freeze digest. Headings and underline (one crop
per item) are not affected. The script itself is fixed in the next step.

### B. Evidence

| What | Where |
|---|---|
| Run records, gates (I1–I7, ownership), hashes | `experiments/out/step19/<tag>/{performance,gates,hashes}/` |
| Before baseline (HEAD at start) | tag `before` |
| Frozen runs | tag `final2` (freeze `.cache/s19/final2_src`, `FROZEN_SOURCE.sha256` digest `0ad2d184…`) |
| Final freeze | tag `final3` (`.cache/s19/final3_src`, digest `86174f9e…`): Spanish run, `layout_compare/` (all five books), `reuse/` (hash proofs), `layout_check/math_holdout.json`, `compare/` |
| Hold-out runs | tags `holdout19` (ENT, Mideast on `final2`; `mideast_census.json`), `holdout19_final3` (math, stopped) |
| First freeze (superseded by the cell and slant fixes) | tag `final` (digest `1092c54c…`) |
| Split-reverted variant | tag `nosplit` (book 4 and Spanish) |
| Worker / mode parity | tags `final2_w2`, `final2_prod` |
| Scores and comparisons | `experiments/out/step19/<tag>/eval/`, `final2/compare/` |
| Sample-page gate | `final2/source_sample_pages.json`, `tools/sample_pages.py` |
| Hand checks | `final2/handcheck/` |
