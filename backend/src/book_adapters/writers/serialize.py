"""Deterministic XML serialization with profile-controlled character forms and line breaks.

Elements with element-only content put each child on its own line; mixed content (para,
title, entry...) stays on one line. Empty elements are self-closed."""

from __future__ import annotations

from lxml import etree


class Serializer:
    def __init__(
        self,
        text_escape: dict[str, str],
        attr_escape: dict[str, str],
        non_ascii: str,
        block_elements: frozenset[str],
        compact: frozenset[str],
    ):
        self.text_escape = text_escape
        self.attr_escape = attr_escape
        self.non_ascii = non_ascii
        self.block = block_elements
        self.compact = compact

    def _char(self, ch: str, table: dict[str, str]) -> str:
        if ch in table:
            return table[ch]
        code = ord(ch)
        if code < 128 or self.non_ascii == "utf8":
            return ch
        return f"&#x{code:04X};" if self.non_ascii == "hex4" else f"&#{code};"

    def text(self, value: str) -> str:
        return "".join(self._char(c, self.text_escape) for c in value)

    def attr(self, value: str) -> str:
        return "".join(self._char(c, self.attr_escape) for c in value)

    def element(self, el: etree._Element) -> str:
        out: list[str] = []
        self._write(el, out, parent_block=False)
        return "".join(out)

    def _write(self, el, out: list[str], parent_block: bool):
        tag = el.tag
        attrs = "".join(f' {k}="{self.attr(v)}"' for k, v in el.attrib.items())
        is_block = tag in self.block and tag not in self.compact
        if not len(el) and not el.text:
            out.append(f"<{tag}{attrs}/>")
        else:
            out.append(f"<{tag}{attrs}>")
            element_only = (
                is_block
                and not (el.text or "").strip()
                and all(not (c.tail or "").strip() for c in el)
            )
            if element_only:
                out.append("\n")
                for child in el:
                    self._write(child, out, parent_block=True)
                    out.append("\n")
            else:
                if el.text:
                    out.append(self.text(el.text))
                for child in el:
                    self._write(child, out, parent_block=False)
                    if child.tail:
                        out.append(self.text(child.tail))
            out.append(f"</{tag}>")
