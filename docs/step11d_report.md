# Step 11d — character repair and hidden-text diagnosis

Status: **FAIL at the baseline gate; implementation held for review.** This commit
freezes the unchanged Step 11c baseline and records the diagnoses. It does not
complete the requested repair implementation. Five existing I5 violations prevent
a passing full-book gate. No checker was weakened and no unrelated layout fix was
introduced. **Step 12 has not started.**

## Scope, exceptions and frozen baseline

Book measurements and PDF/font inspection use only Spanish US history (758 pages),
immigrant children (331), art-therapy index (9, anecdotal), and medical anatomy
(314, development). The sealed ENT book, mideast robustness book and excluded
mismatched pair were not run or scored. Old projects, reference files, gold and
the original text ledger were not edited. References were resolved through the
existing read-only configuration. All PDF inspection uses the project's PyMuPDF
Extractor, including diagnostic subclasses; no OCR or adapter work was done.

The starting revision was `bad1516ca52ebebdfcc8a427ef4bcf19d4699751`. Tracked files
were clean. The sole pre-existing untracked file was `.vscode/settings.json`.
The user explicitly authorized preserving it and documenting this exception;
its SHA-256 is frozen and it is excluded from the commit. Git configuration was
not changed. The frozen [provenance](../experiments/out/step11d/before/provenance.json)
records Git blob identities for existing producers, tests, Step 11c tooling and
documentation. No existing producer was edited during this step.

Initial free space was **40,480,944,128 bytes**. The conservative 1,412-page estimate
was **17,767,071,744 bytes**, leaving **22,713,872,384 bytes**, above the 10 GB stop
threshold. No cache pruning was needed.

Two scope conflicts were handled explicitly:

- The historical 24-page source driver opens science and Canadian-index originals
  outside books 1–4. It was not invoked. A new deterministic sample selects six
  pages from each approved book, freezes that selection, and compares fresh source
  extraction with the archived final source store using the existing TrimBox-centre,
  case-sensitive NFKC token Counter. Historical evidence remains untouched.
- AGENTS permits only explicit TrimBox discards. Hidden-text handling must therefore
  retain tokens through the existing `invisible` stream/unit mechanism; it cannot
  add silent discards. No new exclusion or discard was applied here.

The required existing test suite also exercises its registered historical and
synthetic fixture PDFs. That regression coverage is separate from these four-book
measurements; no additional original book or sealed intake source was opened.

The Step 11c identity tooling was reused before any existing code change. Every
page's native text, layout, reading order, furniture, paragraphs, structure
projection and lists matches committed Step 11c evidence. Whole-book furniture,
paragraphs, structure evidence, structure and list decisions match too. All 1,412
native-object and analysis models additionally match their exact frozen
serialization digests. Cache keys are identical. Canonical page/book comparisons
retain Step 11c's exclusion of only `cache_key_inputs` and `page_keys`; exact model
digests include their complete serialization.

Fresh reported metrics were captured for all four books. Every metric matches the
committed Step 11c summary; only elapsed seconds and cache-hit state are omitted
from this comparison. Producer digests, counts, scores, source text, relationships
and decisions are not omitted. Full measurements and operational fields remain in
the JSON files.

| Book | Pages | Page/book identities | Native/analysis exact digests | Reported metrics |
|---|---:|---|---|---|
| Spanish US history | 758 | identical | identical | identical |
| Immigrant children | 331 | identical | identical | identical |
| Art-therapy index | 9 | identical | identical | identical |
| Medical anatomy | 314 | identical | identical | identical |

Evidence: [frozen baseline](../experiments/out/step11d/before/),
[sample selection](../experiments/out/step11d/before/sample.json),
[source crosscheck](../experiments/out/step11d/before/source_crosscheck.json),
[ledger](../experiments/out/step11d/before/full_book.json), and
[audited comparison](../experiments/out/step11d/verification.json).

## Failed gate: existing I5 credit classification

The full 1,412-page audit found **five I5 violations**, all in book 1. I1–I4,
I6 and I7 are zero on all four books. Every visual line is assigned to exactly
one final unit and ordered exactly once, including artifact/furniture streams.

| Book 1 page | Violations | Failed credit evidence |
|---|---:|---|
| 324 | 1 | isolated, but not near a figure edge |
| 350 | 1 | isolated, but not near a figure edge |
| 361 | 1 | isolated, but not near a figure edge |
| 724 | 2 | near a figure edge, but not isolated from other rotated text |

These are visible rotated citations/credits in the inspected renderings. They are
not the hidden English lesson labels. The layout fallback in
`layout/pipeline.py` labels remaining small rotated lines `credit_candidate` using
relative size alone. The I5 checker calls `credit_like`, which also requires
isolation and figure proximity. The producer groups free rotated lines, whereas
the checker considers rotated text across the page, including figure text. The
fallback and checker thus disagree on these existing pages.

Step 11c's historical fixture I1–I7 result was zero; that result does not establish
zero violations on every page of these four full books. This broader audit exposes
the discrepancy without changing the old report or accepting it as a passing gate.
Changing the layout fallback belongs to a separate review decision under the
instruction to stop at gates and avoid unrelated work.

Evidence: [complete failure explanation](../experiments/out/step11d/diagnosis/i5_full.json)
and each book's `*_full_gates.json` in the frozen baseline. Inspected renderings are
preserved in the [render inventory](../experiments/out/step11d/diagnosis/renders.json),
including [page 724](../experiments/out/step11d/diagnosis/renders/spanish_us_history_724.png).

## Hidden-text diagnosis

An exploratory scan inspected every page's text traces, later drawings/image
bounds, clipping evidence and optional-content metadata. It matches source spans
by exact text and contained trace bounds. It recognizes only rectangular or
strictly supported rounded-rectangle fill cores, requires full glyph containment,
and rejects cover proofs on pages with unsupported soft-mask/blend resources,
groups, layers or clips. This is deliberately incomplete. It is **not a validated
exclusion algorithm** or an exhaustive count of genuinely hidden text.

Counts below are unique native source lines, using the unchanged ledger tokenizer.
"Cover candidate" is an exploratory observation, not a production decision.
Whitespace-only lines have no ink and are reported separately. The original scan's
vacuous blank-or-hidden classification was corrected in diagnostic aggregation;
raw scan totals and original labels remain recorded for provenance.

| Book | Cover candidates, lines / tokens | Other uncertain lines / tokens | Whitespace candidates | Retained uncertain lines / tokens |
|---|---:|---:|---:|---:|
| Spanish US history | 170 / 476 | 1,893 / 2,486 | 109 / 0 | 1,893 / 2,486 |
| Immigrant children | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Art-therapy index | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Medical anatomy | 0 / 0 | 6 / 35 | 1 / 0 | 6 / 35 |

All 170 nonblank cover candidates in Spanish history are already outside the
explicit TrimBox. Their 476 tokens are accounted for by the existing exclusion
ledger. The screen certifies no additional retained nonblank line for exclusion.
Zero candidates in a book is not proof that every glyph is visible: trace matching,
arbitrary paths, images, inherited graphics state and font/resource association
remain incomplete.

The six uncertain medical lines are chapter-title strings. Their content appears
in the reference, and the inspected page 74 rendering shows the corresponding
chapter title. That does not establish visibility of each particular extracted
occurrence beneath overlapping artwork. A substring/reference match cannot decide
which occurrence is visible. All remain retained.

| Evidence class | Reliability when fully established | False-positive risk and present limitation |
|---|---|---|
| Ignored text trace / PDF invisible mode | strong for nonpainting text with exact occurrence attribution | Clip-only text can still affect later artwork; bbox intersection alone is insufficient attribution. No new candidate was established this way. |
| Zero fill/stroke opacity | strong only when every applicable paint operation is nonpainting | A visible stroke or another occurrence can remain. Existing object associations can combine overlapping traces. |
| Text clipping | strong only with effective path and graphics-state tracking | Text bbox or clip bbox alone cannot prove glyph ink is excluded; arbitrary paths and text clip modes remain unverified. |
| Fill/stroke colour versus actual background | insufficient on its own | Gradients, images, masks, blending and later paint change the background. No complete per-glyph background comparison was measured. |
| Later opaque cover | strong with exact order, coverage, clip, alpha, mask and blend evidence | Bounding rectangles include unpainted holes; images may have alpha. The exploratory fill-core screen rejects unsupported context and does not authorize exclusion. |
| Optional content / default-off layers | strong only with resolved default configuration and membership policy | Layer names alone omit membership expressions and view/print differences. No matched candidate was established; page 215 has no OCGs. |
| Outside page, zero area, tiny relative text | review evidence | Combining marks, accents, fine print and glyph-box conventions make these unsafe automatic hiding rules. Tiny means relative to the page median, not an absolute font threshold. |
| Duplicate text or reference omission | weak | Repeated visible labels and intentional repetition are legitimate; neither is a hiding rule. |

Steps 3/4 already retain text render type, opacity, glyph IDs, colour, sequence and
layer evidence. Their visibility predicate accepts a text object when it has no
trace evidence or any associated trace paints with positive/unknown opacity.
Trace-to-object association uses bbox intersection, which can mix distinct
overlapping occurrences. The existing `invisible` handling retains text separately
from prose; there are zero final `invisible` units in these four baseline archives.
Later paint coverage and effective text clipping are not fully resolved by that
predicate. This step did not change it.

### Page 215

The inspected 144 dpi rendering shows Spanish lesson labels; the duplicated
English labels are not visible there. The English INQUIRY and LEARN traces are
ordinary filled text (type 0), opacity 1, without an optional-content layer.
They precede later white box paint and the Spanish text. Duplication is therefore
not evidence of invisible render mode. Native bbox association also attaches
Spanish and English traces to overlapping source objects.

The page contains ExtGState 28319 with `/SMask 28318 0 R`, `/AIS true` and normal
blending. Resource presence alone does not prove that a particular later box is
masked, or that it is opaque. Per-operation graphics-state/mask tracking is needed
before excluding these source occurrences. The conservative screen leaves **48
lines / 174 tokens uncertain** on this page and applies no exclusion.

The baseline has four headings: `TEMA4`, plus the three mixed-language lesson-box
labels LEARN, INQUIRY and REVIEW. Those three remain level 2 in the captured
decision. The Step 11b report says the kept float rule did not change them; its
unrestricted trial would have nested them. Whether safe hidden-text exclusion
would remove the three-heading issue is **unverified**. No counterfactual heading
run was performed, and no heading-level fix is claimed.

The Spanish reference contains none of the three queried English phrases (LEARN,
INQUIRY, Progressive Era Reforms). Book 2 yielded no visibility candidates in this
screen. The medical reference contains the content of all six queried chapter-title
phrases; this is content evidence, not occurrence-level visibility truth.

Evidence: [page 215 source/traces/headings](../experiments/out/step11d/diagnosis/page215.json),
[page 215 rendering](../experiments/out/step11d/diagnosis/renders/spanish_us_history_215.png),
[page 215 scan](../experiments/out/step11d/diagnosis/p215_diagnosis.json),
[four-book totals](../experiments/out/step11d/diagnosis/summary.json),
[reference observations](../experiments/out/step11d/diagnosis/reference_diagnosis.json),
[medical content comparison](../experiments/out/step11d/diagnosis/medical_reference_content.json),
and `hidden_*.json` with stable span/line IDs in the diagnosis directory.

## Character corruption and fontTools

Before installation, the official [fontTools 4.66.1 release metadata](https://pypi.org/project/fonttools/4.66.1/)
and [licence](https://github.com/fonttools/fonttools/blob/4.66.1/LICENSE)
were checked. The package is MIT; its metadata requires Python >=3.11, declares
Python 3.14 support, and supplies a CPython 3.14 Windows x64 wheel. The exact pin is
**`fonttools==4.66.1`**. That verified wheel was installed offline without other
dependencies and imported successfully on Python 3.14.8. The wheel's SHA-256,
metadata and bundled licence notices are preserved. This is a diagnostic-only pin
in `experiments/requirements-step11d.txt`; production dependencies are unchanged.

| Witness | Raw code and PDF mapping | Embedded font evidence | Diagnosis / safe action |
|---|---|---|---|
| Beta-shaped `b`, book 2 | Type 1 code `62` hex; Encoding `/b`; ToUnicode `<62><0062>` | CFF glyph 66 named `b`. Its 73 outline points have identical y coordinates and operator topology to a correctly mapped embedded beta (glyph 67); x differs by shear 0.364164 with maximum residual 0.670 font units. | The font's Unicode/name metadata is wrong for its visible shape. PyMuPDF follows that mapping. Strong diagnostic evidence for beta, but no validated general outline-matching repair rule was established. Keep original and defer repair. |
| `Ǌ` U+01CA, book 4 | Type 1 code `1D` hex; Encoding `/bullet.034`; ToUnicode `<1D><01CA>` | CFF glyph 95 `bullet.034` is an outlined cube, with outer and inner contours. | U+01CA does not describe the painted marker. AGL strips the suffix and suggests `•`, which also fails to describe this outline. The reference's diamond convention does not prove the font intended U+25C6. No repair. |
| `¾` U+00BE, book 4 | Type 0 Identity-H code `00BE`; ToUnicode `<00BE><00BE>` | Glyph/CID 190 `glyph00190` is an arrowhead. The stripped embedded TrueType font has no usable cmap; its decomposed outline is preserved. | The PDF maps a symbol glyph to the fraction code point. The same reference items use `➢` U+27A2, consistent with an arrowhead; the stripped font's own metadata cannot independently establish that mapping. No repair. |

Font names and xrefs in these witnesses identify evidence, not converter rules.
No rule keyed to a book, font, page, word or publisher was added. Raw code values
are established from the witness encoding/CMap and glyph mapping; the extractor's
text trace provides Unicode/glyph IDs, not an independent original-byte field.

| Book | Witnessed beta-shaped `b` | U+01CA marker occurrences | U+00BE marker occurrences | Other glyph-name/cmap disagreement candidates |
|---|---:|---:|---:|---:|
| Spanish US history | 0 | 0 | 0 | 311 |
| Immigrant children | 6 | 0 | 0 | 0 |
| Art-therapy index | 0 | 0 | 0 | 24 |
| Medical anatomy | 0 | 538 | 142 | 1,205 |

These are source occurrences, not repair totals. The six beta-shaped `b` spans
are retained table-column labels on pages 124 and 126. The matching reference
tables use beta. The source also has 22 already extracted beta characters, while
the reference has 26: their global totals do not establish a one-to-one match or
an accuracy gain. The medical source already has 1,589 diamonds and the reference
has 1,590; the reference has neither U+01CA nor U+00BE. It also contains 141 `➢`
characters, including the three corresponding arrow-marked items on page 55.
The page 41 cube-marked learning objectives appear without literal cube characters
in the reference's text. The reference therefore does not prescribe a single
diamond replacement for all marker variants. These global totals are not a
one-to-one alignment or a repair score.

The broad font survey is not a corruption detector. Expected differences include
small capitals, decomposed ligatures and soft hyphens. Its family/resource matching
leaves 8,064 Spanish, 0 immigrant, 22,262 art-index and 4 medical trace characters
unmatched. Missing/ambiguous provenance can also produce disagreements. In
particular, glyph-name comparison misses the beta-shaped `b` because its misleading
name agrees with its misleading CMap, and cannot infer the stripped arrow glyph's
Unicode. Other corruption classes and exhaustive clean-text coverage are
**unverified**.

Evidence: [glyph objects, CMaps and outlines](../experiments/out/step11d/diagnosis/glyph_examples.json),
[reference table snippets](../experiments/out/step11d/diagnosis/reference_snippets.json),
[same-content marker comparison](../experiments/out/step11d/diagnosis/reference_content.json),
[dependency pre-install checks](../experiments/out/step11d/dependency_preinstall.json),
[installation record](../experiments/out/step11d/dependency_install.json), and
`font_scan_*.json` / `specific_*.json` in the diagnosis directory.

## Implementation and separate measurements

Implemented: reproducible baseline, diagnostic scans, explicit witness inspection,
diagnostic aggregation and a checkpoint auditor that returns failure for the
existing I5 violations. The blank-line diagnostic aggregation correction changes
only the reporting of candidates, not a model, cache or semantic output.

Deliberately not implemented: runtime character correction, new visibility
decisions, corrected-text model fields, exclusion rules, outline-matching rules or
an I5 layout fix. The baseline gate requires review, and the diagnosed cases do not
yet support a validated general replacement/exclusion policy. Original text,
NFKC text, stable IDs, ordering, paragraph/list/heading decisions and ledger rules
remain unchanged.

No stage was re-keyed. Existing producer/configuration/upstream fingerprints are
identical to Step 11c. There is no new cache format, pickle, worker policy or runtime
dependency. The one-worker automatic default and hash-once execution remain covered
by existing tests. Diagnostic source scans are separate invocations and are not
claimed as single-hash end-to-end production measurements.

The table intentionally does not manufacture after measurements for unrun variants.
Each baseline link contains **every reported metric**, including worse scores,
per-kind/per-zone breakdowns, reading order, units, lists, page labels, headings,
confidence counts and gates. Stage digests are linked above for all pages/books.

| Book / complete baseline metrics | Hidden text only: after | Character repair only: after | Combined: after |
|---|---|---|---|
| [Spanish history](../experiments/out/step11d/before/metrics/spanish_us_history/summary.json) | unverified; not implemented/run | unverified; not implemented/run | unverified; not implemented/run |
| [Immigrant children](../experiments/out/step11d/before/metrics/immigrant_children/summary.json) | unverified; not implemented/run | unverified; not implemented/run | unverified; not implemented/run |
| [Art index](../experiments/out/step11d/before/metrics/art_therapy_index/summary.json) | unverified; not implemented/run | unverified; not implemented/run | unverified; not implemented/run |
| [Medical anatomy](../experiments/out/step11d/before/metrics/medical_anatomy/summary.json) | unverified; not implemented/run | unverified; not implemented/run | unverified; not implemented/run |

Thus no hidden-only, repair-only or combined improvement/regression claim is made.
The fresh **baseline** metric comparison has no unexplained content differences.
Post-implementation timing, memory and cache-capacity measurements are unverified.

## Gate table

| Required gate | Result and scope |
|---|---|
| All existing tests | **PASS: 869**, 1,857.88 seconds; one pytest cache-directory warning, no test failure |
| New repair/hiding tests | unverified / not applicable to runtime code: no such logic introduced |
| Approved 24-page source sample | **PASS: zero missing / zero extra** |
| Book 1 full original ledger | **PASS: exactly 495,751 tokens**, all source/retention/exclusion checks pass |
| Full-book I1–I7 | **FAIL: I5 = 5** in book 1; every other invariant in all books = 0 |
| Every line assigned and ordered once | **PASS: all 1,412 pages** |
| Books 1–2 not worse; inspect all four | baseline identities and complete reported metrics identical; variant results **unverified** |
| One/two workers identical | **PASS for fresh three-page synthetic fixture**, including final and intermediate files and cold production; fresh four-book equivalence **unverified**; Step 11c's 300-page evidence retained |
| Cache closure, deliberately missing dependency | **PASS** in the full existing suite |
| Ruff from backend | **PASS**: lint and format check cover src, tests and all nine new Step 11d Python tools |
| Report matches committed evidence | checkpoint auditor and file manifest; failed gate remains failure |
| One commit, then stop | diagnostic checkpoint only; `.vscode/settings.json` excluded; stop before Step 12 |

Evidence: [pytest XML](../experiments/out/step11d/pytest_baseline.xml),
[verification](../experiments/out/step11d/verification.json),
[lint record](../experiments/out/step11d/lint.json), and
[evidence checksums](../experiments/out/step11d/manifest.json).
The Step 11d evidence directory is exempted from Git line-ending conversion in
`.gitattributes`, so frozen JSON, logs and executed source snapshots retain the
bytes recorded by the manifest on checkout.

## Reproduction and limitations

Run from the repository root with the existing environment. Diagnostic font tooling
uses the exact pin in `experiments/requirements-step11d.txt`. Baseline output is
frozen and refuses overwriting. Rebuilding historical baseline evidence requires
the unchanged `bad1516` producers and unused output/checkpoint directories; do not
replace the committed baseline. The exact executed capture/scan source snapshots
and their hashes are preserved in `experiments/out/step11d/tools/` and
`execution_sources.json`; maintained Python tools are formatted copies with the
documented blank-line aggregation correction.

```powershell
# Audits frozen evidence without opening PDFs; expected exit 1 while I5 fails.
.venv\Scripts\python.exe experiments/step11d_verify.py
# Checks the committed checkpoint's file hashes; expected exit 0.
.venv\Scripts\python.exe experiments/step11d_verify.py --manifest
# Read-only font/PDF witness and I5 inspection; writes diagnosis JSON.
.venv\Scripts\python.exe experiments/step11d_glyphs.py
.venv\Scripts\python.exe experiments/step11d_page215.py
.venv\Scripts\python.exe experiments/step11d_i5.py
.venv\Scripts\python.exe experiments/step11d_references.py
```

`step11d_fonts.py` and `step11d_visibility.py` survey all four approved sources into
scratch JSON. `step11d_summarize.py` annotates those observations against the frozen
final source stores, retaining the original raw scan totals. These tools never
write PDF sources, reference files or converter caches. Their uncertainty labels
are diagnostic evidence, not production per-span confidence decisions.

From `backend/`:

```powershell
$stepFiles = (Get-ChildItem ../experiments/step11d_*.py).FullName
..\.venv\Scripts\python.exe -m ruff check src tests $stepFiles
..\.venv\Scripts\python.exe -m ruff format --check src tests $stepFiles
..\.venv\Scripts\python.exe -m pytest -q --basetemp=../.cache/step11d/tc `
  --junitxml=../experiments/out/step11d/pytest_baseline.xml
```

Remaining limits are effective graphics-state/soft-mask/clip attribution,
occurrence-level native trace association, incomplete font/resource matching,
outline equivalence false-positive guards and undefined Unicode choices for
decorative marker variants. They require further diagnosis and testing before a
runtime repair can be retained.

Recorded for later review, without implementation: visible rotated credit/citation
ownership (the current blocking I5 discrepancy); figure paint/text associations;
rotated table headers containing beta; symbol/ligature interpretation in math and
lists; and reference marker conventions. This report does not assign a new stage
or start any figure, math, table, adapter or XML work in Steps 12–14.

**Committed scope: diagnostic tools, dependency evidence, frozen baseline,
measurements, exact-byte evidence attributes and this report. Repair implementation
is incomplete. Stop for review.**
