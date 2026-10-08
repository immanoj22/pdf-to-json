"""Optional learned layout evidence, independent of extraction and text accounting."""

from book_core.detection.interfaces import RegionDetector
from book_core.detection.models import DetectionInput, DetectionResult, DetectorRegion
from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector

__all__ = [
    "DetectionInput",
    "DetectionResult",
    "DetectorRegion",
    "HeronDetector",
    "PPDocLayoutV3Detector",
    "RegionDetector",
]
