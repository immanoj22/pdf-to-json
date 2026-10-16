"""Positioned symbols of an equation region: real characters (text path) and drawn glyphs
(drawn path), each with its box, baseline and size.

Text characters come from the rendered glyphs of the page's native text objects (character,
origin on the baseline, glyph box, span size, italic flag), matched one to one with the
span's characters; a span whose glyphs do not match keeps an even share of its box and the
span's own baseline. Drawn glyphs take the character recognised for their shape once per
book (``shapes``), a size from the shape's scale and a baseline from the shape's learned
descent; thin bars and filled rules are ``bar`` symbols whose role (fraction bar, overline,
radical vinculum, minus) the layout decides. A glyph with no recognised character is a
symbol with ``char=None``: the path then fails rather than guess.
"""

from dataclasses import dataclass, field

from book_core.equations import glyphs as glyph_rules

ITALIC = 2  # PyMuPDF span flag bit


@dataclass
class Symbol:
    id: str
    char: str | None
    kind: str  # "char" | "bar"
    box: tuple  # (x0, y0, x1, y1), y downwards
    baseline: float
    size: float
    source: str  # "text" | "drawn"
    italic: bool | None = None
    space_before: bool = False
    span: str | None = None  # text: the span id (characters of one span join words)
    notes: list = field(default_factory=list)
    origin: tuple | None = None  # text: a point on the baseline (the glyph origin)
    direction: tuple = (1.0, 0.0)  # text: the span's writing direction

    @property
    def width(self):
        return self.box[2] - self.box[0]

    @property
    def height(self):
        return self.box[3] - self.box[1]

    @property
    def cx(self):
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self):
        return (self.box[1] + self.box[3]) / 2


def _glyphs_of(native):
    found = {}
    for obj in native.objects:
        if obj.kind != "text" or len(obj.source_spans) != 1:
            continue
        found.setdefault(obj.source_spans[0], []).extend(
            g for info in obj.render_info for g in info.glyphs
        )
    return found


class TextSymbols:
    """Characters of span ranges on one page with their rendered glyph geometry."""

    def __init__(self, page, native):
        self.store = page.store
        self.geometry = native.span_geometry
        self.glyphs = _glyphs_of(native)

    def span_symbols(self, span_id, start, end):
        span = self.store.spans[span_id]
        text = span.raw_text
        start = 0 if start is None else start
        end = len(text) if end is None else end
        found = self.glyphs.get(span_id)
        matched = (
            found is not None
            and len(found) == len(text)
            and all(
                chr(g.unicode) == c and g.bbox is not None for g, c in zip(found, text, strict=True)
            )
        )
        frame = self.geometry.get(span_id)
        span_origin = tuple(frame.origin) if frame is not None else (span.bbox.x0, span.bbox.y1)
        direction = direction_of(self.geometry, span_id)
        size = span.size or (span.bbox.y1 - span.bbox.y0)
        italic = bool(span.flags & ITALIC)
        out = []
        width = (span.bbox.x1 - span.bbox.x0) / max(1, len(text))
        for offset in range(start, end):
            character = text[offset]
            if character.isspace():
                continue
            if matched:
                glyph = found[offset]
                box = (glyph.bbox.x0, glyph.bbox.y0, glyph.bbox.x1, glyph.bbox.y1)
                origin = tuple(glyph.origin)
                notes = []
            else:
                x0 = span.bbox.x0 + width * offset
                box = (x0, span.bbox.y0, x0 + width, span.bbox.y1)
                origin = span_origin
                notes = ["character box is an even share of its span"]
            out.append(
                Symbol(
                    id=f"{span_id}:{offset}",
                    char=character,
                    kind="char",
                    box=box,
                    baseline=origin[1],
                    size=size,
                    source="text",
                    italic=italic,
                    space_before=offset > 0 and text[offset - 1].isspace(),
                    span=span_id,
                    notes=notes,
                    origin=origin,
                    direction=direction,
                )
            )
        return out


def direction_of(geometry, span_id):
    frame = geometry.get(span_id)
    if frame is None:
        return (1.0, 0.0)
    dx, dy = frame.direction
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    return dx / length, dy / length


def to_line_frame(symbols):
    """Text symbols re-expressed in their line's own frame (x along the writing direction,
    y across it, downwards), so a rotated line is laid out like a horizontal one. The frame
    follows the PDF writing direction; no reading order is assumed."""
    if not symbols or all(s.direction == (1.0, 0.0) for s in symbols):
        return symbols
    dx, dy = symbols[0].direction

    def point(x, y):
        return x * dx + y * dy, -x * dy + y * dx

    out = []
    for s in symbols:
        corners = [point(x, y) for x in (s.box[0], s.box[2]) for y in (s.box[1], s.box[3])]
        us, vs = [c[0] for c in corners], [c[1] for c in corners]
        origin = point(*s.origin) if s.origin is not None else (min(us), max(vs))
        out.append(
            Symbol(
                id=s.id,
                char=s.char,
                kind=s.kind,
                box=(min(us), min(vs), max(us), max(vs)),
                baseline=origin[1],
                size=s.size,
                source=s.source,
                italic=s.italic,
                space_before=s.space_before,
                span=s.span,
                notes=list(s.notes),
                origin=origin,
                direction=(1.0, 0.0),
            )
        )
    return out


def drawn_symbol(obj, shapes, book_size):
    """Symbol of one drawn object of a region (glyph, part, dot or bar)."""
    box = (obj.bbox.x0, obj.bbox.y0, obj.bbox.x1, obj.bbox.y1)
    height = obj.bbox.y1 - obj.bbox.y0
    if is_rule(obj, book_size):
        return Symbol(obj.id, None, "bar", box, obj.bbox.y1, book_size, "drawn")
    signature = glyph_rules.shape_signature(obj)
    label = shapes.label(signature) if signature is not None else None
    if label is None:
        notes = ["drawn glyph has no recognised character"]
        return Symbol(obj.id, None, "char", box, obj.bbox.y1, book_size, "drawn", notes=notes)
    scale = shapes.scale(signature, height)
    size = scale * book_size
    baseline = obj.bbox.y1 - shapes.descent(signature) * size
    return Symbol(obj.id, label.char, "char", box, baseline, size, "drawn", italic=label.italic)


def is_rule(obj, size):
    """A bar: a thin stroked or filled line, or a filled rectangle outline."""
    return glyph_rules.is_bar(obj, size) or _rule(obj, size)


def _rule(obj, size):
    """A filled rectangle outline (a rule drawn as a path): wide, thin, straight edges only."""
    if obj.kind != "drawing" or obj.fill is None or not obj.path_items:
        return False
    height, width = obj.bbox.y1 - obj.bbox.y0, obj.bbox.x1 - obj.bbox.x0
    # One closed contour of straight edges (a rectangle), not two (an equals sign).
    items = obj.path_items
    straight = all(i.operator in ("l", "re") for i in items) and (
        len(items) <= 5 if items[0].operator == "l" else len(items) == 1
    )
    return straight and 0 < height <= glyph_rules.BAR_MAX_HEIGHT * 2 * size and width >= 2 * height
