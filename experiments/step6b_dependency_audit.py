"""Primary-source license/package/checkpoint audit; no installers or model inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b"
MODELS = [
    (
        "formula",
        "PaddlePaddle/PP-FormulaNet-L_safetensors",
        "huggingface/transformers",
        "Apache-2.0",
        "5-60 s / synthetic equation (unmeasured)",
    ),
    (
        "table",
        "microsoft/table-transformer-detection",
        "microsoft/table-transformer",
        "MIT",
        "2-15 s / synthetic table image",
    ),
    (
        "table",
        "microsoft/table-transformer-structure-recognition",
        "microsoft/table-transformer",
        "MIT",
        "2-15 s / synthetic table crop",
    ),
    (
        "table",
        "docling-project/docling-models",
        "docling-project/docling-ibm-models",
        "MIT",
        "5-30 s / synthetic table crop",
    ),
    (
        "ocr",
        "PaddlePaddle/PP-OCRv5_mobile_det_safetensors",
        "PaddlePaddle/PaddleOCR",
        "Apache-2.0",
        "1-5 s / synthetic image",
    ),
    (
        "ocr",
        "PaddlePaddle/latin_PP-OCRv5_mobile_rec_safetensors",
        "PaddlePaddle/PaddleOCR",
        "Apache-2.0",
        "0.2-3 s / synthetic line crop",
    ),
    (
        "continuation",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "huggingface/transformers",
        "Apache-2.0",
        "1-10 s / four short strings",
    ),
    (
        "continuation",
        "intfloat/multilingual-e5-small",
        "huggingface/transformers",
        "Apache-2.0",
        "1-10 s / four short strings",
    ),
    (
        "local_vlm",
        "HuggingFaceTB/SmolVLM-256M-Instruct",
        "huggingface/transformers",
        "Apache-2.0",
        "30-180 s / 16 output tokens",
    ),
    (
        "local_vlm",
        "HuggingFaceTB/SmolVLM-500M-Instruct",
        "huggingface/transformers",
        "Apache-2.0",
        "60-300 s / 16 output tokens",
    ),
]
PACKAGES = [
    "timm",
    "scikit-learn",
    "lightgbm",
    "paddlepaddle",
    "paddleocr",
    "pytesseract",
    "tesserocr",
    "docling-ibm-models",
]
CODES = {
    "microsoft/table-transformer": "https://raw.githubusercontent.com/microsoft/table-transformer/main/LICENSE",
    "docling-project/docling-ibm-models": "https://raw.githubusercontent.com/docling-project/docling-ibm-models/main/LICENSE",
    "PaddlePaddle/PaddleOCR": "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE",
    "PaddlePaddle/Paddle": "https://raw.githubusercontent.com/PaddlePaddle/Paddle/develop/LICENSE",
    "tesseract-ocr/tesseract": "https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE",
    "tesseract-ocr/tessdata_fast": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/LICENSE",
    "huggingface/transformers": "https://raw.githubusercontent.com/huggingface/transformers/main/LICENSE",
    "huggingface/pytorch-image-models": "https://raw.githubusercontent.com/huggingface/pytorch-image-models/main/LICENSE",
    "pytorch/pytorch": "https://raw.githubusercontent.com/pytorch/pytorch/main/LICENSE",
    "scikit-learn/scikit-learn": "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/COPYING",
    "lightgbm-org/LightGBM": "https://raw.githubusercontent.com/lightgbm-org/LightGBM/master/LICENSE",
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Step6b-primary-license-audit"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def json_fetch(url):
    return json.loads(fetch(url))


def code_audit(item):
    repo, license_url = item
    body = fetch(license_url)
    metadata = json_fetch("https://api.github.com/repos/" + repo)
    return {
        "repo": repo,
        "primary_license_url": license_url,
        "license_spdx": (metadata.get("license") or {}).get("spdx_id"),
        "license_sha256": hashlib.sha256(body).hexdigest(),
        "license_snippet": " ".join(body.decode("utf8").split()[:25]),
        "archived": metadata["archived"],
        "pushed_at": metadata["pushed_at"],
        "default_branch": metadata["default_branch"],
        "maintenance_evidence_url": "https://api.github.com/repos/" + repo,
    }


def model_audit(item):
    slot, repo, code_repo, code_license, estimate = item
    metadata_url = "https://huggingface.co/api/models/" + repo + "?blobs=true"
    metadata = json_fetch(metadata_url)
    revision = metadata["sha"]
    declared = metadata.get("cardData", {}).get("license")
    terms = declared if isinstance(declared, list) else [declared]
    if not terms or any(term not in {"mit", "apache-2.0", "cdla-permissive-2.0"} for term in terms):
        raise ValueError(f"Stop: checkpoint license is not verified permissive: {repo}: {declared}")
    card_url = f"https://huggingface.co/{repo}/raw/{revision}/README.md"
    card = fetch(card_url)
    weights = []
    for row in metadata.get("siblings", []):
        name = row["rfilename"]
        if not name.endswith(".safetensors") or "/" in name and "tableformer/" not in name:
            continue
        lfs = row.get("lfs", {})
        weights.append(
            {
                "file": name,
                "bytes": row.get("size"),
                "sha256": lfs.get("sha256"),
                "download_url": f"https://huggingface.co/{repo}/resolve/{revision}/{name}",
            }
        )
    return {
        "slot": slot,
        "candidate": repo,
        "code_repo": code_repo,
        "code_license": code_license,
        "weight_license": metadata.get("cardData", {}).get("license"),
        "weight_license_primary_url": card_url,
        "model_card_sha256": hashlib.sha256(card).hexdigest(),
        "revision": revision,
        "weights": weights,
        "weight_bytes": sum(row["bytes"] or 0 for row in weights),
        "last_modified": metadata.get("lastModified"),
        "metadata_primary_url": metadata_url,
        "cpu_estimate": estimate,
        "cpu_estimate_status": "unmeasured engineering estimate",
        "py314_support": (
            "Existing CP314 Torch/Transformers runtime; checkpoint inference not yet measured"
        ),
        "license_status": "permissive_owner_model_card",
        "limitations": (
            [
                "All declared owner licenses retained: CDLA-Permissive-2.0 and Apache-2.0.",
                "TableFormer needs its optional package; full Docling parser is unnecessary.",
            ]
            if "docling-models" in repo
            else []
        ),
    }


def package_audit(name):
    url = f"https://pypi.org/pypi/{name}/json"
    data = json_fetch(url)
    wheels = [row for row in data["urls"] if row["packagetype"] == "bdist_wheel"]
    relevant = [
        row for row in wheels if "win_amd64" in row["filename"] or "py3-none-any" in row["filename"]
    ]
    compatible = [
        row
        for row in relevant
        if (
            "cp314-cp314-win_amd64" in row["filename"]
            or "py3-none-win_amd64" in row["filename"]
            or "py3-none-any" in row["filename"]
        )
    ]
    return {
        "package": name,
        "pin": data["info"]["version"],
        "requires_python": data["info"]["requires_python"],
        "requires_dist": data["info"].get("requires_dist"),
        "declared_license_expression": data["info"].get("license_expression"),
        "declared_license": data["info"].get("license"),
        "primary_url": url,
        "latest_release_time": max(
            (row["upload_time_iso_8601"] for row in data["urls"]), default=None
        ),
        "cp314_windows_wheel_available": bool(compatible),
        "compatible_wheels": [
            {
                "filename": row["filename"],
                "bytes": row["size"],
                "sha256": row["digests"]["sha256"],
                "url": row["url"],
            }
            for row in compatible
        ],
        "support_status": "wheel metadata only; import and inference unmeasured",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT / "dependency_audit.json")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=5) as executor:
        codes = list(executor.map(code_audit, CODES.items()))
        models = list(executor.map(model_audit, MODELS))
        packages = list(executor.map(package_audit, PACKAGES))
    result = {
        "audit_time_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "scope": "optional future-stage candidates; no pipeline integration or benchmark reads",
        "code": codes,
        "models": models,
        "packages": packages,
        "additional_candidates": [
            {
                "slot": "classifier",
                "candidate": "Torch linear classifier",
                "code_license": "BSD-3-Clause",
                "weight_license": "not applicable: synthetic-trained smoke weights only",
                "primary_url": CODES["pytorch/pytorch"],
                "cpu_estimate": "under 1 s / synthetic fit (unmeasured)",
                "selection": "permissive classifier alternative; existing runtime",
            },
            {
                "slot": "ocr",
                "candidate": "Tesseract + tessdata_fast eng/spa",
                "code_license": "Apache-2.0",
                "weight_license": "Apache-2.0",
                "code_primary_url": CODES["tesseract-ocr/tesseract"],
                "weight_primary_url": CODES["tesseract-ocr/tessdata_fast"],
                "cpu_estimate": "0.5-5 s / synthetic image (unmeasured)",
                "py314_support": (
                    "Standalone engine has no CPython ABI; not installed. "
                    "pytesseract pure-Python wrapper compatible; "
                    "no Windows CP314 tesserocr wheel."
                ),
                "selection": "not selected: no engine binary; do not install global software",
            },
            {
                "slot": "classifier",
                "candidate": "scikit-learn",
                "code_license": "BSD-3-Clause",
                "weight_license": "not applicable: no pretrained weights",
                "primary_url": CODES["scikit-learn/scikit-learn"],
                "cpu_estimate": "under 1 s / small synthetic fit (unmeasured)",
                "selection": "excluded: SciPy Windows wheel bundles GPL runtime with GCC exception",
            },
            {
                "slot": "classifier",
                "candidate": "LightGBM",
                "code_license": "MIT",
                "weight_license": "not applicable: no pretrained weights",
                "primary_url": CODES["lightgbm-org/LightGBM"],
                "cpu_estimate": "under 1 s / small synthetic fit (unmeasured)",
                "selection": "excluded: SciPy Windows wheel bundles GPL runtime with GCC exception",
            },
            {
                "slot": "local_vlm",
                "candidate": "Qwen/Qwen2.5-VL-3B-Instruct",
                "code_license": "Apache-2.0 inference framework",
                "weight_license": (
                    "Qwen RESEARCH LICENSE: noncommercial; commercial permission required"
                ),
                "primary_url": "https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/raw/main/LICENSE",
                "selection": "excluded: restricted weights; no install/download/smoke",
            },
        ],
        "notes": [
            "All sizes are primary repository/PyPI file lengths, not installed footprint.",
            "CPU estimates are explicitly unmeasured until smoke results exist.",
            "Semantic embeddings are similarity evidence, not a validated continuation classifier.",
            "Paddle OCR uses official Transformers safetensors; no Paddle runtime needed.",
            "No package installation or model-weight download is performed by this audit.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8", newline="\n"
    )
    print(args.out.relative_to(ROOT).as_posix(), "models", len(models), "packages", len(packages))


if __name__ == "__main__":
    main()
