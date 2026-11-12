# Step 22 bug fixes (reviewer report, Ultrasound book)

Branch `step22-fix`. General rules only; no book, page, coordinate or font rules.

| # | Bug | Fix | Result |
|---|-----|-----|--------|
| 1 | Text of a neighbouring column woven into a sentence (Ultrasound p34, axillary block) | Column gutters: a right column whose rows begin with indented first lines still shows its gutter (`layout/lines.py`, first-line indent allowance next to the hanging-indent one). New check `evaluation/line_order.py` + `experiments/step22_line_order.py`: a unit whose words jump back and forth between two runs of native PDF lines is flagged | Ultrasound woven units 1 → 0; IAP 8 → 7 (the 7 on pp130, 182, 207 were there before and remain — recorded, not fixed here) |
| 2 | Index read across columns | Index pages: lines are put in column order (top of each column first; a title above both columns stays first) before entries are built (`lists/glossary.py` `column_order`, `lists/page.py`) | Ultrasound index pages read column by column; Hypertension p85 index unchanged |
| 3 | "Index" banner duplicated in the index | Not reproducible: the banner is decorative in book.json and the delivery writes "Index" once as the index title. If seen in the app's Browse view it is the banner picture beside the heading text; needs the reviewer's screen to confirm | no change |
| 4 | "Figs. 1A and B" rewritten as "Fig. 1A" | A label naming several figures is written as printed (`LABEL_MORE`, `Figure.verbatim_label`); house rules accept the printed form | label text never changes |

## Gates

| Book | Tokens lost / gained | Pages with order changes | DTD | Lossless missing | House rules | I1–I7 |
|------|------|------|-----|-----|-----|-----|
| Hypertension | 0 / 0 | 0 | 0 | 0 | 0 | 0, owned once |
| ART | 0 / 0 | 0 | 0 | 0 | 0 | 0, owned once |
| IAP | 0 / 0 | 4 (pp100, 117, 205: bug-1 fix un-weaves columns; p326: index order) | 0 | 0 | 0 | 0, owned once |
| Ultrasound | 0 / 0 | 2 (p34 bug 1, p71 index) | 2 (before: 2) | 0 | 0 | — |

Token counts include list-item markers ("3." on IAP p117 moved from a woven paragraph into
its list item's marker; `experiments/step22_tokens.py` now counts markers).
Ultrasound's 2 DTD errors predate this step (a bibliography inside a callout box).

Tests: core 1355 passed, 7 skipped; adapters 134 passed; app 51 passed, 1 skipped. The
browser end-to-end test timed out once at 180 s while all 8 cores ran books; run alone it
passed (2 passed, 1 skipped).
