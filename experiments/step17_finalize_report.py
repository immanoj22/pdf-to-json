"""Write the results-first report from passed final gates, preserving measured details."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step17"
FINAL = OUT / "final"
BOOKS = {"spanish_us_history": "Spanish history", "immigrant_children": "Immigrant children",
         "art_therapy_index": "Art therapy", "medical_anatomy": "Medical anatomy",
         "statistics": "Statistics"}


def read(path):
    return json.loads(path.read_text("utf-8"))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "|" + "|".join("---" for _ in headers) + "|",
                       *["| " + " | ".join(str(v) for v in row) + " |" for row in rows]])


def main():
    gate = read(FINAL / "gate_summary.json")
    assert gate["passed"], "Do not publish a passed report before every gate passes"
    data = read(FINAL / "report_data.json")
    validation = read(FINAL / "validation_record.json")
    path = ROOT / "docs/step17_report.md"
    previous = path.read_text("utf-8")
    start = previous.index("## OCR measurements")
    ends = [previous.index(marker, start) for marker in
            ("## Remaining gate work", "## Review decisions and limitations") if marker in previous[start:]]
    details = previous[start:min(ends)].rstrip()
    lines = ["# Step 17 — assembly: one validated JSON per book", "",
             "Stage 1 now publishes a documented, versioned `universal-book` 1.0.0 JSON, images,",
             "review crops and a checksummed manifest for each of the five books. All required",
             "Step 17 gates pass, with the explicitly allowed Statistics I7 = 1 exception.",
             "This step stops for review; no Stage 2 adapter has been started.", "",
             "## Final results", "",
             table(["Book", "Pages", "Retained ledger", "Missing / extra", "Schema errors", "Round trip", "Reviews"],
                   [[name, data[key]["pages"], f'{data[key]["lossless"]["ledger_retained"]:,}',
                     f'{data[key]["lossless"]["missing"]} / {data[key]["lossless"]["extra"]}',
                     data[key]["schema_errors"], "identical" if data[key]["round_trip_identical"] else "FAIL",
                     data[key]["review_items"]] for key, name in BOOKS.items()]), "",
             "The Spanish ledger remains **495,751** retained tokens; all 34,160 explicit TrimBox",
             "discard tokens also reconstruct exactly. All five books have zero missing/extra",
             "retained and discarded tokens. Furniture, source markers and confirmed hidden text",
             "remain reconstructible from the JSON. The token check does not discard hidden text.", "",
             "Every-page I1–I7 totals are zero on books 1–4. Statistics has I1–I6 = 0 and the",
             "known I7 = 1. Every page has each line/unit owned and ordered once. The fresh native",
             "source crosscheck covers 30 pages with **0 missing / 0 extra**. Archive image hashes,",
             "references and manifests pass, including the OCR-cover raster. The archive gate retains",
             "the earlier assertions with two explicit extensions: OCR raster assets count as images;",
             "post-publication assembly evidence is excluded from the pre-publication archive key set.", "",
             f'**{validation["full_suite"]["count"]:,} backend tests pass** in '
             f'{validation["full_suite"]["seconds"]:.2f} seconds. The post-deletion cache-closure check',
             "passes 62 tests; Ruff passes. The built wheel contains the exact committed JSON Schema",
             "and default TOML bytes. Validation logs and SHA-256 receipts are in",
             "`experiments/out/step17/final/validation_record.json`.", "",
             "### Output and performance", "",
             table(["Book", "JSON MB", "Folder MB", "Units", "Archive run s", "Archive peak GB", "Publication s", "Publication peak GB"],
                   [[name, f'{data[key]["book_json_bytes"]/1e6:.3f}', f'{data[key]["folder_bytes"]/1e6:.3f}',
                     data[key]["units"], data[key]["total_seconds"],
                     f'{data[key]["peak_tree_rss_bytes"]/1e9:.3f}', data[key]["assembly_seconds"],
                     f'{data[key]["assembly_peak_tree_rss_bytes"]/1e9:.3f}'] for key, name in BOOKS.items()]), "",
             "MB/GB are decimal. Archive timing and process-tree peak are the original complete run,",
             "including its original assembly. The final publication is rebuilt from that unchanged",
             "semantic archive and measured separately; those two times must not be added as a new",
             "complete run. Earlier publications and measurements are retained in `assembly_history`.", "",
             table(["Book", "Final publication", "File manifest"],
                   [[name,
                     f'[book.json](../{Path(data[key]["book_json_folder"]).relative_to(ROOT).as_posix()}/book.json)',
                     f'[manifest.json](../{Path(data[key]["book_json_folder"]).relative_to(ROOT).as_posix()}/manifest.json)']
                    for key, name in BOOKS.items()]), "",
             "These are generated local output folders; their compact measurements and checksums",
             "are committed as evidence, rather than duplicating the publication binaries in Git.", "",
             "The authoritative publication paths, file counts, content hashes, process measurements",
             "and disk-reserve records are in `final/performance/*.json` and `final/report_data.json`",
             "under `experiments/out/step17`. Statistics completed all 871 pages with the required",
             "5 GB reserve; no further pruning was needed.", "",
             "### Review workload", ""]
    for category in ("severity", "kind"):
        counts = {}
        for key in BOOKS:
            counts[key] = {}
            for pair, count in data[key]["review_counts"].items():
                severity, kind = pair.split(":", 1)
                value = severity if category == "severity" else kind
                counts[key][value] = counts[key].get(value, 0) + count
            assert sum(counts[key].values()) == data[key]["review_items"]
        values = sorted({value for key in BOOKS for value in counts[key]})
        lines += [f"Counts by {category}:", "",
                  table([category.capitalize(), *BOOKS.values()],
                        [[value, *[counts[key].get(value, 0)
                                   for key in BOOKS]] for value in values]), ""]
    lines += ["All uncertain content units have a review entry. All review unit targets resolve,",
              "including nested text, furniture and retained suppression records; IDs are unique",
              "and continuation targets are reciprocal (`final/contract_check.json`).", "",
              "### Development parity and determinism", "",
              "Continuity and table parity pass on all five full archives. Independent development",
              "assembly matched all five publications. The last publication correction preserves each",
              "entry's own nesting level: a flat index container must not overwrite levels 2/3 with",
              "its own level 1. A failing regression reproduced the defect; all 45 assembly tests pass",
              "after the fix. Art index level accuracy returns to .998821 and anatomy to .962480.", "",
              "For the four unchanged archives, the expensive independent proof was frozen before",
              "this final correction. Every new item level is then checked against its source unit;",
              "every other JSON field is exactly unchanged apart from producer/content hashes.",
              "The OCR-cover book has fresh complete assembly parity. The method and proof hashes",
              "are recorded in `final/parity` and `final/parity_before_entry_levels`; this is scoped",
              "proof reuse, not five repeated full render runs. Full invariant proof reuse likewise",
              "requires exact unchanged input keys and records the proof checksum in `proof_reuse.jsonl`.", "",
              "One-worker, two-worker and development outputs have identical `book.json` and manifest",
              "bytes for the worker fixture. The final producer and every file hash are recorded in",
              "`final/workers_book3.json`.", "",
              "### Reference metrics on the JSON", "",
              table(["Book", "Paragraph F1 page / chained", "Exact paragraph page / chained", "Main-flow order / tau", "Float anchors / within"],
                    [[name,
                      " / ".join(str(data[key]["json_eval"].get("paragraphs", {}).get(v, {}).get("boundary_f1")) for v in ("per_page", "chained")),
                      " / ".join(str(data[key]["json_eval"].get("paragraphs", {}).get(v, {}).get("exact_unit_match")) for v in ("per_page", "chained")),
                      " / ".join(str((data[key]["json_eval"].get("reading_order") or {}).get(v)) for v in ("main_flow", "kendall_tau")),
                      " / ".join(str((data[key]["json_eval"].get("reading_order") or {}).get(v)) for v in ("float_anchors", "within_floats"))]
                     for key, name in BOOKS.items()]), "",
              table(["Book", "List item F1 / exact", "List boundary F1 / nesting exact", "Index exact / level accuracy", "Bibliography F1"],
                    [[name,
                      " / ".join(str(data[key]["json_eval"].get("lists", {}).get("list_items", {}).get(v)) for v in ("item_boundary_f1", "exact_match")),
                      " / ".join(str(data[key]["json_eval"].get("lists", {}).get("list_items", {}).get(v, {}).get("f1" if v == "list_boundary" else "exact")) for v in ("list_boundary", "nesting")),
                      " / ".join(str(data[key]["json_eval"].get("lists", {}).get("index", {}).get(v)) for v in ("exact_match", "sub_entry_level_accuracy")),
                      data[key]["json_eval"].get("lists", {}).get("bibliography", {}).get("boundary_f1")]
                     for key, name in BOOKS.items()]), "",
              "`None` means no applicable reference, not a zero score. Statistics uses joined-table",
              "TEDS and archive order checks; it has no paragraph/list/order gold here. Main-flow",
              "adjacent-unit order agrees with the archive on every measured pair: Spanish 8,126;",
              "immigrant children 934; art 3; anatomy 2,444; Statistics 7,928.", "",
              "Anatomy's 15/15 joined reference tables retain TEDS .9258 (full .8516; whole-only",
              ".9702). Statistics scores 65 of 69 reference tables, retaining .9586 (full .8635;",
              "whole-only .9961). These equal the earlier joined-table measurements.", "",
              "Spanish paragraph F1 changes from .942928 to .942888 per page and .943204 to .943165",
              "chained; exact matches change .896309 to .896304 and .882887 to .882864. The JSON",
              "owner comparison records 75 aligned tokens leaving the scored content view: hidden",
              "table text 14, markers 19, heading candidates 5, paragraphs 3 and figure text 34.",
              "They remain in source-marker/suppression/figure evidence and the lossless ledger.",
              "Anatomy loses one marker token from the scored text view; F1 changes .901418 to",
              ".901479 per page and .903011 to .903072 chained. Statistics similarly excludes one",
              "marker from aligned content scoring. Art and immigrant children have no aligned-owner",
              "difference. These comparisons count reference-aligned tokens, not the ledger totals.", "",
              "Spanish list-item F1 is .890553 and anatomy .887994. The earlier Spanish pre-table",
              "list score .895674 is not the same final table-owned view. Anatomy main-flow order",
              "changes from .933847 to .962046, float anchors from .606 to .577830 and within-float",
              "order from .930191 to .995577 as figures, boxes and tables acquire explicit output",
              "ownership. These representation effects are reported rather than called unchanged",
              "accuracy. Complete list, nesting, index, bibliography and split/merge counts are in",
              "`json_eval/*.json`. Art still has four missed cross-page entries and one false join;",
              "Spanish has nine misses and two false joins. Continuity experiments did not fix them.", "",
              "### Cleanup counts", "",
              table(["Book", "Before unlinked figure-text/figure-stream paragraphs", "After embedded figure text", "After flagged figure-text paragraphs", "Covered spans before / suppression records after"],
                    [[name,
                      sum(data[key]["cleanup"]["before"].get(k, 0) for k in ("figure_text_units_in_paragraph_stream", "figure_stream_paragraphs")),
                      data[key]["cleanup"]["after"].get("figure_text_entries", 0),
                      data[key]["cleanup"]["after"].get("figure_text_paragraphs_left", 0),
                      f'{data[key]["cleanup"]["before"].get("hidden_spans_proven_covered", 0)} / {data[key]["cleanup"]["after"].get("suppressed_covered_by_paint", 0)}']
                     for key, name in BOOKS.items()]), "",
              "Embedded-entry totals also include text already linked in the archive; they are not",
              "net moves of the unlinked cohort. Confirmed hidden spans leave visible content but",
              "remain in suppression/source runs. Spanish additionally has 350 `not_rendered`",
              "suppression records. Suppression record counts are not ledger token counts.", "",
              table(["Book", "Items with marker before", "Structured markers after", "Glued markers flagged", "Index dividers after"],
                    [[name, data[key]["cleanup"]["before"].get("items_with_marker_in_text", 0),
                      sum(data[key]["cleanup"]["markers_as_structure_by_type"].values()),
                      data[key]["cleanup"]["after"].get("markers_kept_glued", 0),
                      sum(data[key]["cleanup"]["index_dividers_by_previous_kind"].values())]
                     for key, name in BOOKS.items()]), "",
              "The marker cohorts include table ownership and suppression changes; totals do not",
              "imply that every original marker became a new item. Marker type counts, original",
              "divider kinds and suppression-token reasons are retained per book in `cleanup`.", "",
              details, "", "## Review decisions and limitations", "",
              "- Keep the measured horizontal-Chinese PP primary policy and revised page flag, with",
              "  the stated sample/calibration limits. Vertical Chinese remains unreliable; Arabic",
              "  and Greek retain Tesseract. Scanned-page tables remain backlog.",
              "- Keep the column-start and broader-float continuity filters disabled: correct joins",
              "  were lost. Explicit equation inputs change no accepted joins and do not establish",
              "  a fix for the Statistics example. Its known I7 count remains one.",
              "- Review weak style agreement, unresolved figure ownership and alt-text slots. Names,",
              "  inline language splitting and model-generated alt text remain off by default.",
              "- Linked/uniquely contained figure text is embedded in `figure.text`. Ambiguous text",
              "  remains explicitly flagged: anatomy has 56 figure-text paragraphs; Statistics has",
              "  934, of which 914 have no surviving figure after table/equation ownership. The",
              "  remaining units cannot be assigned to a figure without evidence. No source text",
              "  is dropped. The before/after counts are in `cleanup/*.json`.",
              "- The OCR cover adds a book title; the prior title-page heading changes only role",
              "  and reasons, with the same ID/level. Body-style letter and candidate counters",
              "  include OCR evidence. English-only job settings also change native language",
              "  annotations on 319 pages: en→und 90, und→en 22, es→en 15, es→und 10 labels.",
              "  Every other non-OCR page field is identical. Those conditional detector scores",
              "  do not demonstrate better language accuracy. The complete audit is in",
              "  `final/book2_change_audit.json`; native text was never OCRed.",
              "- The cleanup audit missed 15 indirect fixture dependencies; they were restored",
              "  under exact current fingerprints. Preserve the deletion/restoration records and",
              "  include indirect dependencies in any future cleanup audit.", "",
              "The ledger keeps the existing benchmark token rule. Word segmentation for unspaced",
              "CJK remains later work; the new scan comparison uses character error rate. Script",
              "and text direction may remain unknown where the source provides no reliable evidence.", "",
              f'Free space at final gate measurement: **{gate["free_bytes"]:,} bytes** '
              f'({gate["free_bytes"]/1e9:.2f} GB decimal).',
              "The original approved plan hash is unchanged; no additional pruning was performed.", "",
              "ENT, mideast and the math hold-out were not run. Gold, reference XML, ledger, models",
              "and old projects were not edited. No NIMAS or other Stage 2 adapter work is included.", "",
              "See `experiments/out/step17/README.md` for evidence provenance and the final records.", ""]
    path.write_text("\n".join(lines), "utf-8")
    print(path)


if __name__ == "__main__":
    main()
