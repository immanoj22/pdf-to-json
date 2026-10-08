"""Check relocated links, executable script syntax and new-root package imports."""

import ast
import json
import re
import sys
from pathlib import Path
import book_core

root = Path(__file__).resolve().parents[1]
assert Path(sys.prefix).resolve() == (root / ".venv").resolve()
assert (
    Path(book_core.__file__).resolve().is_relative_to((root / "backend/src").resolve())
)
syntax = []
for path in (root / "experiments").rglob("*.py"):
    if ".cache" in path.parts or "page_cache" in path.parts:
        continue
    ast.parse(path.read_text("utf-8-sig"), filename=str(path))
    syntax.append(str(path.relative_to(root)))
missing = []
checked = 0
for path in [root / "README.md", *(root / "docs").glob("*.md")]:
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text("utf-8-sig")):
        if target.startswith(("http://", "https://", "C:", "<C:", "/C:", "#")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        checked += 1
        if not (path.parent / target).resolve().exists():
            missing.append({"document": str(path.relative_to(root)), "target": target})
assert not missing, missing
out = root / "experiments/out/step2b"
out.mkdir(parents=True, exist_ok=True)
result = {
    "python": sys.version,
    "prefix": sys.prefix,
    "package": book_core.__file__,
    "relative_links_checked": checked,
    "missing_links": missing,
    "experiment_scripts_parsed": len(syntax),
}
(out / "relocation_checks.json").write_text(
    json.dumps(result, indent=2) + "\n", "utf-8"
)
print(json.dumps(result, indent=2))
