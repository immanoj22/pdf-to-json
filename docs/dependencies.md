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
