"""The "tail" reference XML (Elsevier/Scopus style, ``ce:`` namespace prefix): the exact tag order
of the client's sample, CRLF line ends, pure ASCII with uppercase 5-digit hexadecimal entities.

Accent modes (``accents``):

* ``sample-mapping`` (default) copies the sample: Latin-1 letters and Z/S-caron stay as
  entities, other accented letters become their plain letter, curly quotes and dashes become
  ``'`` ``"`` ``-``, Greek letters become a Latin letter;
* ``keep``: every non-ASCII character stays as an entity;
* ``strip``: every accent is removed (a letter with no plain form stays as an entity).
"""

from __future__ import annotations

import unicodedata

from .vancouver import Reference

ACCENT_MODES = ("sample-mapping", "keep", "strip")

KEEP_EXTRA = frozenset("ŽžŠš")  # Z-caron z-caron S-caron s-caron
PUNCT = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ", " ": " ",
}  # fmt: skip
GREEK = dict(zip("αβγδεκλμω", "abgdeklu" + "w"))
MARKUP = {"&": "&#x00026;", "<": "&#x0003C;", ">": "&#x0003E;"}
STROKED = {"ł": "l", "Ł": "L", "đ": "d", "Đ": "D"}


def base_letter(ch: str) -> str | None:
    """The plain ASCII letter of an accented one, or None when it has none."""
    if ch in STROKED:
        return STROKED[ch]
    plain = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return plain if plain and all(ord(c) < 127 for c in plain) else None


def written(text: str, mode: str = "sample-mapping") -> str:
    """``text`` as the file holds it once its entities are read back: the characters the mode
    keeps, and the plain ones that replace the rest."""
    out = []
    for ch in text:
        if ch in MARKUP or ord(ch) < 127:
            out.append(ch)
        elif mode != "keep" and ch in PUNCT:
            out.append(PUNCT[ch])
        elif mode == "sample-mapping" and ch in GREEK:
            out.append(GREEK[ch])
        else:
            code = ord(ch)
            keep = (0xC0 <= code <= 0xFF and ch not in "\u00d7\u00f7") or ch in KEEP_EXTRA
            plain = base_letter(ch) if mode == "strip" or (mode == "sample-mapping" and not keep) else None
            out.append(plain if plain is not None else ch)
    return "".join(out)


def encode(text: str, mode: str = "sample-mapping") -> str:
    """``text`` as pure ASCII (see the module doc for the modes)."""
    return "".join(
        MARKUP.get(ch) or (ch if ord(ch) < 127 else f"&#x{ord(ch):05X};") for ch in written(text, mode)
    )


def reference_lines(ref: Reference, mode: str = "sample-mapping") -> list[str]:
    """The tags of one reference, in the sample's order."""

    def e(s):
        return encode(s, mode)

    L = [f'<reference seq="{ref.number}">', "<ref-info>"]
    if ref.title:
        L += ["<ref-title>", f"<ref-titletext-english>{e(ref.title)}</ref-titletext-english>", "</ref-title>"]
    if ref.article_number:
        L += ["<itemidlist>", f'<itemid idtype="ARTNUM">{ref.article_number}</itemid>', "</itemidlist>"]
    if ref.authors or ref.et_al:
        L.append("<ref-authors>")
        for i, (initials, surname) in enumerate(ref.authors, 1):
            L.append(f'<author seq="{i}">')
            if initials:
                L.append(f"<ce:initials>{e(initials)}</ce:initials>")
            L.append(f"<ce:surname>{e(surname)}</ce:surname>")
            L.append("</author>")
        if ref.et_al:
            L.append("<et-al/>")
        L.append("</ref-authors>")
    if ref.source:
        L.append(f"<ref-sourcetitle>{e(ref.source)}</ref-sourcetitle>")
    if ref.year:
        L.append(f'<ref-publicationyear first="{ref.year}"/>')
    if ref.volume or ref.first_page:
        L.append("<volisspag>")
        if ref.volume:
            L += ["<volume-issue-number>", f"<vol-first>{e(ref.volume)}</vol-first>"]
            if ref.issue:
                L.append(f"<iss-first>{e(ref.issue)}</iss-first>")
            if ref.issue_last:
                L.append(f"<iss-last>{e(ref.issue_last)}</iss-last>")
            L.append("</volume-issue-number>")
        if ref.first_page:
            L += ["<page-information>", "<pages>", f"<first-page>{ref.first_page}</first-page>"]
            if ref.last_page:
                L.append(f"<last-page>{ref.last_page}</last-page>")
            L += ["</pages>", "</page-information>"]
        L.append("</volisspag>")
    if ref.url:
        L.append(f'<ref-website><ce:e-address type="url">{e(ref.url)}</ce:e-address></ref-website>')
    extra = ref.text or ", ".join(p for p in (ref.edition, ref.place, ref.publisher) if p) or None
    text = "; ".join(x for x in (extra, f"PMID: {ref.pmid}" if ref.pmid else None) if x)
    if text:
        L.append(f"<ref-text>{e(text)}</ref-text>")
    L.append("</ref-info>")
    L.append(f"<ref-fulltext>{e(ref.full)}</ref-fulltext>")
    L.append(f"<ce:source-text>{e(ref.full)}</ce:source-text>")
    L.append("</reference>")
    return L


def document(refs: list[Reference], mode: str = "sample-mapping") -> bytes:
    """The whole file: ``refcount`` is the number of references written."""
    lines = ["<tail>", f'<bibliography refcount="{len(refs)}">']
    for ref in refs:
        lines += reference_lines(ref, mode)
    lines += ["</bibliography>", "</tail>"]
    data = "\r\n".join(lines).encode("ascii")
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")  # CRLF on every line, always
