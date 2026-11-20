# Tail reference XML (`tail`)

The Elsevier/Scopus-style reference list (`<tail><bibliography refcount="N"><reference seq="n">…`,
`ce:` prefix) made from a numbered reference list. Two sources:

* **References only** (document type chosen on the Profile step): the whole PDF is one reference
  list. The converter is told the bibliography is every page (`book_parts`), so no chapter or
  heading is looked for; the profile is `tail`.
* **A full book**: every profile can export `tail`; it holds the entries of every bibliography
  the book has, one reference per entry.

## What is written

* Exact tag order of the client's sample (`ref-title`, `itemidlist`, `ref-authors`,
  `ref-sourcetitle`, `ref-publicationyear`, `volisspag`, `ref-website`, `ref-text`,
  `ref-fulltext`, `ce:source-text`); CRLF line ends; pure ASCII with uppercase 5-digit
  hexadecimal entities (`&#x000E9;`), `&` written `&#x00026;`; `refcount` = the references written.
* The `ce:` prefix is written without a declaration, as in the sample (read in memory with the
  prefix declared).
* Accent mode (profile `tail.accents`, or the book option `accents` on the details page):
  `sample-mapping` (default, copies the sample), `keep`, `strip`.

## Rules (Vancouver / numbered style)

Numbering `[n]` (or `n.` read as the run 1, 2, 3 …); initials `DJ` → `D.J.`; `et al` →
`<et-al/>`; the title ends at the first full stop (or `?`/`!`), the rest of that sentence is the
source; the last page is completed (`311-35` → 335); `E239-53` → item id `e239-e253`; other letter
pages stay pages (`C185-92` → C185 / C192); the address in `[ ]` → `ref-website`; `[PMID: n]` →
`ref-text`; running headers (a line, digits removed, that repeats on many pages) and lone page
numbers are left out; a hyphen at a line end keeps the hyphen. Nothing is looked up or guessed.

## Uncertain references

A reference that does not fit the journal pattern (a book, a web page, no authors, no pages, a
title cut at an inner full stop, no full stop between title and journal) is written best-effort
and is a **review item** (kind `reference`) on its unit and page. The review card offers
"Yes, it's right" or "Correct the text…"; Browse has the same under Edit → "Correct the text…"
(operation `edit_text`, in the audit log, undoable). After a change, Refresh makes the review
list again and the file follows the corrected text. A gap or repeat in the numbers is a
`must_check` item.

## Lossless

Every word of the source is written once in a reference or omitted with a reason (`running header`,
`page number`, `text outside the reference list`): QC reports 0 missing / 0 extra, and the words of
every `ref-fulltext` equal the ledger. Accent mapping is counted as character changes.

## Use

App: Profile step → Document type **References only** (the `tail` profile is chosen for you) →
Convert → Reference list options (accents) → Review → Export (`tail`). Command line:

```
python -m book_core run-book ref.pdf --out out --cache-dir cache --parts parts.json   # parts: bibliography = every page
python -m book_adapters run out/book-<key> --out tail_out --profile tail --format tail
```
