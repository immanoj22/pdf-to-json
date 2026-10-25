# Run from the project root on the Windows Radeon PC. Never alters an existing environment.
param([string]$Environment = ".venv-amd")
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath "backend/pyproject.toml")) {
    throw "Run this script from the pdf_book_converter project root."
}
if (Test-Path -LiteralPath $Environment) {
    throw "Environment already exists; select a new -Environment path."
}
& py -3.14 -m venv $Environment
if ($LASTEXITCODE -ne 0) { throw "Python 3.14 x64 is required." }
$Python = Join-Path $Environment "Scripts/python.exe"
& $Python -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "CPU PyTorch installation failed." }
& $Python -m pip install -c backend/requirements-amd-lock.txt -e "./backend[models,accuracy-models,amd-gpu]"
if ($LASTEXITCODE -ne 0) { throw "Optional AMD environment installation failed." }
$Receipt = ".cache/amd-check/" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffffffZ") + "/hardware.json"
& $Python -B experiments/check_amd_gpu.py --model-cache .cache/huggingface --download-models --out $Receipt
if ($LASTEXITCODE -ne 0) { throw "AMD hardware validation failed. Inspect $Receipt before using this environment." }
Write-Host "Validation receipt: $Receipt"
Write-Host "Use $Python for conversion; --device auto enables DirectML for supported table models."
