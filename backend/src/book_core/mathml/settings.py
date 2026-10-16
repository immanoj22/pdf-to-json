"""Client-profile MathML settings (owner decisions of Steps 13a and 13b, recorded as options).

Kept apart from the job ``Settings`` so that earlier stage keys do not depend on them; they
enter only the MathML stage key.

- ``text_set_math`` (owner decisions 13a and 13c): ``"math_font"`` (default) outputs MathML
  for math set as real text only when it is set in a math font (font-program evidence);
  other text-set math stays text, keeps its PDF characters and is read by the text path only
  (its MathML is stored, not used); ``"text"`` keeps all text-set math as text;
  ``"mathml"`` outputs all of it as MathML. The image path reads text-set math only when its
  output will be MathML.
- ``mixed_expressions``: ``"whole"`` (default) outputs one MathML per expression (text parts
  as MathML tokens); ``"reference"`` keeps the text parts as text and outputs MathML only for
  the drawn parts.
- ``fallback_pattern`` / ``fallback_unlabelled_pattern``: equation image names for a
  low-confidence equation (``{label}`` page label, ``{n}`` the equation's position among the
  page's equation records, ``{index}`` physical PDF page).
- ``min_confidence``: below it an equation is ``must_check``, keeps its original text and
  objects and gets an image fallback.
- ``image_recognition``: the image path ("auto" uses it whenever the models extra is
  installed and warns when not; "on" requires it; "off" skips it).
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


class MathSettings(CoreModel):
    text_set_math: Literal["math_font", "text", "mathml"] = "math_font"
    mixed_expressions: Literal["whole", "reference"] = "whole"
    fallback_pattern: str = "page_{label}_eq_{n}"
    fallback_unlabelled_pattern: str = "page_pdf{index}_eq_{n}"
    fallback_dpi: Annotated[int, Field(ge=72, le=1200)] = 300
    recognition_dpi: Annotated[int, Field(ge=72, le=1200)] = 300
    min_confidence: Annotated[float, Field(ge=0, le=1)] = 0.7
    image_recognition: Literal["auto", "on", "off"] = "auto"

    @field_validator("fallback_pattern")
    @classmethod
    def labelled(cls, value):
        return _check(value, {"label", "n"})

    @field_validator("fallback_unlabelled_pattern")
    @classmethod
    def unlabelled(cls, value):
        return _check(value, {"index", "n"})


def text_output_is_mathml(region, settings):
    """Whether a text-set region is output as MathML (and so also read by the image path)."""
    if settings.text_set_math == "mathml":
        return True
    if settings.text_set_math == "text":
        return False
    signals = getattr(region, "signals", None) or {}
    return signals.get("math_font") is True or "math_font" in (getattr(region, "rules", ()) or ())


MODELS_MISSING = (
    "Formula recognition extras (Torch, Transformers, latex2mathml) are not installed: "
    "equations have no "
    "image reading and drawn glyphs no shape readings; drawn equations get image fallbacks "
    "for review. Install the models extra for full MathML."
)


def models_available():
    """Whether formula recognition can run: the models extra (Torch, Transformers) and the
    math-conversion extra (latex2mathml) are installed."""
    import importlib.util

    return all(
        importlib.util.find_spec(n) is not None for n in ("torch", "transformers", "latex2mathml")
    )


def resolve(settings, supplied=None):
    """(settings with image_recognition resolved to on/off, warning or None): "auto" turns
    recognition on when the models extra is installed (or a reader is supplied) and
    otherwise warns: never a silent loss of the image path."""
    import logging

    if settings.image_recognition == "off":
        return settings, None
    available = supplied is not None or models_available()
    if not available and settings.image_recognition == "on":
        raise RuntimeError(MODELS_MISSING)
    if available:
        return settings.model_copy(update={"image_recognition": "on"}), None
    logging.getLogger("book_core.mathml").warning(MODELS_MISSING)
    return settings.model_copy(update={"image_recognition": "off"}), MODELS_MISSING
