"""Unclassified inline evidence carriers; no paragraph/furniture/layout inference."""

import json

from book_core.extraction.fingerprints import stable_id
from book_core.ledger.accounting import allocate
from book_core.ledger.records import WordLedger
from book_core.model.common import SpanRef, VisualStyle
from book_core.model.document import BodyMatter, Document, FrontMatter, Metadata, RearMatter
from book_core.model.nodes import InlineRun
from book_core.model.spans import ExtractedPage


def provision_page(page: ExtractedPage) -> tuple[Document, WordLedger]:
    """Keep native source line groups as provisional inline runs, never paragraphs."""
    nodes: list[InlineRun] = []
    store = page.store
    for line in store.lines:
        if not store.raw_line_text(line).strip():
            continue
        if not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        styles = {
            (
                store.spans[sid].font,
                store.spans[sid].size,
                store.spans[sid].color,
                store.spans[sid].flags,
            )
            for sid in line.span_ids
        }
        if len(styles) == 1:
            font, size, color, flags = styles.pop()
            style = VisualStyle(font=font, size=size, color=color, flags=flags)
        else:
            style = VisualStyle()
        scripts = {store.spans[sid].script for sid in line.span_ids}
        directions = {store.spans[sid].text_direction for sid in line.span_ids}
        languages = {store.spans[sid].language for sid in line.span_ids}
        nodes.append(
            InlineRun(
                id=stable_id(line.id, "unclassified_inline"),
                content=[SpanRef(span_id=sid) for sid in line.span_ids],
                source_page=line.page,
                bbox=line.bbox,
                source_spans=line.span_ids,
                style=style,
                script=next(iter(scripts)) if len(scripts) == 1 else None,
                text_direction=next(iter(directions)) if len(directions) == 1 else None,
                language=next(iter(languages)) if len(languages) == 1 else "und",
                provenance=store.spans[line.span_ids[0]].provenance,
            )
        )
    did = stable_id(
        page.source_sha256,
        json.dumps(page.extractor.model_dump(), sort_keys=True),
        page.geometry.page,
        "document",
    )
    document = Document(
        id=did,
        metadata=Metadata(
            source_sha256=page.source_sha256, extractor=page.extractor, pages=[page.geometry]
        ),
        front_matter=FrontMatter(id=stable_id(did, "front")),
        body_matter=BodyMatter(id=stable_id(did, "body"), children=nodes),
        rear_matter=RearMatter(id=stable_id(did, "rear")),
        span_store=store,
    )
    return document, allocate(document)
