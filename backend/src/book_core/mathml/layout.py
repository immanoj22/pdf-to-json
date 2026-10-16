"""Expression structure from symbol positions (text and drawn paths).

All tests are relative to the symbols' own sizes and baselines; no font, page or book is
named. Characters are identified only where structure depends on them, by Unicode property:
general categories (operators, brackets, letters, digits) and the character names of the
radical sign and the prime.

1. **Bars** drawn in pieces (touching end to end on one band) merge into one rule.
2. **Radicals**: a radical sign with a bar starting at its top covers the symbols under that
   bar; a wide radical outline covers the symbols inside it; otherwise its extent is unknown
   (flagged) and the sign stays an operator.
3. **Fractions**: a bar with symbols stacked directly above and below it, inside its extent
   (widest bar first; numerator and denominator are built recursively).
4. **Overlines, accents, limits**: a bar right above symbols with nothing over it is an
   overline; a small symbol centred right above one symbol is an accent; symbols centred
   above or below an operator taller than a line, or smaller symbols centred above or below
   an operator, are its limits.
5. **Rows**: distinct baselines of the full-size symbols are rows of a table; within a row,
   symbols are read along the baseline (one expression's own local order, never a page sort).
6. **Atoms**: adjacent digits (with a decimal or group mark between digits) form a number;
   adjacent upright letters of one word form a multi-letter identifier.
7. **Scripts** (``_script``): smaller symbols raised or lowered against the base's baseline
   and axis; a script on a closing bracket belongs to the bracketed group; a bar high above
   the base opens an exponent.

A bar that is none of the above is a minus sign. A symbol with no character fails the path
(``Unknown``): nothing is guessed.
"""

import unicodedata
from dataclasses import dataclass

from book_core.equations.text import SCRIPT_SIZE_RATIO
from book_core.mathml.tree import Node, row, token

AXIS = 0.25  # math axis above the baseline, in sizes
STACK_REACH = 0.9  # bar to the nearest numerator/denominator symbol, in sizes
STACK_TOUCH = 0.45  # further rows of a numerator or denominator join within this gap
EXTENT_SLACK = 0.15  # a stacked symbol may overhang the bar by this share of a size
OVERLINE_REACH = 0.45
ACCENT_HEIGHT = 0.6  # an accent is at most this share of its base's height
ACCENT_REACH = 0.35
ROW_GAP = 0.9  # baselines further apart than this many sizes are rows of a table
NUMBER_GAP = 0.3  # horizontal gap inside a number or word
SCRIPT_REACH = 0.6  # a script starts within this gap after its base
SCRIPT_SIZE = 0.9  # a script is at most this share of its base's size
LARGE_OPERATOR = 1.2  # an operator taller than this many sizes takes limits
VINCULUM_REACH = 0.35
BAR_JOIN = 0.05  # bar pieces closer than this (in sizes) along their band are one rule
CENTRE_SHIFT = 0.12  # a script centre lies this far (sizes) above/below the base's axis
SUP_RISE = 0.2  # a superscript's bottom above the base's baseline, in sizes
SUB_DROP = 0.08  # a subscript's bottom below the base's baseline, in sizes
BAR_RISE = 0.55  # a bar this high above the base's baseline (sizes) opens a superscript
UNKNOWN = "a symbol has no recognised character"
NO_VINCULUM = "radical sign without a bar over its argument; its extent is unknown"
MINUS = "a bar that is no fraction bar, overline or radical bar is read as a minus sign"
CONFIG = {
    "axis": AXIS,
    "stack_reach": STACK_REACH,
    "stack_touch": STACK_TOUCH,
    "extent_slack": EXTENT_SLACK,
    "overline_reach": OVERLINE_REACH,
    "accent_height": ACCENT_HEIGHT,
    "accent_reach": ACCENT_REACH,
    "row_gap": ROW_GAP,
    "number_gap": NUMBER_GAP,
    "script_reach": SCRIPT_REACH,
    "large_operator": LARGE_OPERATOR,
    "vinculum_reach": VINCULUM_REACH,
    "bar_join": BAR_JOIN,
    "centre_shift": CENTRE_SHIFT,
    "sup_rise": SUP_RISE,
    "sub_drop": SUB_DROP,
    "bar_rise": BAR_RISE,
    "script_size": SCRIPT_SIZE,
    "row_size_ratio": SCRIPT_SIZE_RATIO,
}


@dataclass
class Item:
    box: tuple
    baseline: float
    size: float
    ids: tuple
    kind: str  # "char" | "bar" | "atom"
    node: Node | None = None
    char: str | None = None
    italic: bool | None = None
    span: str | None = None
    space_before: bool = False
    axis_at: float | None = None

    @property
    def axis(self):
        return self.axis_at if self.axis_at is not None else self.baseline - AXIS * self.size

    @property
    def cx(self):
        return (self.box[0] + self.box[2]) / 2

    @property
    def width(self):
        return self.box[2] - self.box[0]

    @property
    def height(self):
        return self.box[3] - self.box[1]


class Unknown(Exception):
    """A symbol without a recognised character: the path gives no reading."""


def _union(boxes):
    boxes = list(boxes)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _category(char):
    """General category of a one-character symbol ("" for none or several characters)."""
    return unicodedata.category(char) if char and len(char) == 1 else ""


def _name(char):
    return unicodedata.name(char, "") if char and len(char) == 1 else ""


def _is_radical(item):
    return item.kind == "char" and _name(item.char).endswith("SQUARE ROOT")


def from_symbols(symbols):
    return [
        Item(
            box=s.box,
            baseline=s.baseline,
            size=s.size,
            ids=(s.id,),
            kind=s.kind,
            char=s.char,
            italic=s.italic,
            span=s.span,
            space_before=s.space_before,
        )
        for s in symbols
    ]


def build(symbols):
    """(tree, notes) for positioned symbols; raises ``Unknown`` for an unrecognised glyph."""
    if any(s.kind == "char" and s.char is None for s in symbols):
        raise Unknown(UNKNOWN)
    notes = []
    tree = _build(from_symbols(symbols), notes)
    return tree, sorted(set(notes))


def _build(items, notes):
    if not items:
        return Node("row")
    items = _merge_bars(items)
    items = _radicals(items, notes)
    items = _fractions(items, notes)
    items = _overlines(items, notes)
    items = _stacks(items, notes)
    bands = _bands(items)
    if len(bands) > 1:
        return Node(
            "table",
            children=tuple(
                Node("table_row", children=(Node("table_cell", children=(_line(b, notes),)),))
                for b in bands
            ),
        )
    return _line(items, notes)


def _merge_bars(items):
    """Bars drawn in pieces (touching end to end on one band) are one rule."""
    bars = sorted((i for i in items if i.kind == "bar"), key=lambda b: (b.box[1], b.box[0]))
    if len(bars) < 2:
        return items
    merged, used = [], set()
    for index, bar in enumerate(bars):
        if id(bar) in used:
            continue
        box, ids = list(bar.box), list(bar.ids)
        for other in bars[index + 1 :]:
            if id(other) in used:
                continue
            thickness = max(box[3] - box[1], other.box[3] - other.box[1])
            same_band = (
                abs(other.box[1] - box[1]) <= thickness and abs(other.box[3] - box[3]) <= thickness
            )
            touching = other.box[0] <= box[2] + BAR_JOIN * bar.size and other.box[2] >= box[0]
            if same_band and touching:
                box = [min(box[0], other.box[0]), min(box[1], other.box[1]),
                       max(box[2], other.box[2]), max(box[3], other.box[3])]  # fmt: skip
                ids += other.ids
                used.add(id(other))
        merged.append(Item(tuple(box), bar.baseline, bar.size, tuple(ids), "bar"))
    return [i for i in items if i.kind != "bar"] + merged


def _ref_size(items):
    sizes = [i.size for i in items if i.kind != "bar"]
    return max(sizes) if sizes else items[0].size


def _within(item, x0, x1, slack):
    overlap = min(item.box[2], x1) - max(item.box[0], x0)
    return x0 - slack <= item.cx <= x1 + slack and overlap >= 0.5 * max(item.width, 1e-6)


def _stack(bar, pool, up):
    """Symbols stacked right above (``up``) or below a bar inside its extent."""
    candidates = [
        i
        for i in pool
        if _within(i, bar.box[0], bar.box[2], EXTENT_SLACK * i.size)
        and (i.box[3] <= bar.box[1] + 0.2 * i.size if up else i.box[1] >= bar.box[3] - 0.2 * i.size)
    ]
    if not candidates:
        return []

    def gap(i, edge):
        return edge - i.box[3] if up else i.box[1] - edge

    edge = bar.box[1] if up else bar.box[3]
    chosen = [i for i in candidates if gap(i, edge) <= STACK_REACH * i.size]
    if not chosen:
        return []
    rest = [i for i in candidates if i not in chosen]
    grew = True
    while grew and rest:
        grew = False
        top = min(i.box[1] for i in chosen) if up else max(i.box[3] for i in chosen)
        for i in list(rest):
            if gap(i, top) <= STACK_TOUCH * i.size:
                chosen.append(i)
                rest.remove(i)
                grew = True
    return chosen


def _composite(node, members, extra=(), axis_at=None, size=None):
    boxes = [m.box for m in members] + [e.box for e in extra]
    ids = tuple(i for m in (*members, *extra) for i in m.ids)
    sizes = [m.size for m in members if m.kind != "bar"]
    size = size or (max(sizes) if sizes else members[0].size)
    box = _union(boxes)
    baseline = (axis_at + AXIS * size) if axis_at is not None else max(m.baseline for m in members)
    return Item(box, baseline, size, ids, "atom", node=node, axis_at=axis_at)


def _fractions(items, notes):
    result = list(items)
    for bar in sorted(
        (i for i in items if i.kind == "bar"), key=lambda b: (-b.width, b.box[1], b.box[0])
    ):
        if bar not in result:
            continue
        pool = [i for i in result if i is not bar]
        above = _stack(bar, pool, up=True)
        below = _stack(bar, pool, up=False)
        if not above or not below:
            continue
        numerator = _build(above, notes)
        denominator = _build(below, notes)
        node = Node("fraction", children=(numerator, denominator))
        axis = (bar.box[1] + bar.box[3]) / 2
        members = [*above, *below]
        result = [i for i in result if i is not bar and i not in members]
        result.append(_composite(node, members, (bar,), axis_at=axis))
    return result


def _radicals(items, notes):
    result = list(items)
    for sign in sorted((i for i in items if _is_radical(i)), key=lambda i: -i.width):
        if sign not in result:
            continue
        reach = VINCULUM_REACH * sign.size
        bars = [
            b
            for b in result
            if b.kind == "bar"
            and sign.box[0] + 0.3 * sign.width <= b.box[0] <= sign.box[2] + reach
            and abs(b.box[1] - sign.box[1]) <= reach
        ]
        if bars:
            bar = min(bars, key=lambda b: abs(b.box[1] - sign.box[1]))
            x0, x1, top = bar.box[0], bar.box[2], bar.box[3]
            extra = (sign, bar)
        elif sign.width > 1.5 * sign.size:
            x0, x1, top = sign.box[0] + 0.5 * sign.size, sign.box[2], sign.box[1]
            extra = (sign,)
        else:
            notes.append(NO_VINCULUM)
            continue
        content = [
            i
            for i in result
            if i not in extra
            and x0 - 0.1 * i.size <= i.cx <= x1
            and i.box[1] >= top - 0.2 * i.size
            and i.box[3] <= sign.box[3] + 0.3 * i.size
        ]
        if not content:
            continue
        node = Node("radical", children=(_build(content, notes),), ids=sign.ids)
        result = [i for i in result if i not in extra and i not in content]
        result.append(_composite(node, content, extra, size=max(c.size for c in content)))
    return result


def _overlines(items, notes):
    result = list(items)
    for bar in sorted((i for i in items if i.kind == "bar"), key=lambda b: -b.width):
        if bar not in result:
            continue
        pool = [i for i in result if i is not bar]
        below = [
            i
            for i in pool
            if _within(i, bar.box[0], bar.box[2], EXTENT_SLACK * i.size)
            and 0 - 0.2 * i.size <= i.box[1] - bar.box[3] <= OVERLINE_REACH * i.size
        ]
        if not below:
            continue
        extent = _union(i.box for i in below)
        if bar.width > 1.6 * (extent[2] - extent[0]) + 0.3 * below[0].size:
            continue
        above = [
            i
            for i in pool
            if _within(i, bar.box[0], bar.box[2], 0)
            and 0 <= bar.box[1] - i.box[3] <= STACK_REACH * i.size
        ]
        if above:
            continue
        node = Node("over", children=(_build(below, notes), token("¯", bar.ids)), accent=True)
        result = [i for i in result if i is not bar and i not in below]
        composite = _composite(node, below, (bar,))
        composite.baseline = max(i.baseline for i in below)
        result.append(composite)
    return result


def _stacks(items, notes):
    """Accents over one symbol and limits above/below a large operator."""
    result = list(items)
    for base in sorted((i for i in items if i.kind in ("char", "atom")), key=lambda i: -i.height):
        if base not in result:
            continue
        pool = [i for i in result if i is not base and i.kind != "bar"]
        over = [
            i
            for i in pool
            if base.box[0] <= i.cx <= base.box[2]
            and 0 <= base.box[1] - i.box[3] + 0.15 * i.size
            and i.box[3] <= base.box[1] + 0.3 * base.height
        ]
        under = [
            i
            for i in pool
            if base.box[0] <= i.cx <= base.box[2] and i.box[1] >= base.box[3] - 0.15 * i.size
        ]
        over = [i for i in over if base.box[1] - i.box[3] <= STACK_REACH * i.size]
        under = [i for i in under if i.box[1] - base.box[3] <= STACK_REACH * i.size]
        # Limits: an operator taller than a line, or smaller symbols centred right above or
        # below an operator (limits set under a text-size operator).
        smaller = all(i.size <= SCRIPT_SIZE * base.size for i in (*over, *under))
        large = (
            base.kind == "char"
            and _category(base.char) == "Sm"
            and (base.height >= LARGE_OPERATOR * base.size or ((over or under) and smaller))
        )
        if large and (over or under):
            over = _extend_band(over, pool)
            under = _extend_band(under, [i for i in pool if i not in over])
            node_base = token(base.char, base.ids)
            if over and under:
                node = Node(
                    "underover", children=(node_base, _build(under, notes), _build(over, notes))
                )
            elif over:
                node = Node("over", children=(node_base, _build(over, notes)))
            else:
                node = Node("under", children=(node_base, _build(under, notes)))
            members = [base, *over, *under]
            result = [i for i in result if i not in members]
            composite = _composite(node, [base], [*over, *under])
            composite.baseline, composite.size = base.baseline, base.size
            result.append(composite)
            continue
        accents = [
            i
            for i in over
            if i.height <= ACCENT_HEIGHT * base.height
            and base.box[1] - i.box[3] <= ACCENT_REACH * base.size
            and _within(i, base.box[0], base.box[2], 0)
        ]
        if len(accents) == 1 and base.kind == "char" and accents[0].kind == "char":
            accent = accents[0]
            node = Node(
                "over",
                children=(token(base.char, base.ids), token(accent.char, accent.ids)),
                accent=True,
            )
            result = [i for i in result if i is not base and i is not accent]
            composite = _composite(node, [base], [accent])
            composite.baseline, composite.size = base.baseline, base.size
            result.append(composite)
    return result


def _extend_band(seed, pool):
    """Seed symbols plus the symbols continuing them along their band (a limit such as
    ``(i·j)`` reaches beyond its operator's width)."""
    if not seed:
        return seed
    chosen = list(seed)
    grew = True
    while grew:
        grew = False
        top = min(i.box[1] for i in chosen)
        bottom = max(i.box[3] for i in chosen)
        for item in pool:
            if item in chosen:
                continue
            overlap = min(bottom, item.box[3]) - max(top, item.box[1])
            near = min(
                min(abs(item.box[0] - c.box[2]), abs(c.box[0] - item.box[2])) for c in chosen
            )
            if overlap >= 0.5 * min(item.height, bottom - top) and near <= NUMBER_GAP * item.size:
                chosen.append(item)
                grew = True
    return chosen


def _bands(items):
    """Rows of a multi-row expression, top to bottom.

    Rows are the distinct baselines of the full-size symbols and structures (scripts and
    script-size fractions ride on their row); baselines further apart than ``ROW_GAP``
    line heights start a new row. Every symbol joins the row whose baseline is nearest.
    A single baseline is a single row."""
    sized = [i for i in items if i.kind != "bar"]
    if not sized:
        return [items]
    largest = max(i.size for i in sized)
    main = sorted(
        (i for i in sized if i.size >= SCRIPT_SIZE_RATIO * largest), key=lambda i: i.baseline
    )
    rows = [[main[0].baseline]]
    for item in main[1:]:
        if item.baseline - rows[-1][-1] > ROW_GAP * largest:
            rows.append([item.baseline])
        else:
            rows[-1].append(item.baseline)
    if len(rows) == 1:
        return [items]
    levels = [sum(r) / len(r) for r in rows]
    bands = [[] for _ in levels]
    for item in items:
        nearest = min(range(len(levels)), key=lambda k: abs(item.baseline - levels[k]))
        bands[nearest].append(item)
    return [b for b in bands if b]


def _joins_number(a, b):
    """``b`` continues the number or word ending with ``a`` (same size, same baseline, no
    gap; a decimal or group mark only between digits or before a leading digit)."""
    if a.kind != "char" or b.kind != "char" or b.space_before:
        return False
    size = max(a.size, b.size)
    if b.box[0] - a.box[2] > NUMBER_GAP * size or abs(a.baseline - b.baseline) > 0.1 * size:
        return False
    if abs(a.size - b.size) > 0.1 * size:
        return False
    return True


def _atoms(items):
    """Numbers and multi-letter upright words as single atoms, in reading order."""
    out, index = [], 0
    while index < len(items):
        item = items[index]
        cat = _category(item.char)
        if item.kind == "char" and (cat == "Nd" or (cat == "Po" and _digit_after(items, index))):
            run = [item]
            j = index + 1
            while j < len(items) and _joins_number(items[j - 1], items[j]):
                c = _category(items[j].char)
                if c == "Nd" or (c == "Po" and _digit_after(items, j) and run[-1].char.isdigit()):
                    run.append(items[j])
                    j += 1
                else:
                    break
            if len(run) > 1 or cat == "Nd":
                out.append(_atom(run, "number"))
                index = j
                continue
        if item.kind == "char" and cat[:1] == "L" and item.italic is False:
            run = [item]
            j = index + 1
            while (
                j < len(items)
                and _category(items[j].char)[:1] == "L"
                and items[j].italic is False
                and items[j].span == item.span
                and _joins_number(items[j - 1], items[j])
            ):
                run.append(items[j])
                j += 1
            if len(run) > 1:
                out.append(_atom(run, "identifier"))
                index = j
                continue
        out.append(item)
        index += 1
    return out


def _digit_after(items, index):
    return (
        index + 1 < len(items)
        and items[index + 1].kind == "char"
        and _category(items[index + 1].char) == "Nd"
        and _joins_number(items[index], items[index + 1])
    )


def _atom(run, kind):
    node = Node(kind, "".join(i.char for i in run), ids=tuple(i.ids[0] for i in run))
    item = _composite(node, run)
    item.baseline = sum(i.baseline for i in run) / len(run)
    item.size = max(i.size for i in run)
    return item


def _node(item, notes):
    if item.node is not None:
        return item.node
    if item.kind == "bar":
        notes.append(MINUS)
        return token("−", item.ids)
    return token(item.char, item.ids)


def _can_carry(item):
    """Scripts attach to operands, closing brackets and structures, not to relations."""
    if item.kind == "atom":
        return True
    if item.kind != "char":
        return False
    cat = _category(item.char)
    # Letters, digits and closing brackets; a prime (a raised mark) carries too.
    return cat[:1] in ("L", "N") or cat == "Pe" or _name(item.char).endswith("PRIME")


def _script(item, base):
    """``"sup"``, ``"sub"`` or None for ``item`` right after ``base``.

    A script is no larger than its base (``SCRIPT_SIZE``) and its centre is clearly above or
    below the base's centre (``CENTRE_SHIFT`` of the base height); against the base's
    baseline, a superscript's bottom is raised (``SUP_RISE``) with its top no lower than the
    base's top, and a subscript's bottom drops below the baseline (``SUB_DROP``) with its
    top below the base's top. An operand after a tall bracket or operator is level with its
    middle and is no script. Scripts stop shrinking at a minimum size, so a symbol of the
    base's size counts as a superscript when it lies entirely above the base's middle; a
    bar high above the base's baseline (``BAR_RISE``) opens a superscript (a minus sign in
    an exponent)."""
    if not _can_carry(base) or item.box[0] - base.box[2] > SCRIPT_REACH * base.size:
        return None
    height = max(base.height, 1e-6)
    if item.kind == "bar":
        middle = (item.box[1] + item.box[3]) / 2
        if base.baseline - middle >= BAR_RISE * base.size and item.width <= base.size:
            return "sup"
        return None
    ratio = item.size / base.size if base.size else 1.0
    # Centre against the base's math axis (a box centre is pulled down by descenders).
    lift = base.axis - (item.box[1] + item.box[3]) / 2
    edge = 0.1 * base.size
    if ratio <= SCRIPT_SIZE:
        raised = (
            item.box[3] <= base.baseline - SUP_RISE * base.size
            and item.box[1] <= base.box[1] + edge
        )
        lowered = (
            item.box[3] >= base.baseline + SUB_DROP * base.size
            and item.box[1] >= base.box[1] + 0.1 * height
        )
        if raised and lift >= CENTRE_SHIFT * base.size:
            return "sup"
        if lowered and lift <= -CENTRE_SHIFT * base.size:
            return "sub"
    elif item.box[3] <= (base.box[1] + base.box[3]) / 2 and item.box[1] <= base.box[1]:
        return "sup"
    return None


def _line(items, notes):
    ordered = _atoms(sorted(items, key=lambda i: (i.box[0], i.box[1])))
    elements = []  # [(item, node)]
    index = 0
    while index < len(ordered):
        item = ordered[index]
        base = elements[-1][0] if elements else None
        side = _script(item, base) if base is not None else None
        if side is None:
            elements.append((item, _node(item, notes)))
            index += 1
            continue
        group, index = _script_group(ordered, index, base, side)
        other = None
        if index < len(ordered):
            following = _script(ordered[index], base)
            if following and following != side and ordered[index].box[0] < group[-1].box[2]:
                other, index = _script_group(ordered, index, base, following)
        script = _line(group, notes)
        base_item, base_node = _fenced_base(elements)
        if other is not None:
            second = _line(other, notes)
            sub, sup = (script, second) if side == "sub" else (second, script)
            node = Node("subsup", children=(base_node, sub, sup))
            members = [base_item, *group, *other]
        else:
            node = Node(side, children=(base_node, script))
            members = [base_item, *group]
        combined = _composite(node, [base_item], [m for m in members if m is not base_item])
        combined.baseline, combined.size = base_item.baseline, base_item.size
        combined.axis_at = base_item.axis_at
        elements.append((combined, node))
    return row([node for _, node in elements])


def _fenced_base(elements):
    """Pop the base of a script: a closing bracket takes its whole bracketed group with it
    (a script on ``(x − 2)`` belongs to the group, not to the bracket)."""
    item, node = elements.pop()
    if item.kind != "char" or _category(item.char) != "Pe":
        return item, node
    depth = 0
    for index in range(len(elements) - 1, -1, -1):
        other = elements[index][0]
        category = _category(other.char) if other.kind == "char" else ""
        if category == "Pe":
            depth += 1
        elif category == "Ps":
            if depth == 0:
                group = elements[index:] + [(item, node)]
                del elements[index:]
                members = [m for m, _ in group]
                combined = _composite(row([n for _, n in group]), members)
                combined.baseline = item.baseline
                combined.size = max(m.size for m in members)
                return combined, combined.node
            depth -= 1
    return item, node


def _script_group(ordered, index, base, side):
    """Consecutive symbols at one script level: close to each other, on the baseline of the
    script's first symbol and no larger than it; a minus bar on that level's axis belongs to
    it. A script opened by a bar takes its level from the next symbol centred on the bar."""
    group = [ordered[index]]
    level = None if ordered[index].kind == "bar" else ordered[index]
    index += 1
    while index < len(ordered):
        item = ordered[index]
        if item.box[0] - group[-1].box[2] > SCRIPT_REACH * (level or base).size:
            break
        if level is None:
            bar = group[0]
            middle = (bar.box[1] + bar.box[3]) / 2
            if item.kind == "bar" or abs((item.box[1] + item.box[3]) / 2 - middle) > 0.35 * (
                item.height
            ):
                break
            level = item
        elif item.kind == "bar":
            middle = (item.box[1] + item.box[3]) / 2
            if not (
                level.baseline - 0.6 * level.size <= middle <= level.baseline - 0.1 * level.size
            ):
                break
        elif (
            abs(item.baseline - level.baseline) > 0.12 * level.size
            or item.size > 1.15 * level.size
            or item.box[1] > level.box[1] + 0.25 * level.size
        ):
            # Off the level, larger, or topping out well below it (a relation after a
            # raised mark such as a prime, whose baseline is the main line's).
            break
        group.append(item)
        index += 1
    return group, index
