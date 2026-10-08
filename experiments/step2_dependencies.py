"""Record exact new-environment distributions and their shipped licenses."""

import importlib.metadata as metadata
import json
import platform
from pathlib import Path

root = Path(__file__).resolve().parents[1]
licenses = {
    "colorama": "BSD-3-Clause",
    "setuptools": "MIT",
    "pymupdf": "AGPL-3.0 OR Artifex commercial",
}
runtime = {
    "pymupdf",
    "pydantic",
    "pydantic-core",
    "regex",
    "annotated-types",
    "typing-extensions",
    "typing-inspection",
}
build = {"setuptools"}
rows = []
for dist in metadata.distributions():
    name = dist.metadata["Name"].lower().replace("_", "-")
    if name == "universal-book-core":
        continue
    license = (
        licenses.get(name)
        or dist.metadata.get("License-Expression")
        or dist.metadata.get("License")
    )
    roles = (
        "runtime"
        if name in runtime
        else "build"
        if name in build
        else "bootstrap"
        if name == "pip"
        else "development"
    )
    rows.append(
        {
            "name": name,
            "version": dist.version,
            "license": license,
            "role": roles,
            "license_files": dist.metadata.get_all("License-File", []),
        }
    )
rows.sort(key=lambda row: row["name"])
out = root / "experiments/out/step2/dependencies.json"
out.write_text(
    json.dumps({"python": platform.python_version(), "packages": rows}, indent=2) + "\n", "utf-8"
)
(root / "backend/requirements-lock.txt").write_text(
    "# Exact Step 2 runtime, development and build environment (Windows, Python 3.14).\n"
    + "\n".join(f"{row['name']}=={row['version']}" for row in rows)
    + "\n",
    "utf-8",
)
lines = [
    "# Step 2 dependencies",
    "",
    f"Validated on CPython {platform.python_version()} / Windows x64, CPU only. "
    "Exact direct pins are in backend/pyproject.toml; complete installed pins are in backend/requirements-lock.txt.",
    "",
    "| Package | Version | Scope | License |",
    "|---|---|---|---|",
]
lines.extend(
    f"| {row['name']} | {row['version']} | {row['role']} | {row['license']} |" for row in rows
)
lines.extend(
    [
        "",
        "Evidence: installed wheel METADATA and bundled license files, recorded in "
        "[dependencies.json](../experiments/out/step2/dependencies.json). "
        "colorama's bundled license is BSD-3-Clause; setuptools declares MIT in its classifiers.",
        "",
        "**PyMuPDF/MuPDF is the only runtime copyleft dependency: AGPL or Artifex commercial terms.** "
        "Internal use is the accepted product scope; this does not change the package license. "
        "No GPU, OCR runtime, layout models or adapter libraries are dependencies of this core.",
        "",
        "The lock covers this audited environment; it is a version lock, not a hashed wheel lock. "
        "pip is bootstrap tooling, not an application dependency. Existing Step 1 experiment environments "
        "(including Dulwich Git tooling) are separate and their licenses remain in the Phase 0 report.",
    ]
)
(root / "docs/dependencies.md").write_text("\n".join(lines) + "\n", "utf-8")
print(out)
