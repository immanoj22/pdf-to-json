# Old-project audit evidence (read-only, 2026-10-08)

Old source, staging evidence and deployed application were only read. No old tests/services were run and no old file was changed. Saved artifacts were independently parsed with Python `-B` and lxml; this is artifact rechecking, not rerunning conversion or visually inspecting every page. No `.git` entry was found at the inspected original/staging/deployed project roots.

## Locations, structure, entry points

| Location | Role / entry points | Dependencies |
|---|---|---|
| `C:/coeik/projects/pdf to xml converter/pdf_to_xml` | Original offline package: input, preprocessing/OCR, extraction, layout, analysis, classification, models, rules, XML output, review. `python -m pdf_to_xml`; `pdf-to-xml = pdf_to_xml.main:main`; Flask web via `pdf-to-xml-web = pdf_to_xml.web:main`. | Python >=3.12; PyMuPDF >=1.26,<2; lxml >=6,<7; PyYAML >=6,<7; Flask >=3.1,<4; pytest; optional rnc2rng. |
| `C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade` | Later staging application, diagnostic scripts and historical `checks/`; includes deployment plans/applied records. | FastAPI application family; native extraction, semantic detection and YAML/learned rules. |
| `C:/coeik/projects/nimas/book_xml_backend` | Deployed application reports version `0.5.0rc2`. `uvicorn app.main:app`; `python -m app.cli train/convert/score`; API profile learning/conversions; jobs, storage, extraction, analysis/layout, structure detection, validation and output packages. | Python >=3.12; FastAPI, uvicorn, pydantic/settings, python-multipart, PyMuPDF, lxml, PyYAML, RapidFuzz, regex; pytest/httpx/ruff. |
| `C:/coeik/projects/nimas/book_xml_frontend` | React/TypeScript Vite UI; `src/main.tsx` -> `App.tsx`; `npm run dev/build/test`; Playwright tests. | React/React DOM ^19.2; lucide-react ^0.468; Vite ^7; TypeScript ^5.9; Playwright ^1.56. |

Evidence: [original pyproject](<C:/coeik/projects/pdf to xml converter/pyproject.toml:6>), [original README](<C:/coeik/projects/pdf to xml converter/README.md:79>), [backend pyproject](C:/coeik/projects/nimas/book_xml_backend/pyproject.toml:6), [API entry](C:/coeik/projects/nimas/book_xml_backend/app/main.py:39), [CLI](C:/coeik/projects/nimas/book_xml_backend/app/cli.py:28), [version](C:/coeik/projects/nimas/book_xml_backend/app/__init__.py:1), [frontend manifest](C:/coeik/projects/nimas/book_xml_frontend/package.json:6).

Do not infer that historical 0.4.3/0.4.5 measurements describe every later 0.5.0rc2 behavior. The original package's architecture is not a recommended starting point.

## Exact meaning of 495,751 tokens

**The benchmark is AFTER explicit TrimBox/print-frame exclusions, but BEFORE removal of headers, footers or page numbers: page furniture is included.** It is conservation of already extracted text, not visual/OCR completeness.

1. Build expected text from all source lines except IDs in the explicit exclusions list. Current saved 758-page validation has 92,228 source lines, 7,194 exclusions, all with reason `Outside explicit PDF TrimBox; retained in raw evidence.` This leaves 85,034 retained nonblank source lines.
2. Normalize only the comparison copy with case-sensitive Unicode NFKC. Count regex `[\p{L}\p{M}\p{N}]+` runs using a `Counter`; punctuation and whitespace separate tokens. Compare multisets using intersection, missing, novel and excess repetition counts. Order is explicitly unchecked.
3. Expected/output are both 495,751, zero missing/extra occurrences. Furniture restoration explicitly keeps printed running headers and folios in source/output text. Independently parsed baseline and corrected XML both contain 1,375 furniture-role nodes totaling 4,929 such normalized tokens.
4. Separate diagnostics assign traced own-text to source pages and avoid double counting nested containers. They also check character counters; token totals alone permit mixed columns and split paragraphs.

Evidence: [token implementation](C:/coeik/projects/nimas/book_xml_backend/app/validation/preservation.py:8), [source construction](C:/coeik/projects/nimas/book_xml_backend/app/services/yaml_conversion_service.py:152), [explicit furniture restoration](C:/coeik/projects/nimas/book_xml_backend/app/structure_detection/adapter.py:701), [historical benchmark source construction](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/scripts/check_context_structure.py:142>), [independent page accounting](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/scripts/evaluate_structural_output.py:116>), [saved corrected validation](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-regions-flow-fixed/output/validation.json>), [saved historical report](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-cell-emission-043/report.json>).

Historical cache caveat: the release-042 document says an independent fresh-native audit found two missing and four excess cached occurrences. Therefore equal cached token counts should not be treated as a perfect extractor ground truth. [Evidence](C:/coeik/projects/nimas/book_xml_backend/docs/structure-release-042.md:41).

Exact reusable per-page extraction evidence is under `C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-regions-flow-fixed/output/normalized/pages/`; filter using that output's validation exclusions for like-for-like benchmark comparison. The corresponding raw pages and extracted model preserve evidence before semantic reconstruction.

## Specifically requested failures: independently rechecked saved output

Baseline = `checks/release043-baseline-evaluation`; corrected = `checks/reference-758-regions-flow-fixed/output`, both under staging root above.

| Check | Historical baseline | Corrected 0.4.5 saved output |
|---|---|---|
| Columns, physical page 26 | Paragraph-start trace positions: Según 2, En este relato 5, Los miembros 20, Los ideales 3, La confederación 4, Gobernantes 7: columns interleave. | Positions 2,3,5,6,7,8: requested prose anchors in source flow order. |
| Columns, physical page 100 | Top-right `de la guerra de Independencia...` is first traced node; left `La Unión siguió venciendo...` at 26, after `La victoria del Norte...` at 25. | Left at 13; continuation belongs to complete paragraph starting `El 31 de enero de 1865...` at 15; `La victoria...` at 19. |
| Gobernantes paragraph | Opening `<p>` is truncated after `la estructura`; five prose fragments listed in old audit, interrupted by unrelated content. | One complete `<p>`, from Gobernantes through `los iroqueses:`, owns five source blocks. |
| Furniture in lists | 140 header/footer/page-number nodes under `list` or `li`; original narrower header/footer-only audit counted 55. | Zero; all 1,375 furniture nodes retained. |
| Authors / Biografías / Mapas | All exact labels emit `<p>`. | All emit `<h1>`. |
| Reference tables | Saved comparison confirms 52/71 matched, 44 same row/cell-count shapes, eight shape differences. | Saved comparison confirms 65/71 matched; 56 same shapes, nine shape differences. Detailed categories: 40 exact compared-cell wording/tags/spans, 16 same-shape cell differences, nine shape differences, six unmatched. |

Evidence: [old audit](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/book12-audit-20261006/AUDIT.md:48>), [baseline saved independent checks](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/release043-baseline-evaluation/independent-structure-checks.json>), [corrected independent checks](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-regions-flow-fixed/output/independent-structure-checks.json>), [explicit opt-in regression assertions](C:/coeik/projects/nimas/book_xml_backend/tests/test_reference_structural_examples.py:40), [historical comparison](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-cell-emission-043/reference-comparison.json>), [corrected comparison](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-regions-flow-fixed/output/reference-comparison.json>).

Eight historical matched-table mismatches rechecked from JSON:

| Physical page | Reference/output rows | Recorded explanation |
|---|---|---|
| 79 | 4/7 | Paired ruled writing subrows collapsed by reference. |
| 91 | 7/8 | PDF has A–G; reference omits printed row E. |
| 97 | 13/12 | Reference citation inside merged row; printed citation below grid. |
| 139 | 3/2 | Reference inserts two blank rows into one unruled response area. |
| 283 | 3/4 | Printed three blank writing rows vs reference two. |
| 295 | 2/3 | Table title as output merged first row vs reference caption. |
| 613 | 7/10 | Printed writing subrows grouped differently by reference. |
| 754 | 9/9 | Different title/header/citation row shape despite equal row count. |

These are not eight demonstrated token-loss failures. Explanations are documented inspection notes, not newly visually reproduced in this audit. [Evidence notes](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/scripts/report_reference_tables.py:60>).

Remaining documented limits: six unmatched diagram/map/timeline/unaligned-atlas table structures; cross-page paragraph policy; uncertain figure ownership and descriptions; complex TOC/definition roles; no governing publisher schema. Physical Science 729-page book has 354 native U+FFFD glyphs at physical page 641; recovery was deliberately disabled because rawdict and texttrace positions disagree. Mixed pages with native text are not automatically OCRed, so image text can remain unrecognized. [Table account](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/checks/reference-758-regions-flow-fixed/output/TABLES.md>), [glyph limit](C:/coeik/projects/nimas/book_xml_backend/docs/structure-release-043.md:124), [OCR policy](C:/coeik/projects/nimas/book_xml_backend/README.md:208).

## Useful evidence and tests to carry forward, not architecture

- Native unsorted dict/rawdict extraction; fonts, sizes, colors, bboxes, optional character evidence; raw images/drawings/links/annotations; rotation/crop/TrimBox provenance. Keep original spans and source hashes, and compare extractor output to raw evidence. [Extractor](C:/coeik/projects/nimas/book_xml_backend/app/extraction/pymupdf.py:62), [audit/determinism/Unicode tests](C:/coeik/projects/nimas/book_xml_backend/tests/test_extraction.py:26).
- Unicode token counter plus independently attributed per-page text/character accounting; source-line coverage and semantic ownership checks. Preserve tests that reject silent missing lines, unknown glyphs, duplicate ownership and table-cell migration even when global words match. [Quality tests](C:/coeik/projects/nimas/book_xml_backend/tests/test_production_quality.py:44), [table XML checks](C:/coeik/projects/nimas/book_xml_backend/tests/test_xml_table_integrity.py:120).
- Fixtures/test expectations for 2/3-column flows, spanning artwork, complete multilingual prose, soft-wrap hyphen preservation, list furniture boundaries and composite figures. These are supported-case evidence, not universal accuracy. [Flow tests](C:/coeik/projects/nimas/book_xml_backend/tests/test_supported_flows.py:50), [paragraph text policy](C:/coeik/projects/nimas/book_xml_backend/tests/test_paragraph_text_policy.py:15), [composite figure tests](C:/coeik/projects/nimas/book_xml_backend/tests/test_figure_regions.py:55), [furniture tests](C:/coeik/projects/nimas/book_xml_backend/tests/test_list_furniture_boundaries.py:209).

## Fixture suggestions for visual confirmation by root

Source exists: `C:/9781264958665-Binder1.pdf` (758 physical pages); SHA256 recorded as `de9d916687ecbe556f7a01f1d871048ec89f362ae5c4b399bd08098b1fddc951` in [release verifier](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/scripts/verify_structural_release.py:107>).

- Complex 314: map with unruled country/count inset, recorded 100,305 vector items and geometry guard.
- Complex 465: four illustrated organization cards; reference represents four separate one-column tables; image/text ownership matters.
- Complex 500: multicolumn closed sidebar with Dat Nguyen paragraph spanning source blocks; explicit integration regression.
- Background 389: page-wide background image enclosing worksheet; earlier false decorative edge changed table 5 columns to 4.
- Colored box 727: cached source-region fixture shows white PREGUNTA GUÍA text and colored CONÉCTATE footer, image + summary table; visually confirm category before selection.

Evidence: [table notes](<C:/coeik/projects/pdf to xml converter/book_xml_production_upgrade/scripts/report_reference_tables.py:26>), [sidebar regression](C:/coeik/projects/nimas/book_xml_backend/tests/test_reference_structural_examples.py:93), [background-image correction](C:/coeik/projects/nimas/book_xml_backend/docs/structure-release-043.md:51), [source fixture](C:/coeik/projects/nimas/book_xml_backend/tests/fixtures/source_regions/unnumbered_caption.json).
