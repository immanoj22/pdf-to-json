# Converter dependencies

Validated on CPython 3.14.8 / Windows x64, CPU only. Exact direct pins are in backend/pyproject.toml; complete installed pins are in backend/requirements-lock.txt.

| Package | Version | Scope | License |
|---|---|---|---|
| annotated-types | 0.8.0 | runtime | MIT |
| colorama | 0.4.6 | development | BSD-3-Clause |
| iniconfig | 2.3.1 | development | MIT |
| packaging | 26.3 | development | Apache-2.0 OR BSD-2-Clause |
| pip | 26.2.1 | bootstrap | MIT |
| pluggy | 1.6.0 | development | MIT |
| pydantic | 2.13.5 | runtime | MIT |
| pydantic-core | 2.46.5 | runtime | MIT |
| pygments | 2.21.0 | development | BSD-2-Clause |
| pymupdf | 1.28.2 | runtime | AGPL-3.0 OR Artifex commercial |
| pytest | 9.1.1 | development | MIT |
| regex | 2026.9.29 | runtime | Apache-2.0 AND CNRI-Python |
| ruff | 0.16.10 | development | MIT |
| setuptools | 78.1.0 | build | MIT |
| typing-extensions | 4.16.0 | runtime | PSF-2.0 |
| typing-inspection | 0.4.4 | runtime | MIT |

Evidence: installed wheel METADATA and bundled license files, recorded in [dependencies.json](../experiments/out/step2/dependencies.json). colorama's bundled license is BSD-3-Clause; setuptools declares MIT in its classifiers.

**PyMuPDF/MuPDF uses AGPL or Artifex commercial terms. Step 3 also brings bundled LGPL and GCC runtime notices (below).** Internal use is the accepted product scope; this does not change the package license. The default install has no GPU runtime, OCR, layout models or adapter libraries.

The lock covers this audited environment; it is a version lock, not a hashed wheel lock. pip is bootstrap tooling, not an application dependency. Existing Step 1 experiment environments (including Dulwich Git tooling) are separate and their licenses remain in the Phase 0 report.

## Step 3 additions

All four CPU-default wheels installed and imported on Python 3.14.8 / Windows x64.
Pins are in the backend project and full CPU lock; evidence is in
[dependencies.json](../experiments/out/step3/dependencies.json).

| Package | Pin | License and bundled notices | Result |
|---|---|---|---|
| Shapely | 2.2.0 | BSD-3-Clause; bundled GEOS LGPL-2.1 | import/STRtree OK |
| NetworkX | 3.7 | BSD-3-Clause | import/DiGraph OK |
| NumPy | 2.5.3 | BSD-3-Clause, 0BSD, MIT, Zlib, CC0; OpenBLAS/LAPACK BSD; **GCC runtime GPL-3.0-or-later WITH GCC-exception-3.1** | import/arrays OK |
| opencv-python-headless | 5.0.0.93 | Apache-2.0; wheel wrapper MIT; bundled FFmpeg LGPL-2.1 and other third-party notices | import/render/crops OK |
| torch, optional gpu extra | 2.14.1 | BSD-3-Clause source license; CUDA/runtime binary terms depend on the chosen distribution | CP314 Windows wheel resolves; not installed |
| imagehash | not needed | no added dependency | native exact image digests used |

Audited bundled notices: [Shapely](licenses/shapely/LICENSE.txt),
[GEOS](licenses/shapely/LICENSE_GEOS), [NetworkX](licenses/networkx/LICENSE.txt),
[NumPy including GCC runtime exception](licenses/numpy/LICENSE.txt),
[OpenCV](licenses/opencv/LICENSE.txt) and
[third-party codecs/platform components](licenses/opencv/LICENSE-3RD-PARTY.txt).
The OpenCV notice also describes components for other platforms/non-headless builds;
those are not claims that Qt/macOS libraries ship in this Windows headless environment.

PyTorch's source terms are in its [official license](https://github.com/pytorch/pytorch/blob/main/LICENSE).
The optional wheel was checked with pip dry-run/no dependencies: no GPU runtime or
weights were installed. Its binary dependency/license inventory needs an audit if
the optional GPU distribution is selected for packaging.


## Step 4b learned layout evidence (optional)

The optional `models` extra adds the official Transformers inference paths only.
The default runtime remains CPU-only and does not install Torch, Transformers or
weights. The `RegionDetector` adapters take an Extractor render and return region
observations; they have no text-retention, ledger or reading-order authority.

| Model | Immutable revision | Weight license | Safetensors bytes |
|---|---|---|---:|
| [Docling Heron](https://huggingface.co/docling-project/docling-layout-heron) | `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` | Apache-2.0 | 171,658,996 |
| [PP-DocLayoutV3](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors) | `e4f489dc536556fc1be02b973ba06756e0d4a2ac` | Apache-2.0 | 133,270,468 |

Both immutable revisions match the Phase 0 asset ledger. The source models are
published by their respective model owners; the inference API is
`AutoImageProcessor` + `AutoModelForObjectDetection`.
[Heron's official example](https://huggingface.co/docling-project/docling-layout-heron)
uses the corresponding RT-DETR classes, and the
[official PP-DocLayoutV3 Transformers documentation](https://huggingface.co/docs/transformers/model_doc/pp_doclayout_v3)
documents its AutoModel path. No Docling wrapper, Paddle runtime, OCR runtime or
remote model code is required.

| Direct optional package | Pin | License |
|---|---|---|
| Torch | 2.14.1 (installed 2.14.1+cpu) | BSD-3-Clause source; CPU wheel composite terms below |
| torchvision | 0.29.1 (installed 0.29.1+cpu) | BSD-3-Clause; bundled image-codec notices retained in installed wheel |
| Transformers | 5.19.0 | Apache-2.0 |
| Pillow | 12.3.0 | MIT-CMU; bundled codec notices retained in installed wheel |
| safetensors | 0.8.0 | Apache-2.0 |

Use official CPU wheels for the CPU baseline, then install the project extra:

```powershell
.venv/Scripts/python.exe -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python.exe -m pip install -e "./backend[models]"
```

A CUDA build can be chosen through PyTorch's official distribution instructions
for the optional GPU installation. Device `auto` probes CUDA and retries a failed
GPU operation on CPU; provenance records requested, resolved and execution
devices and any fallback reason. Gold runs explicitly request CPU. Downloads
and model output caches are configured inside the active project's ignored
cache directories. No reference-project environment or cache is reused or
modified.

Both adapters installed and executed successfully in the **main project .venv,
CPython 3.14.8 / Windows x64**, with no compatibility workaround or rejected
model. `pip check` found no broken requirements. Auto device resolution and
execution were CPU because CUDA was unavailable. The complex_map smoke produced
26 Heron and 17 PP regions at the unchanged 0.5 threshold; these are detector
observations, not text-retention counts. The downloaded safetensors lengths
exactly match Phase 0. Package metadata, license-file inventory, weight SHA-256
and inference results are in [models_environment.json](../experiments/out/step4b/models_environment.json).
The complete optional environment pins are in
[requirements-models-lock.txt](../backend/requirements-models-lock.txt);
the default CPU lock is unchanged.

The installed Torch CPU wheel declares:
`Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`.
This records bundled components as well as Torch's BSD source license. Pillow
declares MIT-CMU. torchvision declares BSD metadata and ships its BSD-3-Clause
license. Transformers and Hugging Face Hub declare Apache 2.0; safetensors has
the Apache classifier/license file. Transitive package versions and their
declared licenses are preserved in the inventory linked above. The two wheels
selected from the official CPU index were CP314 Windows builds; no CUDA wheel
or CUDA runtime dependency was installed.

Installation evidence:
[CPU wheel log](../experiments/out/step4b/install_cpu.log),
[CPU resolution report](../experiments/out/step4b/install_cpu_report.json),
[models extra log](../experiments/out/step4b/install_models.log),
[models resolution report](../experiments/out/step4b/install_models_report.json),
[pip check](../experiments/out/step4b/pip_check.log),
[model smoke log](../experiments/out/step4b/models_smoke.log).

## Step 6 document-wide evidence

These CPU packages were audited before installation in the active project `.venv`.
No GPL/AGPL language or repetition candidate was installed; earlier dependency terms
remain as documented above.

| Package | Pin | Scope | Official license |
|---|---|---|---|
| lingua-language-detector | 2.2.0 | default language evidence | [Apache-2.0](https://raw.githubusercontent.com/pemistahl/lingua-py/main/LICENSE.txt) |
| RapidFuzz | 3.14.6 | default repetition similarity | [MIT](https://raw.githubusercontent.com/rapidfuzz/RapidFuzz/main/LICENSE) |
| langid | 1.1.6 | optional `language-comparison` extra only | [BSD-2-Clause](https://raw.githubusercontent.com/saffsd/langid.py/master/LICENSE) |

Lingua is selected behind `LanguageDetector` for its native mixed-language segments.
It uses high accuracy, all supported languages by default, and explicit job language
restrictions when supplied. The sample does **not** establish a Lingua accuracy advantage:
langid was more accurate on book 1, faster, and smaller. Lingua occupies 304,906,502
installed bytes (290.78 MiB), including its bundled models; langid occupies 5,288,683
bytes (5.04 MiB), reusing the existing NumPy dependency.

| Annotated sample | Library | Top-1 correct / language-bearing blocks | Warm ms / block |
|---|---|---:|---:|
| Book 1 | Lingua | 10 / 11 | 41.0143 |
| Book 1 | langid | 11 / 11 | 3.8502 |
| Book 2 | Lingua | 11 / 11 | 36.8361 |
| Book 2 | langid | 11 / 11 | 4.0113 |

Each book has 12 deterministically selected native blocks, annotated before predictions;
one block per book has no identifiable natural-language wording and is excluded from
Top-1 accuracy. Warm timing averages five repetitions and includes Lingua segmentation.
The small sample is a smoke check, not a representative benchmark. Lingua emitted nine
accepted language results on book 1, all correct; on book 2, nine of ten were correct.
Its confident English result on the name-only index block is an explicit failure.
Scores are library confidence evidence, not calibrated correctness probabilities;
short or ambiguous text can retain alternatives with `und`. Bilingual and non-Latin
script behavior is covered separately by synthetic tests.

The [annotated sample](../experiments/step6_language_sample.json) records source digests,
span IDs and text digests. The [measured comparison](../experiments/out/step6/language_comparison.json)
records predictions, sizes, timings, frozen configuration and limitations; the
[sample-only log](../experiments/out/step6/language_sample_runs.jsonl) distinguishes this
explicitly requested book 2 comparison from the final whole-book hold-out run.
## Step 6b optional table, OCR, continuation, classifier and local VLM audit

These are future-stage candidates and synthetic CPU smokes, not production
classifiers or book conversion. Primary license metadata was checked before
installation or checkpoint download. The audit separates source code from
weights. All selected weights use exact repository revisions and SHA-256 hashes
in [dependency_audit.json](../experiments/out/step6b/dependency_audit.json);
[transitive_audit.json](../experiments/out/step6b/transitive_audit.json) records
new mandatory dependencies and exact Windows-wheel license inspection.

Sizes below are decimal MB of weight files, not installed or peak-memory sizes.
Every CPU estimate is an **unmeasured engineering estimate**; measured cold-stage
results follow separately. Python support marked measured means this synthetic
checkpoint call executed in CPython **3.14.8 / Windows x64 / CPU**, not a claim
about every optional upstream feature.

| Table candidate | Code license | Weight license / size | CPU estimate, unmeasured | Python 3.14.8 / maintenance evidence |
|---|---|---|---|---|
| Table Transformer detection | [MIT](https://raw.githubusercontent.com/microsoft/table-transformer/main/LICENSE); Transformers runtime Apache-2.0 | Owner [MIT](https://huggingface.co/microsoft/table-transformer-detection/blob/2357cbe2b5a5d1c03e54f32764f06058933b65ab/README.md); 115.32 MB | 2-15 s / synthetic image | Same installed runtime as structure model; detection checkpoint not smoked. Original repo archived, last push 2024-06-24; checkpoint 2023-09-06. |
| Table Transformer structure | Same MIT source / Apache-2.0 runtime | Owner [MIT](https://huggingface.co/microsoft/table-transformer-structure-recognition/blob/f4d4bdc85c3fe4b1fa49658882a5d38bbdd0f343/README.md); 115.43 MB | 2-15 s / synthetic crop | Measured. Original repo archived, last push 2024-06-24; checkpoint 2023-09-06. |
| Docling TableFormer fast / accurate | [MIT](https://raw.githubusercontent.com/docling-project/docling-ibm-models/main/LICENSE) | Owner declares [CDLA-Permissive-2.0 and Apache-2.0](https://huggingface.co/docling-project/docling-models/blob/2199320848bb9a8a519d22e4b528185a4f9a6f64/README.md); fast 145.45 / accurate 212.76 MB; retain both declared terms | 5-30 s / synthetic crop | Fast measured; accurate not smoked. Active code, last push 2026-09-18; model repo 2025-12-03. |

| OCR candidate | Code license | Weight license / size | CPU estimate, unmeasured | Python 3.14.8 / maintenance evidence |
|---|---|---|---|---|
| Tesseract + tessdata_fast eng/spa | Engine [Apache-2.0](https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE) | [Apache-2.0](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/LICENSE); eng 4.11 / spa 2.29 MB; pinned tree recorded in [metadata](../experiments/out/step6b/tesseract_weight_metadata.json) | 0.5-5 s / synthetic image | Standalone engine has no CPython ABI, but no engine binary is installed. pytesseract 0.3.13 is pure Python; tesserocr 2.11.0 has no CP314 Windows wheel. Engine active, last push 2026-10-09; fast data 2024-08-01. Not installed or smoked. |
| PP-OCRv5 mobile detector safetensors | PaddleOCR [Apache-2.0](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE); Transformers runtime [Apache-2.0](https://raw.githubusercontent.com/huggingface/transformers/main/LICENSE) | Owner [Apache-2.0](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det_safetensors/blob/c5041d225cf951ff06900ab81a3c7d543c45e2ad/README.md); 14.33 MB | 1-5 s / synthetic image | Measured through existing Transformers; no Paddle native runtime. Code active, last push 2026-09-16; checkpoint 2026-04-03. |
| PP-OCRv5 Latin mobile recognizer safetensors | Same Apache-2.0 source/runtime | Owner [Apache-2.0](https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec_safetensors/blob/47901138f5f32dad06282fa88d2c672fa816d450/README.md); 22.66 MB | 0.2-3 s / synthetic line | Call executed, but synthetic text recognition failed; no accuracy claim. Code active 2026-09-16; checkpoint 2026-04-22. |

The native Paddle package 3.3.1 provides no Windows CP314 wheel. PaddleOCR 3.7.0's
pure Python wheel does not remedy that runtime constraint. The safetensors path
uses installed Transformers model implementations and needs no Paddle package.
Only synthetic images were OCRed; normal digital text and books were not OCRed.
The installed OpenCV/Shapely dependencies were already audited in Step 4b.

| Continuation-evidence candidate | Code license | Weight license / size | CPU estimate, unmeasured | Python 3.14.8 / maintenance evidence |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | Transformers [Apache-2.0](https://raw.githubusercontent.com/huggingface/transformers/main/LICENSE); no sentence-transformers package required | Owner [Apache-2.0](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/blob/e8f8c211226b894fcb81acc59f3b34ba3efd5f42/README.md); 470.64 MB | 1-10 s / four short strings | Measured with masked mean pooling. Transformers active, last push 2026-10-09; checkpoint 2026-01-28. |
| multilingual-e5-small | Same Apache-2.0 inference code | Owner [MIT](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md); 470.64 MB | 1-10 s / four short strings | Compatible runtime metadata; checkpoint not smoked. Transformers active 2026-10-09; checkpoint 2026-04-02. |

Embeddings provide semantic similarity, not proven paragraph continuation.
MiniLM is the lighter-dependency smoke choice, reusing AutoTokenizer/AutoModel.
Neither candidate has been trained or evaluated for this project's continuation
decisions; a language-neutral feature/model interface must retain uncertainty.

| Classifier candidate | Code / weights | Size / CPU estimate, unmeasured | Python 3.14.8 / maintenance / disposition |
|---|---|---|---|
| scikit-learn 1.9.1 | Source [BSD-3-Clause](https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/COPYING); no pretrained weights | CP314 Windows wheel 8.38 MB; under 1 s / small synthetic fit | CP314 wheel available; active code last push 2026-10-07. **Step 7: allowed and installed** (optional `classical-ml` extra); see Step 7 section. |
| LightGBM 4.7.0 | Source [MIT](https://raw.githubusercontent.com/lightgbm-org/LightGBM/master/LICENSE); no pretrained weights | Windows wheel 1.36 MB; under 1 s / small synthetic fit | py3 Windows wheel available; active code last push 2026-10-06. **Step 7: allowed and installed** (optional `classical-ml` extra); see Step 7 section. |
| Torch linear classifier | Source [BSD-3-Clause](https://raw.githubusercontent.com/pytorch/pytorch/main/LICENSE); existing CPU wheel's complete permissive license expression is recorded above; no external weights | Reuses installed Torch 2.14.1+cpu; under 1 s / small synthetic fit | Measured; active code last push 2026-10-09. Synthetic-only fitted weights are not a production classifier. |

The exact `scipy-1.18.1-cp314-cp314-win_amd64.whl` license explicitly identifies
`scipy.libs/libscipy_openblas*.dll` with statically linked GCC runtime under
`GPL-3.0-or-later WITH GCC-exception-3.1`. The project's no-GPL policy excludes
that distribution despite the exception. The [wheel audit](../experiments/out/step6b/transitive_audit.json)
contains the primary download URL, file SHA-256, internal license hash and term
flags. Wheel bytes were inspected in memory for licensing and never installed.
The remaining mandatory packages checked were joblib 1.6.0 (BSD-3-Clause),
threadpoolctl 3.7.0 (BSD-3-Clause), narwhals 2.26.0 (MIT) and cloudpickle 3.1.2
(BSD-3-Clause); none was needed or installed after excluding these workflows.

| Local VLM candidate | Code license | Weight license / size | CPU estimate, unmeasured | Python 3.14.8 / maintenance / disposition |
|---|---|---|---|---|
| SmolVLM-256M-Instruct | Transformers [Apache-2.0](https://raw.githubusercontent.com/huggingface/transformers/main/LICENSE) | Owner [Apache-2.0](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct/blob/7e3e67edbbed1bf9888184d9df282b700a323964/README.md); 513.03 MB | 30-180 s / 16 output tokens | Measured; Transformers active 2026-10-09; checkpoint 2025-04-08. Checkpoint emits a pad-token/vocabulary warning, retained in smoke evidence. |
| SmolVLM-500M-Instruct | Same Apache-2.0 inference code | Owner [Apache-2.0](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/blob/a7da5b986cb59b408707209984f360a5f4ad7e47/README.md); 1,015.03 MB | 60-300 s / 16 output tokens | Compatible runtime metadata; not downloaded or smoked. Transformers active 2026-10-09; checkpoint 2025-04-08. |
| Qwen2.5-VL-3B-Instruct | Apache-2.0 inference framework | [Qwen RESEARCH LICENSE](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/raw/main/LICENSE), section 2(a) noncommercial and 2(b) commercial permission | 7509.34 MB (metadata only); CPU estimate omitted for excluded candidate | Excluded for noncommercial weights; no install/download/smoke. Transformers code active 2026-10-09; checkpoint 2025-04-06. [Pinned exclusion metadata](../experiments/out/step6b/qwen_exclusion_metadata.json). |

Optional synthetic formula smoke also verified official
[PP-FormulaNet-L safetensors](https://huggingface.co/PaddlePaddle/PP-FormulaNet-L_safetensors/blob/69869f2891cc61347d230ef234bcc8b8d297c43a/README.md)
(Apache-2.0 owner declaration; 724.49 MB) through existing Apache-2.0 Transformers
code. It requires no SciPy, albumentations, Paddle runtime or Levenshtein package.
The pinned revision and SHA-256 are in the same audit. Its synthetic `E = mc²`
image produced `\mathsf{E}=\mathsf{m}\mathsf{c}^{\,\,2}`. Optional `ftfy` cleanup
was unavailable and remains a recorded warning. This is recognizer evidence;
no book equation was converted. Formula/converter alternatives are detailed in
the separate math audit below.

Root centrally installed only `timm==1.0.30` (Apache-2.0) and
`docling-ibm-models==4.0.3` (MIT) for these smokes, using `--no-deps` after checking
that mandatory dependencies already existed. Wheel SHA-256s and exact primary
URLs are in the audit. No mandatory default-install dependency was added by this
experiment. Keep future models as optional extras. No downloaded Python code or
`trust_remote_code` was used; all model loads were local after pinned download,
with pretrained backbone downloads disabled for TATR. Models and support assets
are contained in the active project's `.cache/step6b/models/hf`.

| Synthetic CPU smoke | Expected / observed | Cold model-stage seconds |
|---|---|---:|
| [TATR structure](../experiments/out/step6b/smoke_tatr.json) | 3 rows / 2 columns; observed 3 rows / 2 columns plus header/table candidates | 21.87 |
| [TableFormer fast](../experiments/out/step6b/smoke_tableformer.json) | 3 rows / 2 columns; observed 3 rows / 2 columns and 6 cells | 15.11 |
| [Paddle detector](../experiments/out/step6b/smoke_ocr_det.json) | 1 line; observed 1 box, model score 0.9509 | 33.86 |
| [Paddle Latin recognizer](../experiments/out/step6b/smoke_ocr_rec.json) | `Hello mundo 123`; observed `cYamaGntaYlowb`, model score 0.7689: accuracy failure | 25.52 |
| [MiniLM](../experiments/out/step6b/smoke_minilm.json) | English/Spanish translation cosine 0.9549; unrelated topic -0.0802 | 25.03 |
| [Torch classifier](../experiments/out/step6b/smoke_torch_classifier.json) | 8 synthetic binary labels; 8 matched | 4.22 |
| [SmolVLM-256M](../experiments/out/step6b/smoke_smolvlm.json) | Red square; observed "The shape is a square with a red background." | 78.37 |
| [PP-FormulaNet-L](../experiments/out/step6b/smoke_formula.json) | `E = mc²`; produced equivalent styled LaTeX hypothesis | 41.66 |

Cold-stage measurements include package imports, model loading, preprocessing
and CPU inference; development work ran concurrently. They are smoke timings,
not a controlled speed benchmark. Total wall times also include downloads where
requested. First TATR/Paddle detector calls exposed scaffold API mismatches;
[the TATR attempt](../experiments/out/step6b/smoke_tatr_first_api_error.json) and
[detector attempt](../experiments/out/step6b/smoke_ocr_det_first_api_error.json)
remain recorded. After API corrections both execute. TATR retains three
unexpected BatchNorm `num_batches_tracked` checkpoint buffers; no missing learned
parameter is silently accepted as proof of identical architecture. OCR failure,
model warnings and small sample sizes prevent a production accuracy claim.

Reproduce optional licensing metadata with `python experiments/step6b_dependency_audit.py`
and `python experiments/step6b_transitive_audit.py`. Run one audited synthetic
checkpoint with `python experiments/step6b_smoke.py --candidate NAME --download`;
choices are `tatr`, `tableformer`, `ocr_det`, `ocr_rec`, `minilm`, `smolvlm`,
`formula`, and `torch_classifier`. Omit `--download` after assets are present.
The scripts never access PDFs, gold, benchmark caches or old-project resources.

## Step 6b math candidates and optional installation

The owner's confirmed exclusion applies to restricted candidates; none below was
installed unless explicitly marked measured. Audit date: 2026-10-09. Separate
code/weight terms, upstream text hashes and repository maintenance timestamps are
preserved in [math_dependency_audit.json](../experiments/out/step6b/math_dependency_audit.json).
[Weight metadata](../experiments/out/step6b/excluded_math_weight_metadata.json)
was read without downloading excluded weights. CPU estimates below are planning
ranges, not benchmarks. Sizes use decimal MB.

| Formula candidate | Code license | Weights / size | CPU estimate / Python 3.14.8 | Maintenance / disposition |
|---|---|---|---|---|
| PP-FormulaNet-L through Transformers 5.19.0 | PaddleOCR and inference code Apache-2.0 | Owner [Apache-2.0](https://huggingface.co/PaddlePaddle/PP-FormulaNet-L_safetensors/blob/69869f2891cc61347d230ef234bcc8b8d297c43a/README.md); 724.49 MB | 5-60 s / equation, unmeasured inference estimate; actual cold stage 41.66 s; measured on CP314 Windows CPU | Selected synthetic smoke; official Transformers implementation, no remote code or Paddle install. Exact model revision and hashes in [smoke](../experiments/out/step6b/smoke_formula.json). |
| pix2tex 0.1.4 / LaTeX-OCR | [MIT](https://github.com/lukas-blecher/LaTeX-OCR/blob/main/LICENSE) | Official [v0.0.1 release declares CC BY-NC-SA 4.0 weights](https://github.com/lukas-blecher/LaTeX-OCR/releases/tag/v0.0.1); 102.11 MB + 19.44 MB resizer | 3-60 s / equation, unmeasured; no CP314 claim, old timm 0.5.4 / x-transformers pins | Last push 2025-01-18, not archived. Excluded for noncommercial weights; standard dependencies also pull the audited SciPy Windows GPL runtime bundle. No package or weights installed. |
| UniMERNet 0.2.3 tiny | [Apache-2.0](https://github.com/opendatalab/UniMERNet/blob/main/LICENSE) | Owner [Apache-2.0](https://huggingface.co/wanderkid/unimernet_tiny/blob/3f09ac4b1cd583be47ea20a7d7daef839473028a/README.md); 430.08 MB | 5-120 s / equation, unmeasured; old Transformers 4.42.4/tokenizer stack unverified on CP314 | Last push 2025-09-28, not archived. **Step 7: allowed, deferred** (blocked on CPython 3.14); see Step 7 section. |
| Nougat small/base | [MIT code](https://github.com/facebookresearch/nougat/blob/main/LICENSE) | Upstream [CC BY-NC 4.0 model terms](https://github.com/facebookresearch/nougat/blob/main/LICENSE-MODEL.md); small 989.98 MB, base 1,395.22 MB | Excluded; no CPU test or CP314 compatibility claim | Last push 2025-02-21, not archived. Excluded by the owner's confirmed Nougat decision and upstream noncommercial terms. The small HF card says CC-BY-4.0 while upstream model terms say NC; the discrepancy is retained in metadata and does not authorize installation. |
| Texify | [GPL-3.0 code](https://github.com/VikParuchuri/texify/blob/master/LICENSE) | Owner [CC BY-SA 4.0](https://github.com/VikParuchuri/texify#commercial-usage); 625.07 MB | Excluded; no CPU test or CP314 claim | Archived 2025-01-29, deprecated by owner. Excluded for GPL code; weights also have reciprocal terms. No install/download. |
| PadishahIII latex-ocr | Owner [MIT code and weights](https://github.com/PadishahIII/latex-ocr#license) | Owner MIT; 269.17 MB / 67M parameters | 3-60 s / equation, unmeasured; Python >=3.11 declared, CP314 untested | Last push 2026-09-03. Standard workflow excluded: [mandatory python-Levenshtein](https://github.com/PadishahIII/latex-ocr/blob/main/pyproject.toml) depends on [GPL Levenshtein](https://github.com/rapidfuzz/Levenshtein/blob/main/LICENSE). No install/download. |

No selected candidate has unclear code or weight terms. The explicitly excluded
Nougat distribution remains excluded despite conflicting small-model card
metadata. Candidate/repository licensing does not establish training-data rights
or production accuracy.

| Math tree / conversion component | Code license / weights | Size | CPU / CP314 compatibility / maintenance |
|---|---|---|---|
| Project glyph/rule geometry frontend | New project-owned interfaces only; no third-party model or weights | No implemented recognizer | Unavailable stub; no speed estimate or accuracy claim. Required frontend remains future work; this step supplies typed geometry and source contracts. |
| SymPy 1.14.0 AST backend | [BSD-3-Clause](https://github.com/sympy/sympy/blob/master/LICENSE); no weights | 72.97 MB installed inventory | Synthetic AST measured on CP314: 0.032 s cold construction. Existing Torch dependency, no new install. Active, last push 2026-10-09. Algebra component, not a glyph geometry recognizer. |
| MathJax 4.1.3 parser / converter | [Apache-2.0](https://github.com/mathjax/MathJax/blob/master/LICENSE); no weights | 19.97 MB unpacked package metadata | JS subprocess has no CPython ABI; Node bridge untested/uninstalled. Estimated 0.01-1 s / short expression after runtime startup, unmeasured. Active, last push 2026-07-03. [Registry metadata](../experiments/out/step6b/mathjax_metadata.json). Geometry frontend still required. |
| latex2mathml 3.81.1 converter | [MIT](https://github.com/roniemartinez/latex2mathml/blob/master/LICENSE); no weights | 0.65 MB installed inventory | Python >=3.10; measured CP314. Three synthetic conversions 0.15-0.47 ms each. Active, last push 2026-10-05. Selected optional converter smoke; no production adapter wired. |

The MathBuilder candidates are components of a future source-referenced geometry
implementation. None claims to reconstruct digital equations today. The
converter alternatives are latex2mathml and a MathJax bridge; SymPy is an AST
backend, not a replacement for layout evidence. See
[synthetic math smoke](../experiments/out/step6b/smoke_math_backends.json).
No book equations were converted.

Optional extras now explicitly separate models from the default installation:

| Extra | Exact new direct pins | Purpose |
|---|---|---|
| `language-evidence` | lingua-language-detector 2.2.0 | Bundled language models; moved out of default dependencies |
| `accuracy-models` | timm 1.0.30; docling-ibm-models 4.0.3; existing Torch/torchvision/Transformers/Pillow/safetensors pins | Synthetic candidate smokes; no provider is enabled automatically |
| `math-conversion` | latex2mathml 3.81.1 | Optional synthetic conversion backend |

The prior Step 6 dependency description is historical: Step 6b now defaults
Lingua to Settings languages spa/eng and requires the language-evidence extra.
The installed environment retains Lingua for unchanged tests and the authorized
book-1 rerun; default project metadata no longer requires it. No model download
runs during package installation or `book_core` import. New packages were
installed centrally with `--no-deps` only after license/dependency verification;
no existing runtime pin changed. Editable metadata was refreshed without
resolving dependencies ([log](../experiments/out/step6b/editable_refresh.log)).

[requirements-accuracy-lock.txt](../backend/requirements-accuracy-lock.txt)
records the complete audited optional CPU smoke environment; it includes the
existing model runtime lock. The separate
[language lock](../backend/requirements-language-lock.txt) records the optional
bundled model. The [installed inventory](../experiments/out/step6b/optional_environment.json)
verifies all 55 combined pins and license-file hashes; [pip check](../experiments/out/step6b/pip_check.log)
passes. No SciPy, scikit-learn, LightGBM, albumentations or Levenshtein package
was installed. Reproduce synthetic math with
`python experiments/step6b_math_smoke.py`; audit snapshots with
`python experiments/step6b_formula_audit.py`. Prior package exceptions/terms
remain historical and were not expanded by this step.

## Step 7: GCC runtime exception allowed; classical ML installed; UniMERNet deferred

Owner decision (see [decisions.md](decisions.md)): bundled compiler runtimes under
`GPL-3.0-or-later WITH GCC-exception-3.1`, as in the NumPy and SciPy Windows wheels, are
allowed. The Step 6b exclusions of scikit-learn, LightGBM and UniMERNet that rested only on
that SciPy bundle are lifted. The Step 6b rows above are kept as history with a pointer here.

| Package | Pin | License (wheel metadata) | Status |
|---|---|---|---|
| scikit-learn | 1.9.1 | BSD-3-Clause (bundled array_api_compat / array_api_extra notices) | Installed, optional `classical-ml` extra |
| LightGBM | 4.7.0 | MIT | Installed, optional `classical-ml` extra |
| SciPy | 1.18.1 | BSD-3-Clause; bundled OpenBLAS with GCC runtime under GPL-3.0-or-later WITH GCC-exception-3.1 (now allowed) | Installed as required dependency |
| joblib / threadpoolctl / narwhals / cloudpickle | 1.6.0 / 3.7.0 / 2.26.0 / 3.1.2 | BSD-3-Clause / BSD-3-Clause / MIT / BSD-3-Clause | Installed as required dependencies |

Installed in the main environment with binary wheels only; `pip check` passes. No existing pin
changed. Neither package has pretrained weights. Exact pins:
[requirements-classical-ml-lock.txt](../backend/requirements-classical-ml-lock.txt);
install log: [classical_ml_install.log](../experiments/out/step7/classical_ml_install.log).
Both stay unused by the pipeline until a later step needs them.

| Synthetic CPU smoke | Result | Seconds (fit + predict) |
|---|---|---:|
| scikit-learn LogisticRegression, 64 synthetic points, one held-out sample | expected 1, predicted 1: pass | 22.05 (cold import while six layout workers ran) |
| LightGBM LGBMClassifier (20 trees, 1 thread), same data | expected 1, predicted 1: pass | 0.24 |

Evidence, including license-file SHA-256s: [smoke_classical_ml.json](../experiments/out/step7/smoke_classical_ml.json).
Runtime evidence only; no accuracy claim. Reproduce: `python experiments/step7_smoke.py`.

**UniMERNet 0.2.3: allowed, deferred (blocked on CPython 3.14).** Code Apache-2.0; tiny weights
owner-declared Apache-2.0 (Step 6b revision `3f09ac4b`). Weights were not downloaded.

1. Upstream pins `transformers==4.42.4`, which requires `numpy<2.0,>=1.17`. NumPy 1.x publishes no
   CPython 3.14 wheel; resolution fails with
   `ResolutionImpossible: transformers 4.42.4 depends on numpy<2.0 and >=1.17`, and building from
   source fails (`numpy ... metadata-generation-failed`; no C compiler on this machine).
2. In a temporary isolated CPython 3.14 environment with the project's transformers 5.19.0 (all
   ~90 resolved dependencies permissively licensed), installation succeeded but `pip check` reports
   `unimernet 0.2.3 has requirement transformers==4.42.4, but you have transformers 5.19.0`, and the
   model cannot be imported: `UniMERModel` inherits the BLIP-2 Q-Former, whose
   `from transformers.modeling_utils import apply_chunking_to_forward` raises
   `ImportError: cannot import name 'apply_chunking_to_forward' from 'transformers.modeling_utils'`
   (removed in transformers 5.x).
3. UniMERNet also pins `timm<0.10` and `opencv-python<5`, which conflict with the main environment
   (timm 1.0.30, opencv-python-headless 5.0.0.93), so it cannot join the main environment either.

No source was patched and no inference ran. The temporary environment was deleted. The main
environment was not modified for UniMERNet. Logs: [unimernet_install.log](../experiments/out/step7/unimernet_install.log).
**PP-FormulaNet-L remains the formula-recognition candidate.** Revisit when UniMERNet supports
transformers 5.x / NumPy 2, or if the owner approves a separate interpreter for it.

