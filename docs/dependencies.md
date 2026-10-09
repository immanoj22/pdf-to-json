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
