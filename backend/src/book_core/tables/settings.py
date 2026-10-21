"""Client settings of the table stage (kept apart from the job settings; they enter only the
tables stage key).

``model_evidence``: the learned table detectors (Heron and PP-DocLayoutV3 table boxes,
Table Transformer detection) as one evidence family. "auto" uses them whenever the models
extra is installed and warns clearly when it is not (tables then need both geometric
families: rules and aligned text); "on" requires them; "off" never runs them.

``structure_reader``: TableFormer (accuracy-models extra) as a second reader of tables that
own their text: header rows where our grid found none, and a review flag where the two
structures disagree (measured in Step 14b). "auto" uses it whenever it is installed and the
learned detectors run, and warns when it is missing; "on" requires it; "off" never runs it.
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


READER_MISSING = (
    "TableFormer (accuracy-models extra) is not installed: tables without header evidence keep "
    "no header rows and no second-opinion review flags are set. Install the accuracy-models "
    "extra for them."
)


class TableSettings(CoreModel):
    model_evidence: Literal["auto", "on", "off"] = "auto"
    detection_dpi: Annotated[int, Field(ge=36, le=300)] = 100  # Table Transformer render
    structure_reader: Literal["auto", "on", "off"] = "auto"


def reader_available():
    return models_available() and importlib.util.find_spec("docling_ibm_models") is not None


def models_available():
    return all(importlib.util.find_spec(n) is not None for n in ("torch", "transformers", "timm"))


def resolve_reader(settings, supplied=None):
    """(settings with structure_reader on/off, warning or None). The reader runs only with
    the learned detectors (``model_evidence`` resolved on)."""
    if settings.structure_reader == "off" or settings.model_evidence != "on":
        if settings.structure_reader == "on":
            raise RuntimeError("The table structure reader needs model evidence on")
        return settings.model_copy(update={"structure_reader": "off"}), None
    available = supplied is not None or reader_available()
    if not available and settings.structure_reader == "on":
        raise RuntimeError(READER_MISSING)
    if available:
        return settings.model_copy(update={"structure_reader": "on"}), None
    LOG.warning(READER_MISSING)
    return settings.model_copy(update={"structure_reader": "off"}), READER_MISSING


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
