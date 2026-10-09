"""Synthetic-only CPU checks for optional math backends; never reads book equations."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path
from xml.etree import ElementTree

from reference_paths import PROJECT_ROOT

OUT = PROJECT_ROOT / "experiments/out/step6b"


def inventory(name: str, license_url: str, license_name: str) -> dict:
    distribution = importlib.metadata.distribution(name)
    files = list(distribution.files or [])
    licenses = [path for path in files if "license" in str(path).casefold()]
    return {
        "package": name,
        "version": distribution.version,
        "code_license": license_name,
        "license_url": license_url,
        "weights": None,
        "requires_python": distribution.metadata.get("Requires-Python"),
        "installed_bytes": sum(
            distribution.locate_file(path).stat().st_size
            for path in files
            if distribution.locate_file(path).is_file()
        ),
        "license_files": [
            {
                "path": str(path),
                "sha256": hashlib.sha256(distribution.locate_file(path).read_bytes()).hexdigest(),
            }
            for path in licenses
            if distribution.locate_file(path).is_file()
        ],
    }


def main() -> None:
    from latex2mathml.converter import convert
    from sympy import Symbol, srepr

    OUT.mkdir(parents=True, exist_ok=True)
    samples = [r"x^2 + y^2 = z^2", r"\frac{\alpha}{2}", r"\sqrt{x+1}"]
    conversions = []
    for expression in samples:
        start = time.perf_counter()
        value = convert(expression)
        elapsed = time.perf_counter() - start
        root = ElementTree.fromstring(value)
        assert root.tag == "{http://www.w3.org/1998/Math/MathML}math"
        assert len(list(root.iter())) > 1
        conversions.append({"latex": expression, "mathml": value, "cpu_seconds": elapsed})
    x = Symbol("x")
    start = time.perf_counter()
    tree = (x**2 + 1) / 2
    representation = srepr(tree)
    elapsed = time.perf_counter() - start
    assert tree.subs(x, 3) == 5
    payload = {
        "scope": "Synthetic samples only; no digital glyph reconstruction or book conversion.",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "device": "cpu",
        "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "converter": {
            **inventory(
                "latex2mathml",
                "https://github.com/roniemartinez/latex2mathml/blob/master/LICENSE",
                "MIT",
            ),
            "passed": True,
            "samples": conversions,
        },
        "math_tree_backend": {
            **inventory(
                "sympy", "https://github.com/sympy/sympy/blob/master/LICENSE", "BSD-3-Clause"
            ),
            "passed": True,
            "synthetic_ast": representation,
            "cpu_seconds": elapsed,
            "limitation": (
                "An algebra AST backend; a glyph/rule geometry frontend is still required."
            ),
        },
    }
    path = OUT / "smoke_math_backends.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"output": path.relative_to(PROJECT_ROOT).as_posix(), "passed": True}))


if __name__ == "__main__":
    main()
