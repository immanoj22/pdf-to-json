"""Neutral mathematical expression evidence, independent of output vocabularies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import CoreModel, SpanRef

MathKind = Literal[
    "symbol",
    "number",
    "operator",
    "sequence",
    "fraction",
    "root",
    "superscript",
    "subscript",
    "subsup",
    "matrix",
    "fenced",
    "unknown",
]


class MathTree(CoreModel):
    """Digital leaves reference source spans; recognized values are derived evidence.

    Child order is mathematical expression order supplied by a builder, never a
    global geometric sort. This representation does not build or convert equations.
    """

    kind: MathKind = "unknown"
    children: list[MathTree] = Field(default_factory=list)
    source_refs: list[SpanRef] = Field(default_factory=list)
    derived_value: str | None = None

    def iter_source_refs(self) -> Iterator[SpanRef]:
        yield from self.source_refs
        for child in self.children:
            yield from child.iter_source_refs()

    @model_validator(mode="after")
    def structure(self) -> MathTree:
        count = len(self.children)
        expected = {
            "fraction": {2},
            "root": {1, 2},
            "superscript": {2},
            "subscript": {2},
            "subsup": {3},
        }
        if self.kind in expected and count not in expected[self.kind]:
            raise ValueError("Math operation has an invalid number of operands")
        if self.kind in {"symbol", "number", "operator"} and count:
            raise ValueError("A mathematical leaf cannot have children")
        if self.derived_value is not None and not self.derived_value.strip():
            raise ValueError("Derived mathematical values cannot be blank")
        refs = [(row.span_id, row.start, row.end) for row in self.source_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Repeated math source reference")
        return self
