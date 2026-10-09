"""Schema independence, evidence references and JSON round trips."""

import pytest
from pydantic import TypeAdapter, ValidationError

from book_core.ingestion.provisional import provision_page
from book_core.model.common import BBox, ExternalDescription, Relationship
from book_core.model.document import Document
from book_core.model.nodes import (
    Callout,
    Caption,
    DefinitionList,
    Equation,
    Figure,
    Footnote,
    Heading,
    IndexEntry,
    InlineRun,
    ListItem,
    ListNode,
    Math,
    Node,
    Note,
    NoteRef,
    PageMarker,
    Paragraph,
    Quote,
    Reference,
    Sidebar,
    Table,
    TableCell,
)

CLASSES = [
    InlineRun,
    Heading,
    Paragraph,
    ListNode,
    ListItem,
    DefinitionList,
    Table,
    Figure,
    Caption,
    Sidebar,
    Callout,
    Quote,
    Equation,
    Math,
    Footnote,
    Note,
    NoteRef,
    Reference,
    IndexEntry,
    PageMarker,
]


@pytest.mark.parametrize("cls", CLASSES, ids=[cls.__name__ for cls in CLASSES])
def test_every_node_round_trip(cls, make_page):
    document, _ = provision_page(make_page())
    original = document.body_matter.children[0]
    data = original.model_dump(exclude={"type", "guessed_role", "role_confidence"})
    data["id"] = "subject"
    if cls is Heading:
        data["level"] = 2
    if cls is Figure:
        data["image_description"] = ExternalDescription()
    if cls is NoteRef:
        data["target_id"] = document.body_matter.id
    node = cls(**data)
    body = document.body_matter.model_copy(update={"children": [node]})
    document = Document.model_validate(
        {
            **document.model_dump(),
            "body_matter": body.model_dump(),
        }
    )
    assert Document.model_validate_json(document.model_dump_json()) == document
    adapter = TypeAdapter(Node)
    assert adapter.validate_json(adapter.dump_json(node)) == node


def test_nested_nodes_figure_text_and_relationships(make_page):
    document, _ = provision_page(make_page())
    text = document.body_matter.children[0]
    figure = Figure(id="figure", embedded_text=[text], image_description=ExternalDescription())
    caption = Caption(
        id="caption",
        relationships=[Relationship(kind="caption_of", target_id=figure.id)],
    )
    body = document.body_matter.model_copy(update={"children": [figure, caption]})
    document = Document.model_validate({**document.model_dump(), "body_matter": body.model_dump()})
    assert text.id in {node.id for node in document.iter_nodes()}
    assert Document.model_validate_json(document.model_dump_json()) == document
    assert Figure.model_json_schema()["$defs"]["Figure"]["properties"]["image_description"][
        "required_but_external"
    ]


def test_description_is_required_and_unresolved_needs_review():
    with pytest.raises(ValidationError):
        Figure(id="missing")
    with pytest.raises(ValidationError):
        ExternalDescription(review_required=False)
    assert ExternalDescription(text="External review.", review_required=False)


def test_model_rejects_dangling_refs_and_duplicate_ids(make_page):
    document, _ = provision_page(make_page())
    payload = document.model_dump()
    payload["body_matter"]["children"][0]["content"][0]["span_id"] = "absent"
    with pytest.raises(ValidationError):
        Document.model_validate(payload)
    payload = document.model_dump()
    payload["rear_matter"]["id"] = payload["body_matter"]["id"]
    with pytest.raises(ValidationError, match="unique"):
        Document.model_validate(payload)
    payload = document.model_dump()
    payload["body_matter"]["children"][0]["relationships"] = [
        {"kind": "refers_to", "target_id": "absent"},
    ]
    with pytest.raises(ValidationError, match="Dangling"):
        Document.model_validate(payload)


def test_geometry_style_and_table_constraints():
    with pytest.raises(ValidationError):
        BBox(x0=5, y0=0, x1=4, y1=1)
    with pytest.raises(ValidationError):
        Heading(id="x", level=0, confidence=1.2)
    with pytest.raises(ValidationError, match="Overlapping"):
        Table(id="x", cells=[TableCell(row=0, column=0), TableCell(row=0, column=0)])
