# Step 18 — sealed hold-out results, 24 October 2026

## Results

**Two books completed; the math book failed in layout validation. ENT did not
pass the lossless or every-page invariant requirements. Mideast passed those
robustness checks, which does not establish semantic accuracy.** No converter,
profile, setting, threshold or scoring algorithm was changed to improve a result.

| Book | Terminal result | Whole-book requirements | Accuracy conclusion |
|---|---|---|---|
| ENT textbook, 612 pages | Attempt 2 completed after the approved environmental retry | Schema/contract/hash checks pass; missing tokens 0, **extra tokens 10**; I1–I6 zero, **I7 42** | Paragraph F1 within the registered band; order, heading levels and sampled math typing weak; reference covers only 43 located pages |
| OpenStax Algebra and Trigonometry 1e, 1,220 pages | **Code failure on physical page 348**, after 347 validated layouts | No complete archive/publication; subsequent gates unmeasured | No equation/table or other accuracy score; no code fix or retry |
| Mideast, 317 pages | Completed | Schema/contract/hash checks pass; lossless 0/0; I1–I7 zero | No matching reference: robustness and descriptive findings only |

The owner expected results at the low end of the development bands or below
because development books were tuned. In-band scores are unsurprising. The
apparently superior list and table scores below have substantial denominator or
scoring limitations; they do not demonstrate broad improvement.

The final machine-readable report is
[results_v2.json](../experiments/out/step18/results_v2.json). The initial assembled
[results.json](../experiments/out/step18/results.json) is retained unchanged;
v2 adds disclosures for registered OCR/RTL/figure components, without replacing
any evaluator result. It contains all **M01–M18 for every book**, the original
registry/computations, raw components, samples and uncertainty. The tables here
use proportions in 0–1 units. “Unmeasured” is not zero; N/A means no applicable
feature in the supported scope. Development bands below are the pre-registered
planning bands, not acceptance thresholds or confidence intervals.

### ENT: all 18 registered metrics

Operational checks cover 612 pages. Reference scores are conditional on the
**43 located reference pages**, not the complete book or all 46 reference markers.

| ID | Result and denominator | Registered development context | Direction / interpretation |
|---|---|---|---|
| M01 completion/schema/contracts | 612/612; schema 0; contract defects 0/32,864 units; JSON round-trip equal; archive/publication manifest mismatches 0 | Completes; zero defects | Positive for completion/contracts; does not override M02/M03 |
| M02 token accounting | Retained 361,637; content 357,246 plus furniture 4,401; missing 0, **extra 10**; explicit discard 0 | Required missing/extra 0/0 | **Negative / failed**; list-marker replication or wrong attachment |
| M03 every-page invariants | I1–I6=0; **I7=42** on 612 pages; ownership/order-once booleans both true | Every invariant zero; old Statistics I7=1 is not an exemption | **Negative / failed** |
| M04 paragraphs | Page P .926152, R .940778, F1 **.933408**, exact 1,429/1,774=.805524; chained P .926626, R .940214, F1 **.933371**, exact 1,428/1,774=.804961 | Page F1 .85–.95; chained .90–.95; exact .68–.90 | Mixed within band; page split/merge 133/230; chained 131/232 |
| M05 reading order | Main agreement **.893759**, tau **.787519**; anchor 41/82=**.5**; within-float **.998498** over 33,300 pairs; internal archive agreement 8,738/8,738=1 | Main .96–1; tau .92–1; anchor .55–.90; within .94–1 | **Negative** main/tau/anchor; positive within-float, with scope limits |
| M06 lists | 2/2 reference items scored: item P/R/F1/exact=1; one list boundary P/R/F1=1; **kind agreement 0**; nesting denominator 0, null | Item F1 .85–.92, exact .70–.85; list boundary .50–.70; nesting .75–.85 | Mixed; above-band values come from only two items; no nesting conclusion |
| M07 tables | 11 reference page segments, 10 predicted/matched: P=1, R=.909091, F1=.952381; structure/full TEDS **.9701**, exact 3/10=.3; adjacency P .9647/R .9968/F1 .9805; header-row exact .4, header-token .992, header-association .7363 | P .88–1, R .65–1; structure .80–.98, full .78–.95 | Mixed; six original reference tables, no problem-table exclusions; full TEDS is order-blind within cells |
| M08 joined tables | One reference multi-page table, one scored; structure/full/whole-only TEDS **.983**; continuation 5/5 correct, 3 other links unscored | Historical joined structure .9258/.9586, full .8516/.8635, whole-only .9702/.9961 | Mixed; tiny matched cohort, same within-cell limitation; repeated-header role defects remain |
| M09 equations | Reference has 0 math equations: strict/expression exactness, symbols, tree distance and coverage N/A | No ENT math truth expected | N/A; emitted whole-book math is not truth |
| M10 figures/captions | Page-count proxy 31 matches/41 predicted/35 reference: P .756098, R .885714; caption coverage 17/20=.85; link correctness 18/29=.62069 | Figure P .50–.93/R .60–.95; caption .30–.65 | Mixed; label/name/credit accuracy unmeasured; 416 published figures and 210 figure-text units are counts |
| M11 continuity | Frozen archive links: 2 correct, 2 wrong, 62 unscored; scored P **.5**. Reference cross-page paragraphs 1/5 joined, 4 missed; 11 within-page reference continuations missed | Desired .95–1; historical anatomy cohort 2/3, not a population baseline | **Negative**, very small scored denominator; visual samples separate below |
| M12 headings | Ref 66, predicted 78, scored predicted 75: P 50/75=.666667, R 48/66=.727273, F1 .695652; level exact 18/48=**.375**, within-one 37/48=.770833 | P .60–.97; R .73–.93; exact level .75–.87 | Mixed P, slightly below-band R; **negative levels**; visual census also weak |
| M13 entries/typing/folios | Covered index/bibliography/cross-page entries 0, definition result empty: no accuracy denominator. Body printed-label/placement 22/22=1. Front-label accuracy unmeasured. Visual census: 13/14 folios correctly furniture; genuine notes 0/4 typed, 5 table cells wrongly notes; formal glossary 0 | Index exact .85–.95/level .95–1, glossary .90–.98 only if present; body labels .99–1; no footnote band | Mixed; body labels positive, note typing poor; no full-book index/glossary claim |
| M14 OCR | Native 612, production OCR 0; OCR word/line/page flag rates N/A. CER/WER/character-multiset F1 unmeasured: no paired transcript | Mostly native; no supported CER band | Descriptive / unmeasured |
| M15 language/script/direction | Book English share .9965; 30,025 text records all script/direction unknown; eligible emitted RTL units/pages 0 | Predominantly English prior; no accuracy baseline | Descriptive, no language or RTL accuracy score |
| M16 styling | Aligned reference recall italic .9842, bold .9676, super .25, sub 0, links 0; per-kind P and body splits below. Visible bold 20/20, italic 20/20, superscript 19/20; math 1 correct/6 wrong/2 unclear | Tentative visible .75–1; reference conventions separate | Mixed; **negative math typing**, low rare-style recall partly measurement/representation limited |
| M17 review workload/safety | 1,918 items, 1,681 distinct targets; **3.134/page**, **58.362/1,000 content units**. Source-first heading capture **1/35**; footnote typing capture 5/6 dedup units, but genuine notes all missed; folio capture 0/1 | Workload .3–4/page; no general safety threshold | Within workload band; **weak observed safety coverage**; no full-book recall estimate |
| M18 resources | Retry wall 5,150.139s; 500ms outer peak 2,613,755,904 B, built-in 20ms peak 3,006,484,480 B; min free 87,909,453,824 B; detailed stages/reuse below | No hard time/RAM target | Measured, warm retry; not fresh whole-pipeline time |

### Math hold-out: all 18 registered metrics

| ID | Result | Development context | Direction / interpretation |
|---|---|---|---|
| M01 | **Failed** `layout.build_layout.PageLayout.validation`, page 348; 347/1,220 validated layouts; duplicate region `fd1a1e3664d0:table_candidate`; no complete archive/publication | Completes all pages, zero defects | **Negative code failure** |
| M02 | Missing/extra/discard/ownership totals unmeasured: no complete publication | Required 0/0 | Unmeasured after failure |
| M03 | Every-page I1–I7 and ownership/order proof unmeasured | Zero expected | Unmeasured after failure |
| M04 | Paragraph boundaries/exactness/splits/merges unmeasured | No independently supported paragraph truth | Unmeasured: failure and truth limitation |
| M05 | Reference and JSON-vs-archive main/float order unmeasured | Internal agreement 1 expected; no prose reference accuracy | Unmeasured after failure |
| M06 | Item/list boundaries, exactness and nesting unmeasured | CNXML is not list truth | Unmeasured: failure and truth limitation |
| M07 | Detection, TEDS, adjacency and header scores unmeasured | P .85–1/R .75–.95; structure .90–.98/full .85–.95 conditional on supported coverage | Unmeasured after failure |
| M08 | Joined tables, repeated headers and continuation scores unmeasured | Structure .92–.97/full .85–.90 conditional | Unmeasured after failure |
| M09 | Equation detection/completeness, strict/expression exactness, symbol/tree distance, inline/display and review splits unmeasured | Strict exact .80–.90/symbol .95–.99; expression exact .75–.85/symbol .90–.97 | **Primary math accuracy unavailable**; no substitute partial-page score |
| M10 | Figure/caption/credit/location and export counts unmeasured | No independent located figure truth registered | Unmeasured after failure |
| M11 | Paragraph/list/entry/table page/column continuity unmeasured | Desired .95–1 where supported | Unmeasured after failure |
| M12 | Reference and seeded heading/level/role census unmeasured | No heading gold; diagnostic expected | No publication for comparison |
| M13 | Index/glossary/bibliography/note/folio typing unmeasured | No independent entry truth | No publication for comparison |
| M14 | Production OCR usage/counts/flags/CER/WER/multiset F1 unmeasured | Native expected; no paired transcript known | Failed before complete usage evidence |
| M15 | Output language/script/direction, RTL and mixed/native decisions unmeasured | English prior, no scored truth | No complete output |
| M16 | Reference and visible style samples unmeasured | Tentative visible .75–1, no CNXML style truth | No complete output |
| M17 | Review counts/rates/capture/correctness unmeasured | Rough workload 2–5/page | No review list |
| M18 | Wall **924.365s**; peak **672,153,600 B**; min free **87,774,904,320 B**; source 86,392,139 B; partial cache 112,480,466 B | No hard time/RAM target | Measured failed attempt, not full-book cost |

The rendered failure page is a collection of scatter plots/exercise graphs
(printed page 330), not a normal rectangular table. Read-only inspection found
that the duplicate identifier's prefix equals the hash of empty line/object
evidence. The frozen region key omits geometry/type/scope. The failed layout was
not persisted, so the exact colliding region pair was **not reconstructed**;
there was no layout rerun. Evidence supports investigating unique identities
for empty-evidence candidates, not asserting a fully proved collision path.

### Mideast: all 18 registered metrics

Directions here describe operational success or observations; **there is no
reference accuracy, visual accuracy percentage, or safety-recall estimate**.

| ID | Result | Development context | Direction / interpretation |
|---|---|---|---|
| M01 | 317/317; schema/contract defects 0/5,969 units; round-trip/content equal; manifest mismatches 0 | Complete, zero defects | Positive robustness |
| M02 | Retained 258,775 = content 258,457 + furniture 314 + retained suppressed 4; missing/extra 0/0; discard 0 | Required 0/0 | Positive token-accounting check |
| M03 | I1–I7 all 0 on 317 pages; ownership/order-once true | All zero | Positive invariant check |
| M04 | All paragraph accuracy components unmeasured | No reference | No accuracy verdict |
| M05 | Internal archive adjacent-pair agreement 4,288/4,288=1; reference main/tau/anchors/within-float accuracy unmeasured | Internal 1 expected | Positive parity only |
| M06 | All item/list/nesting accuracy unmeasured | No reference | No accuracy verdict |
| M07 | One published table; detection/TEDS/adjacency/header accuracy unmeasured | No reference | Descriptive table defects below |
| M08 | Joined-table/repeated-header accuracy unmeasured | No reference | No accuracy verdict |
| M09 | Math detection/completeness/MathML/symbol/tree accuracy unmeasured | No reference | Descriptive sampled math typing below |
| M10 | 291 figures: 202 photo/JPG, 89 drawing/PNG; 138 figure-text units; export bytes 105,847,981; accuracy and converted-vs-original denominator unmeasured | No located figure/credit truth | Descriptive |
| M11 | 69 paragraph page, 33 paragraph column, 3 list page, 1 list-item column links; reference accuracy unmeasured | Counts only | Descriptive endpoint errors below |
| M12 | Census 20 pages: 17 source standalone headings, 1 represented correctly, 16 ordinary paragraphs; 20 running heads typed as headings | No heading gold | Descriptive weakness; no percentage |
| M13 | Census 20 printed folios all furniture; no genuine notes or glossary entries found; entry/note accuracy unmeasured | No reference | Descriptive, zero denominator for absent classes |
| M14 | 316 native pages; OCR page 1 only: Tesseract, 5 word records/3 line IDs/one region; 3 published review items =3/page, .6/word record, 1/line; comparison OCR on 29/30/175 not selected as production | Intake 310 text/1 image-only/6 little-text, no CER band | Usage only; CER/WER/multiset F1 unmeasured |
| M15 | English book share 1; text records 5,829: 1 Latn/ltr, 5,828 unknown/unknown; emitted RTL unit/page count 0 | English prior, no independent script/direction baseline | Descriptive, unknown preserved |
| M16 | Bold 20 correct; italic 19 correct/1 unclear; links 20 unclear; math 1 correct/1 wrong | Descriptive audit only | No accuracy percentage |
| M17 | 698 items/646 distinct targets; **2.202/page**, **116.938/1,000 content units**; 3 must-check +695 needs-review | Rough workload 0–5/page | In workload band; no safety accuracy claim |
| M18 | Wall **11,248.440s** including observed 1,485.488s OS sleep; outer peak **3,588,759,552 B**; built-in peak **3,607,994,368 B**; min free **86,634,754,048 B** | No hard time/RAM target | Measured, environmental interruption disclosed |

## Scope, frozen identities and scoring limits

The tag remains `holdout-freeze-1` at
`8d6a0b0036db3f28dd8b671a2950ceca9918a680`. Pre-registration commit:
`781eb222273461c084a85cc0aef767c25f952796`; addendum commit:
`ba8897c05fea63aa903a1b56dd4a72404cde4018`. Protocols remain unchanged:
[pre-registration](step18_preregistration.md),
[addendum](step18_preregistration_addendum.md).
Default profile `default` v1.0.0 canonical SHA-256:
`cbf9a8369859f4cd43c58370b2db3f5d9988ea21e6544b4cef4a23ddcfb2216d`;
file SHA-256 `85b4d469b6322fcfa086a4a112306c539ea9903fe700c81fda37d26cc200ce2a`.
The source hashes and attempt start/end identities are in the append-only
[hold-out ledger](../experiments/holdout_runs.jsonl).
Accepted Part 0 on the clean freeze had **1,197 tests passing**, Ruff passing,
standard development gates passing and fresh Spanish I1–I7 zero on 758 pages.
Those checks were not repeated after measurement-only documentation/evidence
changes; the frozen backend tree identity is verified again at close-out.

ENT's 46 reference markers resolve to **43 physical pages**:
1–5, 7–13, 15–17, 25–52. FM6/FM14/FM18 contain no locating tokens and stay
unlocated. Body labels 1–22 map to physical 31–52; FM19 maps to 25. The entire
reference has 24,534 tokens, originally 23,583 native-aligned. Forty-three aligned
tokens on ten uncovered pages were removed from scoring eligibility, not from
the originals. The separate scoped bridge was saved **before any score**:
23,540 aligned, 994 unmatched. All reference units and all 46 markers are retained;
unlocated units are not silently removed. Original and scoped hashes/mappings are
in [alignment evidence](../experiments/out/step18/ent_textbook/alignment_evidence/).
No accuracy denominator includes ENT's uncovered pages.

The list score has only two items because the supplied reference encodes most
visually list-like material as paragraphs. Kind agreement is zero. Table TEDS
uses the frozen scorer's **sets of source-ordinal tokens in each cell**; emitted
text order within a cell is absent from that cell label. Thus full TEDS can equal
structure TEDS while multiline prose is visibly reversed. Header roles are also
scored separately. Neither scorer was changed after seeing this limitation.
The .9701 full TEDS and perfect two-item lists are coverage/scoring caveats, not
evidence of improved generalisation.

The frozen figure reader produced no independent printed-label counts. Its raw
“page and printed label” proxy repeats the page-count result; independent label,
linked-name and credit accuracy remain unmeasured. Of 29 caption links, 18 were
correct, nine targeted reference paragraphs, one was unaligned and one a list.
Reference caption coverage was 17/20, above the .30–.65 planning band, but applies
only to this small supported subset. Page-count matching is not IoU/box accuracy.

The raw all-label result 22/43 includes 21 front identifiers such as FM labels,
which are not printed Roman-label truth. It is retained as raw output and is not
reported as front-matter accuracy. Actual sampled printed folio typing is a
separate rendered-source check. The native convention-class set is empty:
adjusted precision/F1 equal the raw .666667/.695652. Role confusions include
front-title→front-title 7, front-title→subsection 8, structural→front-title 2
and structural→subsection 31.

## Typing, styling and review safety

All **559 judgments** retain target IDs, agent verdict/reason, crop/context paths
and image hashes in the
[judgment register](../experiments/out/step18/measurement_evidence/audit/judgments.jsonl).
The owner re-judgment sample is
[20 selected records](../experiments/out/step18/measurement_evidence/audit/owner_audit_selection.json),
seed `20261024:step18:v1:audit`, selected from sorted stable judgment IDs after
all judgments were saved. Owner verdicts and agreement are **pending**. These
are agent judgments, **not independently verified judgments**.

Eligible populations and fixed SHA-ranked selections were recorded before
viewing; no redraws. ENT page 42 had prior output exposure and is explicitly
excluded from source-first safety recall. The typing census still describes
all 20 selected pages, with that exposure marked. The remaining 19 were read
from rendered source before comparing output. Actual model variants, including
`glossary_entry`, were checked rather than assuming one type spelling.

### ENT typing diagnostic

On all 20 pages: 61 standalone headings: 21 whole/correct, 36 missed, four
split/partial. There are 36 output heading nodes: 21 correct whole occurrences,
nine fragment nodes representing four partial source titles, four spurious
metadata/attribution headings and two ambiguous parent-label cases. Strict
whole-heading precision is 21/34=.6176 excluding the two ambiguous cases
(conservative 21/36=.5833); recall 21/61=.3443. These are sampled visual
diagnostics, not the reference M12 score. On the 19 source-first pages, the
corresponding values are 20/33=.6061, conservative 20/35=.5714, and 20/55=.3636.

Four genuine notes on one page are merged into one paragraph; none is typed as
a footnote. Five competency-table cells on another page are wrongly footnotes.
Of 14 printed folios, 13 are furniture and one (`xvii`) is included in a reviewer
paragraph; its inferred page label is nevertheless correct. Formal glossary
occurrences: zero. There is no glossary accuracy estimate.

### ENT independently discovered errors captured by review flags

“Independent” here means the source-first error-discovery stratum was not
selected from flags; the same agent performed the judgments. Deduplication is
within error class by page and sorted owning-unit IDs. Merged source occurrences
remain child IDs. No pooling across classes.

| Error class | Deduplicated errors | Captured by relevant flag | False negatives | Recall; Wilson 95% | Page-cluster bootstrap 95% |
|---|---:|---:|---:|---|---|
| Heading typing | 35 | 1 | 34 | .0286; [.0051,.1453] | [0,.0870] |
| Footnote typing, including false note units | 6 | 5 | 1 | .8333; [.4365,.9699] | [0,1] |
| Printed folio typing | 1 | 0 | 1 | 0; [0,.7935] | [0,0] conditional on resamples containing an error |
| Glossary typing | 0 | — | — | N/A | N/A |

The apparent footnote 5/6 is dominated by **five false note units in one table**.
The four genuine notes merge into **one** missed owning unit, and **none of those
four occurrences is captured**. It would be misleading to call 5/6 genuine
footnote recall. Bootstrap valid resamples: footnotes 886/1,000, folios 650/1,000;
the degenerate folio interval does not indicate population certainty. A caption
“missing link” warning does not capture an unrelated wrong heading even if it
targets the same owner. Full-book and complete reference-backed flag recall are
unmeasured; these 19 pages cannot establish deployment safety.

### Styling details and continuity samples

ENT per-token style pairs use 23,540 aligned reference tokens out of 24,534.

| Reference style | Reference / predicted / both | Precision | Recall | Body reference / predicted / both |
|---|---|---:|---:|---|
| Italic | 568 /579 /559 | .9655 | .9842 | 531 /531 /522 |
| Bold | 1,880 /2,254 /1,819 | .8070 | .9676 | 1,845 /1,923 /1,784 |
| Superscript | 8 /2 /2 | 1 | .25 | See native result, sparse denominator |
| Subscript | 1 /0 /0 | null | 0 | See native result |
| Link | 108 /0 /0 | null | 0 | 92 reference tokens |

Underline, small caps and language markup have no supported reference denominator.
Whole-publication style serialization matched 18,893/18,893 records; this is
parity, not visible truth. Detected-only visible samples show bold 20/20 and
italic 20/20 (Wilson [.8389,1]), superscript 19/20 ([.7639,.9911]), and math
1/7 adjudicated ([.0257,.5131]), with two additional unclear cases; conservative
math correctness 1/9=.1111. All six wrong math samples are anatomical labels or
ordinary list notation promoted to math. One superscript is a baseline control
glyph/bullet. No eligible emitted ENT subscript/underline span lies in the
43-page scope, although the whole book contains those kinds. No sample establishes
recall. Rare reference failures include four token-majority range cases, two
ambiguous alignment/range cases and one math-versus-style representation case.
Twenty sampled reference link omissions remain interaction/convention questions:
a raster cannot prove a live hyperlink existed in the PDF.

ENT visually checked continuity: list-column 13 correct/0 wrong/2 unclear;
list-page 6/1/0; list-item-page 1/1/0; paragraph-page 1/1/0; table-page 5/0/0.
Both endpoints and source context were viewed. These samples use the frozen
endpoint identity/continuation definition; correct identity can coexist with
misowned leading text. Reference archive metrics and final-publication visual
checks are different stages. Their numerators must not be combined.

Mideast descriptions: two erroneous paragraph joins skip the real continuation
or join unrelated sections; one sampled math span is the political designation
`P5+1`, the other a genuine dimension. Character warnings include 18 visible
errors and two unclear cases; caption warnings include 15 corresponding defects
and five wrong-role warnings. The cover OCR preserves the series/year but omits
the main title/edition/author/publisher. The one table visibly merges/reverses
country/header content. These are descriptive observations without accuracy
percentages.

The OCR comparison records on pages 29/30/175 were inspected as already stored:
705/442/11 word records and 116/81/1 line IDs respectively; none replaced native
production text. Production page 1 has five word-granularity Tesseract records,
three lines and one populated region. Its eight stored warnings differ from
three published page review items. Rates per word/line are workload ratios,
not error rates. No OCR engine rerun or alternative selection was used.

### Review workload by kind

Counts cover the complete books. Flags may repeat the same target; rates use
612 ENT pages and 317 Mideast pages. Math has no review list.

| Kind | ENT items | ENT /page | Mideast items | Mideast /page |
|---|---:|---:|---:|---:|
| alt_text | 401 | 0.6552 | 284 | 0.8959 |
| caption | 376 | 0.6144 | 328 | 1.0347 |
| character | 330 | 0.5392 | 50 | 0.1577 |
| credit | 0 | 0.0000 | 1 | 0.0032 |
| figure | 79 | 0.1291 | 2 | 0.0063 |
| footnote | 83 | 0.1356 | 0 | 0.0000 |
| heading | 278 | 0.4542 | 2 | 0.0063 |
| hidden_text | 0 | 0.0000 | 4 | 0.0126 |
| join | 14 | 0.0229 | 2 | 0.0063 |
| language | 6 | 0.0098 | 0 | 0.0000 |
| ocr_page | 0 | 0.0000 | 3 | 0.0095 |
| structure | 218 | 0.3562 | 20 | 0.0631 |
| table | 133 | 0.2173 | 2 | 0.0063 |

### Flag correctness: fixed strata, not pooled book precision

ENT sampling is restricted to the located reference scope. A cautious flag
without a demonstrated defect is kept separate from a definite wrong-role
warning. The error-share denominator below includes definite false and
cautious cases, but excludes unclear and unresolved requirements. Wilson
intervals are conditional on these adjudications, with within-page correlation.
No eligible scoped character flags were found despite 330 whole-book flags.

| ENT kind | Sample | Real error | Definite false | Cautious | Unclear / requirement | Error share; Wilson 95% |
|---|---:|---:|---:|---:|---:|---|
| footnote | 9 | 9 | 0 | 0 | 0 | 9/9=1.0000; [0.7009,1.0000] |
| heading | 9 | 1 | 0 | 7 | 1 | 1/8=0.1250; [0.0224,0.4709] |
| join | 2 | 0 | 1 | 0 | 1 | 0/1=0.0000; [0.0000,0.7935] |
| language | 1 | 0 | 0 | 1 | 0 | 0/1=0.0000; [0.0000,0.7935] |
| structure | 8 | 6 | 0 | 2 | 0 | 6/8=0.7500; [0.4093,0.9285] |
| alt_text | 20 | 0 | 0 | 0 | 20 | unmeasured |
| caption | 20 | 3 | 17 | 0 | 0 | 3/20=0.1500; [0.0524,0.3604] |
| figure | 15 | 0 | 0 | 15 | 0 | 0/15=0.0000; [0.0000,0.2039] |
| table | 7 | 0 | 0 | 7 | 0 | 0/7=0.0000; [0.0000,0.3543] |

Mideast uses descriptive counts only; these do not estimate flag precision.

| Mideast kind | Sample | Corresponding error | Definite false | Cautious | Unclear / requirement |
|---|---:|---:|---:|---:|---:|
| credit | 1 | 0 | 1 | 0 | 0 |
| figure | 2 | 0 | 0 | 2 | 0 |
| heading | 2 | 2 | 0 | 0 | 0 |
| hidden_text | 4 | 0 | 0 | 0 | 4 |
| join | 2 | 2 | 0 | 0 | 0 |
| ocr_page | 3 | 3 | 0 | 0 | 0 |
| table | 2 | 2 | 0 | 0 | 0 |
| alt_text | 20 | 0 | 0 | 0 | 20 |
| caption | 20 | 15 | 5 | 0 | 0 |
| character | 20 | 18 | 0 | 0 | 2 |
| structure | 20 | 4 | 0 | 16 | 0 |

Every sampled flag retains its specific reason. A real role error does not
make an unrelated missing-caption-link warning correct. Alt-text requirements
remain unresolved; they are not counted as demonstrated semantic defects.
Three Mideast must-check OCR warnings target one page, not three independent
errors. ENT structure warning positives also include duplicate targets on the
same erroneous owner. These samples cannot be pooled or weighted into a
whole-book safety percentage.


## Error taxonomy and generalisation gaps

Every below-band family was inspected on the fixed 20 errors, or all when fewer.
No page-specific fix was implemented.

| Family | Inspected / eligible | General cause counts | General rule needed later |
|---|---|---|---|
| Math M01 failure | 1 /1 | 1 code-identity/layout failure; empty-evidence hash mechanism observed, exact colliding pair unavailable | Candidate identity must remain unique even with empty evidence; validate graph/plot candidate ambiguity |
| ENT M02 | 10 /10 extra tokens | 10 ownership/split marker replications or wrong attachments | Bind each printed marker to source evidence and original item identity across splits/columns |
| ENT M03 | 20 /42 findings | 18 furniture/rotated-edge lane cases; 2 numeric-lane context limitations | Separate furniture and actual reading lanes; distinguish answer/matching/index content from locator columns without page rules |
| ENT M05 | 20 /2,518 inversion/anchor errors | 19 column/group ordering; 1 float-anchor convention/layout ambiguity | Order evidence must respect column groups and content/float anchors, without a global coordinate sort |
| ENT M11 | All 17 registered error rows | 11 within-page fragmentation/reference boundary; 4 role/boundary preventing cross-page joins; 2 wrong endpoints | Resolve owner identity and source sequence before linking; keep reference convention ambiguity explicit |
| ENT M12 | 20 /48 level/miss/role error candidates | 14 hierarchy/role; 6 missed/merged headings | Infer document hierarchy jointly with grouping; distinguish parent labels and real titles from captions/furniture |
| ENT M13 | 1 /1 observed folio error | 1 retained printed folio in body | Preserve folios as furniture with source evidence independently of inferred page-label correctness |
| ENT M16 reference | 20 /115 false-negative style tokens | 20 link-markup omissions; live PDF interactivity visually unclear | Separate reference semantic links from visible typography and retain supported interactive evidence |
| ENT M16 visible math | All 6 wrong samples | 6 anatomical/list notation misclassified as math | Require semantic/evidence support for math beyond letter-digit typography |
| ENT M16 rare reference supplement | All 7 rare misses | 4 token-majority range limitations; 2 alignment/range unclear; 1 math/style representation | Audit alignment and range semantics separately from actual glyph styling |

The M11 enumerator initially selected 15 rows and omitted two explicit
`verdict=wrong` rows. The error was corrected **before viewing taxonomy crops**:
all 17 were inspected, with the original population/selection and correction
receipt retained. No sampled case was discarded or replaced.

M02 source inspection shows the extra tokens are not missing prose: page 42
gets one unprinted `1`; page 153 splits printed items and repeats `1`/`3` twice
extra each; page 233 assigns four extra right-column `1` markers to left-column
heading/prose; page 348 copies `23` onto a different question's continuation.
This does not excuse the failed exact-accounting requirement.

### Numerical gaps and uncertainty

Gap is hold-out minus the comparable registered band endpoints. A development
min/max is not a sampling interval. Within-book bootstrap uses 1,000 page-cluster
resamples, seed 20261024; it does not estimate between-book transfer or baseline
variance. Frozen aggregate scores were reproduced exactly from page contributions.
The [complete numeric gap ledger](../experiments/out/step18/measurement_evidence/development_gaps.json)
also records paragraph exactness, table detection, figure/caption counts,
body labels and each visible style kind against their registered endpoints.

| Comparable ENT quantity | Hold-out | Gap to lower / upper planning endpoint | Hold-out 95% page-cluster interval | Interpretation |
|---|---:|---|---|---|
| Paragraph page F1 | .933408 | +.083408 /−.016592 | [.894707,.962004] | Mixed/in band |
| Paragraph chained F1 | .933371 | +.033371 /−.016629 | [.894433,.962160] | Mixed/in band |
| Main order | .893759 | −.066241 /−.106241 | [.858354,.931392] | Negative; interval below planning .96, but no joint baseline significance claim |
| Kendall tau | .787519 | −.132481 /−.212481 | [.716707,.862784] | Negative versus .92–1 |
| Float anchors | .5 | −.05 /−.40 | [.376812,.623377] | Below band, interval crosses .55; noise can cover lower endpoint |
| Within-float order | .998498 | +.058498 /−.001502 | [.992890,1] | Within band; not evidence of improved main order |
| List-item F1 | 1 | +.15 /+.08 | Only two reference items | Apparent positive, coverage inadequate |
| Full table TEDS | .9701 | +.1901 /+.0201 | [.956112,.983731], 10 matched page clusters | Above upper band conditionally; within-cell order omitted |
| Heading precision | .666667 | +.066667 /−.303333 | Counts 50/75 | Within band |
| Heading recall | .727273 | −.002727 /−.202727 | Counts 48/66 | Very slightly below lower band, no strong noise claim |
| Heading exact level | .375 | −.375 /−.495 | Counts 18/48 | Large negative descriptive gap, conventions/hierarchy partly confounded |
| Archive continuity precision | .5 | −.45 /−.5 | Only 2/4 scorable links, 62 unscored | Negative against desired band; not a reliable population difference |
| Visible math typing | .142857 adjudicated | −.607143 /−.857143 | Wilson [.025680,.513128], 1/7 +2 unclear | Clearly weak on this detected sample; no recall estimate |
| Review workload/page | 3.133987 | +2.833987 /−.866013 | Whole-book count | Within .3–4; higher workload is not better accuracy |

Reference paragraph exactness bootstrap is unestimated because the frozen
aggregate does not expose page-attributed exact logical units, including
cross-page chains. Joined-table uncertainty is unestimated with one table.
Within-table page clustering does not supply six independent books or prove
the scorer covers cell reading order. No comparable math accuracy gap is
available; Mideast has no accuracy gap by design.

## Attempts, timing, memory and storage

All three conversions reached terminal status before any scoring or hand checks.
Before each run, the recorded backend diff against the tag was empty, tracked
state matched the authorized documentation commits, only the ledger template
was the initial untracked state difference, and free space exceeded 40 GB.
The active reserve was 5,000,000,000 bytes during conversion/evaluation; no reserve
stop occurred. The frontend CNS job overlapped ENT and was not part of this
benchmark; performance was not isolated.

| Attempt | UTC start → end | Wall | 500ms process-tree peak | Minimum free |
|---|---|---:|---:|---:|
| ENT 1, environmental failure | 07:35:50.558749 →10:15:09.994330 | 9,559.434s | 3,227,299,840 B | 89,469,947,904 B |
| ENT 2, approved warm retry | 10:36:17.300022 →12:02:07.441863 | 5,150.139s | 2,613,755,904 B | 87,909,453,824 B |
| Math 1, code failure | 12:03:11.385 →12:18:35.751990 | 924.365s | 672,153,600 B | 87,774,904,320 B |
| Mideast 1, completed | 12:19:37.890099 →15:27:06.319894 | 11,248.440s | 3,588,759,552 B | 86,634,754,048 B |

ENT attempt 1 stopped in `tables.structure_reader.cache_write`: a 275-character
wrapper cache path caused `path_length_wrapper_error`, an environmental failure.
It had completed all-page native extraction, OCR preparation, analysis, paint,
layout, evidence, reading order, furniture, paragraphs, structure, lists,
characters, figures, equations, MathML and 1,836 table detector records; no
completed table assembly/continuity/archive/publication. Its stage-specific
timings were not persisted at the exception and are not reconstructed.

The owner-approved `.cache/h18/e2` retry copied 10,833 files/401,011,859 B with
checksums verified. The audit checked 10,414 nested gzip JSON key/payload records:
no reusable cache key/record depended on an absolute physical cache path. An OCR
manifest did contain an absolute input directory; **it was not reused** and was
regenerated with the unchanged fingerprint. Attempt 1's 10,841-file checksum
manifest was verified unchanged and the folder was kept untouched. Both attempts
are in the ledger; the environmental reason is preserved.

Retry metadata/native/analysis/layout/order/furniture/paragraph/structure/list/
character/figure/equation/MathML stages are explicitly **reused from attempt 1**.
Their warm wall measurements must not be presented as fresh conversion time.
OCR preparation and book-evidence preparation were fresh. Table detection reused
the 1,836 records, but table assembly (2,214.597s), continuity (130.002s), final
archive output (102.351s), and publication assembly (1,395.020s) were fresh.
Full stage wall/CPU/RSS/cache state remains in M18 JSON. Total ENT spent
14,709.574s over both attempts, including failure and reused work; this is not a
clean one-pass runtime.

The approved ENT path remained below Windows' 260-character limit, but did not
meet the stricter below-200 target imposed on the later books. Math/Mideast
deepest expected paths were checked at 199 characters before starting. No Windows
long-path setting, permission, Git config or power setting was changed.

Mideast's original monitor stopped updating during 12:42:52–12:46 UTC; the cause
of that gap is not reconstructed. An external process-tree reserve monitor was
added at 12:46:01.443359 and followed the same process through completion.
Windows events then show sleep 12:47:45.391039–13:12:30.879280 UTC (1,485.488s),
same PID resumed; elapsed wall time includes it. The interval monitor's peak was
3,592,687,616 B and minimum free 86,634,741,760 B. Built-in 20ms stage peaks were
3,006,484,480 B ENT and 3,607,994,368 B Mideast. Sampling intervals differ, so
the smaller outer peaks are not claimed as exact physical maxima; the earlier
monitor gap remains a measurement limitation.

| Book | Source bytes | Cache bytes | Archive bytes | Publication bytes | Readable JSON copies |
|---|---:|---:|---:|---:|---|
| ENT | 98,420,075 | 402,392,158 | 214,178,367 | 244,416,503 | book 54,201,084; review 793,943; manifest 233,642 |
| Math | 86,392,139 | 112,480,466 partial | None | None | Failure README; no fabricated book/manifest/review |
| Mideast | 112,997,873 | 756,866,295 | 156,918,492 | 151,779,298 | book 23,817,123; review 290,784; manifest 98,599 |

Readable copies parse identically to the original hash-named publications and
their byte identities are recorded in copy receipts. Original outputs stay in
place. No image/crop files are copied into the committed readable directories;
agent crops remain local and their paths/hashes are recorded for the owner audit.
Exported image bytes are 159,264,586 ENT and 105,847,981 Mideast. Conversion-versus-
original-image accuracy/counts are unmeasured because an independently verified
original-byte denominator is not persisted. Evidence packaging also retained
redundant compressed attempt-1 cache records; these are evidence copies, never
used as a new run or presented as fresh work.

Post-run evaluation initially hit a read-access `PermissionError` on the protected
ENT publication. Original failed wrapper receipts were preserved; an authorized
read-access invocation with a new evidence destination succeeded without ACL or
converter changes. Earlier measurement setup failures (missing destination and
compressed JSON decoding) remain failed receipts. The M11 population correction
and invocation-only scoped wrappers are disclosed above. No failed setup attempt
is counted as a passing gate.

## What this benchmark did not measure

- Math correctness after the page-348 failure, including the primary MathML
  strict/expression/symbol metrics; no partial output substitutes for completion.
- Semantic accuracy outside ENT's 43 located pages, or for Mideast without gold.
  CNXML was not extended into prose/list/heading/style truth.
- Independent front-label truth, figure label/credit/name accuracy, full-book
  index/glossary correctness, or whole-book review recall.
- OCR CER/WER/order-free F1 without independent transcripts; vertical/RTL quality
  without eligible emitted units; unknown script/direction was retained.
- Independent human validation of agent hand judgments: owner audit is pending.
  The 20 fixed checks do not independently verify all 559 judgments.
- Broad worker equivalence: the accepted fresh 1-vs-2 comparison covered **nine
  Art Therapy pages only**. No hold-out rerun was made for worker comparisons.
- Independent native-object proof for Spanish table input: the already registered
  bounded reader's checksum/consumed-field proof remains its precise scope.
- Isolated fresh performance: ENT reused approved caches and overlapped frontend
  activity; Mideast included sleep and a monitor gap.

## Ranked Step 19+ backlog — proposals only

Effort estimates are engineering days including regression/independent checking,
not commitments. None is implemented in Step 18.

| Rank | General work | Why it comes first | Rough effort |
|---|---|---|---|
| 1 | Unique layout candidate identities and controlled failure evidence | Math cannot complete; retain region collision context without losing the failed book | 2–4 days |
| 2 | Source-bound list markers and ownership across splits/columns | ENT violates zero-extra accounting despite contract success | 3–6 days |
| 3 | Heading/footnote/folio typing and relevant review capture | Observed source-first heading errors mostly unflagged; genuine notes missed | 6–12 days |
| 4 | Column/group order and continuity endpoint selection | ENT order below band; visual cross-page skips also occur in Mideast | 5–10 days |
| 5 | Table cell text-order/header semantics and independent evaluator coverage | High TEDS conceals reversed cell prose; separate production work from scorer revisions | 4–8 days |
| 6 | Anatomical notation versus math; rare style/range evidence | Weak math typing and misleading reference-style omissions | 3–6 days |
| 7 | OCR cover completeness, script/direction metadata and typed review diagnostics | Mideast cover omissions and widespread unknown metadata; no unsupported OCR promises | 5–10 days |
| 8 | Portable cache paths, monitor continuity and repeatable resource receipts | Approved retry/path failure and sleep/monitor limitations | 2–4 days |

Review the owner audit before accepting the judgment-derived priorities. Create
new independent evaluation data before changing scoring conventions, preserve
Step 18 numbers, and never tune against these books while calling them sealed.

## Future sealed books and licences

**ENT, this math hold-out, and Mideast are now burned for tuning.** The separately
inspected CNS frontend book is also unsuitable as a newly unseen seal. Future
intake must pin exact file hashes, revisions/licences, check content overlap with
all development/hold-out books, and seal truth/coverage before running.

1. **Understanding Linear Algebra — David Austin**, English mathematical prose,
   matrices and diagrams, different author/publisher: [official book site](https://understandinglinearalgebra.org/)
   and [author repository](https://github.com/davidaustinm/ula), **CC BY 4.0**.
   Pin an exact PDF revision/hash and independent equation/table locations before
   use; a title recommendation is not a seal or guarantee of distinct content.
2. **天工開物（中）— 宋應星**, traditional Chinese vertical historical scan,
   [Wikimedia Commons source record](https://commons.wikimedia.org/wiki/File%3A%E5%A4%A9%E5%B7%A5%E9%96%8B%E7%89%A9_%EF%BC%88%E4%B8%AD%EF%BC%89.djvu),
   **Public Domain Mark**. This is a DjVu source requiring an authorized PDF/image
   package; no Ghostscript. Vertical Chinese is a deliberately unsupported stress
   case, not an expected OCR pass. Establish a transcript scope before CER.
3. **Ibn Sina, Kitab al-Qanun fi al-tibb, MS Arabic 16**, Arabic Naskh manuscript
   with coloured headings, [Wellcome collection record](https://wellcomecollection.org/works/ffevyf2m),
   **Public Domain Mark**. Handwriting is an unsupported stress case; do not
   present it as printed-Arabic OCR validation. Pin a permitted scan file and
   independent transcript scope.

Metadata/licence records were checked on 24 October 2026; no new book content was
downloaded or run. Licence receipts are retained with the evidence. An optional
German Fraktur Meyers volume was considered, but the category alone did not
establish a complete-volume licence; it is not a sealed recommendation here.

## Close-out

Final verification receipts accompany the evidence: frozen backend/tag/profile
and protocol hashes, original attempt-1 preservation, readable-copy equality,
metric completeness, crop/target audit integrity, forbidden-file checks and
Git scope. The evidence commit changes no tracked `backend/` file and includes
no converter fix. The earlier 5 MB check applied to the pre-freeze cleanup
evidence commit; the separately requested Step 18 readable book/alignment JSON
files exceed 5 MB and are listed explicitly in the final inventory. The largest
is 54,201,084 bytes; no hidden split or omission is used.

This closes the measurement gate for owner review. Owner re-judgments remain
pending. **Stop here: no Step 19 fixes, Stage 2, XML generation or NIMAS adapter.**
