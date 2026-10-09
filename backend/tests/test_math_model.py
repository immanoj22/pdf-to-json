"""Math metadata remains lossless, optional and independently reviewable."""

import pytest
from pydantic import TypeAdapter, ValidationError

from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.model.common import ExternalDescription, SpanRef
from book_core.model.document import Document
from book_core.model.math import MathTree
from book_core.model.nodes import Math, Node


def test_digital_math_round_trip_preserves_span_store_and_ledger(make_page):
    original, ledger = provision_page(make_page())
    native = original.body_matter.children[0]
    tree = MathTree(
        kind="fraction",
        children=[
            MathTree(kind="symbol", source_refs=[native.content[0]]),
            MathTree(kind="number", derived_value="2"),
        ],
    )
    math = Math(
        **native.model_dump(exclude={"type", "guessed_role", "role_confidence"}),
        source="digital",
        presentation="inline",
        math_tree=tree,
        latex=r"\frac{x}{2}",
        mathml='<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>x</mi><mn>2</mn></mfrac></math>',
    )
    payload = original.model_dump()
    payload["body_matter"]["children"] = [math.model_dump()]
    updated = Document.model_validate(payload)
    assert updated.span_store == original.span_store
    assert updated.metadata == original.metadata
    assert check(updated, ledger).passing
    assert Document.model_validate_json(updated.model_dump_json()) == updated
    assert TypeAdapter(Node).validate_json(math.model_dump_json()) == math


def test_image_math_retains_image_and_original_alt_text():
    node = Math(
        id="formula",
        source="image",
        presentation="display",
        fallback_image_asset="original-image-sha",
        alt_text=ExternalDescription(text="Original supplied description.", review_required=False),
        latex=r"x^2",
        mathml="<math><msup><mi>x</mi><mn>2</mn></msup></math>",
        confidence=0.91,
        review_required=False,
    )
    assert Math.model_validate_json(node.model_dump_json()) == node
    assert node.fallback_image_asset == "original-image-sha"
    assert node.alt_text.text == "Original supplied description."
    with pytest.raises(ValidationError, match="original image"):
        Math(id="lost", source="image")
    with pytest.raises(ValidationError, match="alt text"):
        Math(
            id="unknown-alt",
            source="image",
            presentation="display",
            fallback_image_asset="original",
            mathml="generated",
            confidence=0.9,
            review_required=False,
        )


def test_unresolved_math_stays_under_review():
    assert Math(id="legacy").review_required
    assert Math(id="legacy").math_tree is None
    with pytest.raises(ValidationError, match="under review"):
        Math(id="incomplete", review_required=False)
    with pytest.raises(ValidationError, match="confidence"):
        Math(
            id="no-confidence",
            source="digital",
            presentation="inline",
            mathml="generated",
            review_required=False,
        )
    with pytest.raises(ValidationError):
        Math(id="bad-score", confidence=float("nan"))


def test_tree_operands_and_source_provenance():
    with pytest.raises(ValidationError, match="operands"):
        MathTree(kind="fraction", children=[MathTree()])
    with pytest.raises(ValidationError, match="leaf"):
        MathTree(kind="symbol", children=[MathTree()])
    tree = MathTree(kind="symbol", source_refs=[SpanRef(span_id="missing")])
    with pytest.raises(ValidationError, match="source-span"):
        Math(id="dangling", math_tree=tree)


def test_nested_tree_ranges_are_document_validated(make_page):
    original, _ = provision_page(make_page())
    native = original.body_matter.children[0]
    sid = native.content[0].span_id
    tree = MathTree(
        kind="sequence",
        children=[
            MathTree(
                kind="symbol",
                source_refs=[
                    SpanRef(
                        span_id=sid, start=0, end=len(original.span_store.spans[sid].raw_text) + 1
                    )
                ],
            )
        ],
    )
    node = Math(id="math", source_spans=[sid], math_tree=tree)
    payload = original.model_dump()
    payload["body_matter"]["children"] = [node.model_dump()]
    with pytest.raises(ValidationError, match="range exceeds"):
        Document.model_validate(payload)


def test_non_latin_math_refs_round_trip_without_direction_assumption():
    tree = MathTree(kind="symbol", derived_value="α + 漢字")
    node = Math(
        id="multilingual",
        source="digital",
        presentation="inline",
        math_tree=tree,
        language="ar",
        script="Arab",
        text_direction="rtl",
    )
    assert Math.model_validate_json(node.model_dump_json()) == node
