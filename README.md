# pdf-to-json / PDF Book Converter

Repository: [immanoj22/pdf-to-json](https://github.com/immanoj22/pdf-to-json).

On another Windows PC, clone the project:

```powershell
git clone https://github.com/immanoj22/pdf-to-json.git
cd pdf-to-json
```

For the optional AMD table-model backend, install Python 3.14 x64 and the AMD
graphics driver, then run `./experiments/setup_amd_gpu.ps1`. Read
[AMD setup and validation status](docs/amd_gpu.md) for the supported operations,
CPU fallback and pending Radeon hardware checks. Environments and downloaded
model caches are local and must be provisioned on the new PC.

Internal desktop converter with a CPU-default installation: PDF evidence -> universal semantic model.
Adapters and the desktop interface are deferred. Prefer accuracy: use an available
GPU automatically and recover to CPU on GPU errors. The optional backend gpu extra
provides the runtime probe; native extraction and geometry still execute on CPU.
No models are installed.

- backend/: Python package, pinned dependencies and tests.
- frontend/: placeholder.
- docs/: audit, gate reports and dependency licenses.
- experiments/: fixtures, overlays, read-only evidence probes and configured reference paths.

Create a fresh virtual environment from this repository root:

    python -m venv .venv
    .venv\Scripts\python -m pip install --cache-dir .cache\pip -r backend\requirements-lock.txt
    .venv\Scripts\python -m pip install --no-deps --no-build-isolation -e backend
    .venv\Scripts\python -m pytest backend\tests -q
    .venv\Scripts\ruff check backend\src backend\tests
    .venv\Scripts\book-core ledger-check experiments\fixtures\column_26.pdf --cache-dir .cache\ledger

External books/caches stay read-only at their original locations. Configure them in
experiments/references.toml, or set BOOK_CONVERTER_REFERENCE_CONFIG to another TOML
file. Individual paths can be overridden with BOOK_CONVERTER_SPANISH_PDF,
BOOK_CONVERTER_SPANISH_CACHE and the other BOOK_CONVERTER_<KEY> variables.
Fixture gates are portable. The full-book gate explicitly skips when configured
evidence is unavailable.

OCR languages are configurable per job and region; defaults are spa/eng.
There is an interface and an empty language-pack registry, with no OCR runtime.
Script and text direction are optional evidence, never inferred from language.
The ledger benchmark is script-neutral NFKC Unicode token conservation and does
not certify reading order. CJK segmentation needs a future token rule.

Historical Phase 0 model experiments need separate fresh environments using
experiments/requirements-extract.txt or experiments/requirements-layout.txt.
Their packages and weights are not installed in the converter environment.
The preserved reports record the original audit; historical commit scripts are disabled.

Render a reusable object-role overlay and its complete evidence sidecar:

    .venv\Scripts\book-core overlay experiments\fixtures\colored_box.pdf --page 1 --out experiments\out\review.png

Use --all-objects for exhaustive primitive/text bounds. Default overlays omit
ambiguous drawing primitives and graphics-state records to keep the page readable;
all objects and roles remain in the JSON. See [Step 3 report](docs/step3_report.md).

Review [Step 2 report](docs/step2_report.md) and
[the exact move list](docs/step2b_move_list.md). Stop at each review gate.
