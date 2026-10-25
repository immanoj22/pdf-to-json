"""Official Transformers inference paths for Heron and PP-DocLayoutV3.

Heavy dependencies are imported only when a detector is executed. The adapters accept
rendered pixels, return observations, and have no reference to a text span or ledger.
"""

import hashlib
import importlib.metadata as metadata
import io
import json
import math
import re
from pathlib import Path
from threading import RLock

from book_core.caching import code_digest
from book_core.detection.models import DetectionInput, DetectionResult, DetectorRegion
from book_core.device import DevicePolicy, resolve_device, run_with_device
from book_core.layout.models import RegionType
from book_core.model.common import BBox, Provenance

DEPENDENCIES = (
    "torch",
    "torchvision",
    "transformers",
    "pillow",
    "safetensors",
    "huggingface-hub",
    "numpy",
    "opencv-python-headless",
    "tokenizers",
    "onnx",
    "onnxruntime-directml",
)

LABEL_TYPES: dict[str, RegionType] = {
    "caption": "caption_candidate",
    "figure_title": "caption_candidate",
    "footnote": "footnote_candidate",
    "vision_footnote": "footnote_candidate",
    "page_footer": "header_footer_candidate",
    "page_header": "header_footer_candidate",
    "footer": "header_footer_candidate",
    "header": "header_footer_candidate",
    "picture": "figure",
    "image": "figure",
    "chart": "figure",
    "section_header": "heading_candidate",
    "paragraph_title": "heading_candidate",
    "table": "table_candidate",
    "text": "main_text",
    "list_item": "main_text",
    "document_index": "main_text",
    "content": "main_text",
    "abstract": "main_text",
    "reference": "main_text",
    "reference_content": "main_text",
    "title": "title_candidate",
    "doc_title": "title_candidate",
    "aside_text": "sidebar",
    # A generic number label cannot prove that a region is a page number.
}


def region_type(raw_label: str) -> RegionType:
    label = raw_label.lower().replace("-", "_").replace(" ", "_")
    return LABEL_TYPES.get(label, "unknown")


def _versions() -> dict[str, str]:
    result = {}
    for package in DEPENDENCIES:
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = "not-installed"
    return result


def observations(page, processed, labels, name, revision):
    """Map official pixel output into the supplied page frame without sorting it."""
    sx = (page.page_bbox.x1 - page.page_bbox.x0) / page.raster.width
    sy = (page.page_bbox.y1 - page.page_bbox.y0) / page.raster.height

    def point(x, y):
        return page.page_bbox.x0 + float(x) * sx, page.page_bbox.y0 + float(y) * sy

    polygons = processed.get("polygon_points")
    regions = []
    for index, (score, label, box) in enumerate(
        zip(processed["scores"], processed["labels"], processed["boxes"], strict=True)
    ):
        label_id = int(label.item())
        raw_label = str(labels.get(label_id, labels.get(str(label_id), str(label_id))))
        coords = box.tolist()
        if len(coords) != 4:
            raise ValueError("Detector did not return a four-coordinate bounding box")
        x0, y0 = point(coords[0], coords[1])
        x1, y1 = point(coords[2], coords[3])
        polygon = []
        if polygons is not None:
            polygon = [point(*p) for p in polygons[index].tolist()]
        identity = json.dumps(
            [page.source_sha256, page.page, name, revision, index, label_id],
            separators=(",", ":"),
        )
        regions.append(
            DetectorRegion(
                id=hashlib.sha256(identity.encode()).hexdigest(),
                type=region_type(raw_label),
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                raw_label=raw_label,
                label_id=label_id,
                confidence=float(score.item()),
                polygon=polygon,
                emission_index=index,
            )
        )
    return regions


class TransformersRegionDetector:
    """Lazy official adapter; a failed GPU operation is retried in full on CPU."""

    name: str
    repo_id: str
    default_revision: str
    supports_directml = False

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        device: DevicePolicy = "auto",
        revision: str | None = None,
        cache_dir: Path | None = None,
        local_files_only: bool = False,
    ):
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("Detection threshold must be finite and between zero and one")
        if device not in {"auto", "cpu", "cuda", "directml"}:
            raise ValueError("Unknown device policy")
        self.threshold = threshold
        self.revision = revision or self.default_revision
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("A model revision must be an immutable 40-character commit")
        self.cache_dir = cache_dir
        self.local_files_only = local_files_only
        self._requested_device = device
        self._device = None
        self._processor = None
        self._model = None
        self._directml_session = None
        self._last_execution_device = None
        self._inference_lock = RLock()

    @property
    def producer_source_sha256(self):
        return code_digest("detection")

    @property
    def dependency_versions(self):
        return _versions()

    @property
    def device(self):
        if self._device is None:
            self._device = resolve_device(
                self._requested_device, allow_directml=self.supports_directml
            )
        return self._device

    def _load(self):
        try:
            from transformers import AutoImageProcessor, AutoModelForObjectDetection
        except ImportError as error:
            raise RuntimeError(
                "Learned region detection requires the optional [models] extra"
            ) from error
        options = {
            "revision": self.revision,
            "local_files_only": self.local_files_only,
        }
        if self.cache_dir is not None:
            options["cache_dir"] = str(self.cache_dir)
        processor = AutoImageProcessor.from_pretrained(self.repo_id, **options)
        model = AutoModelForObjectDetection.from_pretrained(self.repo_id, **options)
        resolved_revision = getattr(model.config, "_commit_hash", None)
        if resolved_revision is not None and resolved_revision != self.revision:
            raise RuntimeError(
                "Loaded model revision differs from the requested immutable revision"
            )
        self._processor, self._model = processor, model

    def _infer(self, page, device):
        try:
            import torch
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "Learned region detection requires the optional [models] extra"
            ) from error
        if self._model is None:
            self._load()
        torch_device = "cpu" if device == "directml" else device
        self._model.to(torch_device).eval()
        with Image.open(io.BytesIO(page.raster.png)) as image_file:
            image = image_file.convert("RGB")
        if image.size != (page.raster.width, page.raster.height):
            raise ValueError("Render PNG dimensions disagree with its extraction evidence")
        inputs = self._processor(images=image, return_tensors="pt").to(torch_device)
        if device == "directml":
            from book_core.directml import TableTransformerSession

            if self._directml_session is None:
                self._directml_session = TableTransformerSession(
                    self._model, inputs, threshold=self.threshold
                )
            outputs = self._directml_session.run(self._model, inputs)
        else:
            with torch.inference_mode():
                outputs = self._model(**inputs)
        processed = self._processor.post_process_object_detection(
            outputs,
            target_sizes=[image.size[::-1]],
            threshold=self.threshold,
        )[0]
        return observations(page, processed, self._model.config.id2label, self.name, self.revision)

    def detect(self, page: DetectionInput) -> DetectionResult:
        # Model placement and fallback state are shared by this adapter instance.
        with self._inference_lock:
            return self._detect_locked(page)

    def _detect_locked(self, page: DetectionInput) -> DetectionResult:
        def operation(device):
            # Reload CPU weights after a failed acceleration attempt.
            if device == "cpu" and self._last_execution_device in {"cuda", "directml"}:
                self._model = None
                self._processor = None
                self._directml_session = None
            self._last_execution_device = device
            return self._infer(page, device)

        regions, resolution = run_with_device(operation, self.device)
        self._device = resolution
        notes = [
            f"model_revision:{self.revision}",
            f"threshold:{self.threshold}",
            f"requested_device:{resolution.requested}",
            "Model emission positions are raw evidence; semantic reading order is ignored.",
        ]
        if resolution.fallback_reason:
            notes.append(f"device_fallback:{resolution.fallback_reason}")
        if resolution.resolved == "directml":
            notes.append(
                "ONNX DirectML graph; CPU preprocessing/postprocessing and EP fallback allowed"
            )
        return DetectionResult(
            source_sha256=page.source_sha256,
            page=page.page,
            detector=self.name,
            repo_id=self.repo_id,
            revision=self.revision,
            threshold=self.threshold,
            regions=regions,
            dependency_versions=self.dependency_versions,
            device=resolution,
            provenance=Provenance(
                source_sha256=page.source_sha256,
                engine=self.name,
                engine_version=self.dependency_versions["transformers"],
                method="derived",
                resolved_device=resolution.resolved,
                execution_device=resolution.resolved,
                notes=notes,
            ),
        )


class HeronDetector(TransformersRegionDetector):
    name = "heron"
    repo_id = "docling-project/docling-layout-heron"
    default_revision = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"


class PPDocLayoutV3Detector(TransformersRegionDetector):
    name = "pp_doclayoutv3"
    repo_id = "PaddlePaddle/PP-DocLayoutV3_safetensors"
    default_revision = "e4f489dc536556fc1be02b973ba06756e0d4a2ac"
