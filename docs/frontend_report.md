# Production frontend: PDF to Jaypee DocBook

Status: complete for review. One commit after the (already done) merge. No Docker, no ePub, no
converter or adapter change.

## Summary

- **Part 0.** `adapter-b` was already merged into `main` (commit d1a0b071), so there was no merge
  to make and no merge issue to fix.
- **The app.** `python -m book_app` starts a local web app (`http://127.0.0.1:8777`) with exactly
  the requested flow: upload (drag and drop, 2 GB, PDF checked by content), profile (pick, upload
  YAML with line / field / "did you mean" errors and new "untested" versions, and the
  "Make a profile from a client spec" panel with copy button, steps, the warning and the schema
  download), convert in a background worker (stage progress, elapsed time, cancel), book details
  (ISBN with check digit, never invented), review, export with QC, and download of the delivery
  ZIP and the QC report (HTML). A Books page lists, reopens, re-exports and deletes.
- **Addition (browse mode and edited deliveries).** Review also has **Browse pages**: any page with
  the PDF on the left and the result on the right, with heading level / not a heading / make
  heading, join with next, split here, make a list from selected bullet paragraphs (mark from the
  profile), start a new chapter, and figure descriptions. **Check an edited delivery** takes a
  DocBook ZIP edited elsewhere and shows DTD, house rules and the text compared with the
  converter's, without changing the files.
- **No adapter change.** Decisions are saved per book as an append-only file (who, when, what).
  At draft run, export and check, the app builds an *overlay copy* of `book.json` with the edits
  applied and the adapter reads that unchanged (`docs/decisions.md`, "Production app").
- **Stack.** FastAPI, Starlette and uvicorn (MIT/BSD) and a plain ES-module browser app
  committed as written: no Node, no build step, no CDN, fonts or analytics. Licences are in
  `docs/dependencies.md`. Settings are in one file, `app_settings.yaml`. The data folder is one
  directory (Docker-ready; no Docker work done).

## Bugs that blocked the app

None in Stage 1 or the adapter. (Adapter-side finding, not blocking, left as is: a synthetic book
without a title-page author list yields no pre-filled authors; the app lets the user type them.)

## Tests

| Suite | Result |
|---|---|
| App API tests (`backend/tests_app/test_api.py`: upload, profile list/upload valid/invalid/new version/no overwrite, convert, cancel and clean-up, failure record, restart, details and ISBN, decisions save/restore, browse edits, export blocked/override recorded, downloads, edited-delivery check, delete) | 22 pass |
| Overlay unit tests (split, list, join, heading, figure; text never lost; schema valid) | 6 pass |
| Browser, nine-page art-therapy PDF, **real converter** (Chrome, 1366×768) | pass (about 2 minutes) |
| Browser, cached ART publication (130 pages): details, flagged items, browse fixes, export blocked then override, download, edited-delivery check, delete | pass (about 90 s) |
| Converter and adapter tests | pass (full run below) |
| Ruff check | clean (`backend`); format clean for the new code |

Both browser tests also assert there was no script error and no request to anything but the app.

**Full run:** `pytest` over `tests`, `tests_adapters` and `tests_app`: **1,394 passed, 5 skipped** (the skips need Step 7 vocabulary caches that are not on this machine), 15 min 51 s, including both browser tests.

## Screens

Screenshots are in `docs/screenshots/` (taken by the browser tests at 1366×768):

| Screen | File |
|---|---|
| Upload | `01_upload.png` |
| Profile: invalid upload with errors | `02_profile_invalid_upload.png` |
| Profile: list and "Make a profile" panel | `03_profile_choose_and_maker.png` |
| Convert: progress | `04_convert_progress.png` |
| Convert: done | `05_convert_done.png` |
| Book details | `06_details.png`, `10_art_details.png` |
| Review: flagged items | `07_review_queue.png`, `11_review_queue.png` |
| Review: browse a page | `12_review_browse.png` |
| Review: your changes | `13_review_changes.png` |
| Export blocked / result | `14_export_blocked.png`, `15_export_result.png`, `08_export_result.png` |
| Check an edited delivery | `16_check_edited_delivery.png` |
| Books | `09_books.png`, `17_books.png` |

## Behaviour worth knowing

- **Draft run.** The review list comes from an adapter run on the edited book (about 30 s for 130
  pages). After a fix the list is marked stale until **Refresh the list**; decided items that a
  fix resolves stay counted ("23 of 41"). Export always re-runs everything.
- **Alt text.** ART shows 15 placeholders; export is blocked (409) until each has a description or
  the override box is ticked. The override is in the QC report ("overrides"), the export record
  and the decisions file. A fix written in review clears the placeholder.
- **ART result** (jaypee_v3, as in the Adapter B report): DTD 0 errors, lossless 0 missing / 0
  extra, one house-rule finding (`ids.table`, the converter's merged chapters 3 and 4, R15),
  verdict WARN.
- **Edited-delivery check.** House rules run against the converter's own export of the same book;
  the text comparison is against that export. Edited words show as removed/added (expected). The
  uploaded ZIP is kept byte-identical (tested).
- **Robustness.** Jobs and states persist in `job.json`; a conversion interrupted by a restart
  reads "stopped, press Convert again" and resumes from its cache; failures show the converter's
  record (stage, page, message), never a stack trace; cancel removes the half-made output and
  temporary files; free space is checked before converting against the converter's 5 GB reserve;
  every id is checked as 16 hex characters; names are sanitised; uploads are stored as
  `input.pdf` inside their job; the profile store only appends.

## What is left

1. **Models.** The layout models must be reachable: set `models_folder` in `app_settings.yaml`
   (the header shows "layout models missing" otherwise). The app does not download anything.
2. **Browse edits are limited to the listed operations.** No free-text editing, no table cell
   editing (a table fix is a note), no merging of two lists, no moving text between pages.
   A split starts at a line end; a list needs a printed bullet at the start of each paragraph.
3. **Authors** fixed in review are applied to the confirmed book details by matching the printed
   name; if the details were not yet confirmed, edit them in step 4.
4. **Review list is not live.** It needs a refresh after structural changes (about 30 s on a long
   book), and the first draft run after confirming details takes about as long.
5. **One reviewer name per browser** (not an account); decisions are traceable but not
   authenticated.
6. **Not done by design:** Docker, ePub, converter fixes, the old `frontend_temp/` (kept,
   superseded; delete it when the team agrees), installing the layout models, a Windows launcher.
7. **PyMuPDF is AGPL.** Keep `allow_lan: false` until the licence question is settled.
