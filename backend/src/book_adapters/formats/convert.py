"""The conversion walker shared by the XML format transformers (DTBook, JATS, BITS).

It reads the semantic tree (DocBook-named elements whose hosts hold the already-written text)
and produces the target elements. Inline conversion and the splitting of a para around its
block children are here; each format supplies the element names and the structure."""

from __future__ import annotations

from lxml import etree

from ..engine.model import ReviewEntry
from .markup import add_text
from .source import Source

BLOCK_CHILDREN = frozenset(
    {
        "figure",
        "informalfigure",
        "table",
        "informaltable",
        "itemizedlist",
        "orderedlist",
        "variablelist",
        "sidebar",
        "informalequation",
        "qandaset",
        "bibliography",
        "mediaobject",
    }
)
NUMERATION = {
    "arabic": "1",
    "loweralpha": "a",
    "upperalpha": "A",
    "lowerroman": "i",
    "upperroman": "I",
}


class Converter:
    """Base of a format transformer. Subclasses define ``inline_chain``, ``page_mark`` and the
    ``b_<tag>`` block methods."""

    def __init__(self, src: Source, cfg: dict):
        self.src = src
        self.cfg = cfg
        self.reviews = src.reviews
        self.broken_links = 0
        self.broken_examples: list[str] = []

    # ------------------------------------------------------------------ hooks

    def inline_chain(self, ch) -> list[tuple[str, dict]] | None:
        """Element chain (outermost first) for an inline source element; ``[]`` unwraps it;
        ``None`` means the element is handled by ``inline_special``."""
        raise NotImplementedError

    def inline_special(self, ch, dst) -> bool:
        """Handle a source inline element that is not a plain chain (anchors, links)."""
        return False

    # ------------------------------------------------------------------ inline

    def inline_into(self, src, dst, skip=()):
        """src's text and inline children, converted, appended to dst."""
        add_text(dst, src.text)
        for ch in src:
            if ch.tag in BLOCK_CHILDREN or ch.tag == "para" or ch.tag in skip:
                continue
            if not self.inline_special(ch, dst):
                target = dst
                chain = self.inline_chain(ch)
                for tag, attrs in chain or []:
                    node = etree.SubElement(target, tag)
                    for k, v in attrs.items():
                        if v is not None:
                            node.set(k, v)
                    target = node
                self.inline_into(ch, target)
            add_text(dst, ch.tail)

    def segments(self, para):
        """A para's content as runs: ("inline", [text | element, ...]) and ("block", element)."""
        runs: list = []
        cur: list = []
        if para.text:
            cur.append(para.text)
        for ch in para:
            if ch.tag in BLOCK_CHILDREN:
                if cur:
                    runs.append(("inline", cur))
                    cur = []
                runs.append(("block", ch))
                if ch.tail:
                    cur.append(ch.tail)
            else:
                cur.append(ch)
                if ch.tail:
                    cur.append(ch.tail)
        if cur:
            runs.append(("inline", cur))
        return runs

    def inline_run_into(self, run, dst):
        holder = etree.Element("holder")
        # rebuild a transient parent so inline_into can walk the run
        for item in run:
            if isinstance(item, str):
                add_text(holder, item)
            else:
                tail, item.tail = item.tail, None
                holder.append(_clone(item))
                item.tail = tail
        self.inline_into(holder, dst)

    @staticmethod
    def has_text(run) -> bool:
        return any((isinstance(i, str) and i.strip()) or (not isinstance(i, str)) for i in run)

    # ------------------------------------------------------------------ helpers

    def review(self, kind: str, message: str, unit: str | None = None):
        self.reviews.append(ReviewEntry(kind, message, unit))

    def block(self, el, parent) -> None:
        fn = getattr(self, f"b_{el.tag}", None)
        if fn is None:
            self.review(
                "structure", f"element <{el.tag}> of the content tree has no mapping: dropped"
            )
            return
        fn(el, parent)

    def blocks(self, src, parent, skip=("title",)):
        for ch in src:
            if ch.tag in skip:
                continue
            self.block(ch, parent)


def _clone(el):
    import copy

    return copy.deepcopy(el)
