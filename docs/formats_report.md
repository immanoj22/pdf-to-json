# More output formats — HTML, NIMAS/DTBook, DAISY 3, JATS, BITS

Status: **in progress** (HTML done; the other sections are added as each format is committed).
No Stage 1 (`book_core`) change, no Docker. Branch `formats` (worktree), built on main with the
ePub step (d00e37e6).

## Summary

**What it is.** Five new writers on the existing adapter engine, each with a standard base
profile in `profiles/_base/` that client profiles can `extend`. They share one content pass:
the DocBook writer's passes (outline, ids and numbering, characters, links, review-decisions
overlay, alt-text rule, emission ledger) run unchanged, and a format transformer moves the
already-written text into the format's tags. Text is never copied or changed there, so the
lossless guarantee carries over. A profile chooses its formats with `formats:` (or has the
format's section); every format choice is a profile field (`profile.schema.json`, sections
`html`, `dtbook`, `daisy3`, `jats`, `bits`; existing profiles stay valid).

Run one: `book-adapters run BOOK --out DIR --profile html_base --format html`
(`--format dtbook|daisy3|jats|bits` for the others). Each run writes the delivery folder, its
ZIP and `report/` (QC report, review list), and fails while alt-text placeholders remain
unless the recorded override is given.

| Format | Base profile | Status |
|---|---|---|
| HTML5 | `_base/html_base.yaml` | done |
| NIMAS 1.1 / DTBook 2005-3 | `_base/dtbook_nimas_base.yaml` | see below when committed |
| DAISY 3 (text-only) | `_base/daisy3_base.yaml` | pending |
| JATS 1.4 | `_base/jats_base.yaml` | pending |
| BITS 2.2 | `_base/bits_base.yaml` | pending |

**Official schemas** (downloaded, licences checked, pinned by SHA-256, validated offline with
lxml; nothing installed): JATS 1.4 and BITS 2.2 (public domain), DTBook 2005-3 and the DAISY 3
NCX/resource/SMIL DTDs (DAISY Consortium / NISO), MathML 2 (W3C permissive), OEB 1.2 package DTD
(no licence text in the file: IDPF open standard, stored unmodified, used only to validate;
**owner to confirm**). See `backend/src/book_adapters/validate/dtds/README.md`.

## 1. HTML5

**Result on the 11 publications** (8 Step 20 + Dermatology, cancer biology, RSSDI Atlas):
schema/syntax errors 0, **lossless missing/extra 0/0**, two full runs **byte-identical** (folder
and ZIP) on all 11, QC verdict `warn` on all (alt-text override, must-check items, one rule
finding below), none `fail`. Numbers: `experiments/out/formats/html.json`.

**Output.** `<isbn>_html/`: `index.html` (contents, page list), `title.html`, `copyright.html`,
one page per division (`ch3.html`, `preface1.html`, `book-index.html`, ...), `style.css`,
`images/`. Headings, lists, tables (`caption`, `th scope`), figures (`figure`/`figcaption`,
`alt`), MathML (with `alttext`), page breaks as `span role="doc-pagebreak"` with the printed
label, notes, `lang`. The element conversion is the ePub writer's (same hosts, same ledger); this
writer sets the file layout from the profile's `html` section and writes HTML syntax.

**Checks** (`validate/html_checks.py`, on the files re-read from disk): strict HTML5 reader
(void elements, matching end tags, quoted attributes), doctype/lang/title/h1 per page, unique
ids, internal links resolve to a file and an id, images exist and have `alt`, no skipped heading
level, `th` has `scope`, page-break marks complete and in order, contents page links every
division page, style sheets exist, lossless. No external HTML validator was installed (the
owner asked to be consulted first); the checks above are our own.

**Findings.** One rule finding on 9 of 11 books: *page-break marks out of order* (for ART: the
mark of page 23 is written after page 27's). It comes from the DocBook writer's page-anchor
flushing and is identical in the DocBook delivery; it is reported, not hidden. Spanish and
medical anatomy also have one page without a main heading.

**Mapping choices the standard leaves open** (profile `html`, defaults in brackets): file names
(`{id}.html`, `{kind}{n}.html`, `index.html`, `book-index.html`), style sheets (`default_html.css`),
link colour (inherit), contents depth (3), page list on the contents page (on), MathML as MathML
(on), page labels (title/copyright regions). Fixed: one page per division; parts get their own
page; a footnote is an `aside` in place (the source has no link from a reference mark to its
note); text inside figures follows `figures.embedded_text`.

**Not in the profile yet** (fixed behaviour, listed for the owner): heading level of sidebars,
`b`/`i` rather than `strong`/`em` (the ePub writer's choice).
