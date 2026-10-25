# Optional Windows AMD acceleration

The RX 6700 XT path uses ONNX Runtime DirectML. Installing `amd-gpu` enables
automatic selection for **Table Transformer detection and structure recognition
only**. CUDA retains priority under `auto`; `--device directml` explicitly requests
this path and `--device cpu` bypasses it.

Normal book runs use TATR detection. `TATRStructure` is an optional reader class;
the normal book runner still selects TableFormer for structure reading, on CPU.

Heron, PP-DocLayoutV3, TableFormer, formulas, OCR, native extraction and semantic
rules receive no DirectML acceleration in this change. Explicit DirectML requests
fall back to CPU for those operations. This does not fix the Step 18 crash or
accuracy failures, or establish a whole-book speedup.

## On the Radeon PC

Copy/clone this project revision onto that Windows PC. Install Python 3.14 x64
and a working AMD graphics driver. From the project root in PowerShell:

```powershell
.\experiments\setup_amd_gpu.ps1
```

This creates `.venv-amd`, installs CPU PyTorch plus the existing model extras and
optional DirectML packages, and runs hardware validation. It refuses to overwrite
an existing environment. It changes no execution policy, driver, power, long-path
or Git setting. If execution policy blocks the script, run its commands individually.

The check downloads only the two previously approved MIT TATR checkpoints at their
immutable revisions into `.cache/huggingface`. It reads no hold-out book. It compares
two synthetic table images of different sizes against PyTorch CPU, checks raw values
and thresholded detections, records kernel placement, and times warm inference
separately from export/session startup. Success requires actual DirectML kernel
events for both models. A new receipt is saved under `.cache/amd-check/<timestamp>/`.

After a passing receipt, use `.venv-amd\Scripts\python.exe` for the normal converter
command with `--device auto`. Other model/OCR provisioning instructions still apply:
the hardware check provisions only TATR weights. Copying the repository does not
copy local model caches or OCR installations. To run the check again:

```powershell
.\.venv-amd\Scripts\python.exe -B experiments/check_amd_gpu.py --model-cache .cache/huggingface --out .cache/amd-check/recheck/hardware.json
```

Use a fresh output path each time. `--cpu-onnx` is a developer export test and cannot
certify GPU support. Timings are small model diagnostics with profiling overhead,
not whole-pipeline benchmarks. Some hardware may show no speed benefit.

## Execution safeguards

The probe executes GPU matrix multiplication with CPU EP fallback disabled. Finding
an installed provider is insufficient. Model sessions use sequential execution and
disable memory patterns as required by DirectML. Unsupported graph operators may
execute on CPU: `directml` means a DirectML session with possible CPU participation.
Preprocessing, model loading/export and postprocessing also stay on CPU.

Graphs are exported in memory at opset 17 from unchanged weights and processor
outputs, without quantization or threshold changes. Each new input tensor shape is
checked against PyTorch CPU, including threshold decisions. This guard does not
establish semantic accuracy for all subsequent images of the same size. The legacy
exporter emits deprecation/tracing warnings; both real checkpoints passed the
variable-size checks below. Export repeats per reader/process; there is no persistent
ONNX artifact cache in this version.

Probe, export, session, inference and agreement failures retry the complete reading
on CPU and retain the recovery reason. Recovered CPU readings are cached under CPU
identities. Runtime versions, actual device and producing code enter cache identities;
existing cache files remain intact. The default install remains CPU-only.

## Validation status

The development PC used a separate `.venv-amd-check` environment borrowing the
existing CPU/model packages. It passes `pip check`; the original `.venv` still has
CPU PyTorch and no ONNX/ORT installation.

Both pinned TATR models passed raw numerical and postprocessed label/box agreement
at two image sizes with ONNX CPU execution. The retained
[export receipt](../experiments/out/amd_gpu/cpu_export_v1.json) explicitly records
`CPUExecutionProvider`. **Radeon execution, performance and a fresh target-PC
installation remain pending**, because the RX 6700 XT is on another PC.

Eight focused AMD tests pass in the optional environment, including CPU recovery,
cache identity after recovery, both TATR adapter branches and variable-size ONNX
export. Ruff, PowerShell syntax, dependency consistency and wheel packaging checks
pass. The wheel keeps ONNX dependencies behind the `amd-gpu` extra.

The complete CPU regression run finished with **1,197 passed, 1 skipped, 1 failed
and 4 setup errors** in 1,591.77 seconds. All five unsuccessful cases are in
`test_furniture_books.py`: `load_book_furniture` found no matching historical Step 8
decision for the current producer identity, before semantic assertions ran. Those
caches were not regenerated or relabelled. The skipped ONNX test passes in the
optional environment. The full run collected six AMD tests; the final focused run
also includes the two subsequently added adapter cases. This is **not a clean full
regression gate**. See the [validation receipt](../experiments/out/amd_gpu/validation.json).

Step 18 reports, results, ledgers, profile and freeze tag remain unchanged. This is
new optional execution code after that measurement, not a revised sealed result.

## Dependencies and sources

The supplemental `backend/requirements-amd-lock.txt` pins the optional additions:
ONNX Runtime DirectML 1.24.4 (MIT), ONNX 1.23.2 and FlatBuffers (Apache-2.0),
protobuf (BSD-3-Clause), and ml_dtypes (Apache-2.0). No `torch-directml` or PyTorch
downgrade is used.

Sources checked 25 October 2026:

- [ONNX Runtime DirectML requirements and session restrictions](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html).
- [DirectML runtime package and wheels](https://pypi.org/project/onnxruntime-directml/).
- [PyTorch DirectML package metadata](https://pypi.org/project/torch-directml/): the
  published package pins torch 2.4.1 / torchvision 0.19.1, incompatible with this stack.
- [Microsoft DirectML maintenance status](https://github.com/microsoft/DirectML):
  supported, with new feature development directed toward Windows ML.
