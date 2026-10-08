"""Assemble the review report from measured Phase 0 artifacts; no converter."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/out'
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8-sig'))
rows=load('extractor_results.json');fixtures=load('fixtures_manifest.json');geo={r['id']:r for r in load('geometry_results.json')}
models={m['model']:{f['fixture_id']:f for f in m['fixtures']} for m in load('layout_model_results.json')['models']}
extract={(r['id'],r['extractor']):r for r in rows}
lines=[]
def add(s):lines.append(s)
add("""# Phase 0 / Step 1 report
Date: 2026-10-08. Scope: read-only reference audit, isolated experiments, and review artifacts. **No converter code or Step 2 work was written.**

## Important results
- **495,751 includes headers, footers and page numbers.** It excludes lines outside explicit TrimBoxes and compares unordered, case-sensitive NFKC Unicode token multisets. It cannot prove reading order, paragraph integrity or visual/OCR completeness.
- PyMuPDF exactly reproduced retained cached tokens on all seven Spanish-textbook fixtures. The dense map exposes substantial PDFium/pdfminer/pdfplumber disagreements. This small sample supports keeping extraction evidence independent of semantic layout; it does not establish universal accuracy.
- Heron and PP-DocLayoutV3 both ran on CPU. PP native order fails the column-regression fixture and reverses text inside one organization card. Heron supplies no reading order. Both split one three-panel composite figure into three image regions.
- The 48-page World-history profile is paired with an 86-page US-history XML: exclude it from scoring. Several other XMLs are generated outputs, not independent references.
- PyMuPDF/DocLayout-YOLO and MinerU require explicit licensing choices; permissive model weights do not make every runtime permissive.

## A. Old projects and references
No old code, configuration, data, environments or tests were changed. Read-only Python probes used `-B`; old test suites/services were not run because they can write caches/data. New scripts, environments, fixtures and results are under `experiments/`. No existing Git repository was found at the inspected old roots.

| Old location | Structure / entry points | Dependencies |
|---|---|---|
| `C:/coeik/projects/pdf to xml converter/pdf_to_xml` | Original offline input/OCR/extraction/layout/classification/rules/model/XML/review package. `python -m pdf_to_xml`, `pdf-to-xml`; Flask `pdf-to-xml-web`. | Python >=3.12; PyMuPDF, lxml, PyYAML, Flask; pytest; optional rnc2rng. |
| `.../book_xml_production_upgrade` | Staging application, diagnostic scripts, historical `checks/` and deployment evidence. | FastAPI/backend family. |
| `book_xml_backend/` | Extraction/layout/structure detection, learned/YAML rules, validation, API/jobs/packages. `uvicorn app.main:app`; `python -m app.cli train/convert/score`. Source reports 0.5.0rc2. | FastAPI, uvicorn, pydantic/settings, multipart, PyMuPDF, lxml, PyYAML, RapidFuzz, regex; pytest/httpx/ruff. |
| `book_xml_frontend/` | React/TypeScript/Vite UI; `src/main.tsx`; dev/build and Playwright. Root `start.ps1` launches both services. | React 19, Vite 7, TypeScript 5.9, lucide-react, Playwright. |

Evidence and exact local source citations: [old-project audit](../experiments/out/old_audit.md). Reuse proven extraction behavior, token/accounting tools, source hashes, fixtures and tests as evidence; **do not copy the old architecture**.

### Reference PDF/XML associations
`Downloads` means `C:/Users/Lenovo/Downloads`. Full hashes, PDF page counts and XML inspection results are in [corpus inventory](../experiments/out/corpus_inventory.json), [profile pairs](../experiments/out/reference_pairs.json), and [archive inventory](../experiments/out/reference_archives.json).

| PDF / name | Physical pages | Type | XML and reference status |
|---|---:|---|---|
| `C:/9781264958665-Binder1.pdf` / identical Downloads copy | 758 | Born-digital Spanish US-history textbook; multiple columns, maps, worksheets, boxes | `C:/9781264958665NIMAS.xml`: supplied matching NIMAS reference, 758 folios. Malformed opening quote delimiters inspected with in-memory repair only. |
| `9781264958665-Binder1-1-300.pdf` and `(1)` | 300 each | Duplicate excerpts of the preceding source | Downloads `book (13).xml` is partial generated output; no independent 300-page answer located. |
| `9781266828829-Binder1.pdf` | 729 | Alabama Physical Science; composite diagrams and teaching boxes | Downloads `book (7)/(9)/(10)/(11).xml` are generated variants. No independent publisher XML located. |
| `9798216208693_web.pdf` | 331 | Immigrant Children, social science; tables/indexes; native text plus scanned/blank pages | Supplied manual DocBook `9798216495130_txt_xml.xml`. Generated variants: `book.xml`, `book (1)/(2)/(3)/(4)/(8).xml`. |
| `9780802027962.pdf` | 326 | Canadian Historical Review Index, scanned with OCR/text layer | `book (6).xml` is generated; no independent answer located. |
| `docbook xml index sample/docbook index input.pdf` | 9 | Art-therapy subject/author index, multiple columns | Supplied `docbook index output.xml`: two top-level fragments, wrapped in memory for inspection. Same pair verified inside the ZIP. `book (5).xml` is generated and unrelated to Immigrant Children. |
| Archive `Nimas sample input and output/T01.pdf`; profiles `nimas-example` and `samble-book-xml` | 86 each | Duplicate US-history Tema 1 excerpts | Archive `T01.xml` and both `source.xml` files are hash-identical matching reference excerpts. Count once. |
| Downloads `T01.pdf` / profile `t01/source.pdf` | 48 | World-history Tema 1 | **Wrong paired XML:** profile `source.xml` is the above 86-page US-history answer. No correct 48-page reference located. |

Derived XML-debug PDFs (508/570/1469 pages), reconstructed `result book.pdf` (244 pages), and the 293-page Bloomsbury specification are not new source/reference pairs. Old smoke PDFs/goldens and cached normalized fixtures are useful regression evidence, not independent publisher answers. Corpus scope covers located old references, uploaded/profile samples and supplied reference ZIPs; repeated job outputs are deduplicated, not counted as new books.

### Known failures: historical versus later saved artifacts
The table independently rechecks saved artifacts; it is **not a new run of the deployed 0.5.0rc2 converter**.

| Requested check | Historical baseline | Later saved corrected output |
|---|---|---|
| Columns on physical 26 / 100 | Both interleave columns; page 100 emits top-right continuation before earlier left prose. | Named prose anchors have corrected order. |
| `Gobernantes estadounidenses...` | Opening paragraph truncated after `la estructura`; prose split across multiple `<p>` nodes. | One complete paragraph owns five source blocks. |
| Furniture inside lists | 140 furniture nodes under list/li; narrower header/footer-only audit counted 55. | Zero under lists; furniture retained elsewhere. |
| Tables: 52/71 and eight layout differences | Confirmed 52 matched, 44 same row/cell-count shapes, eight shape differences. | Later 65/71 matched: 40 exact compared-cell matches, 16 same-shape cell differences, nine shape differences, six unmatched. |
| Authors / Mapas / Biografías | Exact labels emit paragraphs. | Emit h1 in the saved corrected output; this does not certify heading hierarchy universally. |
| Complex textbook pages | Map inset tables, organization cards, background grids and stacked sidebars require region ownership. | Residual diagram/map/timeline structures, figure grouping, cross-page paragraphs and schema policy remain unresolved. |

Eight historical table shape differences occur at physical pages **79, 91, 97, 139, 283, 295, 613, 754**: writing-subrow grouping, reference omission of printed row E, citation placement, title-as-caption versus row, and header shapes. They are not eight proven token-loss cases. Later output retains these differences and adds page 732. See [exact artifact/table evidence](../experiments/out/old_audit.md).

Other documented limits: 354 native U+FFFD glyphs on science physical page 641; glyph recovery disabled because rawdict/texttrace positions disagree; native-text pages can still contain unrecognized image text.

Reusable evidence: unsorted dict/rawdict spans and character provenance; independent source-line ownership/coverage, Unicode and character counters, table-cell migration checks; supported 2/3-column flow tests, paragraph/hyphen tests, furniture/list boundaries, composite-figure tests and source hashes. Existing tests establish supported cases, not all-book production correctness.

### Exact benchmark definition
1. Take retained extracted source-line text, joining original spans within each line; exclude only explicit exclusion IDs.
2. Case-sensitive NFKC comparison copy; regex `[\\p{L}\\p{M}\\p{N}]+`; Counter intersection/differences count occurrences. Punctuation/whitespace separate tokens; order is unchecked.
3. Saved 758-page validation: **92,228 source lines - 7,194 TrimBox exclusions = 85,034 retained lines**; source/output each **495,751 tokens**. Furniture contributes **1,375 nodes / 4,929 tokens** and is included.
4. Therefore **after TrimBox exclusion, before header/footer/page-number removal**. This measures conservation of already extracted text, including extraction defects, not text absent from the native layer. An earlier independent fresh-native audit reported two missing/four excess cached occurrences.

Source construction and counters are linked in [audit evidence](../experiments/out/old_audit.md); experiment seven-page expected counts come directly from that saved normalized cache and its exclusion IDs.

## B. Environment and licenses
Python **3.14.8**, Windows AMD64; Intel i5-8265U, 21,349,158,912 bytes RAM, Intel UHD 620. No CUDA/NVIDIA GPU was used. The existing backend venv was only read; its installed editable metadata says 0.1.0 while source reports 0.5.0rc2.

Two new isolated environments: `experiments/.venv-extract` and `experiments/.venv-layout`; all downloads/caches remain under `experiments/.cache`. Both models installed successfully on this Python. PP postprocessing initially lacked OpenCV; adding headless OpenCV fixed it. Full Docling/Paddle wrappers were not installed: their requested layout **models** were tested directly via official Transformers inference paths.

| Candidate / artifact | License | Commercial restriction / implication |
|---|---|---|
| PyMuPDF 1.28.2 / MuPDF | **AGPL-3.0 OR commercial** | Choose an AGPL-compliant deployment or Artifex commercial terms. [Official license](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) |
| pypdfium2 5.14.0 / PDFium | Apache-2.0 OR BSD-3-Clause; PDFium BSD-style + notices | Permissive, but include bundled binary notices. [Official terms](https://github.com/pypdfium2-team/pypdfium2#licensing) |
| pdfminer.six 20260107 / pdfplumber 0.11.10 | MIT | No license-level commercial threshold. [pdfminer](https://github.com/pdfminer/pdfminer.six/blob/master/LICENSE), [pdfplumber](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt) |
| OpenCV headless 5.0.0.93 | Installed metadata Apache-2.0; bundled FFmpeg **LGPL-2.1** | Bundled notices matter. LGPL-3 Qt notes concern non-headless Linux/macOS wheels, not this Windows headless wheel. [Upstream packaging](https://github.com/opencv/opencv-python/blob/4.x/README.md#licensing); installed notices inspected. |
| Docling / Heron weights | Docling MIT / Heron Apache-2.0 | No commercial threshold identified in these licenses. [Docling](https://github.com/docling-project/docling/blob/main/LICENSE), [Heron](https://huggingface.co/docling-project/docling-layout-heron) |
| PP-DocLayoutV3 weights / PaddleOCR / Paddle | Apache-2.0 for all three | No commercial threshold identified. [Official weights](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE), [Paddle](https://github.com/PaddlePaddle/Paddle/blob/develop/LICENSE) |
| DocLayout-YOLO code / author checkpoint | **AGPL-3.0 code** / checkpoint card says Apache-2.0 | Weight metadata does not remove code copyleft. [Code](https://github.com/opendatalab/DocLayout-YOLO/blob/main/LICENSE), [checkpoint](https://huggingface.co/juliozhao/DocLayout-YOLO-DocStructBench) |
| MinerU current master / MinerU2.5-2509-1.2B | Custom Apache-based software terms / **AGPL-3.0 model** | Software commercial license required above consolidated affiliates **100M MAU OR USD20M monthly revenue**; third-party online services require prominent attribution. Pin version and weights; not plain Apache. [Software terms](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md), [model](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B) |
| Dulwich 1.2.17, experiment Git tooling | Apache-2.0 OR **GPL-2.0-or-later** | Apache alternative available; not a proposed converter dependency. Installed metadata recorded below. |

No additional top-level AGPL/GPL declarations were found in the 42-distribution layout environment. MPL-2.0 (certifi/tqdm), LGPL binary notices, and multi-license Torch/NumPy wheel terms remain recorded; top-level package metadata is not a complete binary compliance audit. No candidate above was assumed to forbid commercial use categorically.

""")
# installed package ledger
add("<details>\n<summary>Complete installed package/version/license table (Initial, Extract, Layout)</summary>\n")
add((OUT/'installed_package_licenses.md').read_text())
add("\nInitial = existing read-only backend venv; Extract/Layout = new isolated experiments. License values come from installed metadata/notices; unspecified internal book-xml-backend licensing needs company confirmation. Exact raw metadata: [initial](../experiments/out/environment_initial.json), [extract](../experiments/out/environment_extract.json), [layout](../experiments/out/layout_environment_final.json).\n</details>\n")
add("""## C. Fixtures and extraction experiments
All nine PDFs are single-page copies in `experiments/fixtures/`; source/page/hash/TrimBox metadata is in [fixture manifest](../experiments/out/fixtures_manifest.json). Fixtures were reopened and rendered. Page IDs are diagnostic fixture selection only; no converter page-number logic exists.

| Fixture | Source physical page | Feature / actual body scope |
|---|---:|---|""")
scope={
'column_26':'Two prose columns; central pull quote and wrapped paragraph.',
'column_100':'Two prose columns; chart and cross-column continuation.',
'complex_map':'Two prose columns below a spanning map/inset table.',
'complex_cards':'Two upper prose columns; four lower organization cards.',
'complex_sidebar':'Two prose columns within each stacked sidebar section.',
'science_fission':'One prose column; two composite fission/chain-reaction figures.',
'science_dissolving':'One prose column; Figure 16 has three molecular panels and labels.',
'background_worksheet':'Two prose columns per section over page background; picture/table.',
'colored_box':'One main prose column plus marginal sidebar/table; colored guide/footer.'}
for f in fixtures:add(f"| [{f['id']}](../{f['fixture'].replace(chr(92),'/')}) | {f['physical_page']} | {scope[f['id']]} |")
add("""
Spanish source = 758-page Binder; science source = 729-page Physical Science. Render scale: 1 pixel per PDF point, full page including production marks; model threshold 0.5. Main columns were visually annotated; captions, marginal sidebars and card lanes are separate scope.

### Native token completeness and speed
Cell = **missing / extra token occurrences; median milliseconds per page**. Baseline retained tokens shown separately. Text-only native extraction with explicit frame filtering; includes document open/close, excludes rendering/token scoring. Three sequential runs per fixture. PyMuPDF uses line-center retention as the old benchmark; PDFium uses bounded characters, pdfminer line centers, pdfplumber character centers, so boundary behavior is not identical. No extractor OCR was enabled.

| Fixture | Baseline tokens | PyMuPDF | PDFium | pdfminer.six | pdfplumber |
|---|---:|---|---|---|---|""")
for f in fixtures:
 cells=[]
 for name in ('pymupdf','pypdfium2','pdfminer.six','pdfplumber'):
  r=extract[f['id'],name];cells.append(f"{r['missing']}/{r['extra']}; {r['median_seconds']*1000:.1f}")
 tag=' †' if f['id'].startswith('science') else ''
 add(f"| {f['id']}{tag} | {extract[f['id'],'pymupdf']['baseline']} | "+' | '.join(cells)+' |')
add("""
† Science baseline is current PyMuPDF native text, **not** the old 495,751 benchmark; independent science XML was not found. The other seven rows use exact old cached retained-line text. Full counters/examples: [extractor results](../experiments/out/extractor_results.json). Equal totals alone are misleading: reversed rotated credits and fused/split tokens can preserve counts while changing text. Map PDFium has 125 missing cached occurrences; its observed token coverage is 79.8%, with three extra occurrences.

**One full 331-page book, Immigrant Children:** native-only comparison uses current PyMuPDF as proxy (124,017 tokens). The old matching cache includes offline OCR, so this is not a like-for-like old OCR-inclusive conservation score. Twelve pages have no native text, including possible blanks. One sequential full-book run; parser + bbox retention timed, scoring/cache reading excluded.

| Extractor | Tokens | Missing / extra vs native proxy | Token recall | Total seconds | Seconds/page |
|---|---:|---:|---:|---:|---:|""")
for r in load('full_book_small.json')['results']:
 add(f"| {r['extractor']} | {r['tokens']:,} | {r['missing']} / {r['extra']} | {r['recall']*100:.3f}% | {r['seconds']:.3f} | {r['seconds_per_page']:.5f} |")
add("""
Full-book evidence: [results](../experiments/out/full_book_small.json). These are local observations, not isolated laboratory throughput or visual ground truth. Model timing began after the extraction benchmark completed; the interrupted overlapping model sample was discarded.

### Metadata and geometry capabilities, verified locally
| Extractor | Font / size / color / text bbox | Image boxes | Vector drawing geometry |
|---|---|---|---|
| PyMuPDF | Yes, dict/rawdict spans and texttrace | get_image_info placements, including shade representations | get_drawings paths/items; bboxlog paint sequence |
| pypdfium2 | Yes; wrapper font objects + raw fill RGBA/char boxes; normalize text matrix | PDF page image objects + bounds; shading objects separately | Low-level path objects/segments and bounds; extra reconstruction needed |
| pdfminer.six | Yes, LTChar + graphic-state color; native coordinates | LTImage boxes; shades not represented as LTImage | LTLine/LTRect/LTCurve geometry |
| pdfplumber | Yes, char font/size/color/top-origin bboxes | image dicts; shades not ordinary image entries | curves/rectangles/lines/edges |

Verified on composite/background fixtures: [capability probe](../experiments/out/capability_probe.json). PDFium's object font size can be 1.0 while its text matrix scales it to 12.0/19.8 pt; comparing raw sizes would be wrong. Native color spaces and coordinate systems also require normalization.

### PyMuPDF deep APIs
All four requested calls existed and executed successfully on **every fixture**. Counts below are placements/path records/paint records/trace spans, not semantic figures or paragraphs.

| Fixture | get_image_info | get_drawings (items) | get_bboxlog | get_texttrace |
|---|---:|---:|---:|---:|""")
for f in fixtures:
 a=extract[f['id'],'pymupdf']['apis']
 add(f"| {f['id']} | {a['get_image_info']} | {a['get_drawings']} ({a['vector_items']}) | {a['get_bboxlog']} | {a['get_texttrace']} |")
add("""
- **Composite dissolving page:** 811 image-info placements, all xref 0; bboxlog has **811 fill-shade, 120 fill-text, 27 fill-path, 203 stroke-path** records. PDFium confirms 811 shading objects and zero raster-image objects. The three panels, labels and caption form one semantic Figure 16; API placements do not define figure identity.
- **Composite fission page:** 853 image-info/shading placements plus vector connectors and 104 text traces. Both models find the two complete diagram regions; component/label ownership is not thereby proved.
- **Background worksheet:** four image-info placements; bboxlog **3 fill-image, 1 fill-shade, 98 fill-text, 20 fill-path, 390 stroke-path, 2 stroke-text** records. One earlier image paint overlaps later text, supporting a background role; seven sizeable colored fill paths overlap later text, supporting boxes/panels. These are geometric/paint-order inferences checked visually, not definitive semantic classifications.
- Dense map: 1,668 drawing records contain **100,305 vector items**. Guard expensive geometry processing by actual complexity, not page-number rules.

get_image_info gives placement bbox/transform/resolution/xref/digest; drawings give paths, fill/stroke/opacity/rect/seqno; bboxlog gives paint role+bbox order; texttrace gives characters/font/size/color/bbox/direction/seqno. Bbox overlap alone cannot resolve clipping, masks, visibility or ownership. Only counts/roles are presented; no full dumps.

### Columns/regions, reading order and model footprint
Geometry method: one fixed prose-length/font-size filter, line-box occupancy mask, OpenCV gutter projection plus rendered whitespace/ink signal. It never reads answer XML. It applies a **page-global** left-to-right column policy; models instead supply semantic region boxes. Model prose-lane counts below are **manual interpretations of regions**, not model column predictions or raw region counts.

Cell format: columns / order; runtime seconds. Heron native order is unavailable throughout. PP order is checked against displayed main flow and card text; scoped passes do not certify all page semantics.

| Fixture | Actual body columns | Own geometry / proposed order / s | Heron visible lanes / s | PP visible lanes / native order / s |
|---|---|---|---|---|""")
native={'column_26':'FAIL mixed columns','column_100':'pass main prose; continuation split','complex_map':'pass lower prose; definition omitted','complex_cards':'FAIL text reversal inside card','complex_sidebar':'pass per section; paragraph split','science_fission':'pass main prose','science_dissolving':'pass prose/panel sequence; grouping fails','background_worksheet':'pass per section','colored_box':'pass main prose; sidebar scope open'}
own={'column_26':'body column order yes; quote scope open','column_100':'body column order yes; paragraph join untested','complex_map':'FAIL 1 vs 2','complex_cards':'FAIL 1 vs 2','complex_sidebar':'FAIL global sort mixes section bands','science_fission':'FAIL figure lane counted','science_dissolving':'FAIL figure lane counted','background_worksheet':'FAIL global sort mixes section bands','colored_box':'main prose yes; sidebar scope open'}
for f in fixtures:
 fid=f['id'];g=geo[fid];h=models['heron'][fid];p=models['pp_doclayoutv3'][fid];n=f['actual_main_prose_columns']
 actual=str(n)+(' per section' if fid in ('background_worksheet','complex_sidebar') else '')
 lane=str(n)+(' + 4 card lanes' if fid=='complex_cards' else '')
 add(f"| {fid} | {actual} | {g['columns']} / {own[fid]} / {g['seconds']:.3f} | {lane}; no order / {h['runtime_seconds_median']:.3f} | {lane} / {native[fid]} / {p['runtime_seconds_median']:.3f} |")
add("""
PP regression evidence: column_26 left regions 3/4/5 -> right 6 -> lower-left 7. Card regression: NAACP order25 at y726–759 precedes order26 at y681–724, reversing chronology. Map bottom-right definition is undetected at threshold 0.5; left definition is labelled footer. Model regions must not become the sole token-retention filter.

**Composite grouping:** both models detect dissolving Step 1/2/3 as three image regions with no parent grouping. Correct two-column counts elsewhere do not ensure whole paragraphs; column_100 and stacked sidebar continuations remain separate regions.

Detailed independent review of all 18 model overlays: [layout visual audit](../experiments/out/layout_visual_audit.md). Raw boxes/order/revisions/timing: [model results](../experiments/out/layout_model_results.json); [gutter results](../experiments/out/geometry_results.json).

| Method | Measured / installed footprint | Runtime / hardware |
|---|---|---|""")
e=load('environment_extract.json');l=load('layout_environment_final.json')
add(f"| Geometry/OpenCV | Entire extraction venv {e['venv_bytes']:,} bytes; OpenCV distribution {e['opencv_distribution_bytes']:,} bytes (includes notices/data). Other extractors/Git tools share this env. | CPU; no GPU needed. Per-fixture times above include text mask/render/projection. |")
add(f"| Heron | Weights **171,658,996 bytes**; shared layout venv **{l['venv_logical_file_bytes']:,} bytes**. | CPU 4 Torch threads; 1.847–2.046 s/page. |")
add(f"| PP-DocLayoutV3 | Weights **133,270,468 bytes**, same layout venv. | CPU 4 threads; 2.729–4.028 s/page. |")
add(f"| Downloads/cache | Shared experiment cache **{l['cache_logical_file_bytes']:,} bytes**; not a per-model install size. | Torch + Transformers + OpenCV install: about 372 s. |")
add("""
Sizes are logical file lengths, not allocated/deduplicated disk space. Models share Torch 2.14.1+cpu / Transformers 5.19.0 / torchvision 0.29.1+cpu. Timings include processor/inference/postprocess; image/model loading and overlay drawing excluded, warmup then two-repeat median. Docling wrapper runtime was not benchmarked. Exact model revisions and assets: [asset ledger](../experiments/out/layout_model_assets.json). Models downloaded normally, no GPU or compatibility install blocker remained.

Pinned packages: [extract](../experiments/requirements-extract.txt), [layout](../experiments/requirements-layout.txt). Reproduce with [fixture experiment](../experiments/fixture_experiments.py), [full book experiment](../experiments/full_book_experiment.py), [model experiment](../experiments/layout_models.py); these are research scripts only and use local reference paths.

## Five overlays to review
1. [experiments/out/column_26_pp_doclayoutv3_overlay.png](../experiments/out/column_26_pp_doclayoutv3_overlay.png) — mixed native column order.
2. [experiments/out/complex_cards_pp_doclayoutv3_overlay.png](../experiments/out/complex_cards_pp_doclayoutv3_overlay.png) — four cards and reversed text inside NAACP.
3. [experiments/out/complex_map_geometry_overlay.png](../experiments/out/complex_map_geometry_overlay.png) — global gutter misses the two-column lower body.
4. [experiments/out/science_dissolving_pp_doclayoutv3_overlay.png](../experiments/out/science_dissolving_pp_doclayoutv3_overlay.png) — three detected panels needing one figure parent.
5. [experiments/out/background_worksheet_heron_overlay.png](../experiments/out/background_worksheet_heron_overlay.png) — background, colored panels and stacked section scopes.

## Decisions required before Step 2
1. **Extractor licensing:** Artifex commercial/AGPL deployment versus permissive PDFium, accepting that the map disagreement needs resolution before replacing known-good extraction.
2. **Reference truth:** approve deduplication/mismatched-pair exclusions and a repaired working copy policy for malformed supplied XML; decide how printed tables versus editorial reference shapes are adjudicated.
3. **Furniture and preservation policy:** retain furniture as separate evidence while defining what semantic/output stages may omit; keep conservation metrics separate from body-text accuracy.
4. **Layout baseline and order:** choose which CPU model deserves further evaluation; neither current raw regions nor PP native order meets every fixture requirement. Define acceptance for bands, 2/3-column order, complete paragraphs and figure ownership.
5. **OCR/glyph scope:** define required languages and mixed native/image-text coverage, unknown-glyph handling and escalation for scans. Native extraction alone cannot satisfy every book.
6. **Production constraints:** target hardware, latency/storage budget and permitted dependencies/model versions. These nine fixtures are not a production accuracy estimate; expand annotated unseen books before declaring readiness.

**Stop point:** Step 1 report/fixtures/results are ready for review. No Step 2 implementation is included.
""")
(ROOT/'docs/phase0_report.md').write_text('\n'.join(lines).replace(r'\\p',r'\p'),encoding='utf-8')
print('report lines',len((ROOT/'docs/phase0_report.md').read_text().splitlines()))

