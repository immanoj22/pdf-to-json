"""Text of book.json units: rendering with line-end joins, offsets back to the source text,
and the Stage 1 token rule (``[\\p{L}\\p{M}\\p{N}]+``, case-sensitive)."""

from __future__ import annotations

from dataclasses import dataclass, field

import regex

TOKEN_RE = regex.compile(r"[\p{L}\p{M}\p{N}]+")
# A character an output rule removes (a soft hyphen, a line end inside a web address). Rules
# keep texts the same length, so offsets stay valid; render() skips it like any character
# XML 1.0 does not allow.
DELETE = "\x00"
WS = frozenset(" \t\n\r\f\v              　")


def xml_char(ch: str) -> bool:
    code = ord(ch)
    return (
        (code >= 0x20 or ch in "\t\n\r")
        and not (0xD800 <= code <= 0xDFFF)
        and code not in (0xFFFE, 0xFFFF)
    )


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


@dataclass
class TextRef:
    """A slice of one source text record, written somewhere in the delivery.

    ``addr`` names the record (unit id, or unit id with a field path); ``order`` is the
    record's position in book.json reading order; ``ranges`` are source offsets to write.
    ``move`` names the rule that placed it out of book.json order (or None).
    """

    addr: str
    content: dict
    order: int
    ranges: list[tuple[int, int]] = field(default_factory=list)
    move: str | None = None
    kind: str = "text"  # text | marker (a list marker written as text)
    nospace: bool = False  # joins the previous piece without a space (hyphen/word join)

    def __post_init__(self):
        if not self.ranges:
            self.ranges = [(0, len(self.content["text"]))]

    @property
    def text(self) -> str:
        return self.content["text"]

    def slice(self, start: int, end: int, move: str | None = None) -> TextRef:
        """The part of this ref between source offsets start and end."""
        ranges = []
        for s, e in self.ranges:
            s2, e2 = max(s, start), min(e, end)
            if s2 < e2:
                ranges.append((s2, e2))
        return TextRef(
            self.addr,
            self.content,
            self.order,
            ranges or [(start, start)],
            move or self.move,
            self.kind,
            self.nospace,
        )

    def plain(self) -> str:
        return "".join(ch for ch, _ in render(self.content, self.ranges))

    def is_blank(self) -> bool:
        return not self.plain().strip()


def dropped_offsets(content: dict) -> set[int]:
    """Source offsets that vanish when read: line ends and break hyphens of joins."""
    drop: set[int] = set()
    for join in content.get("joins") or ():
        decision = join["decision"]
        drop.add(join["at"])
        if decision in ("join", "soft_join") and join.get("hyphen_at") is not None:
            drop.add(join["hyphen_at"])
    return drop


def render(
    content: dict, ranges: list[tuple[int, int]], text: str | None = None
) -> list[tuple[str, int]]:
    """Characters as read, with their source offsets. Line ends without a join decision
    read as a space; runs of white space collapse to one space."""
    text = content["text"] if text is None else text
    drop = dropped_offsets(content)
    out: list[tuple[str, int]] = []
    for start, end in ranges:
        for i in range(start, end):
            if i in drop:
                continue
            ch = text[i]
            if ch in WS:
                if out and out[-1][0] == " ":
                    continue
                ch = " "
            elif ch == "­" and (i + 1 >= len(text) or text[i + 1] == "\n"):
                continue  # soft hyphen kept by a join decision only
            elif not xml_char(ch):
                continue  # not allowed in XML 1.0 (C0 controls, U+FFFE/FFFF); never a token
            out.append((ch, i))
    return out


def render_tokens(content: dict, ranges=None) -> list[tuple[str, frozenset[int]]]:
    """Tokens of the rendered text with the source offsets of their characters."""
    ranges = ranges or [(0, len(content["text"]))]
    chars = render(content, ranges)
    rendered = "".join(c for c, _ in chars)
    return [
        (m.group(), frozenset(chars[i][1] for i in range(m.start(), m.end())))
        for m in TOKEN_RE.finditer(rendered)
    ]


def strip_ranges(ref: TextRef) -> TextRef:
    """Drop leading and trailing white space (and leader dots) from a ref's ranges."""
    chars = render(ref.content, ref.ranges)
    keep = [i for i, (c, _) in enumerate(chars) if c not in WS]
    if not keep:
        return ref.slice(ref.ranges[0][0], ref.ranges[0][0])
    first, last = chars[keep[0]][1], chars[keep[-1]][1]
    return ref.slice(first, last + 1)
