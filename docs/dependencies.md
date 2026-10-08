# Step 2 dependencies

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

**PyMuPDF/MuPDF is the only runtime copyleft dependency: AGPL or Artifex commercial terms.** Internal use is the accepted product scope; this does not change the package license. No GPU, OCR runtime, layout models or adapter libraries are dependencies of this core.

The lock covers this audited environment; it is a version lock, not a hashed wheel lock. pip is bootstrap tooling, not an application dependency. Existing Step 1 experiment environments (including Dulwich Git tooling) are separate and their licenses remain in the Phase 0 report.
