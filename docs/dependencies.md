# Converter dependencies

Optional Windows AMD acceleration after Step 18 is documented in [amd_gpu.md](amd_gpu.md).
Its dependencies stay outside the default CPU installation.

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


## Step 12 optional alt-text drafts

| Model | Immutable revision | Weight licence | Architecture |
|---|---|---|---|
| [SmolVLM-256M-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct) | `7e3e67edbbed1bf9888184d9df282b700a323964` | Apache-2.0 | Idefics3 (Transformers `AutoModelForImageTextToText`) |

Used only when `FigureSettings.alt_text_drafts` is on (default off), through the existing
optional `models` extra (Torch 2.14.1+cpu, Transformers 5.19.0, Pillow 12.3.0); no new
package. Verified on CPython 3.14.8 / Windows x64, CPU: weights downloaded into the
project's ignored Hugging Face cache and one English draft generated
([smoke result](../experiments/out/step12/alt_text/smoke.json)). Image export itself uses
OpenCV and PyMuPDF only.

## Step 13a: fontTools core dependency; UniMERNet re-check

| Package | Licence | Use | Decision |
|---|---|---|---|
| fontTools 4.66.1 | MIT | Embedded font programs: OpenType MATH table, character-map coverage, glyph names for the character repair layer (`book_core.equations.fonts`) | **Core dependency** (pure Python, CPython 3.14.8 verified; installed since Step 11d experiments) |
| UniMERNet 0.2.3 | Apache-2.0 | Formula recognition alternative | **Not added**: pins Transformers 4.42.4 / timm < 0.10 / opencv-python < 5 and resolves NumPy 1.26.4 (no CP314 wheel; source build needs a compiler). Log: `experiments/out/step13/dependencies/unimernet_dry_run.log` |


## Step 13c: MathML frameworks (Part 0)

| Package | Version | Licence | CPython 3.14 | Use | Decision |
|---|---|---|---|---|---|
| lxml | 6.1.3 (released 2026-09-02) | BSD-3-Clause | cp314 wheel | Writes MathML and validates every MathML string (well-formed, MathML 3 presentation structure) | **Core dependency** (`pyproject.toml`, `requirements-lock.txt`); [install log](../experiments/out/step13c/dependencies/lxml_install.log) |
| PP-FormulaNet-L | `PaddlePaddle/PP-FormulaNet-L_safetensors` @ `69869f2891cc61347d230ef234bcc8b8d297c43a` | Apache-2.0 (code and weights) | yes (Transformers 5.19.0, Torch 2.14.1+cpu) | Image path and the isolated readings of drawn glyph shapes (`book_core.mathml.recognition`) | Unchanged optional `models` extra; weights in the project Hugging Face cache |
| latex2mathml | 3.81.1 | MIT | pure Python | Recognizer LaTeX to a tree | Optional `math-conversion` extra (unchanged) |
| SymPy | 1.14.0 | BSD-3-Clause | pure Python | Parse check and arithmetic consistency | Added to the `math-conversion` extra (already installed through Torch); the check reports "unavailable" without it |
| fontTools | 4.66.1 | MIT | pure Python | (Step 13a font evidence; not used by 13c) | Core (unchanged) |
| UniMERNet | 0.2.3, tiny weights `wanderkid/unimernet_tiny` @ `3f09ac4b1cd583be47ea20a7d7daef839473028a` | Apache-2.0 (code and weights) | **no** (see below) | Comparison only | **Not kept**; side environment deleted at the Step 13c gate (rebuild steps below) |

The stage imports only core packages at module level (lxml, OpenCV, NumPy, PyMuPDF);
latex2mathml and SymPy are imported where used and degrade cleanly. Image recognition is
"auto": on when the models and math-conversion extras are installed, otherwise the run warns
and drawn equations get image fallbacks for review.

**UniMERNet, option (a): throwaway venv, `--no-deps`, current NumPy — fails.** A venv reading
the project environment's packages read-only (a `.pth` file; the main environment was not
modified) with `unimernet 0.2.3 --no-deps` and its pure-Python helpers: the import stops at
`ImportError: cannot import name 'apply_chunking_to_forward' from
'transformers.modeling_utils'` (removed in Transformers 5.x). No source was patched. The venv
was deleted. [Log](../experiments/out/step13c/dependencies/unimernet_a_venv.log).

**Option (b): side CPython 3.12 environment, called as a subprocess — works.** CPython
3.12.10 from the official NuGet `python` package (SHA-256
`0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8`, extracted under the
git-ignored `.cache/side_envs/`, no system install) with a venv holding UniMERNet's own pins
(Transformers 4.42.4, NumPy 1.26.4, timm 0.9.16, Torch 2.5.1+cpu); `fairscale` 0.4.13 has only
a pure-Python sdist (built locally, no compiler); `datasets` 2.21.0 and `pyarrow` 17.0.0 were
pinned because the resolver's newest `pyarrow` refuses NumPy 1.x at import. `pip check`
passes. The checkpoint is read with `torch.load(weights_only=True)`. The worker
(`experiments/step13c_unimernet_worker.py`) reads PNG paths and writes LaTeX; the main
environment is never altered. [Log](../experiments/out/step13c/dependencies/unimernet_b_side_env.log),
[freeze](../experiments/out/step13c/dependencies/unimernet_side_env_freeze.txt).

**UniMERNet side environment deleted (owner decision at the Step 13c gate).** The comparison
readings stay in `experiments/out/step13c/unimernet/`. Exact rebuild (PowerShell, from the
project root; nothing touches the main environment):

```powershell
# 1. Self-contained CPython 3.12.10 (official NuGet package; no system install)
New-Item -ItemType Directory -Force .cache\side_envs | Out-Null
Invoke-WebRequest https://www.nuget.org/api/v2/package/python/3.12.10 -OutFile .cache\side_envs\python.3.12.10.zip
# expected SHA-256: 0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8
Expand-Archive .cache\side_envs\python.3.12.10.zip .cache\side_envs\python312
.cache\side_envs\python312\tools\python.exe -m venv .cache\side_envs\unimernet
$py = ".cache\side_envs\unimernet\Scripts\python.exe"
# 2. CPU Torch, then UniMERNet with its own pins (fairscale 0.4.13 is a pure-Python sdist)
& $py -m pip install --only-binary :all: --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchvision==0.20.1
& $py -m pip install --prefer-binary --only-binary numpy,torch,torchvision,opencv-python,scipy,scikit-image,pandas,tokenizers,safetensors,matplotlib,pillow -r experiments\out\step13c\dependencies\unimernet_side_env_freeze.txt
# 3. The frozen set includes datasets 2.21.0 / pyarrow 17.0.0 for NumPy 1.26.
& $py -m pip check
# 4. Weights (Apache-2.0), immutable revision, into the project model cache
& $py -c "from huggingface_hub import snapshot_download; snapshot_download('wanderkid/unimernet_tiny', revision='3f09ac4b1cd583be47ea20a7d7daef839473028a', cache_dir='.cache/huggingface')"
```

Resolved versions (complete list:
[unimernet_side_env_freeze.txt](../experiments/out/step13c/dependencies/unimernet_side_env_freeze.txt),
78 packages): unimernet 0.2.3, transformers 4.42.4, tokenizers 0.19.1, numpy 1.26.4, torch
2.5.1+cpu, torchvision 0.20.1+cpu, timm 0.9.16, albumentations 1.4.24, albucore 0.0.23,
fairscale 0.4.13, opencv-python 4.11.0.86, datasets 2.21.0, pyarrow 17.0.0. Run with
`experiments/step13c_unimernet.py --book <book>` (the worker loads the checkpoint with
`torch.load(weights_only=True)`). The tiny weights (430 MB) remain in the project Hugging Face
cache (`.cache/huggingface/models--wanderkid--unimernet_tiny`) and can be deleted separately.

## Step 14a: table frameworks

Licences and CPython 3.14.8 / Windows x64 / CPU checked before use; versions recorded.
Weight files and SHA-256 are in
[table_model_weights.json](../experiments/out/step14a/dependencies/table_model_weights.json).

| Framework | Version / revision | Code licence | Weight licence | CPython 3.14 | Use |
|---|---|---|---|---|---|
| Table Transformer detection | `microsoft/table-transformer-detection` @ `2357cbe2` | MIT | MIT (owner card) | yes (Transformers 5.19.0, timm 1.0.30) | **Production evidence**: one of the three table detectors (with Heron and PP-DocLayoutV3), cached per page |
| Table Transformer structure | `microsoft/table-transformer-structure-recognition` @ `f4d4bdc8` | MIT | MIT | yes | Structure comparison only |
| TableFormer accurate / fast | `docling-project/docling-models` @ `21993208`, `docling-ibm-models` 4.0.3 | MIT | CDLA-Permissive-2.0 and Apache-2.0 (owner card; both retained) | yes | Structure comparison only |
| Heron, PP-DocLayoutV3 | as Step 4b | Apache-2.0 | Apache-2.0 | yes | Production evidence (their `table` boxes; cached since Step 12) |
| pdfplumber | 0.11.10 | MIT | — | yes (pure Python) | Comparison only |
| Camelot | 2.0.0 | MIT | — | yes (pure Python) | Comparison only; **image backend pdfium only, fallback off** (`backend="pdfium", use_fallback=False`); the Ghostscript backend (AGPL) is never installed or used |

The `models` extra gains `timm==1.0.30` (Apache-2.0; already installed through the Step 6b
accuracy smoke): the Table Transformer checkpoints use a timm backbone. Its backbone weights
come from the checkpoint itself (`use_pretrained_backbone = False`); nothing else is
downloaded. New optional extra `table-comparison` (pdfplumber, Camelot) for the comparison
scripts only; the converter never imports it. Its resolved dependencies are all permissive:
pdfminer.six (MIT), pypdfium2 (Apache-2.0 / BSD-3-Clause; the bundled PDFium build licences
include ICU build scripts under GPL with the Autoconf exception, not shipped code, and FreeType
under its FTL/GPLv2 choice), playa-pdf (MIT), pandas (BSD-3-Clause), openpyxl (MIT),
tabulate (MIT), cryptography (Apache-2.0 OR BSD-3-Clause), cffi (MIT-0), charset-normalizer
(MIT), python-dateutil (BSD/Apache-2.0), tzdata (Apache-2.0), six (MIT), et-xmlfile (MIT),
pycparser (BSD-3-Clause), mypy-extensions (MIT). Lock:
[requirements-table-comparison-lock.txt](../backend/requirements-table-comparison-lock.txt);
install log and before/after freezes in
[step14a/dependencies](../experiments/out/step14a/dependencies/). `pip check` passes.

## Step 14b: TableFormer in the table stage

No new dependency. TableFormer (accurate; `docling-ibm-models` 4.0.3 in the existing
`accuracy-models` extra, weights `docling-project/docling-models@2199320848bb9a8a519d22e4b528185a4f9a6f64`,
CDLA-Permissive-2.0 and Apache-2.0) now runs in the table stage as a second reader of
text-owning tables (`tables/opinion.py`): header rows where our grid found none, and a review
flag where the structures disagree. Client setting `structure_reader` (`auto` uses it when the
extra is installed and the learned detectors run, warns otherwise; `on`; `off`). The default
installation stays without it.

## Step 16: OCR assets and licence audit

The default Python environment remains CPU-only. `pytesseract==0.3.13` (Apache-2.0)
is installed in the active environment, without changing any existing dependency.
`pip check` passes. Its wheel is 14,705 bytes; the exact wheel URL and SHA-256 are in
[the install report](../experiments/out/step16/dependencies/pytesseract_install_report.json).
The [upstream audit](../experiments/out/step16/dependencies/upstream_audit.json)
records the package metadata and licence sources before installation.

**Windows Tesseract build audit.** The UB Mannheim 5.5.3 build is Apache-2.0 for
Tesseract itself, but its distribution includes `libjbig-0.dll` (JBIG-KIT,
[GPL-2.0](https://packages.msys2.org/packages/mingw-w64-x86_64-jbigkit)). It was
downloaded and unpacked for inspection only: neither its installer nor its OCR
executable was run. The project-local archive is retained, not selected for use.
The conda-forge alternative also brings a GPL dependency (`lzo` through
`libarchive`) and was rejected at metadata inspection, before downloading binaries.
These do not expand the owner's existing licence exceptions.

The selected source-build recipe uses Tesseract 5.5.3 (Apache-2.0), Leptonica
1.86.0 (BSD-2-Clause), libpng 1.6.50 (libpng-2.0) and zlib 1.3.1 (Zlib), with
optional TIFF, archive, curl and training-tool paths disabled. PNG/PNM inputs are
sufficient for the extractor's rendered pages. Exact source commits and downloaded
licences are in [the build plan](../experiments/out/step16/dependencies/source_build_plan.json).
The local build tools are Zig 0.15.2 (MIT; LLVM runtime Apache-2.0 with LLVM
exceptions; MinGW runtime ZPL-2.1, public-domain, BSD and LGPL notices), CMake
3.31.6 (BSD-3-Clause; Python wrapper Apache-2.0), and Ninja 1.11.1.4 (Apache-2.0).
No administrator install, registry change or system/user PATH change is made.

**Language models.** The `tessdata_best` revision is
`e12c65a915945e4c28e237a9b52bc4a8f39a0cec` (Apache-2.0). Before downloading, the
Git tree measured **162 traineddata files, 1,774,547,803 bytes**, including all 37
`script/` files, `osd`, and the language and auxiliary models. Every file is
checked against the pinned Git blob SHA-1 and recorded with SHA-256. The initial
free-space reading was 14,499,893,248 bytes; provisioning preserves both the 5 GB
project reserve and an additional 4 GB allocation for evaluations. Provisioning
never invokes automatic cache pruning. Language installation alone is not a
measurement of recognition quality.

**PP-OCRv5.** Neither `paddleocr`, `paddlepaddle` nor `paddlex` was installed at
the start. The latest checked PaddlePaddle 3.3.1 Windows wheels target Python
3.9–3.13, not this project's Python 3.14. The existing official Transformers
PP-OCRv5 path is retained (already installed and exercised in Step 6b); an
incompatible Paddle runtime is not installed. All selected model cards declare
Apache-2.0, with immutable revisions and file sizes recorded in
[the model audit](../experiments/out/step16/dependencies/ppocr_models_audit.json).
The server detector and Chinese/English server recognizer, plus English, Arabic,
Cyrillic, Devanagari and Greek mobile recognizers, complement the existing Latin
recognizer. Runtime model loading uses explicit local files only.

**Step 15's two layout weights.** The report names a debug run loading the two
real layout models. The corresponding project-local pinned files are:

| File | Immutable revision | Bytes | Licence |
|---|---|---:|---|
| `docling-project/docling-layout-heron/model.safetensors` | `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` | 171,658,996 | Apache-2.0 |
| `PaddlePaddle/PP-DocLayoutV3_safetensors/model.safetensors` | `e4f489dc536556fc1be02b973ba06756e0d4a2ac` | 133,270,468 | Apache-2.0 |

Their hashes and the evidence limit are recorded in
[step15_model_files.json](../experiments/out/step16/dependencies/step15_model_files.json).
The identification follows the report and the producer's two layout adapters;
there is no retained debug-download event log, and the existing project copies
predate Step 15. An external home cache was not inspected. The producer already
supplies immutable 40-character revisions, so these are not floating runtime
downloads; Step 16's OCR assets likewise use revision pins and local-only loading.

**Step 16 completion (provisioning, test data, runtime pins).** All 162 `tessdata_best`
files (1,774,547,803 bytes, commit `e12c65a915945e4c28e237a9b52bc4a8f39a0cec`) are installed
under `.cache/step16/ocr/tessdata_best/<commit>/`, each verified against its pinned Git blob
SHA-1 ([tessdata_manifest.json](../experiments/out/step16/dependencies/tessdata_manifest.json));
an interrupted download resumes per file and an over-long partial file is restarted. Free
disk before the download was 12.4 GB, above the 5 GB reserve. Tesseract receives its
tessdata directory through `TESSDATA_PREFIX` for the duration of each call (pytesseract
keeps literal quotes in `--tessdata-dir` on Windows).

Runtime model access: a book run constructs every model local-only from the project model
cache (`<cache>/huggingface` unless a directory is given). With `HF_HUB_OFFLINE=1`, all six
run-time models load at their pinned revisions
([runtime_model_pins.json](../experiments/out/step16/dependencies/runtime_model_pins.json)):

| Model | Repository | Revision |
|---|---|---|
| Heron layout | `docling-project/docling-layout-heron` | `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` |
| PP-DocLayoutV3 | `PaddlePaddle/PP-DocLayoutV3_safetensors` | `e4f489dc536556fc1be02b973ba06756e0d4a2ac` |
| PP-FormulaNet-L | `PaddlePaddle/PP-FormulaNet-L_safetensors` | `69869f2891cc61347d230ef234bcc8b8d297c43a` |
| TATR detection | `microsoft/table-transformer-detection` | `2357cbe2b5a5d1c03e54f32764f06058933b65ab` |
| TATR structure | `microsoft/table-transformer-structure-recognition` | `f4d4bdc85c3fe4b1fa49658882a5d38bbdd0f343` |
| TableFormer | `docling-project/docling-models` | `2199320848bb9a8a519d22e4b528185a4f9a6f64` |

Real-scan test data: 26 public-domain Wikisource pages (proofreading level 3 or 4), each
with its Commons licence and revision in `source.json`
([test_data/step16_real_scans](../experiments/test_data/step16_real_scans/)); fetched only
from Wikimedia hosts, rate-limited, at 1,920-pixel thumbnails.

## Step 17: output validation (core dependency)

The book JSON is validated against its JSON Schema with `jsonschema` (Draft 2020-12). It is
a core dependency (pinned in `pyproject.toml` and `backend/requirements-lock.txt`); licences
checked from the installed package metadata before installation:

| Package | Version | Licence | Why |
|---|---|---|---|
| jsonschema | 4.26.0 | MIT | schema validation of every output |
| attrs | 26.1.0 | MIT | jsonschema dependency |
| jsonschema-specifications | 2025.9.1 | MIT | jsonschema dependency (meta-schemas) |
| referencing | 0.37.0 | MIT | jsonschema dependency |
| rpds-py | 2026.9.1 | MIT | referencing dependency |

Real-scan test data added in Step 17 Part 1: 54 public-domain Wikisource pages (Chinese
simplified and traditional, Greek monotonic and polytonic, Arabic; proofreading level 3 or 4),
each with its Commons licence and revision in `source.json`
([test_data/step17_real_scans](../experiments/test_data/step17_real_scans/)), downloaded with
the Step 16 script (Wikimedia hosts only, rate-limited, 1,920-pixel thumbnails).
