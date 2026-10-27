#!/usr/bin/env bash
set -euo pipefail

frontend_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
converter_python="$frontend_dir/../.venv/bin/python"
runtime_settings="$frontend_dir/runtime/settings.linux.json"

if [[ ! -x "$converter_python" ]]; then
    echo "Install the project environment in .venv before starting the app." >&2
    exit 1
fi

"$converter_python" - "$frontend_dir" "$runtime_settings" <<'PY'
import json
import os
import sys
from pathlib import Path

frontend = Path(sys.argv[1])
destination = Path(sys.argv[2])
settings = json.loads((frontend / "settings.json").read_text("utf-8"))
settings["converter_python"] = os.path.relpath(sys.executable, frontend)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(settings, indent=2) + "\n", "utf-8")
PY

exec "$converter_python" -B "$frontend_dir/server.py" --settings "$runtime_settings"
