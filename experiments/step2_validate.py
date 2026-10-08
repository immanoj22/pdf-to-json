"""Run the final Step 2 test gate and capture machine-readable outcome."""

import json
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "experiments/out/step2"
started = time.perf_counter()
run = subprocess.run(
    [sys.executable, "-m", "pytest", "backend/tests",
        "-q", "--tb=short", f"--junitxml={out / 'pytest.xml'}"],
    cwd=root,
    capture_output=True,
    text=True,
)
(out / "pytest.log").write_text(run.stdout + run.stderr, "utf-8")
result = {"exit_code": run.returncode, "seconds": round(time.perf_counter() - started, 3)}
(out / "test_run.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
print(run.stdout)
print(run.stderr)
raise SystemExit(run.returncode)
