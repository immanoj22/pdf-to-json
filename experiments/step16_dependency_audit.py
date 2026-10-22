"""Read upstream OCR package metadata and licence sources before installation."""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
from pathlib import Path

OUT = Path("experiments/out/step16/dependencies")


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "book-core-dependency-audit"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"disk": dict(zip(("total", "used", "free"), shutil.disk_usage(".")))}
    sources = {
        "tesseract_license": "https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.0/LICENSE",
        "tessdata_license": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/LICENSE",
        "pytesseract_license": "https://raw.githubusercontent.com/madmaze/pytesseract/master/LICENSE",
        "paddleocr_license": "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE",
        "paddle_license": "https://raw.githubusercontent.com/PaddlePaddle/Paddle/develop/LICENSE",
        "paddlex_license": "https://raw.githubusercontent.com/PaddlePaddle/PaddleX/develop/LICENSE",
        "tesseract_windows_source": "https://raw.githubusercontent.com/UB-Mannheim/tesseract/main/nsis/tesseract.nsi",
    }
    result["sources"] = {}
    for name, url in sources.items():
        try:
            data = fetch(url)
            (OUT / f"{name}.txt").write_bytes(data)
            result["sources"][name] = {"url": url, "bytes": len(data)}
        except (OSError, ValueError, KeyError) as error:
            result["sources"][name] = {"url": url, "error": str(error)}
    tree = json.loads(
        fetch(
            "https://api.github.com/repos/tesseract-ocr/tessdata_best/git/trees/main?recursive=1"
        )
    )
    packs = [item for item in tree["tree"] if item["path"].endswith(".traineddata")]
    result["tessdata_best"] = {
        "revision": tree["sha"],
        "traineddata_count": len(packs),
        "traineddata_bytes": sum(item["size"] for item in packs),
        "files": packs,
    }
    for package in ("pytesseract", "paddleocr", "paddlepaddle", "paddlex", "tesseract"):
        try:
            data = json.loads(fetch(f"https://pypi.org/pypi/{package}/json"))
            info = data["info"]
            result[package] = {
                "version": info["version"],
                "license": info.get("license_expression") or info.get("license"),
                "requires_python": info["requires_python"],
                "requires_dist": info["requires_dist"],
                "urls": data["urls"],
            }
        except (OSError, ValueError, KeyError) as error:
            result[package] = {"error": str(error)}
    (OUT / "upstream_audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "disk": result["disk"],
                "tessdata_best": {
                    k: v for k, v in result["tessdata_best"].items() if k != "files"
                },
                "versions": {
                    p: result[p].get("version")
                    for p in ("pytesseract", "paddleocr", "paddlepaddle", "paddlex")
                },
            },
            indent=2,
        )
    )


def models():
    candidates = json.loads(
        fetch(
            "https://huggingface.co/api/models?author=PaddlePaddle&search=OCRv5&limit=100"
        )
    )
    result = []
    for candidate in candidates:
        name = candidate["id"]
        if "safetensors" not in name:
            continue
        data = json.loads(fetch(f"https://huggingface.co/api/models/{name}?blobs=true"))
        row = {
            "id": name,
            "revision": data["sha"],
            "license": data.get("cardData", {}).get("license"),
            "siblings": data.get("siblings", []),
        }
        result.append(row)
        print(name, row["revision"], row["license"], flush=True)
    (OUT / "ppocr_models_audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def conda():
    from packaging.version import Version

    pending = ["tesseract"]
    records = {}
    while pending:
        name = pending.pop(0)
        if name in records or name.startswith("__"):
            continue
        data = json.loads(fetch(f"https://api.anaconda.org/package/conda-forge/{name}"))
        files = [
            f
            for f in data["files"]
            if f["basename"].startswith("win-64/") and "main" in f.get("labels", [])
        ]
        if not files:
            files = [
                f
                for f in data["files"]
                if f["basename"].startswith("noarch/") and "main" in f.get("labels", [])
            ]
        record = max(
            files,
            key=lambda f: (
                Version(f["version"]),
                f["attrs"].get("build_number", 0),
                f["upload_time"],
            ),
        )
        records[name] = record
        (OUT / "conda_candidates.json").write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )
        pending.extend(dep.split()[0] for dep in record["attrs"].get("depends", []))
        print(
            name,
            record["version"],
            record["attrs"].get("license"),
            record["attrs"].get("depends"),
            flush=True,
        )
        if record["attrs"].get("license", "").startswith("GPL-"):
            print("Rejected before download: GPL dependency.", flush=True)
            return
    (OUT / "conda_candidates.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--conda", action="store_true")
    args = parser.parse_args()
    conda() if args.conda else models() if args.models else main()
