"""Explicit, offline OCR readers behind the OCR interface.

Tesseract confidences and PP-OCR scores are model evidence, not probabilities of
correct text. This module does not set review thresholds or replace primary text
using incomparable engine scores. All heavy dependencies are imported lazily.
"""

from __future__ import annotations

import io
import os
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from importlib.metadata import version
from pathlib import Path
from threading import RLock

from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox, Provenance
from book_core.model.spans import TextSpan
from book_core.ocr.geometry import (
    ImageTransform,
    apply_transform,
    decode_image,
    encode_image,
    pixel_box_to_pdf,
    prepare_image,
    source_pixel_box,
)
from book_core.ocr.languages import (
    installed_languages,
    map_languages,
    require_language_packs,
    script_languages,
)

_RUNTIME_LOCK = RLock()


@dataclass(frozen=True)
class OcrAlternative:
    engine: str
    text: str
    confidence: float
    pixel_bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class OcrWord:
    text: str
    pixel_bbox: tuple[float, float, float, float]
    confidence: float
    line_key: tuple[int, ...]
    language: str = "und"
    script: str | None = None
    text_direction: str | None = None
    line_confidence: float = 0.0
    raw_confidence: float | None = None
    alternatives: tuple[OcrAlternative, ...] = ()
    granularity: str = "word"


@dataclass(frozen=True)
class OcrOrientation:
    rotation_clockwise: int = 0
    confidence: float | None = None
    script: str | None = None
    script_confidence: float | None = None
    detected: bool = False


@dataclass(frozen=True)
class OcrReading:
    engine: str
    version: str
    languages: tuple[str, ...]
    words: tuple[OcrWord, ...]
    orientation: OcrOrientation
    transform: ImageTransform
    warnings: tuple[str, ...] = ()
    source: str = "ocr"
    model_fingerprints: tuple[tuple[str, str], ...] = ()
    unmatched_secondary: tuple[OcrWord, ...] = ()
    execution_device: str = "cpu"

    @property
    def mean_confidence(self) -> float | None:
        return sum(word.confidence for word in self.words) / len(self.words) if self.words else None


@dataclass(frozen=True)
class OcrPageContext:
    """Explicit document identity and coordinate frame for the byte-only OCR protocol."""

    source_sha256: str
    page_number: int
    raster: RasterPage

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("OCR span context needs a document SHA-256")
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("OCR span context needs a positive document page number")


@contextmanager
def _tesseract_runtime(executable: Path, tessdata: Path | None = None):
    """pytesseract uses a module-global executable; serialize and restore that state."""
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError("Tesseract requires the optional [ocr] extra") from error
    with _RUNTIME_LOCK:
        old_command = pytesseract.pytesseract.tesseract_cmd
        old_threads = os.environ.get("OMP_THREAD_LIMIT")
        old_prefix = os.environ.get("TESSDATA_PREFIX")
        pytesseract.pytesseract.tesseract_cmd = str(executable)
        os.environ["OMP_THREAD_LIMIT"] = "1"
        if tessdata is not None:
            # An env var, not --tessdata-dir: pytesseract keeps literal quotes on Windows.
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
        try:
            yield pytesseract
        finally:
            pytesseract.pytesseract.tesseract_cmd = old_command
            if old_threads is None:
                os.environ.pop("OMP_THREAD_LIMIT", None)
            else:
                os.environ["OMP_THREAD_LIMIT"] = old_threads
            if tessdata is not None:
                if old_prefix is None:
                    os.environ.pop("TESSDATA_PREFIX", None)
                else:
                    os.environ["TESSDATA_PREFIX"] = old_prefix


def _line_confidences(words: list[OcrWord] | tuple[OcrWord, ...]) -> tuple[OcrWord, ...]:
    scores = defaultdict(list)
    for word in words:
        scores[word.line_key].append(word.confidence)
    means = {key: sum(values) / len(values) for key, values in scores.items()}
    return tuple(replace(word, line_confidence=means[word.line_key]) for word in words)


def parse_tesseract_data(
    data: dict, *, languages: tuple[str, ...], script: str | None = None
) -> tuple[OcrWord, ...]:
    """Retain TSV emission order; line IDs are segmentation evidence only."""
    words = []
    required = (
        "text",
        "level",
        "conf",
        "left",
        "top",
        "width",
        "height",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
    )
    lengths = {len(data[key]) for key in required}
    if len(lengths) != 1:
        raise ValueError("Tesseract TSV columns have inconsistent lengths")
    language = (
        languages[0] if len(languages) == 1 and not languages[0].startswith("script/") else "und"
    )
    for index, text in enumerate(data["text"]):
        if int(data["level"][index]) != 5 or not str(text).strip():
            continue
        left, top = float(data["left"][index]), float(data["top"][index])
        width, height = float(data["width"][index]), float(data["height"][index])
        confidence = float(data["conf"][index])
        if min(width, height) < 0 or not 0 <= confidence <= 100:
            raise ValueError("Invalid Tesseract word geometry or confidence")
        word_script, direction = text_properties(str(text))
        words.append(
            OcrWord(
                str(text),
                (left, top, left + width, top + height),
                round(confidence / 100, 8),
                tuple(
                    int(data[key][index])
                    for key in ("page_num", "block_num", "par_num", "line_num")
                ),
                language=language,
                script=word_script,
                text_direction=direction,
                raw_confidence=round(confidence / 100, 8),
            )
        )
    return _line_confidences(words)


def text_properties(text: str) -> tuple[str | None, str | None]:
    """Unicode evidence from the reading itself; OSD's dominant script is not per-word truth."""
    from fontTools.unicodedata import script

    scripts = {script(character) for character in text} - {"Zyyy", "Zinh", "Zzzz"}
    directions = {unicodedata.bidirectional(character) for character in text} & {"L", "R", "AL"}
    direction = (
        "ltr" if directions == {"L"} else "rtl" if directions and "L" not in directions else None
    )
    return next(iter(scripts)) if len(scripts) == 1 else None, direction


class TesseractEngine:
    """Tesseract 5 LSTM via pytesseract, explicit binary and tessdata, one thread.

    ``languages=[]`` invokes OSD script-model fallback. Language refinement must be
    selected by external measured evidence; a higher raw OCR score is not evidence
    that a language-specific re-reading has less error.
    """

    name = "tesseract"

    def __init__(
        self,
        executable: Path,
        tessdata: Path,
        *,
        dpi: int = 300,
        psm: int = 3,
        page_context: OcrPageContext | None = None,
    ):
        self.executable, self.tessdata = Path(executable).resolve(), Path(tessdata).resolve()
        if not self.executable.is_file() or not self.tessdata.is_dir():
            raise FileNotFoundError("OCR requires an installed executable and tessdata directory")
        if dpi <= 0 or psm not in {3, 4, 5, 6, 7, 8, 11, 12, 13}:
            raise ValueError("Invalid Tesseract DPI or segmentation mode")
        if '"' in str(self.tessdata):
            raise ValueError("Tessdata path cannot contain a quote")
        self.dpi, self.psm = dpi, psm
        self.page_context = page_context
        self._version = None
        self._fingerprints: dict[str, str] = {}
        self._pack_signatures: dict[str, tuple[int, int]] = {}

    @property
    def identity(self) -> dict:
        return {
            "name": self.name,
            "version": self.engine_version,
            "pytesseract_version": version("pytesseract"),
            "executable_sha256": source_digest(self.executable),
            "installed_languages": installed_languages(self.tessdata),
            "dpi": self.dpi,
            "psm": self.psm,
            "oem": 1,
            "threads": 1,
        }

    @property
    def engine_version(self) -> str:
        if self._version is None:
            with _tesseract_runtime(self.executable) as runtime:
                self._version = str(runtime.get_tesseract_version())
            if not self._version.startswith("5."):
                raise RuntimeError("This OCR stage requires a Tesseract 5.x build")
        return self._version

    def model_fingerprints(self, languages: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        for code in languages:
            path = self.tessdata / f"{code}.traineddata"
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if self._pack_signatures.get(code) != signature:
                self._fingerprints[code] = source_digest(path)
                self._pack_signatures[code] = signature
        return tuple((code, self._fingerprints[code]) for code in languages)

    def read(
        self,
        image: bytes,
        *,
        languages: list[str],
        orient: bool = True,
        deskew: bool = False,
        transform: ImageTransform | None = None,
    ) -> OcrReading:
        from PIL import Image

        warnings = []
        orientation = OcrOrientation()
        base_config = f"--dpi {self.dpi}"
        with _tesseract_runtime(self.executable, self.tessdata) as runtime:
            if orient and transform is None:
                require_language_packs(self.tessdata, ("osd",))
                try:
                    result = runtime.image_to_osd(
                        Image.open(io.BytesIO(image)),
                        config=base_config,
                        output_type=runtime.Output.DICT,
                    )
                    orientation = OcrOrientation(
                        int(result["rotate"]),
                        float(result["orientation_conf"]),
                        str(result["script"]),
                        float(result["script_conf"]),
                        True,
                    )
                except runtime.TesseractError as error:
                    # Too few characters is ordinary on sparse pages; retain evidence.
                    if "too few characters" not in str(error).lower():
                        raise
                    warnings.append("osd_insufficient_text")
            selected = (
                map_languages(languages) if languages else script_languages(orientation.script)
            )
            require_language_packs(self.tessdata, selected)
            if transform is None:
                prepared, transform = prepare_image(
                    image,
                    rotation_clockwise=orientation.rotation_clockwise,
                    deskew=deskew,
                )
            else:
                prepared = encode_image(apply_transform(decode_image(image), transform))
            data = runtime.image_to_data(
                Image.open(io.BytesIO(prepared)),
                lang="+".join(selected),
                config=f"{base_config} --oem 1 --psm {self.psm}",
                output_type=runtime.Output.DICT,
            )
        packs = (
            (*selected, "osd")
            if orient and transform is not None and orientation.detected
            else selected
        )
        return OcrReading(
            self.name,
            self.engine_version,
            selected,
            parse_tesseract_data(data, languages=selected, script=orientation.script),
            orientation,
            transform,
            tuple(warnings),
            model_fingerprints=self.model_fingerprints(tuple(dict.fromkeys(packs))),
        )

    def recognize(self, image: bytes, *, languages: list[str]) -> Iterator[TextSpan]:
        """Original OCR protocol, bound to an explicit source page at construction."""
        if self.page_context is None:
            raise ValueError("recognize requires OcrPageContext; use read for raster-only evidence")
        context = self.page_context
        if image != context.raster.png:
            raise ValueError("OCR image differs from the bound page raster")
        reading = self.read(image, languages=languages)
        digest = context.source_sha256
        for index, word in enumerate(reading.words):
            line_id = stable_id(digest, "ocr-line", context.page_number, *word.line_key)
            bbox = pixel_box_to_pdf(reading.transform, word.pixel_bbox, context.raster)
            yield TextSpan(
                id=stable_id(digest, "ocr-word", context.page_number, index),
                line_id=line_id,
                page=context.page_number,
                raw_text=word.text,
                text=unicodedata.normalize("NFKC", word.text),
                bbox=bbox,
                font="ocr-estimated",
                size=bbox.y1 - bbox.y0,
                color=0,
                flags=0,
                language=word.language,
                script=word.script,
                provenance=Provenance(
                    source_sha256=digest,
                    engine=self.name,
                    engine_version=reading.version,
                    method="ocr",
                    notes=["explicit OCR page context; line-height font size estimate"],
                ),
            )


@dataclass(frozen=True)
class PpRecognitionModel:
    """Local official PP-OCRv5 files and explicitly documented language coverage."""

    path: Path
    revision: str
    languages: tuple[str, ...]
    name: str

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("PP-OCRv5 models require an immutable revision")
        if not self.path.is_dir() or not self.languages:
            raise ValueError("PP-OCRv5 requires an installed model and language coverage")


class PpOcrV5Engine:
    """Independent PP-OCRv5 detector/recognizers through official Transformers.

    The output exposes detected *line* boxes without manufacturing word boxes.
    ``regions`` optionally runs recognition on primary words for a paired comparison;
    that result is explicitly marked, and is not independent detection accuracy.
    """

    name = "pp_ocrv5"

    def __init__(
        self,
        detector_path: Path,
        detector_revision: str,
        recognizers: tuple[PpRecognitionModel, ...],
        *,
        device: str = "auto",
    ):
        from book_core.device import resolve_device

        self.detector_path = Path(detector_path)
        if not self.detector_path.is_dir() or not re.fullmatch(r"[0-9a-f]{40}", detector_revision):
            raise ValueError("PP-OCRv5 requires a local detector and immutable revision")
        names = [model.name for model in recognizers]
        if len(names) != len(set(names)) or "detector" in names:
            raise ValueError(
                "PP-OCRv5 recognizer names must be distinct from one another and detector"
            )
        self.detector_revision = detector_revision
        self.recognizers = recognizers
        self._resolution = resolve_device(device)
        self._models = {}
        self._processors = {}
        self._lock = RLock()
        self._asset_digests: dict[Path, tuple[tuple[int, int], str]] = {}

    def model_fingerprints(self) -> tuple[tuple[str, str], ...]:
        """Model and processor contents enter the cache key before inference."""
        values = []
        folders = [
            ("detector", self.detector_path),
            *((model.name, model.path) for model in self.recognizers),
        ]
        for label, folder in folders:
            for path in sorted(folder.iterdir()):
                if not path.is_file() or path.suffix not in {".json", ".safetensors"}:
                    continue
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                if path not in self._asset_digests or self._asset_digests[path][0] != signature:
                    self._asset_digests[path] = (signature, source_digest(path))
                values.append((f"{label}/{path.name}", self._asset_digests[path][1]))
        return tuple(values)

    @property
    def identity(self) -> dict:
        return {
            "name": self.name,
            "runtime": "transformers",
            "version": version("transformers"),
            "detector_revision": self.detector_revision,
            "recognizers": [
                {"name": model.name, "revision": model.revision, "languages": model.languages}
                for model in self.recognizers
            ],
            "threads": 1,
            "device": self._resolution.resolved,
            "local_files_only": True,
            "model_fingerprints": self.model_fingerprints(),
        }

    def supports(self, languages: list[str]) -> bool:
        selected = set(map_languages(languages))
        return bool(selected) and any(
            selected <= set(model.languages) for model in self.recognizers
        )

    def _load_detector(self):
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        if "detector" not in self._models:
            self._processors["detector"] = AutoImageProcessor.from_pretrained(
                str(self.detector_path),
                local_files_only=True,
                trust_remote_code=False,
            )
            self._models["detector"] = AutoModelForObjectDetection.from_pretrained(
                str(self.detector_path),
                local_files_only=True,
                trust_remote_code=False,
            ).eval()

    def _load(self, specification: PpRecognitionModel):
        from transformers import AutoImageProcessor, AutoModelForTextRecognition

        self._load_detector()
        if specification.name not in self._models:
            self._processors[specification.name] = AutoImageProcessor.from_pretrained(
                str(specification.path),
                local_files_only=True,
                trust_remote_code=False,
            )
            self._models[specification.name] = AutoModelForTextRecognition.from_pretrained(
                str(specification.path),
                local_files_only=True,
                trust_remote_code=False,
            ).eval()

    def _detect(self, image, device):
        import torch

        detector = self._models["detector"].to(device)
        processor = self._processors["detector"]
        inputs = processor(images=image, return_tensors="pt").to(device)
        with torch.inference_mode():
            return processor.post_process_object_detection(
                detector(**inputs),
                target_sizes=torch.tensor([image.size[::-1]], device=device),
            )[0]

    def detect_text(self, image: bytes) -> tuple[BBox, ...]:
        """Text detection only, in the input image's pixels; no OCR or language choice."""
        import cv2
        from PIL import Image

        from book_core.device import run_with_device

        pil = Image.fromarray(cv2.cvtColor(decode_image(image), cv2.COLOR_BGR2RGB))
        with self._lock, _RUNTIME_LOCK:
            self._load_detector()
            result, self._resolution = run_with_device(
                lambda device: self._detect(pil, device),
                self._resolution,
            )
        return tuple(
            BBox(
                x0=float(points[:, 0].min()),
                y0=float(points[:, 1].min()),
                x1=float(points[:, 0].max()),
                y1=float(points[:, 1].max()),
            )
            for points in result["boxes"].detach().cpu().numpy()
        )

    def read(
        self,
        image: bytes,
        *,
        languages: list[str],
        transform: ImageTransform | None = None,
        regions: tuple[OcrWord, ...] | None = None,
    ) -> OcrReading:
        from book_core.device import run_with_device

        selected = map_languages(languages)
        specification = next(
            (model for model in self.recognizers if set(selected) <= set(model.languages)), None
        )
        if not selected or specification is None:
            raise ValueError(f"PP-OCRv5 has no installed recognizer covering {selected}")
        array = decode_image(image)
        transform = transform or ImageTransform.identity(array.shape[1], array.shape[0])
        prepared = apply_transform(array, transform)
        with self._lock, _RUNTIME_LOCK:
            self._load(specification)
            words, self._resolution = run_with_device(
                lambda device: self._infer(prepared, specification, device, regions),
                self._resolution,
            )
        warnings = (
            ("secondary word crops use primary segmentation",)
            if regions is not None
            else ("secondary geometry is detected line geometry; no word boxes are inferred",)
        )
        fingerprints = tuple(
            item
            for item in self.model_fingerprints()
            if item[0].split("/", 1)[0] in {"detector", specification.name}
        )
        return OcrReading(
            self.name,
            version("transformers"),
            selected,
            _line_confidences(words),
            OcrOrientation(transform.rotation_clockwise),
            transform,
            warnings,
            model_fingerprints=fingerprints,
            execution_device=self._resolution.resolved,
        )

    def _infer(self, array, specification, device, regions):
        import cv2
        import numpy as np
        import torch
        from PIL import Image

        image = Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))
        recognizer = self._models[specification.name].to(device)
        processor = self._processors[specification.name]
        if regions is None:
            result = self._detect(image, device)
            crops = []
            # Preserve detector emission order as evidence, never claim reading order.
            for index, points in enumerate(result["boxes"].detach().cpu().numpy()):
                points = np.asarray(points, dtype=np.float32).reshape(4, 2)
                width = max(
                    np.linalg.norm(points[1] - points[0]), np.linalg.norm(points[2] - points[3])
                )
                height = max(
                    np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[2] - points[1])
                )
                if width < 1 or height < 1:
                    continue
                target = np.array(
                    [[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32
                )
                matrix = cv2.getPerspectiveTransform(points, target)
                crop = cv2.warpPerspective(
                    array,
                    matrix,
                    (int(np.ceil(width)), int(np.ceil(height))),
                    borderValue=(255, 255, 255),
                )
                box = (*points.min(axis=0), *points.max(axis=0))
                crops.append((crop, tuple(float(value) for value in box), (index,), "line"))
        else:
            crops = []
            for word in regions:
                x0, y0, x1, y1 = word.pixel_bbox
                left, top = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
                right, bottom = (
                    min(array.shape[1], int(np.ceil(x1))),
                    min(array.shape[0], int(np.ceil(y1))),
                )
                if right <= left or bottom <= top:
                    continue
                crops.append(
                    (array[top:bottom, left:right], word.pixel_bbox, word.line_key, "word")
                )
        words = []
        for crop, bbox, line_key, granularity in crops:
            inputs = processor(
                images=Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), return_tensors="pt"
            ).to(device)
            with torch.inference_mode():
                result = processor.post_process_text_recognition(recognizer(**inputs))[0]
            text, confidence = str(result["text"]), float(result["score"])
            # An empty CTC result has a NaN mean in the upstream implementation.
            if not text:
                confidence = 0.0
            if not np.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("PP-OCRv5 emitted an invalid confidence")
            if text or granularity == "word":
                script, direction = text_properties(text)
                words.append(
                    OcrWord(
                        text,
                        bbox,
                        round(confidence, 8),
                        line_key,
                        script=script,
                        text_direction=direction,
                        raw_confidence=round(confidence, 8),
                        granularity=granularity,
                    )
                )
        return tuple(words)


def _overlap(a: BBox, b: BBox) -> float:
    area = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    denominator = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
    return area / denominator if denominator else 0.0


def compare_readings(primary: OcrReading, secondary: OcrReading) -> OcrReading:
    """Compare spatially corresponding lines, retaining primary emission order/text.

    Secondary recognizers may expose line boxes only. Their token comparisons retain
    that line's box (never invent word boxes). No-space scripts stay a comparison
    segment; their tokenization is not treated as a measured word boundary.
    """
    if (primary.transform.input_width, primary.transform.input_height) != (
        secondary.transform.input_width,
        secondary.transform.input_height,
    ):
        raise ValueError("OCR readings refer to different image frames")
    primary_lines: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for index, word in enumerate(primary.words):
        primary_lines[word.line_key].append(index)
    secondary_groups = defaultdict(list)
    unmatched = []
    primary_bounds = {}
    for key, indices in primary_lines.items():
        boxes = [
            source_pixel_box(primary.transform, primary.words[index].pixel_bbox)
            for index in indices
        ]
        primary_bounds[key] = BBox(
            x0=min(box.x0 for box in boxes),
            y0=min(box.y0 for box in boxes),
            x1=max(box.x1 for box in boxes),
            y1=max(box.y1 for box in boxes),
        )
    for word in secondary.words:
        box = source_pixel_box(secondary.transform, word.pixel_bbox)
        candidates = [(_overlap(bounds, box), key) for key, bounds in primary_bounds.items()]
        overlap, key = max(candidates, default=(0.0, ()), key=lambda item: item[0])
        if overlap <= 0:
            unmatched.append(word)
        else:
            secondary_groups[key].append(word)
    words = list(primary.words)
    for key, indices in primary_lines.items():
        other = secondary_groups.get(key, [])
        tokens = [(token, word) for word in other for token in re.findall(r"\S+", word.text)]
        originals = [unicodedata.normalize("NFKC", primary.words[index].text) for index in indices]
        readings = [unicodedata.normalize("NFKC", token) for token, _ in tokens]
        matcher = SequenceMatcher(None, originals, readings, autojunk=False)
        for kind, start, end, second_start, second_end in matcher.get_opcodes():
            if kind == "insert":
                unmatched.extend(word for _, word in tokens[second_start:second_end])
                continue
            alternatives = tuple(
                OcrAlternative(secondary.engine, token, word.confidence, word.pixel_bbox)
                for token, word in tokens[second_start:second_end]
            )
            for position in range(start, end):
                index = indices[position]
                word = words[index]
                if kind == "equal":
                    alternative = alternatives[position - start : position - start + 1]
                    words[index] = replace(word, alternatives=alternative)
                else:
                    text = " ".join(item.text for item in alternatives)
                    agreement = SequenceMatcher(None, word.text, text, autojunk=False).ratio()
                    words[index] = replace(
                        word,
                        confidence=round(word.confidence * agreement, 8),
                        raw_confidence=word.raw_confidence
                        if word.raw_confidence is not None
                        else word.confidence,
                        alternatives=alternatives
                        or (OcrAlternative(secondary.engine, "", 0.0, word.pixel_bbox),),
                    )
    return replace(
        primary,
        words=_line_confidences(words),
        unmatched_secondary=tuple(unmatched),
        warnings=(
            *primary.warnings,
            *secondary.warnings,
            "agreement-adjusted score is not a calibrated correctness probability",
        ),
    )
