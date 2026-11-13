# Step 22 add-on: titles, split sentences, front matter, heading levels, safe refresh

Branch `step22-addon` (on the bug-fix commit). General rules only; no book, page or font
rules, and no new hard-coded words: the rules use digits, letter case, layout and style. The
sectioning-word lexicon gained "appendice" and "allegato" (and Italian reference-list
titles), with a test in Italian, Spanish, French and German.

| # | Fix | Where |
|---|-----|-------|
| 1 | The printed opener number of a part/chapter heading ("1" above, "2" below the title) is the division's label, never title text; used as the label when it runs on from the previous one, otherwise kept in the title and listed for review. A numbered heading whose start holds only artwork and a list (a section opener listing its chapters) opens a part. A sectioning word set smaller than the open numbered chapter ("PART I" inside chapter 1) is a heading inside it | adapter `outline.py`; Stage 1 `hierarchy.py` |
| 2 | A full line without sentence punctuation followed by a lowercase line stays one paragraph inside a hanging-indent block and across a line typed as a caption; a list item may continue as plain text at the top of the next page | Stage 1 `paragraphs/segment.py`, `crosspage.py` |
| 3 | A lower-case roman numeral alone ("vi") is never a heading, so a front-matter page takes its title from its printed heading or banner and the next page continues it | Stage 1 `headings.py` |
| 4 | A printed heading style that prints many unique titles in the running text is one level, recurring titles included; headings placed by style alone take their style's usual level (never creating a level skip) | Stage 1 `decide.py`, `hierarchy.py` |
| 5 | Review list refresh builds in `preview.tmp/` and swaps by rename; reads take a short swap lock; a refresh with unchanged edits (and unchanged adapter code) does not rebuild. Test: two simulated reviewers, one refreshing while the other reads | app `service.py`, `api.py` |

Side fixes found on the way: a page ending with a numbered list after running text is judged
as a list from that list on (layout evidence; it had turned ART p31's "CONCLUSION" into
plain text once paragraphs stopped being split line by line).

## Before → after

| | Ultrasound | PULSE | Hypertension | ART | IAP |
|---|---|---|---|---|---|
| Part/chapter titles with a number | 20 → **0** (5 sections, 14 chapters) | 0 → 0 | 15 → **0** | 22 → **0** | 29 → 9 ¹ |
| Split sentences | 11 → **0** | 31 → **7** | 9 → 2 | 29 → 2 | 139 → 24 |
| New joins | 10 | 22 | 7 | 25 | 116 |
| Front-matter titles | — | "", "vi" → **Contributors** | same | same | same |
| Heading level changes | 133 (one level per style) | 10 (ch. 1 sections to level 2) | 0 | 0 | 1 |
| Tokens lost / gained | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| DTD / lossless / house rules | 0 / 0 / 0 (DTD was 2) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| I1–I7 | — | — | 0 | 0 | 0 |

¹ IAP: Stage 1 makes two extra chapter headings (a bare "23", a list line "38. Using AI…"), so
from chapter 23 the printed number trails the count by one; the number then stays in the
title as printed (safe rule) and is listed for review.

Hand check of 30 new joins (22 PULSE, 8 ART): 30 correct, precision 1.00.
PULSE's "CHAPTER 1 · 1 Knobology": the delivery already reads "CHAPTER 1 / Knobology…";
the "1" is the Stage-1 heading text (kept losslessly), which the Browse panel shows raw.

Tests: core + adapters 1498 passed, 7 skipped (before the last structure fixes; re-run on
main); app 53 passed, 1 skipped; browser e2e passes alone.
