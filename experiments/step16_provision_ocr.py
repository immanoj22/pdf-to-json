"""Provision audited OCR assets locally; never run an installer or alter PATH."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step16/dependencies"
ASSETS = ROOT / ".cache/step16/ocr"
REVISION = "e12c65a915945e4c28e237a9b52bc4a8f39a0cec"


def get(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "book-core-ocr-provision"}
    )
    return urllib.request.urlopen(request, timeout=120)


def download(url, path, size=None, sha256=None, git_sha=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if size is not None and path.exists() and path.stat().st_size > size:
        path.unlink()  # over-long partial from an interrupted run; restart this file
    if not path.exists() or (size is not None and path.stat().st_size != size):
        for attempt in range(12):
            try:
                offset = path.stat().st_size if path.exists() else 0
                headers = {"User-Agent": "book-core-ocr-provision"}
                if offset and size is not None:
                    headers["Range"] = f"bytes={offset}-"
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=45) as source:
                    mode = "ab" if offset and source.status == 206 else "wb"
                    with path.open(mode) as destination:
                        shutil.copyfileobj(source, destination)
                if size is None or path.stat().st_size == size:
                    break
            except (TimeoutError, OSError):
                if attempt == 11:
                    raise
                time.sleep(1)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if size is not None and len(data) != size:
        raise ValueError(f"Wrong size for {path}: {len(data)} != {size}")
    if sha256 is not None and digest != sha256:
        raise ValueError(f"Wrong SHA-256 for {path}")
    if git_sha is not None:
        actual = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if actual != git_sha:
            raise ValueError(f"Wrong Git blob digest for {path}")
    return {
        "url": url,
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(data),
        "sha256": digest,
    }


def reserve(need):
    free = shutil.disk_usage(ROOT).free
    # Preserve the project 5 GB floor and a separate 4 GB evaluation allocation.
    if free - need < 9_000_000_000:
        raise RuntimeError(
            f"Disk reserve refused: free={free}, need={need}, reserve=9000000000"
        )
    return {"free_before": free, "planned_bytes": need, "reserve_bytes": 9_000_000_000}


def packs():
    audit = json.loads((OUT / "upstream_audit.json").read_text(encoding="utf-8"))[
        "tessdata_best"
    ]
    assert audit["revision"] == REVISION
    directory = ASSETS / "tessdata_best" / REVISION
    need = sum(
        item["size"]
        for item in audit["files"]
        if not (directory / item["path"]).exists()
    )
    disk = reserve(need)

    def one(item):
        return download(
            f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{REVISION}/{item['path']}",
            directory / item["path"],
            item["size"],
            git_sha=item["sha"],
        )

    priority = {
        "eng.traineddata",
        "spa.traineddata",
        "osd.traineddata",
        "hin.traineddata",
        "ara.traineddata",
        "chi_sim.traineddata",
        "rus.traineddata",
        "ell.traineddata",
    }
    ordered = sorted(
        audit["files"], key=lambda item: (item["path"] not in priority, item["path"])
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        records = []
        for record in executor.map(one, ordered):
            records.append(record)
            print(f"Verified {record['path']}", flush=True)
    licence = download(
        f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{REVISION}/LICENSE",
        directory / "LICENSE",
    )
    result = {
        "revision": REVISION,
        "disk": disk,
        "license": "Apache-2.0",
        "license_file": licence,
        "files": records,
        "total_bytes": sum(r["bytes"] for r in records),
    }
    (OUT / "tessdata_manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Verified {len(records)} traineddata files, {result['total_bytes']} bytes",
        flush=True,
    )


def binary():
    entries = []
    for repo, tag, names in (
        ("ip7z/7zip", "25.01", ("7zr.exe", "7z2501-x64.exe")),
        (
            "tesseract-ocr/tesseract",
            "5.5.3",
            ("tesseract-ocr-w64-setup-5.5.3.20260724.exe",),
        ),
    ):
        with get(
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        ) as response:
            release = json.load(response)
        for name in names:
            asset = next(a for a in release["assets"] if a["name"] == name)
            entries.append(asset)
    disk = reserve(sum(a["size"] for a in entries) + 350_000_000)
    (OUT / "binary_plan.json").write_text(
        json.dumps({"disk": disk, "assets": entries}, indent=2) + "\n", encoding="utf-8"
    )
    records = []
    for asset in entries:
        digest = asset.get("digest")
        records.append(
            download(
                asset["browser_download_url"],
                ASSETS / "downloads" / asset["name"],
                asset["size"],
                digest.removeprefix("sha256:") if digest else None,
            )
        )
    download("https://www.7-zip.org/license.txt", ASSETS / "downloads/7zip_license.txt")
    seven = ASSETS / "7zip-25.01"
    commands = [
        [
            str(ASSETS / "downloads/7zr.exe"),
            "x",
            str(ASSETS / "downloads/7z2501-x64.exe"),
            f"-o{seven}",
            "-y",
        ],
        [
            str(seven / "7z.exe"),
            "x",
            str(ASSETS / "downloads/tesseract-ocr-w64-setup-5.5.3.20260724.exe"),
            f"-o{ASSETS / 'tesseract-5.5.3'}",
            "-y",
        ],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        (OUT / f"extract_{index}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
    (OUT / "binary_manifest.json").write_text(
        json.dumps({"disk": disk, "downloads": records, "commands": commands}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print("Extracted Tesseract locally; installer was not executed.", flush=True)


def ppmodels():
    names = {
        "PP-OCRv5_server_det_safetensors",
        "PP-OCRv5_server_rec_safetensors",
        "en_PP-OCRv5_mobile_rec_safetensors",
        "arabic_PP-OCRv5_mobile_rec_safetensors",
        "cyrillic_PP-OCRv5_mobile_rec_safetensors",
        "devanagari_PP-OCRv5_mobile_rec_safetensors",
        "el_PP-OCRv5_mobile_rec_safetensors",
    }
    candidates = json.loads(
        (OUT / "ppocr_models_audit.json").read_text(encoding="utf-8")
    )
    selected = [item for item in candidates if item["id"].split("/")[-1] in names]
    assert len(selected) == len(names)
    assert all(item["license"] == "apache-2.0" for item in selected)
    disk = reserve(
        sum(file.get("size", 0) for item in selected for file in item["siblings"])
    )
    records = []
    for item in selected:
        directory = ASSETS / "ppocr" / item["id"].split("/")[-1] / item["revision"]
        files = []
        for file in item["siblings"]:
            name = file["rfilename"]
            if name == ".gitattributes":
                continue
            files.append(
                download(
                    f"https://huggingface.co/{item['id']}/resolve/{item['revision']}/{name}",
                    directory / name,
                    file.get("size"),
                    file.get("lfs", {}).get("sha256"),
                )
            )
        records.append(
            {
                **item,
                "local_directory": directory.relative_to(ROOT).as_posix(),
                "files": files,
            }
        )
        print(f"Verified PP-OCRv5 model {item['id']}", flush=True)
    (OUT / "ppocr_manifest.json").write_text(
        json.dumps({"disk": disk, "models": records}, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("packs", "binary", "ppmodels"))
    arguments = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"packs": packs, "binary": binary, "ppmodels": ppmodels}[arguments.action]()
