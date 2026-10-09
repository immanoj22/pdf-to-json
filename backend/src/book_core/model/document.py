"""Document matters, metadata and referential-integrity validation."""

from collections.abc import Iterator
from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import CoreModel, Digest, Identifier, SpanRef
from book_core.model.nodes import BaseNode, Figure, IndexEntry, Node, NoteRef, Table
from book_core.model.spans import ExtractorIdentity, PageGeometry, SpanStore


class Metadata(CoreModel):
    source_sha256: Digest
    extractor: ExtractorIdentity | None = None
    pages: list[PageGeometry] = Field(default_factory=list)
    title: list[SpanRef] = Field(default_factory=list)
    creators: list[list[SpanRef]] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["und"])


class Matter(BaseNode):
    """Structural matter container with the same evidence fields as every node."""


class FrontMatter(Matter):
    type: Literal["front_matter"] = "front_matter"


class BodyMatter(Matter):
    type: Literal["body_matter"] = "body_matter"


class RearMatter(Matter):
    type: Literal["rear_matter"] = "rear_matter"


def walk_nodes(nodes: list[Node]) -> Iterator[BaseNode]:
    for node in nodes:
        yield node
        yield from walk_nodes(node.children)
        if isinstance(node, Figure):
            yield from walk_nodes(node.embedded_text)


class Document(CoreModel):
    id: Identifier
    schema_version: Literal["1.0"] = "1.0"
    metadata: Metadata
    front_matter: FrontMatter
    body_matter: BodyMatter
    rear_matter: RearMatter
    span_store: SpanStore

    def iter_nodes(self) -> Iterator[BaseNode]:
        for matter in (self.front_matter, self.body_matter, self.rear_matter):
            yield matter
            yield from walk_nodes(matter.children)

    @model_validator(mode="after")
    def integrity(self) -> "Document":
        ids = [self.id]
        nodes = list(self.iter_nodes())
        ids.extend(node.id for node in nodes)
        if len(ids) != len(set(ids)):
            raise ValueError("Document/node identifiers must be unique")
        node_ids = {node.id for node in nodes}
        span_ids = set(self.span_store.spans)
        pages = {page.page for page in self.metadata.pages}
        if len(pages) != len(self.metadata.pages):
            raise ValueError("Duplicate source page geometry")
        for span in self.span_store.spans.values():
            if (
                span.page not in pages
                or span.provenance.source_sha256 != self.metadata.source_sha256
            ):
                raise ValueError("Store evidence does not match document source/pages")
        refs = [*self.metadata.title, *(r for creator in self.metadata.creators for r in creator)]
        for node in nodes:
            if node.source_page is not None and node.source_page not in pages:
                raise ValueError("Node source page has no geometry")
            refs.extend(node.content)
            if not set(node.source_spans).issubset(span_ids):
                raise ValueError("Unknown node source-span reference")
            targets = [rel.target_id for rel in node.relationships]
            if isinstance(node, NoteRef):
                targets.append(node.target_id)
            if isinstance(node, IndexEntry):
                targets.extend(node.target_ids)
            if isinstance(node, Table):
                targets.extend(target for cell in node.cells for target in cell.node_ids)
            if not set(targets).issubset(node_ids):
                raise ValueError("Dangling semantic relationship")
        if any(ref.span_id not in span_ids for ref in refs):
            raise ValueError("Unknown content span reference")
        if any(
            ref.end is not None and ref.end > len(self.span_store.spans[ref.span_id].raw_text)
            for ref in refs
        ):
            raise ValueError("Character range exceeds source span")
        return self
