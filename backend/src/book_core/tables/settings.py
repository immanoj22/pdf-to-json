"""Client settings of the table stage (kept apart from the job settings; they enter only the
tables stage key).

``model_evidence``: the learned table detectors (Heron and PP-DocLayoutV3 table boxes,
Table Transformer detection) as one evidence family. "auto" uses them whenever the models
extra is installed and warns clearly when it is not (tables then need both geometric
families: rules and aligned text); "on" requires them; "off" never runs them.
"""

import importlib.util
import logging
from typing import Annotated, Literal

from pydantic import Field

from book_core.model.common import CoreModel

LOG = logging.getLogger("book_core.tables")
MODELS_MISSING = (
    "Table-model extras (Torch, Transformers, timm) are not installed: tables are detected "
    "from rules and aligned text only (no learned detector evidence). Install the models "
    "extra for full table evidence."
)


class TableSettings(CoreModel):
    model_evidence: Literal["auto", "on", "off"] = "auto"
    detection_dpi: Annotated[int, Field(ge=36, le=300)] = 100  # Table Transformer render


def models_available():
    return all(importlib.util.find_spec(n) is not None for n in ("torch", "transformers", "timm"))


def resolve(settings, supplied=None):
    """(settings with model_evidence on/off, warning or None)."""
    if settings.model_evidence == "off":
        return settings, None
    available = supplied is not None or models_available()
    if not available and settings.model_evidence == "on":
        raise RuntimeError(MODELS_MISSING)
    if available:
        return settings.model_copy(update={"model_evidence": "on"}), None
    LOG.warning(MODELS_MISSING)
    return settings.model_copy(update={"model_evidence": "off"}), MODELS_MISSING
