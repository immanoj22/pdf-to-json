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
| NIMAS 1.1 / DTBook 2005-3 | `_base/dtbook_nimas_base.yaml` | done |
| DAISY 3 (text-only) | `_base/daisy3_base.yaml` | done |
| JATS 1.4 | `_base/jats_base.yaml` | pending |
| BITS 2.2 | `_base/bits_base.yaml` | pending |

**Official schemas** (downloaded, licences checked, pinned by SHA-256, validated offline with
lxml; nothing installed): JATS 1.4 and BITS 2.2 (public domain), DTBook 2005-3 and the DAISY 3
NCX/resource/SMIL DTDs (DAISY Consortium / NISO), MathML 2 (W3C permissive), OEB 1.2 package DTD
(no licence text in the file: IDPF open standard, stored unmodified, used only to validate;
accepted by the owner 2026-11-04; recorded in `docs/dependencies.md`). See `backend/src/book_adapters/validate/dtds/README.md`.

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

## 2. NIMAS 1.1 / DTBook 2005-3

**Result on the 11 publications:** schema errors 0 on 11/11; **lossless missing/extra 0/0** on 11/11; two full runs **byte-identical** (folder and ZIP) on 11/11; QC verdict `warn` (none `fail`: True); rule findings by check (books affected): {'page_numbers': 9}. Numbers: `experiments/out/formats/dtbook.json`.

**Output.** `<isbn>_nimas/`: `<isbn>.xml` (DTBook), `<isbn>.opf` (NIMAS package, OEB 1.2 package
DTD), `images/`, and `<isbn>_titlecopyright.pdf` when the source PDF is given (the app always
gives it; on the command line it is listed as to supply). `frontmatter` (`doctitle`, `docauthor`,
copyright/ISBN `level1`, prefaces), `bodymatter`, `rearmatter`; `level1`-`level6` with `h1`-`h6`
(a deeper section heading is a `bridgehead`, reported, never a skipped level); `pagenum` with
`page="front|normal"` and the printed label; `imggroup` / `img alt` / `caption` / `prodnote`
(text inside figures); `note`; `sidebar render=optional`; `list type=ul|ol|pl`; `dl`; tables with
`th scope`; MathML through the DAISY MathML module (MathML 2 DTD, `m:math` with `alttext`).
The title/copyright PDF is cut with pypdfium2 (Apache-2.0/BSD-3), not PyMuPDF; its date and ID are
fixed so reruns are byte-identical.

**Checks** (files re-read from disk): DTBook DTD with the MathML module, the OPF against the OEB
1.2 package DTD (both offline, pinned); links resolve, images exist with `alt`, `pagenum`
complete and in order with the printed label, required metadata (`dc:Title`, `dtb:uid`,
`dc:Language`), manifest files exist and list every image, lossless.

**Required NIMAS metadata that the PDF does not give is listed, never invented** (review entries
`must check`): `dc:Publisher`, `dc:Date`, `dc:Rights`, `dc:Source` (ISBN), `nimas-SourceEdition`,
the title/copyright PDF. Book settings / the app's Book details supply `publisher`,
`publication_date`, `rights`, `isbn`, `edition`.

**Mapping choices the standard leaves open** (profile `dtbook`, default in brackets):
part nesting (`nested`: chapters are `level2` of a part `level1`; `flat` keeps depth for sections),
deepest level (6), `sidebar_render` (`optional`), publisher/rights/language, the NIMAS file names
and `dc:Format` ("NIMAS 1.1"), which converter sections make the title/copyright PDF
(`title_page`, `copyright`). Fixed: `dtb:uid` is the ISBN, else a content hash; alt text only in
`img alt`; a footnote is a `note` in place (no `noteref`: the source has no link from a mark to
its note); labels the profile derives ("Fig. 1") are `span class="label"` and not source text;
an index entry is a `list type="pl"` item (`ie1`/`ie2`/`ie3`) with its page numbers linked.

## 3. DAISY 3 (text-only digital talking book)

**Result on the 11 publications:** schema errors 0 on 11/11; **lossless missing/extra 0/0** on 11/11; two full runs **byte-identical** (folder and ZIP) on 11/11; QC verdict `warn` (none `fail`: True); rule findings by check (books affected): {'page_numbers': 9}. Numbers: `experiments/out/formats/daisy3.json`.

**Standard followed.** ANSI/NISO Z39.86-2005: DTBook 2005-3, NCX 2005-1, DTB SMIL 2005-2,
resource file 2005-1, package file = OEB 1.2 package DTD (all from the official pinned DTDs).
The specification (read from daisy.org) requires at least one SMIL file even for a text-only
book (section 7.4.10) and allows only SMIL files in the spine (3.4), so those are written.

**Files.** `<isbn>.xml` (the DTBook file; every heading, paragraph, list item, caption, page
number and note has an `id` and a `smilref`), `<isbn>_NNN.smil` (one per top-level division, a
`par` with a `text src` for each synchronized element; `customTest` for page numbers and notes),
`<isbn>.ncx` (`navMap` from the level/heading structure with `playOrder`, `pageList` from the
page numbers with `type` front/normal and `value`, `dtb:depth`, `dtb:totalPageCount`,
`dtb:maxPageNumber`), `<isbn>.res` (resource file; optional in the standard, on by default),
`<isbn>.opf` (`dtb:multimediaType` = `textNCX`, `dtb:multimediaContent`, `dc:Format` =
"ANSI/NISO Z39.86-2005", manifest of every file including itself, spine = SMIL files), images.

**Checks.** Every file against its official DTD; NCX `content` -> SMIL `par` -> DTBook `id`;
every synchronized element is in a SMIL; `playOrder` unique and ascending; page list lists every
`pagenum`; `dtb:depth` and `dtb:totalPageCount` match; manifest complete, spine only SMIL;
plus the DTBook checks and lossless. **No DAISY Pipeline or other validator was installed**
(licence question not raised; the official DTDs are the validators).

**Mapping choices** (profile `daisy3`): everything the DTBook has (parts, depth, sidebar render,
MathML), file names, SMIL split (`level1`: one per top-level division; `single`), NCX page-list
label, resource file on/off and its labels ("Page", "Note", ...). Required `dc:Publisher` and
`dc:Date` missing from the settings are listed as to supply.
