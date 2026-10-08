"""Verify optional model install in the active main environment, not a Phase 0 venv."""

import importlib.metadata as metadata
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

from book_core.detection import DetectionInput, HeronDetector, PPDocLayoutV3Detector
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments/out/step4b"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


def save(name, value):
    (OUT / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    import torch

    torch.set_num_threads(4)
    inventory = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "")
        licenses = [
            str(file)
            for file in dist.files or ()
            if any(word in str(file).lower() for word in ("license", "copying", "notice"))
        ]
        inventory.append(
            {
                "name": name,
                "version": dist.version,
                "license_expression": dist.metadata.get("License-Expression", ""),
                "license_metadata": dist.metadata.get("License", ""),
                "license_classifiers": [
                    classifier
                    for classifier in dist.metadata.get_all("Classifier", [])
                    if classifier.startswith("License ::")
                ],
                "license_files": licenses,
            }
        )
    result = {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "cuda_available": torch.cuda.is_available(),
        "cuda_build": torch.version.cuda,
        "torch_threads": torch.get_num_threads(),
        "packages": sorted(inventory, key=lambda item: item["name"].lower()),
        "models": [],
    }
    save("models_environment.json", result)
    extractor = PyMuPDFExtractor()
    source = ROOT / "experiments/fixtures/complex_map.pdf"
    render = extractor.render_page(source, 1, dpi=72)
    page = DetectionInput.from_raster(source_digest(source), 1, render)
    for detector_class in (HeronDetector, PPDocLayoutV3Detector):
        start = time.perf_counter()
        detector = detector_class(device="auto", cache_dir=ROOT / ".cache/huggingface")
        try:
            evidence = detector.detect(page)
            item = {
                "status": "passed",
                "detector": detector.name,
                "repo_id": detector.repo_id,
                "revision": detector.revision,
                "threshold": detector.threshold,
                "regions": len(evidence.regions),
                "device": evidence.device.model_dump(),
                "provenance": evidence.provenance.model_dump(),
                "dependency_versions": evidence.dependency_versions,
                "elapsed_seconds": time.perf_counter() - start,
            }
            save(f"smoke_{detector.name}.json", evidence.model_dump(mode="json"))
            snapshot = (
                ROOT / ".cache/huggingface" / ("models--" + detector.repo_id.replace("/", "--"))
            )
            snapshot /= "snapshots/" + detector.revision
            item["weights"] = [
                {
                    "path": file.relative_to(ROOT).as_posix(),
                    "bytes": file.stat().st_size,
                    "sha256": source_digest(file),
                }
                for file in snapshot.rglob("*.safetensors")
            ]
        except Exception as error:
            item = {
                "status": "failed",
                "detector": detector.name,
                "error": repr(error),
                "traceback": traceback.format_exc(),
                "elapsed_seconds": time.perf_counter() - start,
            }
        result["models"].append(item)
        save("models_environment.json", result)
        print(json.dumps(item), flush=True)
    if any(item["status"] != "passed" for item in result["models"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
