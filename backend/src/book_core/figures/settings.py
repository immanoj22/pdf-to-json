"""Client-profile figure settings: image naming, export resolution and alt-text drafts.

Kept apart from the job ``Settings`` so that earlier stage keys do not depend on them; they
enter only the figures stage key. Patterns use ``{label}`` (the page label made file-safe),
``{n}`` (the figure's 1-based reading position on its page) and ``{index}`` (the physical
PDF page); a format spec such as ``{n:03d}`` is allowed.
"""

import string
from typing import Annotated, Literal

from pydantic import Field, field_validator

from book_core.model.common import CoreModel

FIELDS = {"label", "n", "index"}


def _check(pattern, required):
    names = set()
    for _, name, _, conversion in string.Formatter().parse(pattern):
        if name is None:
            continue
        if name not in FIELDS or conversion:
            raise ValueError(f"Unknown naming field {name!r}; use {sorted(FIELDS)}")
        names.add(name)
    missing = required - names
    if missing:
        raise ValueError(f"A naming pattern needs {sorted(missing)}")
    return pattern


class FigureSettings(CoreModel):
    name_pattern: str = "page_{label}_{n}"
    unlabelled_pattern: str = "page_pdf{index}_{n}"
    export_dpi: Annotated[int, Field(ge=36, le=1200)] = 300
    jpeg_quality: Annotated[int, Field(ge=50, le=100)] = 92
    export_images: bool = True
    alt_text_drafts: bool = False  # optional SmolVLM drafts; off by default
    # Figures smaller than this share of the content area are marked small artwork (icons,
    # bullets, logos). Information for the adapter, which may skip them; never an error.
    small_figure_share: Annotated[float, Field(ge=0, le=1)] = 0.02
    # Layout-model figure evidence: figures the models do not support get a review flag;
    # nothing is dropped. "auto" uses the models whenever the models extra is installed and
    # warns clearly when it is not (review flags are then reduced); "on" requires them.
    model_evidence: Literal["auto", "on", "off"] = "auto"
    model_disagreement: Literal["neither", "not_both", "heron", "pp"] = "not_both"

    @field_validator("name_pattern")
    @classmethod
    def labelled(cls, value):
        return _check(value, {"label", "n"})

    @field_validator("unlabelled_pattern")
    @classmethod
    def unlabelled(cls, value):
        return _check(value, {"index", "n"})
