# Step 20 — structure on real company books (columns, headings, zones, tables, TOC)

Status: **complete for review.** One commit; no frontend, ePub or profile-maker work.

## Summary

**What was broken.** On the owner's real books the converter failed in a few basic places:

- **Columns read as one line.** Two columns with a narrow gutter were joined into single lines
  (the gutter was narrower than a justified word space). Paragraphs, reading order, lists and
  table-cell order then mixed both columns: IAP had 43% of its body text interleaved, ART 40%.
- **The table of contents was the whole outline.** Every title below the depth the contents
  list was demoted to a "display title": ART found 8% of its headings, IAP had 732 display titles.
- **Titles drawn on artwork were picture text.** ART's part and chapter titles sit inside
  opener panels with letter-spaced "C H A P T E R" / "SEC TION", so the part level was missing
  and almost every heading level was one step off.
- **Over-eager guesses.** Abstract labels ("Background:", "Methods:") made Trichology pages
  77–272 a glossary in the rear matter; journal citations under a rule became footnotes.

**What changed.** Every fix is general (any book, any language): no page, coordinate, font,
book or word rules.

- Lines never join across a **gutter**, found as a white channel whose column edges line up
  on several rows (direction-aware, ink-checked, list markers and locators kept with their rows).
- The contents decide the outline **only to the depth they list**; deeper titles stay headings.
- **Opener titles on artwork** become headings (the artwork's sectioning label is the
  evidence); the hierarchy ranks sectioning words by the book's own nesting; the artwork is
  marked **decorative**.
- A **glossary** needs enough set-off terms in alphabetical order; a **footnote** needs its
  note mark (unmarked note text stays a side note).
- **Contents entries** carry their printed text, their entry unit and flags when unresolved.
- Name and signature lines in front matter are not headings; numbered caption lines inside
  figures become captions; web addresses and upright one-letter words are not math.
- OCR no longer leaves the whole process on one thread: formula reading 186 → 534 equations an
  hour on Statistics, identical readings.

**Before → after per book** (final run, second freeze `3b34bb30…`; "before" is the same code
as Step 19's `final3`). **ART is a development book with a reference, not an unseen score.**

| Book | What moved | Before | After |
|---|---|---|---|
| ART (Jaypee reference) | Headings F1 / levels exactly right | 0.14 / 0.07 | **0.94 / 0.99** |
| | Paragraphs exactly right / boundary F1 | 0.80 / 0.90 | **0.88 / 0.93** |
| | Main order / Kendall tau | 0.90 / 0.80 | **0.96 / 0.92** |
| | List items exactly right | 0.75 | **0.92** |
| | Text order inside table cells (exact) | 0.68 | **0.99** |
| | Float anchors | 0.79 | 0.73 (explained below) |
| | Images exported by the Jaypee profile (Jaypee delivered 13) | 41 (17 with the earlier adapter) | **15** |
| IAP MEC (no reference) | Body text interleaved across columns (target < 5%) | 43% | **0.6%** |
| | Body pages interleaved | 272 / 294 | **22 / 294** |
| | Display titles → headings | 732 / 124 | **0 / 860** |
| Trichology (no reference) | Zones (target: body 77–264) | rear from p77 | **body 30–264, rear 265–272** |
| | Footnotes (all false) | 55 | **0** |
| Book 4 | Headings F1 / levels exactly right | 0.73 / 0.87 | **0.76 / 0.89** |
| | Paragraphs exactly right | 0.78 | **0.86** |
| | Main order / list items exactly right | 0.97 / 0.78 | **0.99 / 0.89** |
| | In-cell order (exact) | 0.95 | **0.995** |
| Book 2 | Paragraphs exactly right | 0.878 | **0.889** |
| | Headings, order, tables | — | unchanged |
| Spanish | Main order / Kendall tau | 0.979 / 0.957 | **0.992 / 0.983** |
| | Paragraphs exactly right / in-cell order | 0.884 / 0.918 | **0.894 / 0.932** |
| | Headings, glossary definitions, tables, anchors | — | unchanged (anchors 0.854 → 0.856) |
| Statistics | MathML strict / symbol (gold) | 87.35% / 98.61% | 87.35% / 98.61% (identical) |
| Art therapy | everything | — | unchanged |

On every development book: **lossless** 0 missing / 0 extra; **I1–I7 = 0**; every line owned once.

**Seeded hand checks on the final output** (agent-judged against the printed page):

| Check | ART | IAP | Trichology |
|---|---|---|---|
| Headings right | 38/40 | 37/40 | 36/40 |
| Page links right | 18/18 (all links) | 39/40 | 40/40 |
| Table cells in order | 20/20 | — | — |

**Still broken** (first Step 21 items in `decisions.md`):

- Statistics: 754 of 871 pages in the front zone (back-matter "Chapter N" headings start the body).
- IAP: its first contents page is not detected; 41 of 69 contents entries are unlinked (flagged).
- Character clean-up deferred (in-line soft hyphens, broken bullet glyphs, letter-spaced words).
- Two-line headings split in two; bold "Term:" lead-ins; inline-math expression boundaries;
  float anchors (no new anchor rule); formula batching.

## Part status

| Part | Status | Final number |
|---|---|---|
| 0.1 Start clean | Done | Two untracked Step 19 run-record folders committed as Step 19 evidence (`6e46a6c9`). |
| 0.2 Merge `adapter-a` | Done | Merged (`59c64977`). Two merge issues fixed: the adapter tests' `conftest.py` hid the core one (made `tests_adapters` a package), and the core boundary test scanned the adapter package (now `book_core` only, plus "no `book_adapters` import"). |
| 0.3 Hand-check sheet numbering | Done | Sheets numbered by a counter (`step19_handcheck.py`, `step20_handcheck.py`). |
| 0.4 Baselines | Done | Books 1–4 and Statistics: the converter equals Step 19 `final3` file for file, so `final2`/`final3` scores are the baseline. ART, IAP, Trichology: `before` runs on the merge commit. |
| 1 Gutter-aware lines | Done | Joined-across lines: IAP 3,022 → 32, ART 758 → 14, book 4 637 → 40; Statistics, art therapy unchanged. |
| 2 Contents depth | Done | ART headings F1 0.14 → 0.87 from this rule alone; books 2, 4, Spanish unchanged. |
| 3 Opener titles on artwork | Done | ART levels exactly right 0.29 → 0.99 with the book-ranked hierarchy. |
| 4 Zones | Done | Trichology body 30–264 (target met); every other book's zones unchanged. |
| 5 In-cell order | Done (by fix 1) | ART 0.68 → 0.99; book 4 0.95 → 0.995; Spanish 0.92 → 0.93. |
| 6 Column order and anchors | Partly | Main order rose through the line fix only; no new anchor rule. |
| 7 Contents entries | Done | Entries carry text and entry unit (ART 18/18, book 4 115/133, Trichology 198/252); unresolved ones flagged. |
| 8 Citations not footnotes | Done | Trichology 55 → 0; unmarked note text is a `note_text` side note. |
| 9 Headings | Partly | Name and signature lines are labels (IAP 27, ART 5, book 4 4). Bold lead-ins and two-line headings open. |
| 10 Inline math | Partly | Addresses and upright one-letter words are not math (Statistics marks 5,280 → 5,243; gold unchanged). Expression boundaries open. |
| 11 Captions inside figures | Done | "Flowchart 2: …" lines become captions (labels learned from the book). |
| 12 Decorative figures | Done | ART: 21 of 41 figures decorative; the Jaypee profile exports 15 images (Jaypee 13). |
| 13 Character clean-up | Deferred (owner) | Conflicts with "text is never edited"; Step 21 records it as evidence. |
| 14 Formula speed | Partly | Thread leak fixed: 186 → 534 equations an hour, identical readings. Batching not done. |

## Gates

| Gate | Result |
|---|---|
| Full test suite (incl. adapter tests) | **1,352 passed, 0 failed, 0 skipped**, 2 warnings (PyTorch ONNX exporter deprecation, `test_directml`). The 5 furniture-book tests ran on caches rebuilt with the second freeze (`.cache/s20/furniture`; Spanish 2,245 s + the earlier 7,424 s, book 2 519 s). |
| Source sample pages, fresh extraction | **30/30 at 0 missing / 0 extra** (the Step 19 sample of 24 plus 6 Statistics pages) |
| Book 1 ledger 495,751 | **Pass** (`test_full_book.py` in the suite) |
| I1–I7 = 0, every line owned once | **all 8 development books: yes** |
| Lossless | **0 missing / 0 extra on all 8 books** |
| Development vs production (art therapy, fresh production) | **Fails on one digit** (owner decision: Step 21 item 3). 13 files; 11 identical; page 9's archive and the manifest differ only in one model score of a rejected-table record (Heron 0.8068 vs 0.8069; no decision changed). Cause: model scores depend on the torch thread count, which detection caches do not key on; the development run reused Step 19 detections computed while the OCR engine still left the process on one thread. |
| 1 vs 2 workers (ART, fresh with 2 workers, vs the final run) | **Content identical; not byte-identical** (Step 21 item 3). 498/500 files identical, including every page archive and the published book; the archive's `book.json.gz` (and the manifest that hashes it) differs only in the key order of two `cache_key_inputs` records (0 differences when parsed). |
| Cache closure | **Pass** (cache tests in the suite) |
| Ruff lint | **Clean** (backend and Step 20 tools); no changed file needs reformatting |
| Sealed books and hold-outs | not read, not run |
| Adapter: 8 books DTD-valid, 0/0 lossless | **Pass**: 0 DTD errors and 0/0 on all 8 books. Jaypee house-rule findings (not a gate): Spanish 22, book 4 12, Statistics 466, ART 1, IAP 30, others 0. |

## The ART adapter compare (our DocBook vs Jaypee's delivery)

Development book with reference, not an unseen score. Before = Adapter A on the Step 18/19
publication; after = Step 20.

| Element | Before | After | Jaypee |
|---|---|---|---|
| part / partintro | 5 / 5 (printed-contents fallback) | **5 / 4** | 5 / 5 |
| chapter | 17 | **17** | 17 |
| section | 9 | **139** | 144 |
| para | 2,026 | **1,890** | 1,720 |
| emphasis | 1,019 | **883** | 854 |
| listitem / orderedlist | 121 / 7 | 146 / **6** | 125 / 6 |
| figure / informalfigure | 10 / 7 | 10 / **5** | 11 / 2 |
| images exported | 17 | **15** | 13 |
| sidebar | 17 | **16** | 5 |
| table / informaltable / entry | 65 / 15 / 1,369 | same | 67 / 0 / 1,349 |
| index entries | 0 | 0 | 271 |
| ulink | 331 | 333 | 970 |

Biggest remaining differences: the index (the adapter writes no `<index>`), links (`ulink`),
more paragraphs than Jaypee (lines Jaypee keeps inside one paragraph), and sidebars. Two adapter
fixes (Stage 2, no converter change) were needed for these numbers: an omitted figure (small or
decorative) no longer crashes the writer, and a body heading above the book's chapter level
opens a part whatever its role. The second is measured here only (no unit test yet).

## Hand checks

Seeded samples (`step20_handcheck.py`, seed 20) of the final publications, judged by the agent
against the rendered page; not independently verified. Items, reasons and sheets:
`experiments/out/step20/final/handcheck/`.

| Book | Headings: right / errors (flagged) | Page links right (population) | Notes |
|---|---|---|---|
| ART | 38 / 2 (2) | 18/18 (18) | Both errors are local contents entries on section openers ("2. Quality Control…"). |
| IAP | 37 / 3 (1) | 39/40 (130) | Errors: a bare chapter number "4" as its own heading, an author name under a chapter title (flagged), a two-line title split. The wrong link joins the right paragraph but its first line on the next page is a separate unit. "INTRODUCTION" is level 2 in one chapter and 3 in another. |
| Trichology | 36 / 4 (2) | 40/40 (49) | Two section-divider titles read in the wrong word order (flagged); two two-line titles split. "Abstract" and "COMMENT" count as headings (each article's labelled parts). |

ART table cells, 20 multi-line cells: **20/20 read in order**.

Sheets viewed: ART headings 1, 2, 4; IAP links 9; Trichology headings 5. Other items were judged
from their text, level and previous heading after their class was checked on a viewed sheet.

## Known limits

- **Model scores depend on the thread count** (Step 21 item 3): see the parity gates.
- **Formula reading**: 534 equations an hour on CPU with all cores (was 186); the math hold-out
  (41,056 images) would still need about 77 h on CPU. Batching is not done.
- **Two columns in one span.** A gutter inside one extracted span cannot be split at the line
  stage (spans are the lossless unit); remaining joined-across lines: IAP 32, ART 14, book 4 40.
- **Contents entries.** Spanish 928 entries all carry text; 158 resolve to their entry unit and
  805 are flagged (mostly no unit on the target page matches the entry title).
- **Float anchors.** ART 0.79 → 0.73: the title-art figures that were easy anchored floats are
  now headings; the content figures score about the same.

## Events during the step

- **Book files.** IAP MEC and Trichology were in the Trash; ART's files were in Downloads. With
  the owner's approval they were placed under `external_references/` and the local config was
  rewritten for Linux (Windows original kept).
- **Merge issues.** After merging `adapter-a`, the suite stopped at collection (two
  `conftest.py`) and one boundary test failed (it scanned the adapter package); both fixed.
- **A baseline stopped safely.** The Trichology `before` run stopped when the layout source
  changed under it ("producer source changed; restart the worker"); it was rerun from a worktree
  of the merge commit (`.cache/s20/before_src`), reusing its cached stages.
- **Second freeze (owner decision).** The first freeze (`97e77133…`) had two assembly defects:
  contents entries never resolved to their unit, and unmarked note text was pulled into the main
  flow (Spanish anchors 0.854 → 0.799). Both were fixed in assembly; the second freeze
  (`3b34bb30…`) differs only in assembly, the evaluator and new tools, and only the assembly
  stage reran. First-freeze results: `experiments/out/step20/final1_superseded/`.
- **Adapter crash** on decorative figures (an omitted figure returned `None`); fixed in the
  adapter.
- **Session restart.** The furniture-cache rebuild was cut off by a session end and resumed
  from its cache.

## Memory and time

| Run (second freeze) | Wall | Peak |
|---|---|---|
| Spanish (publication from cache) | 89 min | 5.4 GB |
| Book 2 | 23 min | 1.5 GB |
| Statistics | 16 min | 1.7 GB |
| ART | 20 min | 1.7 GB |
| Book 4 (resumed) | 8 min | 1.2 GB |
| IAP / Trichology / art therapy | 6 / 7 / 0 min | ≤ 1.1 GB |
| First-freeze full runs (Spanish / Statistics / book 2) | 5.5 h / 1.6 h / 1.3 h | ≤ 2.0 GB |

The machine never fell below 3.8 GB free; the 1 GB memory floor was never reached.

## Caches (dry run; nothing deleted)

145 GB free; no cleanup is needed. Step 20 caches, for the owner's decision:

| Folder | Size | Holds |
|---|---|---|
| `.cache/s20/final_src` | 1.7 GB | the second freeze and its run outputs (keep) |
| `.cache/s20/final1_src` | 1.5 GB | the superseded first freeze and its outputs |
| `.cache/s20/before_src` | 1.1 GB | git worktree of the merge commit; Trichology baseline outputs |
| `.cache/s20/furniture` | 1.9 GB | furniture-test caches for the Step 20 layout (keep for tests) |
| `.cache/s20/{art_lab,iap_mec,trichology}` | 0.5 GB | the new books' stage caches (keep) |
| `.cache/s20/pub`, `.cache/s20/adapter` | 0.4 GB | dev publications, adapter deliveries |

## Skips

- **Fix 13** (character clean-up): deferred by the owner to Step 21.
- **Parity gates**: failure deferred by the owner to Step 21 (item 3).
- **Bold lead-ins, two-line headings, inline-math boundaries, a new anchor rule, formula
  batching**: not done; Step 21 item 5.
- **Sealed test books, science PDF, hold-outs (ENT, Mideast, math)**: not read, not run.

## Evidence

| What | Where |
|---|---|
| Run records, gates, hashes, scores, checks | `experiments/out/step20/<tag>/{performance,gates,hashes,eval,checks}/` |
| Tags | `before` (new books' baselines), `dev1`–`dev3` (development runs), `final` (second freeze), `final_w2`, `final_prod`, `final1_superseded` |
| ART derived gold | `backend/tests/gold_derived/art_lab/`, `backend/tests/gold_derived_tables/art_lab/` (human_approved=false); `experiments/out/step20/gold/cross_check.json` |
| Line-building checks on every book | `experiments/out/step20/dev/lines_v4/` |
| Statistics MathML scores | `experiments/out/step20/math/` |
| Formula speed | `experiments/out/step20/formula_speed.json` |
| Adapter runs and ART compare | `experiments/out/step20/final/adapter/` |
| Tools | `experiments/step20_{run,eval,checks,lines,structure,gold,math,handcheck,adapter,sample_pages,formula_speed}.py` |
