"""Layout-model figure evidence for review flags (optional ``models`` extra).

The learned detectors (Heron, PP-DocLayoutV3) are evidence, never the decider: a figure they
do not support keeps its record, image, links and text, and only gains a review flag. Model
disagreement never drops a figure. Detections are cached per page by the detection stage.
"""

import importlib.util
import logging

from book_core.model.common import BBox

LOG = logging.getLogger("book_core.figures")
MODELS_MISSING = (
    "Layout-model extras (Torch, Transformers) are not installed: figure review flags are "
    "reduced (no 'model disagrees' flags). Install the models extra for full review evidence."
)

MODEL_DISAGREES = "layout models do not find a figure here (model disagrees); review"
MODELS = ("heron", "pp")


def supported(box: BBox, model_boxes: list[BBox]) -> bool:
    """A model figure supports ours when they overlap by at least half the smaller box."""

    def area(b):
        return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)

    for other in model_boxes:
        w = min(box.x1, other.x1) - max(box.x0, other.x0)
        h = min(box.y1, other.y1) - max(box.y0, other.y0)
        if w > 0 and h > 0 and w * h >= 0.5 * min(area(box), area(other)):
            return True
    return False


def disagrees(support: dict[str, bool], rule: str) -> bool:
    """Whether the configured rule reads the per-model support as disagreement."""
    if rule == "neither":  # no model finds the figure
        return not any(support.values())
    if rule == "not_both":  # at least one model does not find it
        return not all(support.values())
    return not support[rule]  # one named model does not find it


class DetectorFigures:
    """{model: [figure boxes]} of one page from the cached detectors (lazy, per page)."""

    def __init__(self, source, extractor, detectors, cache_dir):
        from book_core.detection.cache import detect_page

        self._detect = detect_page
        self.source, self.extractor, self.cache_dir = source, extractor, cache_dir
        self.detectors = dict(zip(MODELS, detectors, strict=True))

    @property
    def identity(self):
        return {
            name: f"{d.repo_id}@{d.revision}/threshold={d.threshold}"
            for name, d in self.detectors.items()
        }

    def __call__(self, number):
        return {
            name: [
                region.bbox
                for region in self._detect(
                    self.source, number, self.extractor, detector, self.cache_dir
                ).regions
                if region.type == "figure"
            ]
            for name, detector in self.detectors.items()
        }


def models_available() -> bool:
    """Whether the optional models extra (Torch and Transformers) is installed."""
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers"))


def resolve(settings, supplied=None):
    """(settings with model_evidence resolved to on/off, warning or None).

    "auto" turns the evidence on when the models extra is installed (or evidence is
    supplied) and otherwise warns: never a silent reduction of review flags.
    """
    if settings.model_evidence == "off":
        return settings, None
    available = supplied is not None or models_available()
    if not available and settings.model_evidence == "on":
        raise RuntimeError(MODELS_MISSING)
    if available:
        return settings.model_copy(update={"model_evidence": "on"}), None
    LOG.warning(MODELS_MISSING)
    return settings.model_copy(update={"model_evidence": "off"}), MODELS_MISSING
