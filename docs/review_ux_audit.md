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
