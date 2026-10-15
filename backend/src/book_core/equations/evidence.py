"""Layout-model formula boxes as equation evidence (optional ``models`` extra).

The learned detectors support or question a region; they never create or drop one. Their
formula vocabulary is model data (configuration), read from each detection's raw label.
Detections are cached per page by the detection stage.
"""

FORMULA_LABELS = ("formula", "display_formula", "inline_formula", "equation")
MODELS = ("heron", "pp")


def formula_label(raw_label: str) -> bool:
    return raw_label.casefold().replace("-", "_").replace(" ", "_") in FORMULA_LABELS


class DetectorFormulas:
    """{model: [(box, raw label)]} of one page's formula detections (lazy, cached)."""

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
                (region.bbox, region.raw_label)
                for region in self._detect(
                    self.source, number, self.extractor, detector, self.cache_dir
                ).regions
                if formula_label(region.raw_label)
            ]
            for name, detector in self.detectors.items()
        }
