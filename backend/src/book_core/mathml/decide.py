"""Combining the paths of one equation: agreement, confidence, review status and output.

The position path (text, or drawn with text parts) is the primary reading: its characters
come from the PDF's own evidence. The image path is an independent reading of the rendered
region. Exact agreement (after the comparison folding of ``checks.fold``) gives high
confidence; disagreement lowers confidence by the trees' edit distance and is flagged. A
single path keeps a middling confidence; an image reading alone is never above the review
threshold. Failed checks lower confidence further. Confidence is a rule heuristic, not a
calibrated probability.
"""

from book_core.mathml.checks import check, fold
from book_core.mathml.distance import tree_distance
from book_core.mathml.latex import latex
from book_core.mathml.models import EquationMath, PathReading
from book_core.mathml.settings import text_output_is_mathml
from book_core.mathml.tree import canonical, size, sourced

AGREE = 0.95
DISAGREE_BASE, DISAGREE_SPAN = 0.45, 0.35
TEXT_ALONE = 0.75
DRAWN_ALONE = 0.7
IMAGE_ALONE = 0.5
SHAPE_DOUBT = 0.8  # drawn shapes below this label confidence cap a disagreeing reading
PENALTY = {"symbols": 0.2, "brackets": 0.1, "numeric": 0.15, "extent": 0.1, "mathml": 1.0}
CONFIG = {
    "agree": AGREE,
    "disagree_base": DISAGREE_BASE,
    "disagree_span": DISAGREE_SPAN,
    "text_alone": TEXT_ALONE,
    "drawn_alone": DRAWN_ALONE,
    "image_alone": IMAGE_ALONE,
    "shape_doubt": SHAPE_DOUBT,
    "penalty": PENALTY,
}
PATHS_DISAGREE = "position and image readings disagree"
IMAGE_ONLY = "only the image reading is available: unchecked against the PDF evidence"
NO_READING = "no path produced a valid reading"
DOUBTFUL_SHAPES = "drawn glyphs with uncertain characters"


def _fold_char(c):
    return "".join(fold(c))


def _trimmed(node):
    """A comparison row without sentence punctuation at either end: a region crop can take
    in the full stop or comma set right after the expression."""
    import unicodedata

    from book_core.mathml.tree import row

    items = list(node.children) if node.kind == "row" else [node]
    while items and items[-1].kind == "operator" and unicodedata.category(items[-1].text) == "Po":
        items.pop()
    while items and items[0].kind == "operator" and unicodedata.category(items[0].text) == "Po":
        items.pop(0)
    return row(items) if items else node


def compare(a, b):
    """(equal, similarity) of two trees in comparison form."""
    ca, cb = canonical(a, fold), canonical(b, fold)
    if ca == cb or _trimmed(ca) == _trimmed(cb):
        return True, 1.0
    distance = tree_distance(ca, cb)
    return False, max(0.0, 1.0 - distance / max(size(ca), size(cb)))


def _record(reading, checks):
    return PathReading(
        path=reading.path,
        recognizer=reading.recognizer,
        latex=reading.latex
        if reading.latex is not None
        else (latex(reading.tree) if reading.tree is not None else None),
        # Markup that fails validation is not recorded as MathML (its problems are).
        mathml=checks["mathml"] if checks and checks["mathml3"] else None,
        problems=list(reading.problems) + (checks["problems"] if checks else []),
        notes=list(reading.notes),
        characters=checks["symbols_found"] if checks else None,
        checks={k: v for k, v in (checks or {}).items() if k not in {"mathml", "problems"}},
    )


def decide(region, position, image, settings, shape_confidence=None):
    """EquationMath for a region from its position reading and image reading (either None)."""
    display = region.presentation == "display"
    flags = []
    position_checks = image_checks = None
    expected = position.symbols if position is not None and position.symbols else None
    if position is not None and position.tree is not None:
        position_checks = check(position.tree, position.symbols, display)
        # Bars become characters (minus, overline) or none (fraction bars): the exact test
        # is that every character symbol is used exactly once.
        position_checks["symbols_match"] = position.complete
        expected = position_checks["symbols_found"]
    if image is not None and image.tree is not None:
        image_checks = check(image.tree, expected, display)
    position_ok = bool(position and position.ok and position_checks and position_checks["mathml3"])
    image_ok = bool(image and image.ok and image_checks and image_checks["mathml3"])
    similarity = None
    if position_ok and image_ok:
        same, similarity = compare(position.tree, image.tree)
        if same:
            agreement, confidence = "agree", AGREE
        else:
            agreement = "disagree"
            confidence = DISAGREE_BASE + DISAGREE_SPAN * similarity
            flags.append(PATHS_DISAGREE)
            if shape_confidence is not None and shape_confidence < SHAPE_DOUBT:
                confidence = min(confidence, shape_confidence)
                flags.append(DOUBTFUL_SHAPES)
        chosen, chosen_checks = position, position_checks
    elif position_ok:
        agreement = "single"
        confidence = TEXT_ALONE if position.path == "text" else DRAWN_ALONE
        if shape_confidence is not None:
            confidence = min(confidence, shape_confidence)
        chosen, chosen_checks = position, position_checks
    elif image_ok:
        agreement, confidence = "single", IMAGE_ALONE
        flags.append(IMAGE_ONLY)
        chosen, chosen_checks = image, image_checks
    else:
        agreement, confidence, chosen, chosen_checks = "none", 0.0, None, None
        flags.append(NO_READING)
    if chosen_checks is not None:
        if chosen_checks["symbols_match"] is False:
            confidence -= PENALTY["symbols"]
            flags.append("character count differs from the region's evidence")
        if not chosen_checks["brackets_balanced"]:
            confidence -= PENALTY["brackets"]
            flags.append("brackets do not balance")
        if chosen_checks["numeric"] == "inconsistent":
            confidence -= PENALTY["numeric"]
            flags.append("the written arithmetic does not hold: a character may be misread")
    if chosen is position and position is not None:
        from book_core.mathml.layout import NO_VINCULUM

        if NO_VINCULUM in position.notes:
            confidence -= PENALTY["extent"]
            flags.append(NO_VINCULUM)
    confidence = round(min(1.0, max(0.0, confidence)), 4)
    if confidence < settings.min_confidence or chosen is None:
        review = "must_check"
    elif (
        agreement == "agree"
        and chosen_checks["symbols_match"] is not False
        and chosen_checks["brackets_balanced"]
    ):
        review = "paths_agree"
    else:
        review = "needs_review"
    if region.source == "text":
        mathml = text_output_is_mathml(region, settings)
        output = "mathml" if mathml and review != "must_check" else "text"
    elif review == "must_check":
        output = "image"
    else:
        output = "mathml"
    readings = [
        _record(r, c)
        for r, c in ((position, position_checks), (image, image_checks))
        if r is not None
    ]
    sources = []
    if chosen is not None and chosen is position:
        sources = [i for _, i in sourced(chosen.tree)]
    return EquationMath(
        equation_id=region.id,
        page=region.page,
        source=region.source,
        presentation=region.presentation,
        mathml=chosen_checks["mathml"] if chosen is not None else None,
        latex=(chosen.latex or latex(chosen.tree)) if chosen is not None else None,
        path=chosen.path if chosen is not None else None,
        readings=readings,
        agreement=agreement,
        similarity=None if similarity is None else round(similarity, 4),
        confidence=confidence,
        review_status=review,
        output=output,
        sources=sources,
        flags=sorted(set(flags)),
    )
