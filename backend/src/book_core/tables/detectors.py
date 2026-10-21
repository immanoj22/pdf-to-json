"""Table boxes of the learned detectors for one page (cached detections, evidence only).

Heron and PP-DocLayoutV3 (their ``table`` labels, the same cached detections the figure
stage reads) and Table Transformer detection (``table`` and ``table rotated``). A model box
never decides a table: it is one evidence family (``tables.detect``).
"""

TABLE_LABELS = ("table",)  # raw labels starting with this word ("table", "table rotated")


class DetectorTables:
    """{model: [(bbox, score, raw label)]} of one page from the cached detectors."""

    def __init__(self, source, extractor, detectors, cache_dir, tatr_dpi):
        from book_core.detection.cache import detect_page

        self._detect = detect_page
        self.source, self.extractor, self.cache_dir = source, extractor, cache_dir
        self.detectors = dict(detectors)
        self.tatr_dpi = tatr_dpi

    @property
    def identity(self):
        return {
            name: f"{d.repo_id}@{d.revision}/threshold={d.threshold}"
            + (f"/dpi={self.tatr_dpi}" if name == "tatr" else "")
            for name, d in self.detectors.items()
        }

    def __call__(self, number):
        found = {}
        for name, detector in self.detectors.items():
            options = {"dpi": self.tatr_dpi} if name == "tatr" else {}
            result = self._detect(
                self.source, number, self.extractor, detector, self.cache_dir, **options
            )
            found[name] = [
                (region.bbox, region.confidence, region.raw_label)
                for region in result.regions
                if region.raw_label.lower().startswith(TABLE_LABELS)
            ]
        return found
