"""Supplement the Step 6b primary-source audit for math candidates; never installs."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b"
SOURCES = {
    "pix2tex_license": "https://raw.githubusercontent.com/lukas-blecher/LaTeX-OCR/main/LICENSE",
    "unimernet_license": "https://raw.githubusercontent.com/opendatalab/UniMERNet/main/LICENSE",
    "unimernet_dependencies": "https://raw.githubusercontent.com/opendatalab/UniMERNet/main/pyproject.toml",
    "nougat_code_license": "https://raw.githubusercontent.com/facebookresearch/nougat/main/LICENSE",
    "nougat_weights_license": "https://raw.githubusercontent.com/facebookresearch/nougat/main/LICENSE-MODEL.md",
    "texify_code_license": "https://raw.githubusercontent.com/VikParuchuri/texify/master/LICENSE",
    "texify_weights_terms": "https://raw.githubusercontent.com/VikParuchuri/texify/master/README.md",
    "padishah_code_and_weights_terms": "https://raw.githubusercontent.com/PadishahIII/latex-ocr/main/README.md",
    "padishah_dependencies": "https://raw.githubusercontent.com/PadishahIII/latex-ocr/main/pyproject.toml",
    "latex2mathml_license": "https://raw.githubusercontent.com/roniemartinez/latex2mathml/master/LICENSE",
    "mathjax_license": "https://raw.githubusercontent.com/mathjax/MathJax/master/LICENSE",
    "sympy_license": "https://raw.githubusercontent.com/sympy/sympy/master/LICENSE",
}
REPOSITORIES = (
    "lukas-blecher/LaTeX-OCR",
    "opendatalab/UniMERNet",
    "facebookresearch/nougat",
    "VikParuchuri/texify",
    "roniemartinez/latex2mathml",
    "mathjax/MathJax",
    "sympy/sympy",
    "PadishahIII/latex-ocr",
)


def fetch(item):
    key, url = item
    request = urllib.request.Request(
        url, headers={"User-Agent": "pdf-book-converter-license-audit"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        content = response.read()
    return key, {
        "url": url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "text": content.decode(),
    }


def main():
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = dict(pool.map(fetch, SOURCES.items()))
        repositories = dict(
            pool.map(
                fetch, [(repo, "https://api.github.com/repos/" + repo) for repo in REPOSITORIES]
            )
        )
    metadata = {}
    for repo, record in repositories.items():
        data = json.loads(record["text"])
        metadata[repo] = {
            "url": record["url"],
            "response_sha256": record["sha256"],
            **{
                key: data.get(key)
                for key in ("pushed_at", "updated_at", "archived", "default_branch")
            },
        }
    preflight_path = OUT / "formula_preflight.json"
    preflight = json.loads(preflight_path.read_text("utf-8"))
    release = json.loads(preflight["pix2tex_release"]["text"])
    package = json.loads(preflight["pix2tex_package"]["text"])
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_snapshot": records,
        "repository_status": metadata,
        "preflight_sha256": hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
        "pix2tex_release": {
            "url": release["html_url"],
            "tag": release["tag_name"],
            "published_at": release["published_at"],
            "body": release["body"],
            "assets": [{"name": row["name"], "bytes": row["size"]} for row in release["assets"]],
        },
        "pix2tex_package": {
            **{
                key: package["info"].get(key)
                for key in ("version", "requires_python", "requires_dist")
            },
            "files": [
                {"name": row["filename"], "bytes": row["size"], "sha256": row["digests"]["sha256"]}
                for row in package["urls"]
            ],
        },
        "installation": "No candidate or dependency installed by this audit.",
    }
    (OUT / "math_dependency_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"sources": len(records), "repositories": len(metadata)}))


if __name__ == "__main__":
    main()
