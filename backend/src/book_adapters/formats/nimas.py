"""NIMAS 1.1 file-set pieces: the OPF package file and the title/copyright PDF."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape, quoteattr

OEB_NS = "http://openebook.org/namespaces/oeb-package/1.0/"
OPF_PUBLIC = "+//ISBN 0-9673008-1-9//DTD OEB 1.2 Package//EN"
OPF_SYSTEM = "http://openebook.org/dtds/oeb-1.2/oebpkg12.dtd"


def opf_bytes(meta: dict, manifest: list[tuple[str, str, str]], spine: list[str]) -> bytes:
    """meta: dc fields (Identifier, Title, Language required) and x-meta pairs.
    manifest: (id, href, media-type)."""
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!DOCTYPE package PUBLIC "{OPF_PUBLIC}" "{OPF_SYSTEM}">',
        f'<package xmlns="{OEB_NS}" unique-identifier="uid">',
        "<metadata>",
        '<dc-metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">',
    ]
    for name, value in meta["dc"]:
        attr = ' id="uid"' if name == "Identifier" and value == meta["uid"] else ""
        out.append(f"<dc:{name}{attr}>{escape(value)}</dc:{name}>")
    out.append("</dc-metadata>")
    if meta["x"]:
        out.append("<x-metadata>")
        out += [f"<meta name={quoteattr(k)} content={quoteattr(v)}/>" for k, v in meta["x"]]
        out.append("</x-metadata>")
    out += ["</metadata>", "<manifest>"]
    out += [
        f"<item id={quoteattr(i)} href={quoteattr(h)} media-type={quoteattr(m)}/>"
        for i, h, m in manifest
    ]
    out += ["</manifest>", "<spine>"]
    out += [f"<itemref idref={quoteattr(i)}/>" for i in spine]
    out += ["</spine>", "</package>", ""]
    return "\n".join(out).encode("utf-8")


def cut_pages(source_pdf, pages: list[int]) -> bytes:
    """A PDF of the given 1-based pages of the source (pypdfium2, Apache-2.0/BSD-3; not
    PyMuPDF). The bytes depend only on the source pages."""
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(str(source_pdf))
    dst = pdfium.PdfDocument.new()
    dst.import_pages(src, [p - 1 for p in pages])
    buf = io.BytesIO()
    dst.save(buf)
    data = buf.getvalue()
    for obj in (dst, src):
        obj.close()
    return _stable(data)


def _stable(data: bytes) -> bytes:
    """Fix the dates and the trailer /ID (same length) so repeated cuts are byte-identical."""
    import re

    def zero(m):
        return re.sub(rb"[0-9A-Fa-f]", b"0", m.group())

    data = re.sub(
        rb"/(CreationDate|ModDate)\(D:\d{14}",
        lambda m: b"/" + m.group(1) + b"(D:19800101000000",
        data,
    )
    return re.sub(rb"/ID\s*\[\s*<[0-9A-Fa-f]+>\s*<[0-9A-Fa-f]+>\s*\]", zero, data)
