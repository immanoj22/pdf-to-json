# Step 4a-v: validation on unseen pages

I ran the Step 4a layout pipeline unchanged on 15 pages that it had never seen. No code, threshold or rule in `backend/` changed. No gold was written. Device policy was `auto`, which resolved to CPU on this machine. Step 4b has not started.

## Gate

| Gate | Result |
|---|---|
| pytest (backend, unchanged) | **121 passed** |
| 15 unseen fixtures: ledger missing / extra | **0 / 0 on all 15** ([text_gate.json](../experiments/out/step4av/text_gate.json)) |
| 15 unseen fixtures: cross-check against the original source page | **0 / 0 on all 15** (see below) |
| Full 758-page book | **495,751 retained tokens**, 0 / 0 against the frozen cache ([full_book.json](../experiments/out/step4av/full_book.json)) |

The cross-check reads the same physical page from the original source PDF directly with PyMuPDF (`rawdict`). It keeps lines whose centre is inside the TrimBox and tokenizes them with the benchmark tokenizer. This shows that cutting the fixture lost no text and added none.

## Part 0: decisions recorded

[decisions.md](decisions.md) records the following:

- A box that holds a whole section is a callout scope with its own bands.
- A caption box is a callout with a caption child.
- Card text is proposed as `sidebar`.
- Column gold and role gold stay `human_approved: false`.

## Pages

These pages were approved in Part 1. All five reference PDFs were present. The art-therapy index and the Canadian index are reached through the `downloads` path in `references.toml`. The fixtures are in `experiments/fixtures_unseen/`. Their source SHA-256 and fixture SHA-256 are in [fixtures_manifest.json](../experiments/out/step4av/fixtures_manifest.json). The selection evidence is [candidates.md](../experiments/out/step4av/candidates.md), [contact_sheet.png](../experiments/out/step4av/contact_sheet.png) and `page_stats.jsonl`.

**No 3-column prose page exists in these PDFs.** 3-column behaviour is therefore tested on indexes only (u01, u02).

| ID | Source, physical page | Covers |
|---|---|---|
| u01 | art-therapy index p3 | 3-column index |
| u02 | science p709 | index: banner, then 3 columns |
| u03 | Spanish 758-page book p700 | 4-column index |
| u04 | Canadian index p200 | scanned page with an invisible OCR layer |
| u05 | Immigrant Children p1 | image only, no text |
| u06 | science p656 | ruled table |
| u07 | Immigrant Children p71 | table rotated 90° |
| u08 | Immigrant Children p206 | table without rules, then prose |
| u09 | science p11 | unframed cards |
| u10 | science p113 | full-width figure strip |
| u11 | Spanish p654 | full-page map |
| u12 | Spanish p675 | bilingual glossary (ruled two-column table) |
| u13 | science p696 | bilingual glossary (English and Spanish columns) |
| u14 | Spanish p145 | framed sidebar beside a wide column |
| u15 | science p299 | narrow column next to a wide one, no frame |

## Bands, columns and regions per page

Each band is written as y-range: **columns** [lanes] confidence. "callout" marks a band inside a callout scope. ⚑ means the band needs review. Column counts include text-column lanes only. Overlays and complete `PageLayout` JSON for each page are in `experiments/out/step4av/uNN_*_regions.{png,json}`.

| ID | Bands | Region types | Flags |
|---|---|---|---:|
| u01 | y26–37: **1** [column] 0.70<br>y53–623: **3** [column, column, column] 0.85 | main_text 3, header_footer_candidate 1, page_number_candidate 1 | 3 |
| u02 | y45–117: **1** [column] 0.70<br>y119–801: **3** [column, column, column] 0.85 | artifact_candidate 8, main_text 4, heading_candidate 4, header_footer_candidate 1 | 7 |
| u03 | y71–82: **1** [column] 0.70<br>y96–117: **3** [column, column, column] 0.70<br>y115–798: **4** [column ×4] 0.85 | main_text 8, artifact_candidate 7, header_footer_candidate 2, page_number_candidate 1, heading_candidate 1 | 6 |
| u04 | none | unknown 44 | 45 |
| u05 | none | none | 1 |
| u06 | y27–761: **1** [caption, column] 0.55 ⚑<br>y138–200: **1** [column] 0.85<br>y220–236: **0** [table] 0.75<br>y676–748: **0** [table] 0.75<br>y788–802: **1** [column] 0.70 | caption_candidate 12, artifact_candidate 7, table_candidate 6, figure 2, main_text 1, heading_candidate 1, header_footer_candidate 1 | 1,557 |
| u07 | y48–57: **1** [column] 0.70 | credit_candidate 109, artifact_candidate 77, main_text 2 | 10 |
| u08 | y48–580: **1** [column] 0.85 | main_text 4, artifact_candidate 4 | 0 |
| u09 | y45–117: **1** [column] 0.70<br>y95–330: **0** [figure] 0.80<br>y347–449: **1** [column] 0.85<br>y454–516: **4** [column ×4] 0.85<br>y532–564: **1** [column, unknown, unknown] 0.40 ⚑<br>y568–590: **4** [column ×4] 0.70<br>y611–801: **1** [column] 0.85 | main_text 12, artifact_candidate 7, heading_candidate 3, header_footer_candidate 1, caption_candidate 1, title_candidate 1, figure 1 | 13 |
| u10 | y66–227: **1** [column] 0.85<br>y234–270: **0** [callout] 0.80<br>y285–404: **1** [column] 0.85<br>y422–594: **0** [figure] 0.80<br>y591–649: **1** [column] 0.85<br>y660–779: **0** [callout] 0.80<br>y783–828: **1** [column] 0.70<br>callout y236–268: **1** [column] 0.70<br>callout y664–747: **1** [column] 0.85 | artifact_candidate 7, main_text 4, heading_candidate 4, callout 3, caption_candidate 1, header_footer_candidate 1, credit_candidate 1, figure 1 | 37 |
| u11 | y0–915: **0** [figure] 0.80 | artifact_candidate 102 (95 whitespace-only lines, 7 outside the TrimBox), figure 1 | 4,370 |
| u12 | y18–838: **3** [column, column, column, figure] 0.80<br>y71–118: **1** [column, unknown] 0.40 ⚑<br>y121–238: **2** [column, column, unknown] 0.40 ⚑<br>y508–684: **2** [column, column, unknown] 0.40 ⚑<br>y693–798: **1** [column, unknown] 0.40 ⚑ | main_text 21, artifact_candidate 8, heading_candidate 3, caption_candidate 2, header_footer_candidate 1, figure 1 | 269 |
| u13 | y27–243: **0** [figure] 0.80<br>y163–536: **2** [column, column] 0.85<br>y556–579: **1** [column] 0.70<br>y579–749: **2** [column, column] 0.85<br>y787–801: **1** [column] 0.70 | artifact_candidate 8, main_text 4, caption_candidate 1, title_candidate 1, heading_candidate 1, header_footer_candidate 1, figure 1 | 1,518 |
| u14 | y57–472: **1** [sidebar, column] 0.75<br>y474–509: **1** [unknown, column, margin] 0.40 ⚑<br>y529–798: **1** [column] 0.75<br>callout y155–214: **1** [column] 0.85<br>callout y219–315: **0** [table] 0.75<br>callout y426–462: **1** [column] 0.85 | heading_candidate 8, main_text 7, artifact_candidate 7, callout 2, footnote_candidate 1, header_footer_candidate 1, page_number_candidate 1, sidebar 1, figure 1, table_candidate 1 | 290 |
| u15 | y69–420: **1** [column] 0.75<br>y445–616: **1** [column] 0.85<br>y627–678: **0** [callout] 0.80<br>y690–774: **1** [column] 0.85<br>y783–828: **1** [column] 0.70<br>callout y630–675: **1** [column] 0.85 | main_text 6, artifact_candidate 5, heading_candidate 3, caption_candidate 1, header_footer_candidate 1, credit_candidate 1, figure 1, callout 1 | 414 |

## Review flags grouped by cause

Counts are totals over the 15 pages; [review_flags_by_cause.json](../experiments/out/step4av/review_flags_by_cause.json) has them per page.

| Cause | Count | Pages carrying most of it |
|---|---:|---|
| Visual object: no visible in-page bounds | 4,678 | u11 1,848; u06 1,362; u13 1,362; u14 106 |
| Visual object: unknown role (insufficient native evidence) | 2,425 | u11 1,620; u12 254; u14 165; u15 161 |
| Visual object: clip/group graphics state | 1,329 | u11 872; u15 247; u06 89; u13 72 |
| Region: unknown, invisible text layer | 44 | u04 only |
| Visual object: non-normal blend | 21 | u11 20, u09 1 |
| Visual object: overpainted image | 17 | u06 10, u15 5, u11 2 |
| Visual object: paint association unavailable | 10 | u11 8, u14 2 |
| Visual object: broad filled band may be a local backdrop | 9 | 7 pages, 1–2 each |
| Band: low confidence 0.40, with an unknown lane | 6 | u12 4, u09 1, u14 1 |
| Band: low confidence 0.55 | 1 | u06 |

No region other than the u04 invisible-text lines fell below the 0.6 unknown threshold.

## Scanned and no-text pages

- **u04, Canadian index (scan with an OCR layer).** Native text does exist: 337 spans and 448 tokens, all invisible (render mode 3). The page image got the Step 3 role **`scan_layer`** (one object, 0.97). The ledger keeps all 448 tokens in nodes (0 missing / 0 extra). The layout step does not use invisible text for structure. Its 44 visual lines become `unknown` regions marked "Invisible text layer; review before use", and the page has **no bands and no columns**. OCR was not run, and no OcrEngine exists yet.
- **u05, Immigrant Children cover.** There is **no native text**: 0 spans and 0 tokens. The one image gets role `unknown`, not `scan_layer`, because no text lies over it. There are no lines, bands or regions. OCR was not run.

## Pages that look wrong (not fixed)

**Body text absorbed into figures.** These are the most serious failures. Text inside the figure box becomes embedded figure text, so it leaves the main flow.

1. **u15, narrow next to wide.** Figure 5's block grows downward over the heading "Electromagnetic waves interact with matter" and the first two lines of the paragraph below it. These 3 lines become embedded text of the figure. The narrow caption column on the right is not found as its own lane, so the band reads as 1 column, and only "Figure 5 As an" is a caption.
   - Probable rule: figure clustering in `blocks.py` ("Adjacent unresolved artwork joined as connectors") joins local leader-line artwork. `regions.embedded` then claims every line inside the enlarged box.
2. **u06, ruled table.** A figure joins the banner's triangle artwork, the side tab and the right half of the table. It holds 74 lines, including the Precaution and Remedy cells. This creates a band from y27 to y761 with confidence 0.55 that overlaps the other bands. The table splits into 6 `table_candidate` regions at its heavy rules. The row labels become 12 `caption_candidate` regions, and the icon column becomes a figure.
   - Probable rule: the same connector chaining, plus table grids cut at each thick rule.
3. **u09, unframed cards.** The grey reviewer panel is a raster. Together with the "Authors" heading and the first author row, it forms one figure with 48 embedded lines. The other card grids read as 4 columns, which matches the known limitation. The "Authors" row of 3 cards reads as 1 column. The "Contributing Writers" heading band has unknown lanes.
   - Probable rule: in `blocks.py`, a Step 3 `content_image` behind text is used as a figure seed instead of a backdrop or panel. Cards without frames have no rule that tells them apart from columns.
4. **u11, full-page map.** The figure block covers the whole MediaBox (0–915). The CONÉCTATE footer bar text is embedded in the map figure instead of staying furniture. The map labels are correctly embedded in the figure.
   - Probable rule: figure seeds take the bbox of the page-size clip or image without limiting it to the content frame.

**Structure that is missed or not detected.**

5. **u07, rotated table.** All 109 rotated cells become `credit_candidate` ("Rotated small text outside figures"). No band, table or column is built for the rotated content; only the running head forms a band.
   - Probable rule: `pipeline.ownership` sets rotated lines aside as "rotated", outside band segmentation, and the region typing then treats every one of them as a credit.
6. **u08, table without rules.** The table reads as plain `main_text` in a 1-column band, with no table candidate. The running head "Immigrant Youth in Portugal" and the folio "195" at the top are `main_text`, not header or page number.
   - Probable rule: table candidates in `blocks.py` need a ruled grid. The header and page-number cues in `pipeline.build_regions` were tuned on the Step 4a fixtures and do not fire for this book's top furniture. That second point is unconfirmed.
7. **u12, bilingual glossary.** A decorative tab running the full page height on the right edge becomes a `figure` lane. That produces a band from y18 to y838 that overlaps four smaller bands, all at confidence 0.40 with unknown lanes. The "(pág. N)" column becomes its own column lane, so the large band reads as 3 columns.
   - Probable rule: in `bands.py`, tall edge artwork opens a gutter and lane across the whole page. The page-reference column is treated as a text column, and nothing stops bands from overlapping.

**Smaller defects.**

8. **u03, Spanish index.** The first two text rows are split off as a separate 3-column band (y96–117) that overlaps the 4-column band below it. The fourth column's first lines fall into lane 3. "Hallelujah, i217" is a `header_footer_candidate`.
   - Probable rule: a band boundary in `build_bands` where the rule above the index ends, and header typing driven by style contrast.
9. **u13, science glossary.** The banner art and the side tab become a figure that embeds the guide word "vida media/inercia" and the "Glossary/Glosario" tab, and it overlaps the first 2-column band. The letter "H" is a `title_candidate` and the guide word "half-life/inertia" is a `caption_candidate`. Both column bands are otherwise correct.
10. **u14, sidebar.** The sidebar, its callout, the table inside it and the main column are correct. The chart legend lies outside the chart's figure. Its right half becomes a `sidebar` region in a "margin" lane, inside a band with confidence 0.40. A glossary note under a rule is a `footnote_candidate`, which is plausible but unconfirmed.
11. **Inverted lanes.** u09, u12 and u14 have `unknown` lanes with x1 < x0, for example [466, 242] and [626, 614]. The `Lane` model does not reject these.
    - Probable rule: lane construction in `bands.py` for gutters beyond the band's content edge.

**Pages that look right:** u01 and u02 (3 columns), u03's main 4-column band, u10 (full-width figure band, figure labels in a callout strip, vocabulary callout, vertical credit), u13's two column bands, and u14's sidebar lane. u04 and u05 are handled conservatively.

## Notes

- `u11_spanish_fullpage_map.pdf` is 47.7 MB because the map raster is embedded, so it is **not tracked** (`.gitignore`). `python experiments/recreate_unseen_fixtures.py` recreates any missing fixture from [fixtures_manifest.json](../experiments/out/step4av/fixtures_manifest.json) (source key, physical page, source and fixture SHA-256) and refuses a digest mismatch. Fixtures are cut byte-reproducibly (no random trailer `/ID`); re-cutting changed only fixture digests and ID-derived ordering, not any band, lane or region.
- The selection statistics (`step4av_scan.py`) read the PDFs with PyMuPDF directly. They are an offline selection aid; extraction still goes only through the Extractor.
- Reproduce with: `cd experiments; python step4av_scan.py; python step4av_select.py; python step4av_run.py`.

**Step 4a-v stops here.**
