# Local Linux installation — 2026-10-27

Installed in this repository's `.venv` using Python 3.14.4 on Ubuntu x86_64.
The scan covered 260 backend modules, 63 test/support modules, four UI Python
files and 324 experiment scripts, plus dependency manifests and setup documentation.

## Installed packages

All core requirements and every optional group in `backend/pyproject.toml` are
satisfied for Linux. The [complete inventory](local_installation_packages.txt)
lists exact versions of all 100 installed Python distributions.

| Group | Direct packages |
| --- | --- |
| core | `pymupdf==1.28.2`, `rapidfuzz==3.14.6`, `pydantic==2.13.5`, `regex==2026.9.29`, `shapely==2.2.0`, `networkx==3.7`, `numpy==2.5.3`, `opencv-python-headless==5.0.0.93`, `fonttools==4.66.1`, `lxml==6.1.3`, `jsonschema==4.26.0` |
| language-evidence | `lingua-language-detector==2.2.0` |
| math-conversion | `latex2mathml==3.81.1`, `sympy==1.14.0` |
| accuracy-models | `torch==2.14.1+cpu`, `torchvision==0.29.1+cpu`, `transformers==5.19.0`, `pillow==12.3.0`, `safetensors==0.8.0`, `timm==1.0.30`, `docling-ibm-models==4.0.3` |
| gpu | `torch==2.14.1+cpu` |
| amd-gpu | `onnxruntime-directml` (Windows only; skipped), `onnx==1.23.2` |
| models | `torch==2.14.1+cpu`, `torchvision==0.29.1+cpu`, `transformers==5.19.0`, `pillow==12.3.0`, `safetensors==0.8.0`, `timm==1.0.30` |
| dev | `pytest==9.1.1`, `ruff==0.16.10` |
| language-comparison | `langid==1.1.6` |
| table-comparison | `pdfplumber==0.11.10`, `camelot-py==2.0.0` |
| classical-ml | `scikit-learn==1.9.1`, `lightgbm==4.7.0`, `scipy==1.18.1`, `joblib==1.6.0`, `threadpoolctl==3.7.0`, `narwhals==2.26.0`, `cloudpickle==3.1.2` |

Additional imports/tools found outside the declared extras are installed:
`pytesseract`, `dulwich`, `requests`, `urllib3`, `omegaconf`, Linux `onnxruntime`,
`flatbuffers`, `protobuf`, `ml_dtypes`, CMake and Ninja. Node.js 24.22.1 LTS is
installed in `.cache/tools/node-v24.22.1-linux-x64/` for the existing JavaScript
checks; the page itself needs no Node/npm packages. Pip was bootstrapped from
the official PyPA site into `.venv` because system Python has no pip/ensurepip
and sudo requires interactive authentication. No system installation was needed.

## Platform and historical environments

This machine has Intel UHD 620 graphics. The converter resolves `auto` to CPU.
PyTorch 2.14.1+cpu and torchvision 0.29.1+cpu came from the official PyTorch CPU
index. Windows-only DirectML cannot be installed on Linux; ONNX and Linux ONNX
Runtime are installed. CUDA and DirectML acceleration are unavailable on this
machine. The project's default dependency definitions are unchanged.

Historical extract/layout requirement snapshots were inspected. Their packages
are covered by the active environment using its current pins; conflicting older
NumPy/networkx/pycparser versions were not overlaid on it. The retired UniMERNet
comparison environment remains uninstalled: its archived Python 3.12 /
Transformers 4.42 / NumPy 1.x stack conflicts with the active converter, and the
project records its removal by the owner. Retained experiment code and weights
remain available. This environment is not used by the backend or upload page.

## Model and optional OCR assets

The six recorded runtime checkpoints are present at immutable revisions: Heron,
PP-DocLayoutV3, PP-FormulaNet-L, Table Transformer detection and structure, and
TableFormer accurate/fast. Eight safetensors files in the private UI model cache
passed format validation. The optional SmolVLM checkpoint is also present.

All 162 `tessdata_best` language/script files at revision
`e12c65a915945e4c28e237a9b52bc4a8f39a0cec` were downloaded and verified against
the recorded Git blob hashes. All 15 audited PP-OCRv5 models (79 files), including
the seven runtime models and the mobile/language alternatives, were provisioned
from recorded URLs with size and SHA-256/Git blob verification. They are installed under
`.cache/step16/ocr/`. Provisioning does not enable OCR or change job settings.

Tesseract 5.5.3 was built locally from the recorded source revision with Leptonica
1.86.0, libpng 1.6.50 and zlib 1.3.1. The existing recipe's optional TIFF/archive/
curl/training paths are disabled. The executable is
`.cache/local-setup/ocr-linux/bin/tesseract`. It lists all 162 language/script
files, includes `spa`, `eng` and `osd`, and passed a synthetic PNG recognition
check through `pytesseract`. These assets are optional and require explicit OCR
job settings to use them; the upload page retains its existing settings.

## Start and stop

From the repository root:

```bash
bash frontend_temp/start.sh
```

Open http://127.0.0.1:8765. One server serves the HTML/CSS/JavaScript page and
starts the installed backend CLI for each conversion. `frontend/` is a placeholder.
The launcher generates ignored `frontend_temp/runtime/settings.linux.json` with
the virtual environment interpreter; Windows settings remain usable. The wrapper
preserves the venv executable path instead of resolving its Unix symlink to
system Python.

For a foreground server, stop with Ctrl+C. The setup session's background process
ID is in ignored `frontend_temp/server.pid`; logs are in
`frontend_temp/server.stdout.log` and `frontend_temp/server.stderr.log`.

## Verification

- `pip check`: passed.
- Every Linux-applicable core and optional requirement: exact-version check passed.
- All 37 checked external imports: passed.
- Converter CLI startup: passed.
- Backend Ruff check: passed.
- Existing JavaScript UI checks: 8/8 passed.
- Fixture ledger: passed, zero missing/extra tokens.
- Live HTTP fixture upload, backend conversion and all three JSON downloads: passed.
- Optional native OCR: version, 162-language discovery and synthetic PNG checks passed.
- Initial backend test suite: 1,198 passed, 1 skipped, 2 failed and 4 setup errors
  in 19 minutes. One failure was the checkout's CRLF `CLAUDE.md`; normalizing it
  to the repository's LF policy fixed it, and both boundary checks passed on
  recheck. The remaining failure and four setup errors are the five cached
  furniture-book regressions: their configured Windows reference PDF locations
  do not exist on Linux. They also need the historical Step 7/8 caches. These
  are evidence prerequisites, not installable packages. The optional full-book
  benchmark skipped because its original book/extraction cache is unavailable.

Machine-local receipts, source/model hashes, dependency scan inventory, full
package freeze, build scripts and validation logs are in `.cache/local-setup/`.
Uploads, generated outputs, environments and caches are ignored by Git.
