"""Learned table evidence behind small interfaces (optional ``models`` extra).

- ``TATRDetector``: Table Transformer detection (Microsoft, MIT code and weights) as a page
  region detector; its observations go through the cached detection path like the layout
  models. Labels ``table`` and ``table rotated`` are kept raw.
- ``TATRStructure``: Table Transformer structure recognition on a rendered table crop: rows,
  columns, spanning cells, column headers and projected row headers (pixel boxes).
- ``TableFormerStructure``: Docling TableFormer (IBM, MIT code; CDLA-Permissive-2.0 and
  Apache-2.0 weights) on the same crop: cells with row/column offsets, spans and header
  flags (pixel boxes). No text is passed: cells are matched to spans by geometry later.

Models receive pixels only and never decide a table alone. Readings are cached per image
digest with the model identity and this module's code. Heavy imports happen only when a
model runs; a failed GPU operation is retried on CPU. Revisions are immutable commits.
"""

import hashlib
import importlib.metadata as metadata
import io
import json
import re
from pathlib import Path
from threading import RLock

from book_core.cache_store import read_json, write_json
from book_core.caching import code_digest
from book_core.detection.transformers import TransformersRegionDetector
from book_core.device import resolve_device, run_with_device

CACHE_VERSION = "table-reading-1"
DEPENDENCIES = ("torch", "transformers", "pillow", "timm", "docling-ibm-models", "safetensors")


def _versions():
    found = {}
    for package in DEPENDENCIES:
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = "not-installed"
    return found


VERSIONS = _versions()


def _revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("A model revision must be an immutable 40-character commit")
    return value


def _tatr_load(repo_id, revision, cache_dir, local_files_only):
    try:
        from transformers import AutoConfig, AutoImageProcessor, TableTransformerForObjectDetection
    except ImportError as error:
        raise RuntimeError("Table models require the optional [models] extra") from error
    options = {"revision": revision, "local_files_only": local_files_only}
    if cache_dir is not None:
        options["cache_dir"] = str(cache_dir)
    config = AutoConfig.from_pretrained(repo_id, **options)
    # The backbone weights are inside the checkpoint; never download a separate backbone.
    config.use_pretrained_backbone = False
    processor = AutoImageProcessor.from_pretrained(repo_id, **options)
    model = TableTransformerForObjectDetection.from_pretrained(repo_id, config=config, **options)
    resolved = getattr(model.config, "_commit_hash", None)
    if resolved is not None and resolved != revision:
        raise RuntimeError("Loaded model revision differs from the requested revision")
    return processor, model.eval()


class TATRDetector(TransformersRegionDetector):
    """Table Transformer detection on whole-page renders (cached like the layout models)."""

    name = "tatr_detection"
    repo_id = "microsoft/table-transformer-detection"
    default_revision = "2357cbe2b5a5d1c03e54f32764f06058933b65ab"

    @property
    def producer_source_sha256(self):
        return code_digest("table_models")

    def _load(self):
        self._processor, self._model = _tatr_load(
            self.repo_id, self.revision, self.cache_dir, self.local_files_only
        )


class _CropModel:
    name = ""
    repo_id = ""
    default_revision = ""

    def __init__(self, *, device="auto", revision=None, cache_dir=None, local_files_only=False):
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Unknown device policy")
        self.revision = _revision(revision or self.default_revision)
        self.cache_dir, self.local_files_only = cache_dir, local_files_only
        self._requested, self._device, self._last = device, None, None
        self._model = self._processor = None
        self._lock = RLock()

    @property
    def device(self):
        if self._device is None:
            self._device = resolve_device(self._requested)
        return self._device

    @property
    def identity(self):
        return {
            "recognizer": self.name,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "settings": self.settings(),
            "dependencies": VERSIONS,
            "device": self.device.resolved,
        }

    def settings(self):
        return {}

    def read(self, png):
        with self._lock:

            def operation(device):
                if device == "cpu" and self._last == "cuda":
                    self._model = self._processor = None
                self._last = device
                return self._infer(png, device)

            result, resolution = run_with_device(operation, self.device)
            self._device = resolution
            return result


class TATRStructure(_CropModel):
    """Rows, columns, spanning cells and headers of one table crop (pixel boxes)."""

    name = "tatr_structure"
    repo_id = "microsoft/table-transformer-structure-recognition"
    default_revision = "f4d4bdc85c3fe4b1fa49658882a5d38bbdd0f343"
    threshold = 0.3

    def settings(self):
        return {"threshold": self.threshold}

    def _infer(self, png, device):
        import torch
        from PIL import Image

        if self._model is None:
            self._processor, self._model = _tatr_load(
                self.repo_id, self.revision, self.cache_dir, self.local_files_only
            )
        self._model.to(device)
        with Image.open(io.BytesIO(png)) as image_file:
            image = image_file.convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt").to(device)
        with torch.inference_mode():
            outputs = self._model(**inputs)
        found = self._processor.post_process_object_detection(
            outputs, threshold=self.threshold, target_sizes=[image.size[::-1]]
        )[0]
        labels = self._model.config.id2label
        return {
            "width": image.size[0],
            "height": image.size[1],
            "objects": [
                {
                    "label": labels[int(label)],
                    "score": round(float(score), 4),
                    "box": [round(float(v), 2) for v in box.tolist()],
                }
                for score, label, box in zip(
                    found["scores"], found["labels"], found["boxes"], strict=True
                )
            ],
        }


class TableFormerStructure(_CropModel):
    """Cells with grid offsets, spans and header flags for one table crop (pixel boxes)."""

    name = "tableformer"
    repo_id = "docling-project/docling-models"
    default_revision = "2199320848bb9a8a519d22e4b528185a4f9a6f64"

    def __init__(self, *, mode="accurate", threads=4, **options):
        super().__init__(**options)
        if mode not in {"accurate", "fast"}:
            raise ValueError("TableFormer mode is accurate or fast")
        self.mode, self.threads = mode, threads

    def settings(self):
        return {"mode": self.mode}

    def _infer(self, png, device):
        import numpy as np
        import torch
        from huggingface_hub import snapshot_download
        from PIL import Image

        if self._model is None:
            try:
                from docling_ibm_models.tableformer.data_management.tf_predictor import (
                    TFPredictor,
                )
            except ImportError as error:
                raise RuntimeError("TableFormer requires the optional models extra") from error
            root = snapshot_download(
                self.repo_id,
                revision=self.revision,
                cache_dir=None if self.cache_dir is None else str(self.cache_dir),
                allow_patterns=[f"model_artifacts/tableformer/{self.mode}/*"],
                local_files_only=self.local_files_only,
            )
            directory = Path(root) / "model_artifacts" / "tableformer" / self.mode
            config = json.loads((directory / "tm_config.json").read_text("utf-8"))
            config["model"]["save_dir"] = str(directory)
            self._model = TFPredictor(config, device=device, num_threads=self.threads)
        with Image.open(io.BytesIO(png)) as image_file:
            image = np.asarray(image_file.convert("RGB"))
        height, width = image.shape[:2]
        page = {"image": image, "tokens": [], "width": width, "height": height}
        with torch.inference_mode():
            result = self._model.multi_table_predict(
                page, [[0.0, 0.0, float(width), float(height)]], do_matching=False
            )
        details = result[0]["predict_details"] if result else {}
        cells = []
        for cell in result[0]["tf_responses"] if result else []:
            box = cell["bbox"]
            cells.append(
                {
                    "box": [
                        round(box["l"], 2),
                        round(box["t"], 2),
                        round(box["r"], 2),
                        round(box["b"], 2),
                    ],  # fmt: skip
                    "row": int(cell["start_row_offset_idx"]),
                    "column": int(cell["start_col_offset_idx"]),
                    "row_span": int(cell["row_span"]),
                    "column_span": int(cell["col_span"]),
                    "column_header": bool(cell.get("column_header")),
                    "row_header": bool(cell.get("row_header")),
                    "row_section": bool(cell.get("row_section")),
                }
            )
        return {
            "width": width,
            "height": height,
            "rows": int(details.get("num_rows", 0) or 0),
            "columns": int(details.get("num_cols", 0) or 0),
            "cells": cells,
        }


class ReadingCache:
    """Cached readings of one crop model, keyed by image digest and model identity."""

    def __init__(self, reader, cache_dir):
        self.reader = reader
        self.root = Path(cache_dir) / "table_readings"
        self.producer = code_digest("table_models")

    def key(self):
        identity = {
            **self.reader.identity,
            "cache_version": CACHE_VERSION,
            "producer_sha256": self.producer,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def read(self, png):
        digest = hashlib.sha256(png).hexdigest()
        key = self.key()
        path = self.root / key / digest[:2] / f"{digest}.json"
        if path.exists():
            record = read_json(path)
            if record.get("image_sha256") == digest and record.get("key") == key:
                return record["reading"]
        reading = self.reader.read(png)
        write_json(path, {"key": key, "image_sha256": digest, "reading": reading,
                          "identity": self.reader.identity})  # fmt: skip
        return reading
