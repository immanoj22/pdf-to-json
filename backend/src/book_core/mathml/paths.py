"""The three recognition paths of an equation region.

- **text**: the region's real characters (span ranges) laid out from their glyph positions;
- **drawn**: the region's drawn objects, each glyph read through the book's shape table, laid
  out the same way; text parts of a mixed region enter as real characters (text path);
- **image**: the rendered region read by a formula recognizer (LaTeX), then converted to a
  tree through latex2mathml.

Every path returns a ``Reading`` (tree or None, LaTeX, problems); a path never guesses a
character it cannot read.
"""

import statistics
from collections import Counter
from dataclasses import dataclass, field

from book_core.mathml import layout, shapes
from book_core.mathml.latex import from_latex, latex
from book_core.mathml.symbols import drawn_symbol, to_line_frame
from book_core.mathml.tree import sourced, structure_ids

NO_EVIDENCE = "no evidence for this path"


@dataclass
class Reading:
    path: str
    tree: object = None
    latex: str | None = None
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    symbols: int = 0  # characters the path started from (characters and glyphs)
    complete: bool | None = None  # every character symbol used exactly once
    shapes: list = field(default_factory=list)  # drawn: signatures used
    recognizer: str | None = None

    @property
    def ok(self):
        return self.tree is not None and not self.problems


def _layout(path, symbols, used_shapes=()):
    chars = [s for s in symbols if s.kind == "char"]
    reading = Reading(path, symbols=sum(len(s.char or " ") for s in chars))
    reading.shapes = sorted(set(used_shapes))
    if not symbols:
        reading.problems.append(NO_EVIDENCE)
        return reading
    try:
        tree, notes = layout.build(symbols)
    except layout.Unknown as error:
        reading.problems.append(str(error))
        return reading
    reading.tree, reading.notes = tree, notes
    reading.latex = latex(tree)
    expected = Counter({s.id: len(s.char) for s in chars})
    bars = {s.id for s in symbols if s.kind == "bar"}
    used = Counter(i for _, i in sourced(tree) if i is not None and i not in bars)
    used.update(i for i in structure_ids(tree) if i not in bars)
    reading.complete = used == expected
    return reading


def text_path(region, text):
    """Reading of a region's characters (``text``: ``TextSymbols`` of its page)."""
    symbols = [
        s for ref in region.span_refs for s in text.span_symbols(ref.span_id, ref.start, ref.end)
    ]
    return _layout("text", to_line_frame(symbols))


def drawn_symbols(region, objects, table, book_size):
    """Symbols of a region's drawn objects with shape characters by position class."""
    first = []
    for oid in region.object_ids:
        obj = objects.get(oid)
        if obj is None or obj.bbox is None:
            continue
        first.append((obj, drawn_symbol(obj, table, book_size)))
    chars = [s for _, s in first if s.kind == "char" and s.char is not None]
    result = []
    for obj, symbol in first:
        signature = shapes.shape_of(obj) if symbol.kind == "char" else None
        if signature is not None and symbol.char is not None:
            place = position(symbol, chars)
            label = table.label(signature, place)
            if label is not None:
                symbol.char, symbol.italic = label.char, label.italic
        result.append((symbol, signature))
    return result


def position(symbol, chars):
    """Position class of a symbol against the baseline of the characters on its row."""
    row = [
        c.baseline
        for c in chars
        if c is not symbol
        and min(c.box[3], symbol.box[3]) > max(c.box[1], symbol.box[1]) - 0.5 * c.size
        and c.height >= symbol.height
    ]
    baseline = statistics.median(row) if row else symbol.baseline
    return shapes.position_class(baseline - (symbol.box[1] + symbol.box[3]) / 2, symbol.size)


def drawn_path(region, objects, text, table, book_size):
    """Reading of a region's drawn objects (and the real characters of a mixed region)."""
    pairs = drawn_symbols(region, objects, table, book_size)
    symbols = [s for s, _ in pairs]
    symbols += [
        s for ref in region.span_refs for s in text.span_symbols(ref.span_id, ref.start, ref.end)
    ]
    return _layout("drawn", symbols, [sig for _, sig in pairs if sig is not None])


def image_path(latex_source, recognizer, truncated=False):
    """Reading of a recognizer's LaTeX for the region image."""
    reading = Reading("image", latex=latex_source, recognizer=recognizer)
    if not latex_source or not latex_source.strip():
        reading.problems.append("the recognizer returned no reading")
        return reading
    if truncated:
        reading.problems.append("the recognizer reading was cut at its length limit")
    tree = from_latex(latex_source)
    if tree is None:
        reading.problems.append("the recognizer LaTeX could not be converted")
        return reading
    reading.tree = tree
    return reading
