# Project rules

- Stage 1 is the converter: PDF -> universal semantic model. Stage 2 is adapters, later. No adapter or XML work yet.
- Old projects are read-only, including their code, environments, caches, configuration, reference files and tests. Use docs/phase0_report.md and experiments/out/ as evidence. The active Python package and tests are in backend/. External references are read only through experiments/references.toml or environment overrides; no absolute reference paths in src.
- Prioritize accuracy and production-grade structure. Processing time is not a constraint. Cache extraction results per page with source/configuration/version fingerprints.
- The product is an internal desktop app for office workers. All processing must work on CPU; no GPU dependency.
- PyMuPDF is the primary extractor for internal use. All extraction goes through the Extractor interface.
- Never classify headings by font size alone.
- Never treat PDF lines as paragraphs.
- Never globally sort by (y,x).
- Never assume a fixed number of columns.
- Never hardcode page numbers, coordinates or fonts. Page numbers are allowed only in tests/fixtures.
- Never OCR normal digital text. Multi-language OCR is behind OcrEngine; no OCR implementation yet. Configure a list of language codes per job and per region through Settings (job default: spa, eng). The language-pack registry is a placeholder.
- Exclude the mismatched 48-page reference pair. Generated XML is not independent reference truth.
- Colored boxes become callout regions. Text inside figures becomes embedded text on the figure node.
- The core model contains no XML tag names. Text spans and text-bearing nodes carry optional script and text_direction (ltr/rtl/ttb), defaulting to unknown. The model, tokenizer and ledger never assume Latin script or left-to-right order. CJK without spaces needs a different token rule later; preserve the current benchmark now.
- Text is lossless: a span store holds all extracted text with stable IDs. Nodes reference spans and never copy source text. Keep original and NFKC-normalized text in the store.
- Every token ends in one node or an explicit DiscardRecord with a reason. At this step, only explicit TrimBox exclusions may be discarded. Furniture stays retained.
- Preserve native text order as extraction evidence; do not claim semantic reading order or paragraph classification at this gate.
- One git commit per step. Stop at each gate for review.

