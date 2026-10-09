"""Extractor-neutral render output, in the same unrotated crop frame as object bounds."""

from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt

from book_core.model.common import CoreModel


class RasterPage(CoreModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, ser_json_bytes="base64", val_json_bytes="base64"
    )
    png: bytes
    width: PositiveInt
    height: PositiveInt
    page_width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    page_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
