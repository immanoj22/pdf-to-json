# Step 5, Part 1: reference inventory

Scope: every PDF/XML file under the paths and folders listed in `experiments/references.toml`:
the configured files, `downloads` (including ZIP members), `old_root`, `legacy_upgrade` and
`old_original`. The first draft also walked the whole old converter tree around `old_original`;
on owner instruction, discovery is now limited to the listed folders. Everything was read-only,
and malformed XML was repaired in memory only. **85 unique XMLs and 64 unique PDFs** (by SHA-256)
were found. Files named in a git-ignored local list are skipped entirely: they are not opened,
hashed or listed. Raw evidence: [inventory.json](../experiments/out/step5/inventory.json),
produced by [step5_inventory.py](../experiments/step5_inventory.py).

**Method.** Tokens use the benchmark tokenizer (case-sensitive NFKC `[\p{L}\p{M}\p{N}]+`).
XML tokens come from element text only, with attributes excluded. PDF tokens are retained native
lines, by TrimBox centre, read through the Extractor. Each XML was scored against every distinct
source PDF. Where an XML has page markers (DTBook `pagenum`, DocBook `<?page?>`), each marker's
text segment was placed on a PDF page by rare-token votes (document frequency <= 3). That gives
three checks: order monotonicity, the page offset, and whether the marker's printed folio appears
as a token on the matched page.

## Verdicts

| # | Book (PDF) | Pages | XML | Dialect | Origin | Pairing evidence | Verdict |
|---|---|---:|---|---|---|---|---|
| 1 | Spanish US history `9781264958665-Binder1.pdf` | 758 | `C:/9781264958665NIMAS.xml` | DTBook 2005-3 (NIMAS) | Independent: publisher NIMAS ids and DOCTYPE | 99.18% of XML tokens in PDF; 95.33% of PDF tokens in XML. 758 `pagenum` = 758 pages; 755 placed; folio on matched page 93.8%; median page overlap 1.00 | **Usable** (see caveats) |
| 2 | Immigrant Children `9798216208693_web.pdf` | 331 | `9798216495130_txt_xml.xml` | DocBook 5 (Bloomsbury schema) | Independent: oXygen/Bloomsbury schema PIs, DOI, editorial `xml:id`s | 98.36% / 91.03%. 309 `<?page?>` markers; 292 placed; offset +1 for 285; monotonic 99.7%; folio on page 99.0%; median overlap 0.98 | **Usable** |
| 3 | Art-therapy index `docbook index input.pdf` | 9 | `docbook index output.xml` | DocBook index fragments, two top-level roots | Independent (supplied sample) | 97.60% / 98.63%. 9 markers for 9 pages (280-288), but only 4 segments placeable, median overlap 0.24 | **Usable for text, index structure and order; page markers low confidence** |
| 4 | US-history Tema 1 `T01.pdf` (ZIP, two old profiles) | 86 | `T01.xml` (ZIP and three profile copies, one hash) | DTBook body without root/namespace | Independent: NIMAS9781264958665 ids | 99.30% / 95.62%; 86/86 placed, offset 0, folio 97.7%. **The PDF is pages 25-110 of book 1 (100% token containment), and the XML is 100% contained in the NIMAS XML** | **Duplicate of 1**: same book, count once |
| 5 | `9781264958665-Binder1-1-300.pdf` and `(1)` | 300 | No own reference (NIMAS covers it) | - | - | Contains 98.86% of its tokens in NIMAS; it is pages 1-300 of book 1 | **Duplicate of 1** |
| 6 | World-history Tema 1 `T01.pdf` (Downloads, `t01` profile) | 48 | `t01` profile `source.xml` (= the US-history `T01.xml`) | - | - | 41.56% / 65.03%; monotonic 31%; folio 8% | **Mismatched**: excluded |
| 7 | Alabama Physical Science `9781266828829-Binder1.pdf` | 729 | `book (7)/(9)/(10)/(11).xml` and 15 more | DTBook-like fragments | **Generated** by the old backend (`src-yaml-*` / `generated-*` ids) | 99%+ token overlap is expected: these XMLs were produced from this PDF | **Generated**: no independent reference |
| 8 | Canadian Historical Review Index `9780802027962.pdf` | 326 | `book (6).xml` | Internal profile, no namespace | **Generated** (`profile="internal-standard"`) | - | **Generated**: no independent reference |

### Everything else (all generated or not a reference)

| Family | Unique XMLs (locations) | Evidence |
|---|---:|---|
| Book 1 outputs of the old backend (`C:/book (13).xml`, `book (12).xml`, `nimasbook.xml`, 22 `checks/reference-758-*` variants, binder-v2) | 25 (44) | `src-yaml-*` / `generated-*` ids |
| Book 1 excerpt outputs (300-page `book (13).xml`, 30-page and 8-page checks, T01 86/48 benchmarks and checks) | 14 (20) | Same old-backend id families |
| Immigrant Children outputs (`book.xml`, `book (1)-(4)`, `(8)`, checks) | 11 (26) | ElementTree `ns0:` serialisation, `src-yaml-*` ids |
| Physical Science outputs | 19 (33) | Old-backend id families |
| Canadian and art-index outputs (`book (6).xml`, `book (5).xml`) | 2 (2) | `internal-standard` profile |
| `xml2xml-app (2).zip` output `body-output-list-separation.xml` | 1 | Bloomsbury schema PIs, but title "Input File" and zeroed `xml:id`s: a transformed derivative |
| Non-book XML (junit suites, IDE settings) | 7 | No usable book text |
| Derived copies of the NIMAS reference (`reference-header-corrected.xml`, `reference-comparison-local-names.xml`) | 2 | Same 476,525 tokens as the original; old-project repairs. **Do not use**: the original plus in-memory repair is the evidence |

Non-source PDFs: XML-debug renders (`book.pdf` 508 pages, `book (2).pdf` 570, `9798216495130_txt_xml.pdf` 1469), the Bloomsbury specification (293), `result book.pdf` (244, an Immigrant Children reconstruction), and old one- to three-page test or upload PDFs. None has an independent XML.

## Caveats that affect Part 2

1. **Book 1's XML is not in PDF page order.** It places PDF pages 723-758 (`pagenum` HT1-HT36) inside the front matter, after page xxii, and moves the `special` pages to the end. Three apparent single-page outliers (labels 327, 477, 517) were **not** real moves. Each
   segment lies fully on its own page (label + 24 = PDF 351, 501, 541; containment 100%, 100%,
   97%). These are short unit-opener pages, mostly one photo caption, and the same captions are
   reprinted on the table-of-contents pages (p11, p13). The diagnostic's independent rare-token
   argmax picked the reprint. Consequence for the aligner: place segments with a monotonic
   page-range pass, and treat a token as an anchor only when it is unique within the window. The aligner therefore needs anchored, piecewise-monotonic alignment with block transpositions, not one global monotonic pass. The XML sequence becomes the reference unit order, as the brief asks.
2. **Book 1's XML is malformed** (doubled quote delimiters in lines 2-3). It parses only with the recorded in-memory repair, consistent with Phase 0 decision 2 (pending approval).
3. **Book 1 coverage gap:** 4.67% of PDF tokens are absent from the XML. Furniture accounts for at least 4,929 of these tokens (about 1%); the rest are expected to be image or map text and omissions. Part 2 will classify them by cause.
4. **Book 2 identity** rests on content, not ISBN. The XML lists paperback, epub and XML ISBNs, but not the web-PDF ISBN 979-8-216-20869-3. Twelve PDF pages have no native text, so their XML text will be unaligned with cause "no native PDF text"; no OCR is involved.
5. **Book 3 page markers** do not delimit page content in the XML: index entries are restructured across the PIs. Page-marker derived gold from book 3 will carry low confidence.

## Proposed hold-out plan (by book)

There are only **three independent books**. Rows 4 and 5 are book 1.

| Split | Books | Use |
|---|---|---|
| Development | **1** Spanish US history (758), including the T01 and 300-page excerpts | Aligner design and tuning; derived-gold inspection; the existing hand-gold fixtures already come from this book |
| Hold-out A | **2** Immigrant Children (331, DocBook, English, academic) | Never used to tune the aligner or any stage. The aligner runs once on it; coverage is reported. Any later aligner change made after seeing these results is logged as hold-out contamination |
| Hold-out B | **3** Art-therapy index (9, DocBook fragments) | Same rule; index-genre check only |
| No reference | Physical Science (729), Canadian index (326), World-history T01 (48) | No derived gold; PDF-only gates (ledger and layout) as before |

## Decisions for you

1. Approve the usable set: **books 1, 2 and 3**, with rows 4 and 5 folded into book 1. Row 6 stays excluded; rows 7 and 8 have generated XML only.
2. Approve the hold-out split above, or choose leave-one-book-out instead. With only three books, the alternative is cheap, but book 3 is very small.
3. Confirm the in-memory repair of book 1's XML header (no corrected copy is ever written).
4. Book 3 page markers: derive page-marker gold with low confidence, or skip page-marker gold for book 3.

## Owner decisions (approved after Part 1)

1. Usable set: books 1, 2 and 3, with the excerpts counted as book 1. Book 2 is marked
   "identity by text only".
2. Hold-out: tune on book 1 only. Books 2 and 3 run once; every aligner change made after
   that is logged. Book 3 (9 pages) is reported as anecdotal.
3. The in-memory header repair is accepted: the original file is never modified and no corrected
   copy is written. The repair is a deterministic, documented function with a test, and each
   repair is recorded in the output. A pair is excluded if a repair would change text or order.
   The original NIMAS file is used, not the old project's repaired copies.
4. Book 3 page markers are derived at low confidence and excluded from gates.
