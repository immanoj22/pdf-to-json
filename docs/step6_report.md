# Step 6: document-wide evidence

Whole-book typography, navigation, repetition, native-block language and vocabulary evidence is cached for later stages. Confidence is evidence, not a role decision. No heading levels, furniture removal, paragraph boundaries, reading order or zones are decided here. The text ledger and gold are untouched; old projects remain read-only.

## Gates and provenance

| Gate | Result | Evidence |
|---|---|---|
| Earlier and new tests | 527 passed; 0 failed / 0 skipped; testcase time 147.80 s | [JUnit](../experiments/out/step6/pytest.xml) |
| 24 measured pages vs original sources | 0 missing / 0 extra on all 24 | [source cross-check](../experiments/out/step6/original_source_crosscheck.json) |
| Full book | 495,751 retained tokens; 0 missing / 0 extra | [unchanged full-book gate](../experiments/out/step6/full_book.json) |
| Ruff check / format | pass, run from backend/ | [log](../experiments/out/step6/ruff.log) |
| Derived-gold checksums after LF renormalization | all three books verify; no gold edits | [integrity](../experiments/out/step6/gold_integrity.json) |
| Scope | Step 6 only; semantic decisions deferred | [confirmed decisions](decisions.md) |

`.gitattributes` now has `* text=auto eol=lf`; both hand-made gold and derived gold are protected by `-text` exceptions, preserving their exact bytes. Reference units are provisional (`human_approved: false`). Book 2 has identity by text only; book 3 is anecdotal, and its low-confidence page markers remain excluded from gates. Metrics below are per book, with no overall score.

The book cache key covers PDF hash, complete page/metadata/block digests, extractor identity, producer source digest, runtime/library versions, configuration and the actual bundled language-model binary hash. Per-page native caching remains source-hashed and atomic. Changed producer code requires a worker restart.

## Whole-book profiles

| Book | Evidence | Observed |
|---|---|---|
| Book 1: Spanish US history | Split | development |
| Book 1: Spanish US history | Pages / retained tokens | 758 / 495,751 |
| Book 1: Spanish US history | Modal body-style candidate | proximanova; 9.8 pt; regular; #231f20; mixed |
| Book 1: Spanish US history | Body-style character share | 35.21% |
| Book 1: Spanish US history | Style keys / size clusters / style clusters | 1065 / 50 / 892 |
| Book 1: Spanish US history | Bookmarks / printed entries / PDF labels | 764 / 1790 / 0 |
| Book 1: Spanish US history | Printed TOC candidate pages | 33: 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22 ... |
| Book 1: Spanish US history | Geometry-only ambiguous TOC pages | 24 |
| Book 1: Spanish US history | Native blocks / model mixed-segment evidence | 34,340 / 6,750 |
| Book 1: Spanish US history | Block language evidence | und: 22,961; es: 10,733; en: 583; fr: 21; tl: 11; la: 10; cy: 4; yo: 4; mi: 3; de: 2; +7 other kinds |
| Book 1: Spanish US history | Vocabulary / native-adjacent join hypotheses / attested | 34,151 / 44 / 4 |
| Book 1: Spanish US history | Device / wall seconds | cpu / 62.60 |
| Book 1: Spanish US history | Book artifact cache hit / native hits / native misses | True / 758 / 0 |
| Book 1: Spanish US history | Cached book artifact | [90fe275348ad5692](../.cache/step6/document/90fe275348ad569233f6d0203d1d6cfa6a64476bb9f01af22048b9e63a6ac700.json) |
| Book 2: Immigrant Children | Split | hold-out; identity by text only |
| Book 2: Immigrant Children | Pages / retained tokens | 331 / 124,017 |
| Book 2: Immigrant Children | Modal body-style candidate | times; 10.5 pt; regular; #231f20; mixed |
| Book 2: Immigrant Children | Body-style character share | 42.96% |
| Book 2: Immigrant Children | Style keys / size clusters / style clusters | 91 / 21 / 91 |
| Book 2: Immigrant Children | Bookmarks / printed entries / PDF labels | 21 / 1245 / 331 |
| Book 2: Immigrant Children | Printed TOC candidate pages | 17: 9, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322 ... |
| Book 2: Immigrant Children | Geometry-only ambiguous TOC pages | 0 |
| Book 2: Immigrant Children | Native blocks / model mixed-segment evidence | 2,715 / 1,255 |
| Book 2: Immigrant Children | Block language evidence | en: 1,729; und: 957; de: 8; la: 6; fr: 4; cy: 2; nb: 2; pt: 2; tl: 2; es: 1; +2 other kinds |
| Book 2: Immigrant Children | Vocabulary / native-adjacent join hypotheses / attested | 10,747 / 1,239 / 1,117 |
| Book 2: Immigrant Children | Device / wall seconds | cpu / 117.27 |
| Book 2: Immigrant Children | Book artifact cache hit / native hits / native misses | False / 0 / 331 |
| Book 2: Immigrant Children | Cached book artifact | [045d0d22a7df1d2b](../.cache/step6/document/045d0d22a7df1d2b6ec7cde83802eea55085557812ea6fdd99b3c732caef4b18.json) |
| Book 3: art-therapy index | Split | hold-out; anecdotal |
| Book 3: art-therapy index | Pages / retained tokens | 9 / 4,249 |
| Book 3: art-therapy index | Modal body-style candidate | freighttextprobook-regul; 8 pt; regular; #231f20; lower |
| Book 3: art-therapy index | Body-style character share | 53.11% |
| Book 3: art-therapy index | Style keys / size clusters / style clusters | 11 / 4 / 11 |
| Book 3: art-therapy index | Bookmarks / printed entries / PDF labels | 0 / 0 / 0 |
| Book 3: art-therapy index | Printed TOC candidate pages | 0: none |
| Book 3: art-therapy index | Geometry-only ambiguous TOC pages | 0 |
| Book 3: art-therapy index | Native blocks / model mixed-segment evidence | 365 / 49 |
| Book 3: art-therapy index | Block language evidence | und: 280; en: 78; cy: 2; de: 1; es: 1; la: 1; nl: 1; yo: 1 |
| Book 3: art-therapy index | Vocabulary / native-adjacent join hypotheses / attested | 1,314 / 2 / 0 |
| Book 3: art-therapy index | Device / wall seconds | cpu / 10.05 |
| Book 3: art-therapy index | Book artifact cache hit / native hits / native misses | False / 0 / 9 |
| Book 3: art-therapy index | Cached book artifact | [929d65938aaac8be](../.cache/step6/document/929d65938aaac8bedfcc987be3b97b99a7a265e2e093cfc6c6b0c1f04dffd314.json) |

The body-style candidate is the character-weighted mode, with rounded size, normalized family, native bold/italic flags, color and caps. All extracted lines retain style evidence; no font-size-only heading classifier is introduced. Vocabulary retains the unchanged NFKC Unicode token rule and TrimBox retention. Native-adjacent spelling attestations do not establish paragraph continuity or reading order.

Reported whole-book wall times include cache effects, evaluation and optional overlays.

Scope: style and native-block language profiles include all extracted lines/blocks, including explicit TrimBox-excluded extraction evidence. Vocabulary, repetition and derived-gold evaluation use retained content. Overlays show all native styles, including prepress text outside the content frame; Step 6 makes no semantic retention decision.

Language distributions and mixed-segment counts are unvalidated model evidence, not proven monolingual or bilingual truth. Caps-sensitive style keys can split typography into many clusters; the cluster count is descriptive.

## Evaluation against provisional derived gold

Titles use one-to-one fuzzy matching of casefolded Unicode tokens at the frozen similarity threshold. Target success requires one resolved physical page in the matched heading's aligned token runs. Precision divides by entries; recall divides by reference heading units. Combined navigation deduplicates identical titles with equal resolved target pages or equal unresolved printed labels; destination-free entries remain separate. Unresolved labels stay unresolved; no page offset is guessed. When PDF labels are absent, printed targets remain unresolved while bookmark destinations remain usable. Navigation/title precision is an evidence diagnostic, not heading classification.

### Book 1: Spanish US history

Frozen title similarity threshold: 90.0/100.

Book 1's native bookmark titles are production file identifiers, yielding 0 reference heading-title matches. Their native PDF destinations remain evidence; no book-specific title decoding was attempted.

| Navigation | Entries | Ref. headings | Title matches | Title precision / recall | Title + target matches | Title + target precision / recall | Unresolved / ambiguous |
|---|---|---|---|---|---|---|---|
| Bookmarks | 764 | 505 | 0 | 0.00% / 0.00% | 0 | 0.00% / 0.00% | 0 / 0 |
| Printed TOC | 1790 | 505 | 126 | 7.04% / 24.95% | 0 | 0.00% / 0.00% | 1790 / 0 |
| Combined unique | 2071 | 505 | 126 | 6.08% / 24.95% | 0 | 0.00% / 0.00% | 1307 / 0 |

| Repetition evidence | Count |
|---|---|
| Candidates | 167 |
| Unique retained candidate tokens | 7,064 |
| Not aligned to a reference unit (absence proxy) | 2,613 |
| Aligned to reference units (potential false candidates) | 4,451 |
| Aligned unit kinds | paragraph: 3,666; heading: 442; list_item: 215; image_description: 77; definition_description: 47; caption: 3; byline: 1 |
| Position bands | side: 66; bottom: 51; top: 50 |
| Physical-page periodicity | even: 59; mixed: 56; odd: 52 |

Largest reference-aligned candidate groups; the source line is illustrative, not a furniture decision.

| Source line sample | Band | Pages | Confidence | Aligned / candidate tokens | Reference kinds |
|---|---|---|---|---|---|
| CONÉCTATE Explora la versión digital del Libro del estudiante y descubre mapas, líneas cronológicas y herramientas in... | bottom | 142 | 0.655 | 2,414 / 2,431 | paragraph: 2,414 |
| Remítete a la Pregunta de indagación y a las | top | 16 | 0.516 | 143 / 143 | paragraph: 143 |
| EVALUAR FUENTES Y UTILIZAR INFORMACIÓN | top | 27 | 0.548 | 135 / 135 | paragraph: 135 |

Reference heading units: **505**. Top eight observed clusters follow; these are distributions, with no classifier or heading level.

| Style cluster | Observed style | Heading units touching cluster | Heading tokens | Token share |
|---|---|---|---|---|
| dbc1c1bc6e27 | proximanova; 20 pt; bold; #4d4d4f; mixed | 103 | 646 | 26.69% |
| 1494e7e67142 | proximanova; 8 pt; bold; #ffffff; upper; cluster sizes 8-8.1 pt | 88 | 404 | 16.69% |
| e0c392887a3e | proximanova; 8 pt; bold; #355178; upper | 61 | 183 | 7.56% |
| f4dc67253cdf | proximanova; 18 pt; bold; #ffffff; upper | 33 | 148 | 6.12% |
| 3af8ad6fedc6 | proximanova; 9.8 pt; bold; #ffe180; upper; cluster sizes 9.8-10 pt | 42 | 117 | 4.83% |
| 3cee079f118c | proximanova; 10 pt; bold; #c02455; upper | 40 | 113 | 4.67% |
| 0a25faa644d8 | proximanova; 37.5 pt; bold; #343c46; uncased | 112 | 112 | 4.63% |
| abf56407eb17 | proximanova; 10 pt; bold; #027fa4; upper | 27 | 110 | 4.55% |

Full per-book metrics: [evaluation](../experiments/out/step6/spanish_us_history/evaluation.json).

### Book 2: Immigrant Children

Frozen title similarity threshold: 90.0/100.

Most Book 2 printed candidates are index rows with valid PDF labels. Its 0.56% printed title precision shows that valid labels alone do not distinguish a table of contents from an index. No post-hold-out tuning was performed.

| Navigation | Entries | Ref. headings | Title matches | Title precision / recall | Title + target matches | Title + target precision / recall | Unresolved / ambiguous |
|---|---|---|---|---|---|---|---|
| Bookmarks | 21 | 246 | 15 | 71.43% / 6.10% | 15 | 71.43% / 6.10% | 0 / 0 |
| Printed TOC | 1245 | 246 | 7 | 0.56% / 2.85% | 6 | 0.48% / 2.44% | 1 / 0 |
| Combined unique | 1261 | 246 | 15 | 1.19% / 6.10% | 15 | 1.19% / 6.10% | 1 / 0 |

| Repetition evidence | Count |
|---|---|
| Candidates | 22 |
| Unique retained candidate tokens | 1,307 |
| Not aligned to a reference unit (absence proxy) | 1,287 |
| Aligned to reference units (potential false candidates) | 20 |
| Aligned unit kinds | other: 16; paragraph: 4 |
| Position bands | top: 18; bottom: 2; side: 2 |
| Physical-page periodicity | even: 16; mixed: 4; odd: 2 |

Largest reference-aligned candidate groups; the source line is illustrative, not a furniture decision.

| Source line sample | Band | Pages | Confidence | Aligned / candidate tokens | Reference kinds |
|---|---|---|---|---|---|
| 125 | bottom | 12 | 0.561 | 10 / 12 | other: 10 |
| 27 | bottom | 4 | 0.369 | 4 / 4 | other: 4 |
| Chapter 1 | top | 141 | 0.928 | 2 / 282 | other: 1; paragraph: 1 |

Reference heading units: **246**. Top eight observed clusters follow; these are distributions, with no classifier or heading level.

| Style cluster | Observed style | Heading units touching cluster | Heading tokens | Token share |
|---|---|---|---|---|
| 7f3be5d9917d | palatino; 10.5 pt; bold; #231f20; mixed | 60 | 421 | 39.98% |
| 11aa46e61448 | palatino; 10.5 pt; bold; #231f20; upper | 77 | 258 | 24.50% |
| e74342433d9e | palatino; 10.5 pt; bold; #231f20; title | 46 | 101 | 9.59% |
| cb2407b96a22 | palatino; 18 pt; bold; #231f20; mixed | 12 | 97 | 9.21% |
| 125bcfe5a7e3 | palatino; 10.5 pt; italic; #231f20; title | 24 | 47 | 4.46% |
| 2cb6cacd1bca | palatino; 16 pt; bold, italic; #231f20; mixed | 5 | 38 | 3.61% |
| 5cb45e574d29 | palatino; 18 pt; bold; #231f20; title | 13 | 31 | 2.94% |
| 4affc42a35ab | palatino; 10.5 pt; italic; #231f20; mixed | 6 | 28 | 2.66% |

Full per-book metrics: [evaluation](../experiments/out/step6/immigrant_children/evaluation.json).

### Book 3: art-therapy index

Frozen title similarity threshold: 90.0/100.

| Navigation | Entries | Ref. headings | Title matches | Title precision / recall | Title + target matches | Title + target precision / recall | Unresolved / ambiguous |
|---|---|---|---|---|---|---|---|
| Bookmarks | 0 | 2 | 0 | n/a / 0.00% | 0 | n/a / 0.00% | 0 / 0 |
| Printed TOC | 0 | 2 | 0 | n/a / 0.00% | 0 | n/a / 0.00% | 0 / 0 |
| Combined unique | 0 | 2 | 0 | n/a / 0.00% | 0 | n/a / 0.00% | 0 / 0 |

| Repetition evidence | Count |
|---|---|
| Candidates | 2 |
| Unique retained candidate tokens | 41 |
| Not aligned to a reference unit (absence proxy) | 38 |
| Aligned to reference units (potential false candidates) | 3 |
| Aligned unit kinds | other: 3 |
| Position bands | bottom: 1; top: 1 |
| Physical-page periodicity | mixed: 1; odd: 1 |

Largest reference-aligned candidate groups; the source line is illustrative, not a furniture decision.

| Source line sample | Band | Pages | Confidence | Aligned / candidate tokens | Reference kinds |
|---|---|---|---|---|---|
| 280 | bottom | 9 | 1.000 | 3 / 9 | other: 3 |

Reference heading units: **2**. Top eight observed clusters follow; these are distributions, with no classifier or heading level.

| Style cluster | Observed style | Heading units touching cluster | Heading tokens | Token share |
|---|---|---|---|---|
| 1682fa2785a6 | acuminprocond; 22 pt; regular; #231f20; title | 2 | 4 | 100.00% |

Full per-book metrics: [evaluation](../experiments/out/step6/art_therapy_index/evaluation.json).

Unaligned repetition tokens are an absence proxy, not proof of reference absence or furniture. Reference-aligned tokens show potential false candidates and remain retained. Unit-kind counts may overlap for shared tokens; heading units can touch multiple style clusters. Heading-style statistics assign each token its containing line's dominant style cluster and lose within-line mixtures; full style distributions remain retained in the cached artifact. Physical PDF parity is separate from printed label parity.

## Language libraries and licenses

| Package | Pin | Scope | License | Recorded installed bytes, excluding bytecode |
|---|---|---|---|---|
| lingua-language-detector | 2.2.0 | default CPU runtime | [Apache-2.0](https://github.com/pemistahl/lingua-py/blob/main/LICENSE.txt) | 304,906,146 |
| RapidFuzz | 3.14.6 | default CPU runtime | [MIT](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE) | 6,561,872 |
| langid | 1.1.6 | comparison only; not required by the converter runtime | [BSD-2-Clause](https://github.com/saffsd/langid.py/blob/master/LICENSE) | 2,734,025 |

| Book | Library | Top-1 / language-bearing sample | Accepted correct / emitted | Warm ms / block |
|---|---|---|---|---|
| Book 1 | lingua-language-detector | 10 / 11 | 9 / 9 | 41.0143 |
| Book 1 | langid | 11 / 11 | no abstention wrapper | 3.8502 |
| Book 2 | lingua-language-detector | 11 / 11 | 9 / 10 | 36.8361 |
| Book 2 | langid | 11 / 11 | no abstention wrapper | 4.0113 |

Lingua 2.2.0 is selected behind `LanguageDetector` for native mixed-language segments, with all supported languages by default. The small monolingual sample favors langid on book 1; both score 11/11 on book 2. Each book also contains one manually annotated nonlinguistic block, excluded from Top-1 accuracy. Lingua confidently calls the personal-name-only index English: a documented false result, not corrected after hold-out sampling.

Comparison-time on-disk sizes, including generated bytecode: Lingua 290.78 MiB, langid 5.04 MiB; langid reuses existing NumPy. Warm timing averages five repetitions and includes Lingua segmentation. Constructor timing excludes lazy inference/model loading. Scores are library evidence, not calibrated correctness probabilities. No GPL/AGPL language or repetition candidate was installed.

The 24 source-native blocks were selected deterministically and annotated before predictions. Bilingual, Arabic, Hebrew and unspaced Japanese behavior is synthetic-test coverage. See the [annotated sample](../experiments/step6_language_sample.json), [measured comparison](../experiments/out/step6/language_comparison.json), [dependency audit](../experiments/out/step6/dependencies.json) and [dependency decisions](dependencies.md).

## Five review overlays

`S` labels the style cluster; red frames mark repetition candidates; blue frames and `T>` show printed navigation links. Sidecars preserve full IDs and incoming links. All five overlays were visually reviewed; map overlays are dense. Empty `T>` means the printed target is unresolved; its original locator label remains in the navigation artifact.

| Overlay | Sidecar |
|---|---|
| [evidence_p7](../experiments/out/step6/spanish_us_history/evidence_p7.png) | [line evidence](../experiments/out/step6/spanish_us_history/evidence_p7.json) |
| [evidence_p8](../experiments/out/step6/spanish_us_history/evidence_p8.png) | [line evidence](../experiments/out/step6/spanish_us_history/evidence_p8.json) |
| [evidence_p663](../experiments/out/step6/spanish_us_history/evidence_p663.png) | [line evidence](../experiments/out/step6/spanish_us_history/evidence_p663.json) |
| [evidence_p654](../experiments/out/step6/spanish_us_history/evidence_p654.png) | [line evidence](../experiments/out/step6/spanish_us_history/evidence_p654.json) |
| [evidence_p751](../experiments/out/step6/spanish_us_history/evidence_p751.png) | [line evidence](../experiments/out/step6/spanish_us_history/evidence_p751.json) |

## Hold-out discipline

| Book | Final whole-book runs | Frozen producer | Artifact key |
|---|---|---|---|
| Book 2 | 1 started / 1 completed | e979e0237af6c38f | 045d0d22a7df1d2b |
| Book 3 | 1 started / 1 completed | e979e0237af6c38f | 929d65938aaac8be |

Book 1 was the development source. Books 2 and 3 each ran once after freezing; the [hold-out log](../experiments/out/step6/holdout_runs.jsonl) records hashes and configuration. The explicitly requested book 2 library sample is separately recorded in the [language sample log](../experiments/out/step6/language_sample_runs.jsonl); it performed no whole-book evidence analysis or derived-gold evaluation.

## Limitations and decisions for review

- Navigation is partial evidence: complex wraps, nonstandard locators and repeated table/index structures may be missed or falsely proposed. Geometry-only TOC evidence can flag index/table pages and is explicitly ambiguous. Review per-book precision/recall and unresolved targets before later stages consume this evidence. No thresholds were tuned on the hold-outs.
- Repeated edge text can be real content. The K1 science-fixture `Energy` label is outside these three approved reference pairs, so no measured K1 result is claimed. Synthetic repeated content/table-label cases remain candidates, illustrating why Step 8 must decide furniture.
- Style clusters describe typography; reference headings can share body styles, and the mode can include retained furniture or production text. Cluster shares are not heading probabilities. Caps and other style attributes can produce numerous small clusters; no semantic grouping is inferred.
- Language scores can be confidently wrong on names; the annotated sample is small and has no naturally bilingual block. Whole-book mixed-segment counts are unvalidated model outputs, not bilingual truth. Confirm whether Lingua's roughly 291 MiB footprint and mixed-language segments justify the measured speed/size tradeoff. Changing engines later requires an explicit, logged cache/evaluation change.
- Native order is preserved as extraction evidence. Hyphen hypotheses only describe that sequence; no joins cross pages, and CJK word segmentation remains deferred.
- Review the evidence artifact shape and unresolved/ambiguous navigation policy before authorizing subsequent stages. This gate makes no heading, furniture or zone decision.

## Reproduce

From the project root (hold-out commands are for a fresh run; the runner refuses a second started run in the existing log):

```powershell
.venv/Scripts/python.exe experiments/step6_integrity.py
.venv/Scripts/python.exe experiments/step6_dependencies.py
.venv/Scripts/python.exe experiments/step6_source_crosscheck.py
.venv/Scripts/python.exe experiments/step6_run.py --book spanish_us_history --overlays
.venv/Scripts/python.exe experiments/step6_run.py --book immigrant_children --holdout
.venv/Scripts/python.exe experiments/step6_run.py --book art_therapy_index --holdout
.venv/Scripts/python.exe experiments/step6_report.py
```

Overlay an existing cached book artifact using explicit source, page and output arguments (from the project environment):

```powershell
python -m book_core overlay SOURCE.pdf --page PAGE --out OUTPUT.png --document-artifact BOOK_CACHE.json
```

Tests and Ruff must run from `backend/`; report generation follows their final completed logs. From `backend/`:

```powershell
../.venv/Scripts/python.exe -m pytest --junitxml=../experiments/out/step6/pytest.xml
../.venv/Scripts/python.exe -m ruff check .
../.venv/Scripts/python.exe -m ruff format --check .
```

The language comparison uses the committed annotations with `python experiments/step6_language_compare.py --compare`, recording any sample-only rerun. See [dependencies](dependencies.md) for installation pins and licenses.

**Step 6 stops here for owner review. Step 7 has not started.**
