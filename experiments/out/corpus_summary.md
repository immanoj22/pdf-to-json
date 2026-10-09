# Corpus audit notes

Inventory and hashes: `experiments/out/corpus_inventory.json`. Source files were read only. Types below are supported by title/front-matter inspection; generated XML is never treated as an independent answer.

| Source PDF | Pages | Type | XML association and confidence |
|---|---:|---|---|
| `C:/9781264958665-Binder1.pdf` (same SHA as Downloads copy) | 758 | Born-digital Spanish US-history textbook; multi-column, maps, worksheets, colored boxes | Supplied `C:/9781264958665NIMAS.xml` (758 pagenums), independently matching title. Original malformed delimiter quotes only in opening lines 2–3; inspection repair performed only in memory. `C:/book (13).xml`, Downloads `book (12).xml`, `nimasbook.xml` are generated variants. |
| Downloads `9781264958665-Binder1-1-300.pdf` and `(1)` | 300 each | Identical first-300-page excerpts of preceding book | Downloads `book (13).xml` is a partial generated variant; distinct from full `C:/book (13).xml`. No independent 300-page answer located. |
| Downloads `9781266828829-Binder1.pdf` | 729 | Alabama Physical Science textbook; composite diagrams, colored teaching boxes | Downloads `book (7).xml`, `(9)`, `(10)`, `(11)` identify this book but are generated variants. No independent publisher answer located. |
| Downloads `9798216208693_web.pdf` | 331 | Immigrant Children; academic social-science volume with tables, references and indexes; digital text plus scanned/blank pages | Supplied manual DocBook `9798216495130_txt_xml.xml`; title/author identity and old audit establish this pairing. Downloads `book.xml`, `(1)`, `(2)`, `(3)`, `(4)`, `(8)` are generated variants. |
| Downloads `9780802027962.pdf` | 326 | Canadian Historical Review Index, volumes LII–LXXI 1971–1990; scanned with text/OCR layer, dense indexes | Downloads `book (6).xml` is a generated output. No independent publisher answer located. |
| Downloads `docbook xml index sample/docbook index input.pdf` | 9 | Art-therapy subject/author index excerpt, printed 280–288; multi-column born-digital | Supplied `docbook index output.xml` contains two top-level index fragments. Wrapped only in memory for inspection. Downloads `book (5).xml` is generated; it is not the answer for the 331-page Immigrant Children book. |
| `nimas-example` / `samble-book-xml` profile `source.pdf` | 86 each | Duplicate excerpts of US-history Tema 1, La creación de una nueva nación | Both `source.xml` files are identical, contain 86 pagenums and matching heading. The PDFs are also identical; count once. Profile filename `T01.pdf` is ambiguous. |
| Downloads `T01.pdf` and profile `t01/source.pdf` | 48 | World-history Tema 1, El mundo antes de los tiempos modernos | **Mismatched** to profile `t01/source.xml`, which is the same 86-page US-history XML above. Exclude this pair from reference scoring. |

Additional PDFs are derived artifacts, not new source books: `book.pdf` (508 pages), `book (2).pdf` (570), `9798216495130_txt_xml.pdf` (1469) display XML attribute/layout debugging; `result book.pdf` (244) is a reconstructed Immigrant Children output; the Bloomsbury specification (293) is a rule reference.

Synthetic versus reference corpus: old `examples/sample.pdf` is a three-page deterministic smoke book; Spanish smoke scan is one synthetic page; independent science page-34 table fixture is one diagnostic page; Binder first-30 PDF is a 30-page excerpt. The `source_regions` corpus has seven normalized real pages plus one synthetic negative-control page. Its generated XML goldens prove compatibility of `source_book -> arrange_roles -> generate`; they intentionally skip PDF extraction/table reconstruction and do not prove semantic correctness.

Measured native text availability (`corpus_source_text_modes.json`): Canadian index 1/326 pages without native text and 8/first10 pages with raster covering >75% of page; Immigrant Children 12/331 without native text and 1/first10 with such raster; art-therapy index 0/9 without native text and no such raster. Missing native text includes blank pages, so this count is not an OCR requirement count.

Science fixtures visually verified:

| PDF page (printed) | Image placements | Semantic visual structure |
|---|---:|---|
| 527 (510) | 853 | Figure 8 nuclear-fission diagram and Figure 9 branching chain reaction, built from many individual atom/neutron images plus labels/caption/legend. Main prose occupies the upper-left lane; figure/caption lanes are separate semantic regions. |
| 546 (529) | 811 | One Figure 16, dissolving sugar in water, spans three stacked molecular panels and Step 1/2/3 labels. This is one composite figure; 811 placements are not 811 figures. Main prose is one left column; the right lane is the figure. |

Verified 331-page old extraction cache: `C:/coeik/projects/pdf to xml converter/output/web-jobs/c5ef0798c0114484ab8f5cb73254306f/result/book.json` (32,979,309 bytes). `pages[*].blocks` preserves text, styles, bbox, spans, exclusion and provenance. It includes `offline_ocr` content on scanned pages; direct native extraction comparisons must distinguish this from source-native completeness. Matching source hash is `4825a40c9905048df0cee7eb173802438e5c7b71fe2d768255dc09314baa593f`.
