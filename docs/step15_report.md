# Step 15 — content that continues across pages

Status: **complete for review.** A new `continuity` stage (after tables) records paragraphs,
list items, index and bibliography entries and tables that continue across a page break (and
paragraphs that continue into the next column where the paragraph stage did not join them),
as chains of per-page pieces with the page-break position kept for the adapter. Earlier
stages are unchanged except the three Part 0 changes. Following your instruction during the
step, **only rules whose new joins are about 0.95 or more correct are kept**; every new join
of the check set was verified by hand (below).

Main results (Step 14b final → Step 15 final):

| Book | Reference units crossing a page break, held in one chain | Links (new ones) | New joins correct (manual) | Paragraphs, reference convention |
|---|---|---|---|---|
| 1 Spanish US history | continuation pairs¹ **77 → 105 of 244** | 94 → 138 (+30 page, +12 column, +2 entry) | **44 / 44** | per page: F1 0.9422 → **0.9429**, exact 0.8943 → 0.8963 |
| 2 Immigrant children | **139 → 155 of 170** | 141 → 161 (+20) | **20 / 20** | chained: F1 0.9327 → **0.9446**, exact 0.857 → **0.877** |
| 3 Art-therapy index | 0 of 4 (index entries) | 1 → 1 | — | (no paragraph gold) |
| 4 Medical anatomy | 12 → 13 of 83 | 27 → 30 (+3) | **2 / 3** (lists 2/2, paragraph 0/1) | per page unchanged 0.9014; chained 0.9029 → 0.9030 |
| Statistics | (no paragraph gold) | 89 → 107 (+18) | **17 / 18** (lists 11/11, paragraph 6/7) | — |

| Tables over several pages | Continuation links | Correct (manual) | TEDS of the joined table (duplicated headers kept) | Repeated header rows recognised |
|---|---|---|---|---|
| 4 Medical anatomy (15 reference tables) | 25 | **25 / 25** | **0.926** (0.893); 0.970 on the 13 held whole | 15 |
| Statistics (69 reference tables) | 65 → **61** (4 wrong ones withdrawn, flagged) | **61 / 61** | **0.959** (0.897); 0.996 on the 47 held whole | 44 |

¹ Book 1's reference splits every paragraph at a page break, so it has no reference unit
spanning pages; its truth is derived (Task 1).

## Scope and baseline

HEAD at start: `0bdb8ff` (Step 14b and its gate decisions in; the tracked tree clean; the
untracked `.vscode/`, one Step 11d output and the Step 13c/14a development files left
untouched). Baseline: the Step 14b final capture, frozen into
[step15/before](../experiments/out/step15/before/). Only books 1–4 and Statistics were run;
ENT, mideast, the mismatched pair and the math hold-out were not. Gold, reference XML, the
ledger and old projects were not edited. Your two instructions during the step are recorded
in [decisions.md](decisions.md#step-15-owner-instructions-during-step-15).

## Part 0 — Step 14b carry-overs (measured on all books)

| Change | Where | Effect |
|---|---|---|
| **Disagreement flag severity** | `tables/models.py`: every table carries `review_status`, implied by its flags; no table flag is `must_check` (`MUST_CHECK` is empty), so the TableFormer disagreement is `needs_review` only | all flagged tables `needs_review` (book 1 28, book 2 8, book 4 12, Statistics 85); no `must_check` |
| **Table drawing fragments holding a numbered title** become table pieces | `tables/captions.py` (`title_pieces`): a figure made only of drawings, with no caption or credit, whose text is the table's linked numbered title and the table's own lines, lying within the table and its title (90% of its box), is absorbed; the title is no longer flagged | Statistics **362 of 364** absorbed and not exported (renders checked, [pieces](../experiments/out/step15/pieces/)); 2 stay flagged (their figure holds other text); no other book has such figures |
| **Glossary pages typed as table regions** read as entries | `lists/page.py`: on a glossary page, table streams and table-text units are list text (entry order applied) | only book 1 **p676 and p684** change (all 70 + 81 + 9 + 13 + 2 navigation pages rebuilt, [lists](../experiments/out/step15/lists/)): p684 definition entries 1 → 17, p676 30 → 36; p684 gains 10 reference boundaries with no false one; glossary descriptions exact **0.952 → 0.966** |

## Task 1 — measure first

From the references ([measure/before](../experiments/out/step15/measure/before/)): a reference
unit crosses a page break when its aligned tokens lie on two or more pages. Today's handling
(Step 14b): the lists stage keeps Step 9 page joins and links index/bibliography entries.

| Book | Reference cross-page units | Already joined | Existing links correct |
|---|---|---|---|
| 1 | 19 (17 list items/index, 1 paragraph, 1 caption) + 244 derived continuation pairs¹ | 8 + 77 | 92 / 94 |
| 2 | 170 (167 paragraphs, 3 bibliography entries) | 139 | 141 / 141 |
| 3 | 4 index entries (gold location low-confidence, pp. 1→6) | 0 | 0 / 1 |
| 4 | 83 paragraphs | 12 | 26 / 27 |
| Tables | book 4: 16 reference tables, 26 page breaks; Statistics: 69 tables, 76 breaks | 24; 52 | 24 / 24; 50 / 56 (6 wrong) |

¹ Book 1: consecutive sibling units of one kind in the reference tree, the first ending page p
and the second starting p + 1, page credits between them skipped (the reference places them
between the halves), the first one's last line ending without a sentence end.

**Top failure classes** at the break (A: our unit before it, B: after it):

| Class | Book 1 | Book 2 | Book 4 | Example |
|---|---:|---:|---:|---|
| Something set apart after A or before B in the main flow (boxes, margin glossary definitions, map questions) | 33 | 4 | 9 | book 1 p135: two margin definitions after "…Una" / "empresa integrada…" |
| Step 7 says "neutral" (open end before a capital or digit) | 16 | 14 | 1 | book 2 p86 "…minority group in the" / "United States…" |
| Step 7 says "break" (sentence end, same paragraph) | — | 6 | 2 | book 2 p13 "…school contexts." / "First, how the…" |
| A or B outside the main flow (figure/note/callout streams, table cells) | 6 | 3 | 30 | book 4 p102: B in a note stream |
| Float-only page between the halves | — | 3 | 2 | book 2 p70 → (p71 rotated table) → p72 |
| Entry link dropped by the lists stage (index continuation) | 8 | — | — | book 1 p707 "…Indios de todas las" / "tribus, 495–96" |
| List items without punctuation (not continuations: questions, map labels) | 74 | — | — | counted by the derived truth, never joined |
| Index continuation read before its entry (p686, Step 11b) | known | — | — | reading-order limitation, unchanged |

Column changes inside a page: book 1 **121** reference units split at a column change (57
paragraph, 42 index, 11 glossary), book 4 81 (Step 9 column joins cover the rest).

## Task 2 — paragraphs, lists and entries across pages

`backend/src/book_core/continuity/` (`edges.py`, `decide.py`, `tables.py`, `cache.py`,
`models.py`); stage wired into `book_run.py`, cache scope `continuity`, registry and disk rule
in `cache_admin.py`.

- **Model** (`models.py`): a `Chain` lists its members (final-view unit ids or table ids) and
  a `PageBreak` between each two: the last line before the break, the first after it, the
  printed label of the page that begins (the page marker), skipped float items and
  float-only pages, the line join with its hyphen/split-word decision (Step 9 rule), source,
  confidence and reasons. Nothing is merged and no text is copied (owner decision, Step 10:
  linked per-page units). Candidates examined and not joined keep their reasons. The final
  archive publishes the book record and, per page, its breaks; units' `continues_from` /
  `continues_to` are the continuity record's.
- **Edges** (`edges.py`): the main flow over the final unit view; items are floats (tables,
  their titles and notes, captions, figure text, units a figure links), headings (structure
  stage, real headings or section starts), set apart (other style than the book's body style,
  or heading candidates that are not headings), or body.
- **Decision** (`decide.py`): A is the last body unit of page p, B the first of p + 1, floats
  and set-apart units skipped, a heading stopping the search; float-only pages skipped (at
  most 2). A paragraph or list item continues into B when B opens no new item (no list
  marker, no enumerator, no run-in heading), same style, B not indented, same column width,
  and the text says so:
  - break hyphen (0.85), or open end before a lowercase or digit start (0.9);
  - open end before a capital on a full last line (0.75);
  - sentence end, full last line, no indent, in a book that indents its paragraphs (0.7; no
    book qualified);
  - **when anything was skipped between A and B, only an open end before a lowercase or
    digit start joins** (added after a synthetic test showed a table skipped before a capital);
  - a list item continues only from a full last line (items end without punctuation).
- **Entries**: an index or bibliography entry links to B (same kind) when B is an indented
  line without an open entry, or A ends open and B opens lowercase; glossary and definition
  rows are not linked by rule (they end without punctuation; 16 wrong links measured on book
  1 pp. 664–682 and removed).
- **Columns**: consecutive body units of one page where B starts a new column (right of and
  above A's last line), A ends its column and B begins the next, with the same evidence.
  Measured: book 1 12 links, 12/12 correct (of 121 reference units split at a column
  change); book 4 0/12 correct before the column-end test, no link after.
- **Earlier links kept**: Step 9 page joins the lists stage kept (with their line join) and
  lists-stage entry links; none was dropped by the final view.
- **Never across a heading**: a structure-stage heading between the halves stops the search.

**The enumerator fix (during the final runs).** *Cause:* reviewing the first final run's
new Statistics joins by hand, 15 of 33 were wrong; 13 joined numbered answers ("61 .
quantitative discrete, 11,234 students" → "65 . quantitative continuous", "13 . Let X…") and
1 a lettered item ("Then," → "a. Find P(…)"). The lists stage does not read "NN ." (number,
space, full stop) as a list marker there, so B looked like running text and "open end before
a digit" joined it. *Change:* a page that opens with an enumerator — a number of at most
three digits or one letter, then "." or ")" and a space — opens a new item and never
continues the previous unit (`edges.ENUMERATOR`, `start_kind` = "enumerator"); numbers that
are text still continue ("12 horas", "38.6 percent", "2001). Further"). *Which books:* only
Statistics changed (new joins 33 → 18, wrong 15 → 1); books 1–4 kept exactly the same chains
(parity of the rerun); test `test_an_enumerator_opens_a_new_item_never_a_continuation`.
Only the continuity stage and the final archives were recomputed (every other cache key
identical; the pre-fix capture is kept in
[final_prefix](../experiments/out/step15/final_prefix/)).

**A guard tried and rejected:** requiring A to end its page's body text and B to begin the
next page's (no body text after/before them in other columns), meant for book 4 p293, did
not catch p293 (its true continuation is not in our main flow) and removed 5 correct
Statistics joins; reverted (the code is byte-identical to the final runs' producer).

## Task 3 — tables across pages

`continuity/tables.py`, `tables/records.py` (`title_checks`), `tables/captions.py`:

- The tables stage's continuation marks become **table chains**: column map (one to one;
  the tables stage requires equal counts and proportions), **repeated header rows** (the
  continuation's leading rows whose cell texts equal the first part's header rows, or its
  first row when it has none; named, not repeated in the logical table), **continuation
  marks** (a one-line unit of at most two words directly below the first part or above the
  continuation, "Contd…"; a continuation title repeating the label and number).
- **Wrong continuation marks withdrawn** (your instruction): when the next table has its own
  numbered title that is not the first one's (the title's number is a derived descriptor,
  `TableText.number`), the mark is withdrawn and both tables get the review flag
  "continuation across the page withdrawn …" (`needs_review`). Statistics repeats the same
  title under each part, so equal numbers keep the mark. Of the six wrong Step 14b marks:
  **4 withdrawn** (Tables 2.3/2.4, 4.10/4.11, p603, p835); **2 kept and correct** — Table 4.28
  (p288) and Table 12.3 (p658) do continue; the gold aligns their few tokens to another table
  (renders checked). No correct mark was lost (books 2, 4: none withdrawn).
- **Mismatches stay separate**: a last and a first table at the break in one frame whose
  column counts differ is a review candidate, not joined.

Joined-table scores ([joined_tables](../experiments/out/step15/final/joined_tables/)): the
whole reference table against our chain stacked without repeated header rows.

| Book | Reference multi-page tables | Held whole / partly / not detected | TEDS joined | TEDS with duplicated headers | Full TEDS joined | Header rows exact | Header duplicates removed |
|---|---:|---|---:|---:|---:|---:|---:|
| 4 | 15 | 13 / 2 / 0 | **0.926** | 0.893 | 0.852 | 1.0 | 15 |
| Statistics | 69 | 47 / 18 / 4 | **0.959** | 0.897 | 0.864 | 0.92 | 44 |

## Task 4 — evaluation

**Join precision per book and kind** — manual check of 241 joins
([check set](../experiments/out/step15/manual/check_set.json),
[verdicts](../experiments/out/step15/manual/verdicts.json),
[precision](../experiments/out/step15/manual/precision.json), joins listed as text in
[joins/](../experiments/out/step15/manual/joins/), book 4 unit joins rendered in
[check/](../experiments/out/step15/manual/check/), all 86 table continuations on contact
sheets in [sheets/](../experiments/out/step15/manual/sheets/)): every join of book 4, every Statistics
table continuation (with the six Step 14b marks), book 1 p260, 25 seeded random joins
(seed 1500) each in books 1 and 2 over all their joins, and every new join of every book.

| Book | Kind | New joins correct / checked | Kept (earlier) joins checked | Reference-scored links (gold) |
|---|---|---|---|---|
| 1 | paragraph (page) | **30 / 30** | 16 / 16 | 104 correct / 4 "wrong"² |
| 1 | column | **12 / 12** | — | 12 / 12 |
| 1 | entry (index) | **2 / 2** | 4 / 4 | 18 / 18 |
| 1 | random sample (all joins) | 25 / 25 | | |
| 2 | paragraph | **20 / 20** | 23 / 23 | 158 / 158 |
| 2 | random sample (all joins) | 25 / 25 | | |
| 4 | list item | **2 / 2** | 14 / 14 | 16 / 16 |
| 4 | paragraph | **0 / 1** (p293) | 12 / 13 (p177) | 12 / 14 |
| 4 | table | **25 / 25** | — | 24 correct, 1 unscored |
| Statistics | list item | **11 / 11** | — | (no gold) |
| Statistics | paragraph | **6 / 7** (p361) | — | (no gold) |
| Statistics | table | **61 / 61** | — | 50 correct, 2 "wrong"³, 9 unscored |

² Book 1's two Step 9 joins p478, p509 and two new joins p364, p412 are scored "wrong" by the
derived truth; by hand all four continue the sentence (the reference puts a quotation-source
line between the halves). ³ Tables 4.28 and 12.3 (gold alignment noise, renders checked).

Wrong joins: **book 4 p293→294** (new): a two-column page where the text continues in the left
column under two figures ("somatic cells have alleles…"), which our main flow misses; B is
the top of the right column. **Book 4 p177→178** (kept Step 9 join): B starts mid-column.
**Statistics p361→362** (new): "…we designate this by writing" is followed by a display
equation; "The curve is symmetric…" opens a new paragraph. **Book 1 p260** (wrong in
development): refused now ("text skipped between them: only an open end before a lowercase
or digit start joins"; A ends open, B starts with a capital).

Book 4 does not reach 0.95 on new paragraph joins (0 of 1); no general rule separated p293
without removing correct joins elsewhere (the column guard above; skipped unlinked captions
also precede four correct book-1 joins), so recall there stays low as you allowed: 3 new
joins in the book.

**Cross-page reference units held in one chain** (Step 14b → Step 15,
[measure/after](../experiments/out/step15/measure/after/)): book 1 continuation pairs 77 →
**105** of 244 (paragraphs 76 → 104 of 217; the 74 list-item "pairs" are unpunctuated items,
not continuations); book 2 139 → **155** of 170 (remaining: 6 sentence-final page ends; the rest text taken
into table cells or order and kind cases); book 4 12 → 13 of 83 (remaining classes above); book 3
0 of 4 (low-confidence gold locations pp. 1→6).

**Paragraphs before → after** ([effect](../experiments/out/step15/final/effect/)); every
boundary change is on a page with a new link or the Part 0 change
(`unexplained_pages: []` in every book and view):

| Book | View | Boundary P / R / F1 | Exact units |
|---|---|---|---|
| 1 | per page (reference convention) | 0.9174 / 0.9685 / 0.9422 → 0.9181 / 0.9691 / **0.9429** | 0.8943 → **0.8963** |
| 1 | chained | 0.9182 / 0.9680 / 0.9424 → 0.9190 / 0.9687 / 0.9432 | 0.8847 → 0.8829 |
| 2 | per page | 0.7873 / 0.9352 / 0.8549 (unchanged) | 0.6803 (unchanged) |
| 2 | chained (reference convention) | 0.9303 / 0.9352 / 0.9327 → **0.9541** / 0.9352 / **0.9446** | 0.857 → **0.877** |
| 4 | per page | 0.8714 / 0.9335 / 0.9014 (unchanged) | 0.7655 (unchanged) |
| 4 | chained | 0.9029 → 0.9030 | 0.7661 → 0.7662 |

Book 1's chained exact units fall slightly because its reference splits at page breaks (a
correct link joins two reference units there); its per-page view, the convention of its
reference, improves (12 column links remove 12 false boundaries; p684 +10 boundaries).
Unit kinds change only in book 1 (definition entries 1,293 → 1,315, table text 88 → 80:
Part 0). Cell order in reference tables and reading order are unchanged (books 1–4
compare: native text, layout, reading order, furniture, paragraphs, structure identical;
lists differ only on book 1 pp. 676 and 684).

**Hyphen repair across pages**: 3 page joins carry a hyphen decision (book 2, all "join",
kept Step 9 joins, e.g. "conceptu-/alized"); no new join ends on a break hyphen in these books
(the rule is tested on a synthetic book).

**Overlays** (seed 1501, one per class; [overlays](../experiments/out/step15/overlays/)):
[hyphen, book 2 p191](../experiments/out/step15/overlays/1_hyphen_immigrant_children_p191.png),
[floats skipped, book 1 p137](../experiments/out/step15/overlays/2_floats_skipped_spanish_us_history_p137.png),
[column, book 1 p249](../experiments/out/step15/overlays/3_column_spanish_us_history_p249.png),
[entry, book 1 p714](../experiments/out/step15/overlays/4_entry_spanish_us_history_p714.png),
[table with repeated header, book 4 p26](../experiments/out/step15/overlays/5_table_repeated_header_medical_anatomy_p26.png),
[refused candidate, Statistics p10](../experiments/out/step15/overlays/6_refused_statistics_p10.png).

**Time and memory** (one worker, CPU). The lists change re-keyed every later stage, so each
book recomputed characters, figures, equations, MathML, tables and the new stage:

| Book | Whole first run | Tables stage | Continuity stage | Peak memory | Enumerator rerun (continuity + archive) |
|---|---:|---:|---:|---:|---:|
| 1 | 2 h 50 min | 35 min | 1.4 min | 13.2 GB (tables) | 3 min |
| 2 | 52 min | 12 min | 0.2 min | 1.4 GB | 0.6 min |
| 3 | 2 min | 0.1 min | < 0.1 min | 0.2 GB | < 0.1 min |
| 4 | 31 min | 7 min | 0.4 min | 1.3 GB | 0.8 min |
| Statistics | 64 min | 11 min | 0.8 min | 1.5 GB | 2 min |

Disk: no cache was deleted; the runs used less than the estimate (14 GB free after all runs
and the parity bundles). A dry-run list of the Step 14b stage caches the Step 15 runs
superseded (0.53 GB) is in
[cache_prune_dry_run.json](../experiments/out/step15/cache_prune_dry_run.json); not applied.

## Task 5 — tests

`backend/tests/test_continuity.py` (17): join on open end and lowercase; sentence end does
not join unless the book indents (and then not past an indent); style change, indent and
width refuse; a capital after an open end needs a full last line; skipped set-apart text needs
a lowercase start; list items continue only from a full line, a new marker never continues;
entries are linked, glossary rows not by rule; an enumerator opens a new item, text numbers
continue; script-neutral text cues (no case → decided on the end alone); a heading stops the
search, floats are skipped, a float-only page is skipped; column change and column ends;
table review status `needs_review`; a continuation into a differently numbered table is
withdrawn, a repeated title keeps it; title fragments become table pieces; a glossary page
set as table text is read as entries (and not elsewhere); cache closure of the stage and of
`final`; and a small book run end to end — **a hyphen across the page repaired by decision,
the page marker kept with the break, a sentence end at a page bottom not joined, a table
continued with its repeated header row named, 1 vs 2 workers byte-identical**. Updated: the
disk-need test's stage layout (`test_step11c.py`).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | PASS: **1,078 passed, 0 failed** (after the final runs) | [pytest.xml](../experiments/out/step15/final/pytest.xml) |
| Six-pages-per-book sample + Statistics sample | PASS: 0 missing / 0 extra on 30 pages | [source crosscheck](../experiments/out/step15/final/source_crosscheck.json) |
| Book 1 ledger 495,751 | PASS (ledger and final archive) | [full_book.json](../experiments/out/step15/final/full_book.json) |
| Full-book I1–I7 on books 1–4 | PASS: all zero | `final/after/*_full_gates.json` |
| Every line owned once (five books) | PASS: lists units and order once on every page; final view + tables own every line once; continuity links equal the units' links; every break names its members' last/first lines | [final_outputs.json](../experiments/out/step15/final/final_outputs.json) |
| Books 1–2 not worse | PASS: book 1 per-page F1 0.9422 → 0.9429; book 2 chained 0.9327 → 0.9446, per page unchanged; every change explained | [effect](../experiments/out/step15/final/effect/) |
| Parity (stage vs development) | PASS: **identical on all five books**: continuity chains, candidates and dropped links (138 / 161 / 1 / 44 / 164 chains); tables on every page (grids, roles, header references, content kinds, titles, notes, continuation marks, absorbed figures, review status, possible tables) | [parity](../experiments/out/step15/final/parity/) |
| Pre-run sweep | PASS: 0 failures on all five books | [sweep_prerun.log](../experiments/out/step15/sweep_prerun.log) |
| Ruff (src, tests, Step 15 scripts) | PASS | — |
| Gold, reference, ledger, old projects untouched | PASS | — |
| ENT, mideast, math hold-out not run | PASS | — |
| Statistics (information) | I1–I6 zero; I7 = 1 (p870 index gutter, backlog); lines owned once | `final/after/statistics_full_gates.json` |

**Run notes.** (1) A full test run was stopped and restarted because Ruff formatting edited
producer files while it ran. (2) An ad-hoc debug run outside pytest loaded the real layout
models and fetched two model files from the Hugging Face hub into the local model cache
(nothing uploaded). (3) My edits had written CRLF line endings into changed files; they were
converted to LF before any run (producer digests normalise line endings either way).

## Limitations

1. **Book 4** recall stays low (13 of 83 reference cross-page paragraphs): its two-column
   reading order upstream interleaves columns and leaves continuation text in figure/note
   streams; one new join is wrong (p293) and one kept Step 9 join (p177).
2. **Statistics p361**: a display equation between the halves is not seen (equation records
   are not stage input); "open end before a capital on a full line" joined a new paragraph.
3. **Book 1**: 74 derived "continuations" are unpunctuated list items (not real); index
   continuations read before their entry (p686) and entries split inside a page by the lists
   stage stay.
4. **Glossary/definition rows** are not linked across pages by rule.
5. **Column joins** fire only where both units end/begin their columns cleanly (book 1 12 of
   121 column splits; book 4 none).
6. **Table continuations** need detection on both pages (Statistics: 17 breaks miss a table on
   one or both pages; 7 marks missing for edge position or column count).

## Decisions for you

1. **Book 4 precision**: new paragraph joins 0/1 (p293) and one kept Step 9 join wrong (p177).
   Accept as is (lower recall, 3 new joins), or drop *kept* Step 9 joins whose second part
   does not begin its column (would remove p177; to be measured on all books)?
2. **Display equations as floats**: give the continuity stage the equation records so a
   display equation between halves counts as a skipped float (fixes Statistics p361's class)?
3. **Glossary rows across pages**: keep them unlinked by rule, or link a glossary entry whose
   continuation opens the next page without a leading term?
4. **Archive units**: the final archive's units carry the continuity links (replacing the
   lists-stage links, which remain in `lists.page_links`). Keep this single source?

**Step 15 is complete; the next step has not started.**
