# Review screen UX audit (Phase 1, analysis only, no code changed)

Evidence: the live app (127.0.0.1:8777), `view_review.js`, `view_edit.js`, `decisions.py`, `service.py`, `api.py`, and the review lists of four jobs
(b919e59e0c41d19b "Final Binder", 965d78af65efc4c4 = PULSE `9789372029260.pdf`, 3211b89dd49cb4fd "Sample 1", b3c776e2cefe0c91).
Screenshots (1440×900, scale 2) are in `docs/review_ux_audit_img/`: `01_review_list`, `A_<kind>_<n>` (card) and `A_<kind>_<n>_fix` (state after my accidental Fix click), `B_browse`, `C_change_element`, `E_export`.

**Not covered by screenshots:** kinds `author`, `index`, `adapter-inferred` (PULSE job) and `hidden_text` (one item) are described from data and code only. The Preview button of Change element, the Chapters and parts panel inside Browse (it is in `B_browse`) and the QC pages of past exports were not exercised (no export exists; Preview was not clicked). The queue has no kinds for MCQ, references, boxes, footnotes or running heads: those exist only as entries in the Change element menu, so they are found only by browsing every page.

## Top findings (all must be fixed before any redesign is trusted)

1. **"Fix" saves immediately with default values, with no preview or confirm.** `view_review.js` `decide("fix")` posts the decision as soon as the button is pressed, using whatever the inline editor currently shows (radio defaults, e.g. the dash editor defaults to "Minus (−)" even when the converter kept an en dash; the figure editor defaults to the current value). While capturing screenshots this created 7 real edits (+ 4 stacked duplicates) in job b919e59e0c41d19b; a reviewer can do the same. They were revoked through the app's undo; each item shows its earlier decision again. **Fix must open the editor first and save only on an explicit confirm.**
2. **The review list takes ~27 s to open (first load after any edit: longer), with only a spinner.** `GET /review` reads the review list from `preview/`; the preview key (`_run_key`) includes the full edit list, so after any edit/undo the adapter re-runs on the edited book. Show items as they load (stream or page), keep the old list visible while the new one builds, and cache.
3. **One undo of an edit takes ~1 min or more** (measured: several `DELETE /decisions/<edit id>` calls exceeded 60 s and some 150 s; undoing a plain decision took ~2 s). Likely cause, from code (`api.py` `undo`): an edit's undo calls `service.effective_book()` twice (before and after), and each call re-applies all ~218 edits to a fresh copy of the 258-page book; the cache key changes with the edit list, so the "after" call is never cached. `decisions.json` (581 KB) is also reloaded on every call. To confirm with a profiler in Phase 2 before changing. Plan: return the undo at once and refresh the page rows in the background; apply edits incrementally instead of replaying all of them; skip the "before" book when it is cached.
4. **Auto-advance after a decision is not predictable**: with "open items" filter the item disappears and the next one slides in; with "all items" the index moves. Keyboard shortcuts do not exist.
5. **Many items are already decided** (647 of 650 in the Final Binder, mostly by "Claude Desktop (AI)"), and the card shows "Decided: accept by …" as a small banner only; a human cannot tell AI decisions from human ones at a glance.

## Common problems on every card

* Header says "FIGURE / to review / page 1 (printed 1) · Stage 1": "Stage 1", "adapter", "must check" vs "to review" are internal terms.
* The reason is the raw converter message, often with a bracketed hint: the "what to check" sentence is glued to the cause.
* "OUR CURRENT RESULT" shows type/role/level as code (`list_item · level 2`, `paragraph · body`) and raw text with `|` and `\n`.
* The page crop (`review_crops/…png`) is capped at 140 px high and sits below the text; the big page image is far left. The reader must match the two by eye.
* Three equal buttons (Accept / Fix / Skip) with no stated consequence; "Skip" and "Accept" mean different things only in the audit log.
* A free-text note box on every card, though few need it.
* No "how it will look in the output" anywhere.

## Per kind (what is seen now, why it is slow, the plain question)

| Kind (count in Final Binder) | What the employee sees now (exact) | What is confusing or slow | Plain question |
|---|---|---|---|
| Figure (201) | "FIGURE · to review · page 1 (printed 1) · Stage 1 / layout models do not find a figure here (model disagrees); review (Check the figure's extent and its caption and credit links.)" then "A real figure (keep) / Decoration (leave out)". Other reasons: "page label inferred from the folio sequence, not printed", "photo/drawing evidence is mixed; encoded as PNG", "no page label: named by the physical PDF page". | The reason has nothing to do with the question for the last three (page-label note on a figure card). "model disagrees", "encoded as PNG" are jargon. Crop is tiny. Two items on the same figure appear as separate cards. | Is this a picture? |
| Picture description / alt text (116 must-check) | "alt text to supply (placeholder written)" then "Describe the picture / It is decoration (no description)" and a text box. | "alt text" and "placeholder" are jargon; writing text per card is slow; 661 of these across the four jobs. | What does this picture show? (or: Skip, it is decoration) |
| Heading (123) | "heading decision below confidence (Check whether this is a heading and its level.)" / "heading-like text not marked as a heading" then a drop-down "What is it? Not a heading, Heading level 1…5, Start of a new chapter". | "below confidence" is jargon; a drop-down needs several clicks; level numbers mean nothing without the outline. | Is "NOTES" a heading? Which level? |
| Structure (32) | "unit boundary below confidence (Check where the unit starts and ends and what kind it is.)", "a list marker is glued to the word that follows it; kept in the text", "part without chapters delivered as a chapter", "preface without a printed title", "section without content (a para is required by the DTD)". | "unit", "boundary", "DTD", "delivered as" are internal. For most there is no editor ("Accept it if it is right, or skip it."), so the only choices are accept or skip. | Is this the start of a new part/chapter/section? |
| List (221 must-check) | "broken bullet glyph '\x99': mark 'bullet' (add it to lists.marks)" | Instruction aimed at a developer (`lists.marks`); an employee cannot act on it. 221 near-identical cards (same glyph repeated). | Is this symbol a bullet? (group: 159 items use the same symbol) |
| Table (38) | "1 section row(s) span the table (Check the table's grid, header cells and cell text against the page.)", "header rows from TableFormer (no header evidence in the grid)", "note candidate not linked: opens with a word and a full stop or colon that opens no other table's notes in this book; not linked; review". Choices "Looks right / Needs fixing" with the note "Table fixes are recorded as a note for the production team; the table text is not changed here." | "TableFormer", "section row" are jargon. "Needs fixing" does not fix anything, which is not said until after choosing. The table is not shown rendered. | Does this table look right? |
| Character (17 + 43 hidden) | "en dash or minus before a number at offset 87: kept en dash" with "Minus sign (−) / En dash (–)". Also "a character's decoding may not match the painted glyph (Check the character against the page image.)" with only Accept/Skip. | "offset 87" cannot be found on the page; the character is not highlighted or enlarged; the default (−) is not the converter's choice (–). | Is this a range (–) or a minus (−)? |
| Text break / join (3) | "a possible continuation was not joined: tables at the page break in one frame, column counts differ (5 -> 2): kept separate; review (Confirm whether the text continues across the break.)" | Very long reason; "frame" and "column counts" are jargon; for tables the card says "This break is in a list or table. Accept to keep as it is." with no editor. | Does this text continue on the next page? |
| Language (35) | "the unit's language is uncertain (Confirm the language of the text.)" with the role drop-down "Change it to — choose —" | The drop-down offers heading roles, not languages: the question and the answer do not match. | Which language is this text? |
| Caption (12) | "caption not linked to a figure or table (Link the caption to its figure or table, or confirm it stands alone.)" with no editor | The instruction asks to "link" but the card cannot link; that is only possible in Browse → Change element → Figure caption. | Does this caption belong to a picture or table? |
| Page label (10) | "the printed page label is uncertain (Confirm the printed page number of the page.)" no editor | Cannot type the right number on the card. | What number is printed on this page? |
| Book setting (2) | "ISBN not supplied: delivery uses 'ISBN_TO_SUPPLY' as its name", "book title to supply". Pressing Fix shows "Fill in the fix first." with no field. | The fix field does not exist on the card; page shows "page –". | What is the ISBN? / What is the title? |
| Author (8, PULSE) | "author read from the title page: contrib='Editors'; firstname='Divya'; surname='Srivastava'; degrees='MD PDCC FACEE MAMS'; …" with three fields. | The reason is a code dump; the fields are filled from a regex of that dump. | Is this person's name right? |
| Index (344, PULSE) | "locator '45' has no resolved page", "sub-entry without a main entry written as a main entry" | "locator", "resolved" are jargon; 344 cards, many identical. | Which page does "45" point to? |
| Adapter-inferred (177, PULSE) | "index item split by the adapter into 2 entries at line ends", "index locators read by the adapter (book.json has none here): 97" | "adapter" and "book.json" are internal. | Is this index entry split correctly? |
| Hidden text (1) | "hidden text dropped from content (covered_by_paint) (Confirm the dropped text is not visible on the page.)" | "covered_by_paint" is jargon. | Is this text really hidden on the page? |

## Browse pages, Change element, Chapters, Export

* **Browse** (`B_browse`): each block is a row with raw buttons (↑ ↓ "Read this column first" "Change…") and, for a heading, a full inline form: level 1-5, "Set level", "Not a heading", "Start a new chapter here", Part/Chapter/Section/Front matter/Back matter, "Set kind", "Set number", "Belongs to the chapter before", "Save title". Seven or more controls per block; the consequence is not told. The page's chapter table ("Chapters and parts (0 parts, 9 chapters)") is on top and long.
* **Change element** (`C_change_element`): one flat drop-down of 29 entries ("— choose what it is —"), then two radio choices ("This block only" / "This block and what follows"), then Preview, Save the change, Cancel. Entries mix kinds of action (type change, level, move, remove from the book: "Not book content: running head", "Unwrap: a table, figure or box becomes its text"). Preview shows before/after rows only after a click. Good: the preview and save are separate, which the review card lacks.
* **Export / QC** (`E_export`): reached only through the 6-step bar; QC verdict banners and "Download the QC report" links. Not exercised (no export was made).

## Timing today (estimate, to be measured in Phase 3)

Reading the card, locating the problem on the left page image, thinking about jargon, choosing and waiting: **~20-40 s per item** for figure/heading/structure; **5-10 s** for items with only Accept/Skip. Plus up to ~27 s to open the list and ~1 min per undo.

## Proposed design (Phase 2, awaiting OK)

1. **One card = one problem.** Left: the PDF crop of exactly the problem area, highlighted, large (not 140 px). Right: how it will look in the output (rendered, e.g. a picture, a heading, a table, a bullet list), not raw text or tags.
2. **One plain question** (≤10 words, from the table above); everything technical ("Stage 1", offsets, model names, `lists.marks`) behind a small "Details" toggle, which also holds the original reason text.
3. **2-4 big answer buttons that name the result**: "Yes, it's a picture" / "No, it's text"; "Range (–)" / "Minus (−)"; heading levels shown as the outline. A hover preview of the result. "Fix in Browse" link only for kinds that cannot be answered on the card (captions, tables).
4. **Confirm-first:** the suggested answer is pre-selected; Enter accepts it; nothing is saved by selecting. This removes finding 1.
5. **Keyboard:** 1/2/3/4 answer, Enter accepts suggested, ← → move, U undo; auto-advance to the next open item.
6. **Groups:** "159 items use the same bullet symbol: apply the same answer to all?" with a list to untick (same idea as the existing "Apply to all similar…").
7. **Order and progress:** structure (parts/chapters) first, then must-check, then the rest; a progress bar per group; no layout jump, no full reload, page and zoom stay.
8. **Plain labels everywhere**: Part, Chapter, Section; Picture, Decoration; Table, List, Box; colour and icon per kind.
9. **Help line per card:** "What to check" and "What happens if you choose…".
10. **Speed work (findings 2 and 3):** stream or page the list, serve the old list while a new one builds, make undo return at once, apply edits incrementally.
11. **Missing kinds:** add queue items (or at least browse shortcuts) for MCQ, references/index/glossary, boxes, footnotes and running heads, so every scenario in the brief can be reviewed without opening each page.

Open question for you: the 647 of 650 items already decided by "Claude Desktop (AI)": should the new queue show those as "AI suggested, please confirm" (a human confirms with one key), or hide them?

---

# Phase 3: check (after the redesign, commit 3acab9e9)

## Before / after, one card per kind

"Before" are the Phase 1 captures (`A_<kind>_0.png`), "after" the new cards (`N_<kind>.png`), both in `docs/review_ux_audit_img/`. Kinds without an "after" image (author, index, adapter-inferred, hidden text) were not captured on the Final Binder job; their card uses the generic answers ("Looks right" / skip) or the author form.

| Kind | Before | After | New question |
|---|---|---|---|
| Picture | ![](review_ux_audit_img/A_figure_0.png) | ![](review_ux_audit_img/N_figure.png) | Is this a picture? |
| Character | ![](review_ux_audit_img/A_character_1.png) | ![](review_ux_audit_img/N_character.png) | Is this a range (–) or a minus (−)? (dash items) |
| Heading | ![](review_ux_audit_img/A_heading_0.png) | ![](review_ux_audit_img/N_heading.png) | Is "NOTES" a heading? |
| Picture description | ![](review_ux_audit_img/A_alt_text_0.png) | ![](review_ux_audit_img/N_alt_text.png) | What does this picture show? |
| Table | ![](review_ux_audit_img/A_table_0.png) | ![](review_ux_audit_img/N_table.png) | Does this table look right? |
| List | ![](review_ux_audit_img/A_list_0.png) | ![](review_ux_audit_img/N_list.png) | Is this symbol a bullet? |
| Text break | ![](review_ux_audit_img/A_join_0.png) | ![](review_ux_audit_img/N_join.png) | Does this text continue after the break? |
| Language | ![](review_ux_audit_img/A_language_0.png) | ![](review_ux_audit_img/N_language.png) | Is the language of this text right? |
| Caption | ![](review_ux_audit_img/A_caption_0.png) | ![](review_ux_audit_img/N_caption.png) | Does this caption belong to a picture or table? |
| Page number | ![](review_ux_audit_img/A_page_label_0.png) | ![](review_ux_audit_img/N_page_label.png) | Is the page number right? |
| Book setting | ![](review_ux_audit_img/A_settings_0.png) | ![](review_ux_audit_img/N_settings.png) | What is the ISBN of this book? |
| Structure | ![](review_ux_audit_img/A_structure_0.png) | ![](review_ux_audit_img/N_structure.png) | Where does this part, chapter or section start? |

## What was fixed, against the top findings

1. **Fix saves immediately**: fixed. Answers that name their result save with one click; anything that needs typing or choosing opens a form with Confirm / Cancel. Character answers follow what the tool kept.
2. **List takes ~27-39 s**: after the first open it is 0.16 s; the first open after a restart is now prepared at start-up (not yet timed on the live app).
3. **Undo takes ~1 min**: 0.65 s measured on a copy (fixed by the earlier commit 611ea64a, which was already running).
4. **Keys**: 1-3 answer, Enter = suggested / Confirm, S skip, ← → move, U undo; tested.
5. **Assistant-decided items**: shown as "Decided by Claude Desktop (AI) … Please confirm or change it" and stay open until a person confirms.

## Timing estimate (seconds per item)

Estimates, not stopwatch measurements of reviewers. Reading cost is assumed from the amount of text and the number of controls; the keyboard test confirms the mechanics (20 mixed items in ~17 s of machine time, including page loads).

| Kind | Before | After |
|---|---|---|
| Picture / heading / structure | 20-40 | 4-8 |
| Character, table, join | 15-30 | 4-8 |
| Bullets, language, caption, page number | 5-15 | 2-4 (and one answer for a whole group via "N other items look like this") |
| Picture description | 30-60 (typing) | 20-40 (typing; "It's a decoration" is one key) |
| Open the list | 27-39 s | 0.2 s (after the first open) |
| Undo | 60 s+ | < 1 s |

## Checks done

* Browser test of the card data (`test_review_model`): passes.
* Keyboard-only test on a copy of the book, 20 mixed items: every answer reached the audit log with the same fields as before (`who, key, item_kind, action, fix, note, item`), U took the last one back. Nothing was run against the live app.
* Conversion output: the diff of 611ea64a..3acab9e9 under `backend/src` touches only `static/assets/*` (the screen) and `api.py` (the start-up preparation of the review list). No converter, adapter or export code changed, so the export for the same decisions is unchanged by construction. An actual export before/after was **not** run (no export exists for these books and an export writes into the job).
* Limits: the author, index, adapter-inferred and hidden-text cards were not looked at; the old browser test steps were updated but are skipped on this machine.
* Full app test suite: all pass except what is below. Four failures in the first full run (16 min, machine busy): `test_art_publication_review_export_check` was a real failure (it expected must-check items first; the queue now shows structure first, test updated, passes). The three `test_queue.py` failures ("job stayed uploaded") were not caused by the review screen: they failed the same way on the old code and passed (6 of 6) once /tmp had free space again; the converter will not start a book when the disk is nearly full, and scratch copies of two books had filled /tmp. Earlier one-off failures (`survives_a_restart`, `two_reviewers_refresh…`) passed when run alone.
* The same decisions exported with the old code (611ea64a) and the new code (3acab9e9) on identical copies of the PULSE book (jaypee_v5): 657 files each; the DocBook XML and the ePub are byte-identical; only three `run.json`/`export.json` timing counters differ; lossless 0 missing / 0 extra in both.
* First list open after a restart on the live app: the book worked on last 1.6 s; other books 2 s, 11 s and 48 s on first open (not warmed then). The start-up preparation now covers the two most recent books.
