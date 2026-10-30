"""The emission ledger: what a writer wrote, where it came from, in output order.

Kinds: ``text`` (source text written as text), ``attr`` (source text that became an
attribute, such as a printed label), ``structure`` (a list marker shown by list numbering or
mark), ``generated`` (profile text, such as a default title), ``settings`` (book settings
text, such as the ISBN). ``block`` groups entries written into one output block, so token
boundaries can be compared with the output."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entry:
    kind: str
    rendered: str
    block: int
    addr: str | None = None
    ranges: list[tuple[int, int]] = field(default_factory=list)
    order: int | None = None
    move: str | None = None
    note: str | None = None


class Ledger:
    def __init__(self):
        self.entries: list[Entry] = []
        self._blocks: dict[int, int] = {}
        self._alive: list = []

    def block_id(self, element) -> int:
        key = id(element)
        if key not in self._blocks:
            self._blocks[key] = len(self._blocks)
            self._alive.append(element)  # keep the proxy alive so its id is never reused
        return self._blocks[key]

    def text(self, ref, rendered: str, element, kind: str = "text"):
        self.entries.append(
            Entry(
                kind,
                rendered,
                self.block_id(element),
                ref.addr,
                list(ref.ranges),
                ref.order,
                ref.move,
            )
        )

    def attr(self, ref, value: str, note: str):
        self.entries.append(
            Entry("attr", value, -1, ref.addr, list(ref.ranges), ref.order, ref.move, note)
        )

    def structure(self, addr: str, order: int, length: int, note: str):
        self.entries.append(Entry("structure", "", -1, addr, [(0, length)], order, None, note))

    def other(self, kind: str, rendered: str, element, note: str):
        self.entries.append(Entry(kind, rendered, self.block_id(element), note=note))
