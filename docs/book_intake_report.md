# Book intake: new reference samples

This step takes in the new reference samples by counting what each file contains. It changes
nothing in the pipeline:

- no src rule, gold, ledger or dialect change;
- no pipeline run and no accuracy metric on the new books;
- reference XML was read only for counts, the root, the doctype, page markers and the
  metadata title/ISBN (to check the pairing).

Real file names are only in the git-ignored `experiments/private_files.local.txt`, as comment
lines, so discovery is unaffected. Evidence:
[inventory.json](../experiments/out/book_intake/inventory.json), which holds IDs and counts
only. Probes: [book_intake_probe.py](../experiments/book_intake_probe.py) and
[book_intake_probe2.py](../experiments/book_intake_probe2.py).

**Disk:** 17 GB free before the step. Nothing was extracted or cached; the archive was read in
memory.

**Main finding.** The samples hold one usable pair and one mismatched pair:

- **JP:** one partial pair. Its XML covers only the front matter and chapter 1.
- **Deanta:** no usable pair. Its XML is a different book from both of its PDFs.

## Task 1: inventory

Two category folders: **Deanta** and **JP**.

| | `deanta_pdf_mideast` | `deanta_xml_canada` | `ent_textbook` |
|---|---|---|---|
| Category | Deanta | Deanta | JP |
| What it is | Country volume of a yearly world-affairs series | Another country volume of the same series | Medical (ENT) textbook |
| PDF found | Yes (Input). The archive's `pdfs/` folder holds the same book in 14 chapter parts (316 pp.) | **No.** Its archive PDFs are the other book | Yes |
| Reference XML found | **No** | Yes, inside the zip archive (the archive tests clean) | Yes: a master file, plus `front.xml` and `ch01.xml` |
| PDF pages | 317 (page labels Cover…310) | – | 612 (no page labels) |
| Encrypted / password | No / no | No (archive parts) | No / no |
| Pages with text / image only / little text | 310 / 1 / 6: born-digital | (archive parts: 310 / 3 / 3) | 605 / 0 / 7: born-digital |
| Language (Lingua, word share on a page sample) | eng 0.94 | – | eng 0.85; lat 0.07, probably Latin anatomical terms |
| XML root / doctype | – | `book`, DocBook 5 namespace, no doctype | `book`, no namespace, DocBook XML **V4.2** DTD |
| Page-marker convention | – | `<?page value="…"?>` PIs: 232 (8 roman), i…223 | Empty `anchor` with id `page<label>`: 24 `pageFM<n>` + 22 `page<n>` (1…22) |
| Existing dialect detected | – | `docbook` (same as book 2) | `docbook4-page-anchors` (same as book 4) |
| Reader | – | parses, no repairs | master parses, no repairs |
| Math | – | 0 | 0 |
| Tables | – | 3 informaltable | 4 table + 2 informaltable |
| Figures / images | – | 220 informalfigure, 234 mediaobject | 33 figure + 2 informalfigure, 37 imagedata |
| Lists | – | 0 (10 bibliolist with 576 bibliomixed entries) | 56 orderedlist + 130 itemizedlist |
| Footnotes | – | 0 | 4 |
| Sectioning | – | 2 part, 10 chapter, 100 section, 2 preface | 1 part, 1 chapter, 58 section, 6 preface |

### Problems

1. **Deanta: the XML does not match its PDF.**
   - XML: its metadata title, series subtitle and ISBN name one country volume. Its page
     markers end at 223.
   - Input PDF and archive PDFs: both print the ISBNs and title of another volume, and their
     folios run to 310.
   - The PDF file name carries a third ISBN.
   - The titles and ISBNs are in the private file.
   - So the Deanta folder holds no reference pair. The two PDFs are one book (the input PDF
     has one extra cover page).
2. **`ent_textbook` is a partial reference.**
   - The XML covers only the front matter (24 marker pages) and chapter 1 (pp. 1–22), which
     `page_info.xml` confirms. That is 46 of 612 PDF pages.
   - The image folders reach chapter 17, but there is no XML for chapters 2–17.
3. **`front.xml` is not well-formed** (unexpected end at line 1562). The master file holds
   the same front matter and parses, so the master is the reference.
   - `ch01.xml` alone parses, but detects as `docbook-like-fragments`.
4. **The JP `Output` folder is empty.**
5. **`ent_textbook` shares book 4's publisher and dialect.** It is a less independent
   hold-out than a book from another source.
6. **No new reference contains math** (0 math elements in either XML).

## Task 2: split (approved)

**Procedure, fixed before the draw:**

- Per category, take the usable pairs, sorted by ID.
- Draw `max(1, floor(n/3))` hold-outs with `random.Random(f"{seed}:{category}")`.
- Draw nothing when the category has no usable pair.
- **Seed: 20261012.**

| Category | Usable pairs | Hold-out (sealed) | Development | Note |
|---|---|---|---|---|
| Deanta | 0 | – | – | No matching pair (problem 1). Redraw with the same seed when a matching pair arrives |
| JP | 1 (`ent_textbook`, partial) | **`ent_textbook`** | – | n = 1, so the draw is forced |

Requirements:

- **Hold-out with tables:** met by `ent_textbook` (6 tables in the covered pages; a small
  sample).
- **Hold-out with math:** **not possible.** No new reference contains math.

Not in the split:

- `deanta_pdf_mideast` has no reference. It could serve later as an unlabelled robustness
  book (run without metrics) if you want.

## Task 3: dialects

**No new dialect.** Both XML files are detected by existing profiles, and the reader parses
them without repairs:

| Book | Dialect | Profile digest (unchanged) | Same as |
|---|---|---|---|
| `deanta_xml_canada` | `docbook` | `46c3aca9…8613` | book 2 (same page PIs, same naming) |
| `ent_textbook` | `docbook4-page-anchors` | `025950b4…9c93` | book 4 (same `page<label>` and `pageFM<n>` anchors) |

**Vocabulary observations (not a profile change):**

- Elements outside the common vocabulary: `qandaset`/`question`/`answer`, `footnote`,
  `blockquote`, `sidebar` and `epigraph`/`attribution`.
- All of them except `epigraph`/`attribution` already occur in book 2 or 4.
- They matter for the later footnote and question steps, not for dialect detection.

**Registration note:** `ent_textbook` numbers its front matter in its own series
(`pageFM<n>`). That is the existing `reference_own_front_numbering` case, so its body-page
label figure is the comparable one.

## Owner decisions (recorded in [decisions.md](decisions.md))

1. **`ent_textbook` is the sealed hold-out.**
   - Its evaluation is restricted to the 46 pages its reference covers: the front matter and
     chapter 1.
   - The pipeline may run all 612 pages for robustness only (no crash, ledger complete,
     I1–I7, timings), with no metrics on uncovered pages.
   - Results are labelled "small sample, same publisher as book 4".
   - It is not run in this step.
2. **`deanta_pdf_mideast` is an unlabelled robustness book:** no reference and no metrics;
   only no crash, ledger, invariants and timings.
   - `deanta_xml_canada` is not registered.
   - Deanta is redrawn with the same seed if a matching pair arrives.
3. **Math hold-out: open need.** You will supply a book with math in its reference XML before
   Step 13.
4. **Real paths** live in the git-ignored `experiments/references.local.toml`, for books 1–4
   too. The committed `references.toml` keeps keys only. Git history is not rewritten.

## Registration

- **Keys** (empty in `references.toml`, real paths in `references.local.toml`):
  - `ent_textbook_pdf` and `ent_textbook_xml`;
  - `mideast_pdf`.
- **Registry:** [registry.json](../experiments/out/book_intake/registry.json) records, per
  book:
  - the split;
  - the evaluation scope, and the robustness-only checks;
  - the result label;
  - the draw (seed and procedure);
  - the open math need.
- **Seal:** [holdout_runs.jsonl](../experiments/out/book_intake/holdout_runs.jsonl) has one
  `sealed` row for `ent_textbook`.
- **Not done yet:** the run scripts have no entry for the new books, so nothing can run them
  by accident. The step that first runs them adds the entries, with the page restriction.

**Resolution order** in [reference_paths.py](../experiments/reference_paths.py):

1. the `BOOK_CONVERTER_<KEY>` environment variable;
2. the sibling `<config stem>.local.toml`;
3. the committed config.

An empty value with no local path is an error, and so is an unknown key. Three new tests in
[test_reference_configuration.py](../backend/tests/test_reference_configuration.py) cover the
overlay, the errors, and a committed file that holds keys only.

**Not re-run:** the Step 6 rule audit (`step6_rule_audit.py`) treats `references.toml` as a
frozen Step 6 contract, so it would now report a diff. It is a historical audit and is not
re-run.

## Evidence that books 1–4 are unchanged

| Check | Result | Evidence |
|---|---|---|
| Every configured key (15) resolves to the same absolute path, with the same file SHA-256 and size | **identical** | [paths/](../experiments/out/book_intake/paths/): hashes only, no names |
| Step 11 evaluation re-run on books 1–4 vs the Step 11b `final` summaries | **identical** in all four books: every metric and the `cache_key_inputs` | [metrics_check.json](../experiments/out/book_intake/metrics_check.json) |
| Cache use in that re-run | structure and lists **hit** in all four books | same file |
| Cache directory listing (names and sizes) before the move vs after the re-runs | **identical**: 31,428 entries, none added | [paths/after_runs.json](../experiments/out/book_intake/paths/after_runs.json) |
| Probes re-run after formatting | same inventory | (scratch comparison) |

Notes:

- The comparison leaves out `seconds` and `cache_hit`, which are run state and not results.
- Book 3 (anecdotal) ran once for this check, logged in
  [runs.jsonl](../experiments/out/book_intake/runs.jsonl).

## Gates

| Gate | Result | Evidence |
|---|---|---|
| All tests | **844 passed**, 0 failed / 0 skipped (841 at Step 11b + 3 new path tests) | [JUnit](../experiments/out/book_intake/pytest.xml), [log](../experiments/out/book_intake/pytest.log) |
| 24 measured pages vs original sources | **0 missing / 0 extra** | [cross-check](../experiments/out/book_intake/gates/original_source_crosscheck.json) |
| Full book | **495,751** retained tokens (same as Step 11b); passing | [full_book.json](../experiments/out/book_intake/gates/full_book.json) |
| I1–I7 on 24 pages | **0 each**; every line ordered once | [invariants.json](../experiments/out/book_intake/gates/invariants.json) |
| Every line in exactly one unit; structure and lists stages on the one-page fixtures | pass | [gates/](../experiments/out/book_intake/gates/) |
| Ruff check / format, from backend/ (including the new experiments files) | pass | [ruff.log](../experiments/out/book_intake/ruff.log) |
| Disk | 17 GB free before and after; no cache entry added or deleted | `df`; cache listing above |

Gates: `python book_intake_gates.py` (the Step 11 gate suite, written to
`out/book_intake/gates`, so the Step 11b evidence is not overwritten).

**The book intake stops here for owner review. Step 12 has not started.**
