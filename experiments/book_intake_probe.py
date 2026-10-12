"""Book intake probe: counts only. Reads PDFs and reference XML read-only; writes one JSON."""

import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import pymupdf
from lingua import LanguageDetectorBuilder

DETECTOR = LanguageDetectorBuilder.from_all_languages().build()

MATH = {
    "math",
    "mml:math",
    "inlineequation",
    "equation",
    "informalequation",
    "mathphrase",
}
TABLE = {"table", "informaltable"}
FIGURE = {
    "figure",
    "informalfigure",
    "img",
    "imagedata",
    "graphic",
    "mediaobject",
    "inlinemediaobject",
}
LIST = {
    "itemizedlist",
    "orderedlist",
    "variablelist",
    "simplelist",
    "list",
    "ul",
    "ol",
    "dl",
    "glosslist",
}
FOOTNOTE = {"footnote", "note", "noteref", "footnoteref"}
MARKERS = {"pagenum", "pagebreak", "anchor", "beginpage"}


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def pdf_info(doc, sample_pages=12):
    pages = doc.page_count
    scanned = born = empty = 0
    sample_text = []
    step = max(1, pages // sample_pages)
    for index in range(pages):
        page = doc[index]
        chars = len(page.get_text("text").strip())
        area = page.rect.width * page.rect.height or 1
        image_cover = 0.0
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            image_cover = max(image_cover, (x1 - x0) * (y1 - y0) / area)
        if chars >= 50:
            born += 1
        elif image_cover > 0.8:
            scanned += 1
        else:
            empty += 1
        if index % step == 0 and chars > 200:
            sample_text.append(page.get_text("text"))
    langs = collections.Counter()
    for text in sample_text:
        for result in DETECTOR.detect_multiple_languages_of(text):
            words = len(text[result.start_index : result.end_index].split())
            langs[result.language.iso_code_639_3.name.lower()] += words
    total = sum(langs.values()) or 1
    meta = doc.metadata or {}
    return {
        "pages": pages,
        "encrypted": doc.is_encrypted,
        "needs_pass": doc.needs_pass,
        "pages_with_text": born,
        "pages_image_only": scanned,
        "pages_little_text": empty,
        "language_word_share": {k: round(v / total, 3) for k, v in langs.most_common(5)},
        "metadata_title": meta.get("title", ""),
        "page_labels": bool(doc.get_page_labels()),
        "first_label": doc[0].get_label() if pages else "",
        "last_label": doc[pages - 1].get_label() if pages else "",
    }


def xml_info(data):
    head = data[:3000].decode("utf-8", "replace")
    doctype = re.search(r"<!DOCTYPE[^\[>]*", head)
    counts = collections.Counter()
    pis = collections.Counter()
    marker_ids = []
    title = None
    root = root_ns = None
    stack = []
    parser = ET.XMLPullParser(events=("start", "end", "pi"))
    # Undeclared entities from the DTD would stop the parser; map them to a placeholder.
    body = re.sub(
        rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)[A-Za-z0-9._-]+;",
        b"?",
        data,
    )
    parser.feed(body)
    parser.close()
    for event, node in parser.read_events():
        if event == "pi":
            pis[(node.text or "").split(" ", 1)[0]] += 1
            continue
        name = local(node.tag)
        if event == "start":
            if root is None:
                root = name
                root_ns = node.tag[1:].split("}")[0] if node.tag.startswith("{") else ""
            stack.append(name)
            counts[name] += 1
            if name in MARKERS:
                marker_ids.append(
                    node.get("id")
                    or node.get("{http://www.w3.org/XML/1998/namespace}id")
                    or node.get("page")
                    or ""
                )
        else:
            if title is None and name == "title" and len(stack) <= 3:
                title = "".join(node.itertext()).strip()[:120]
            stack.pop()
    id_patterns = collections.Counter(
        re.sub(r"\d+", "N", re.sub(r"[ivxlcdm]+$", "R", i)) for i in marker_ids
    )

    def total(group):
        return sum(counts[n] for n in group)

    return {
        "bytes": len(data),
        "xml_declaration": head.lstrip().startswith("<?xml"),
        "doctype": doctype.group(0) if doctype else None,
        "root": root,
        "root_namespace": root_ns,
        "top_title": title,
        "elements": sum(counts.values()),
        "processing_instructions": dict(pis),
        "page_marker_elements": {n: counts[n] for n in sorted(MARKERS) if counts[n]},
        "page_marker_id_patterns": dict(id_patterns.most_common(5)),
        "page_marker_first_last": [marker_ids[0], marker_ids[-1]] if marker_ids else [],
        "math": {n: counts[n] for n in sorted(MATH) if counts[n]},
        "tables": {n: counts[n] for n in sorted(TABLE) if counts[n]},
        "figures": {n: counts[n] for n in sorted(FIGURE) if counts[n]},
        "lists": {n: counts[n] for n in sorted(LIST) if counts[n]},
        "footnotes": {n: counts[n] for n in sorted(FOOTNOTE) if counts[n]},
        "sectioning": {
            n: counts[n]
            for n in (
                "part",
                "chapter",
                "sect1",
                "sect2",
                "section",
                "level1",
                "appendix",
                "index",
                "glossary",
                "bibliography",
                "preface",
            )
            if counts[n]
        },
        "tag_vocabulary": sorted(counts),
    }


def main(manifest_path, out_path):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    report = {}
    for book_id, spec in manifest.items():
        entry = {}
        try:
            doc = pymupdf.open(spec["pdf"])
            entry["pdf"] = pdf_info(doc)
        except Exception as error:  # broken files are reported, not raised
            entry["pdf"] = {"error": repr(error)}
        if "archive" in spec:
            archive = zipfile.ZipFile(spec["archive"])
            entry["archive_testzip"] = archive.testzip()
            parts = []
            for name in sorted(n for n in archive.namelist() if n.lower().endswith(".pdf")):
                part = pymupdf.open(stream=archive.read(name), filetype="pdf")
                parts.append(
                    {
                        "name": name.rsplit("/", 1)[-1],
                        "pages": part.page_count,
                        "first_label": part[0].get_label(),
                        "encrypted": part.is_encrypted,
                        "metadata_title": (part.metadata or {}).get("title", ""),
                    }
                )
            entry["archive_pdfs"] = parts
            entry["archive_pdf_pages"] = sum(p["pages"] for p in parts)
            xml_names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            entry["xml"] = {n: xml_info(archive.read(n)) for n in xml_names}
        else:
            entry["xml"] = {}
            for path in spec["xml"]:
                try:
                    entry["xml"][path.rsplit("/", 1)[-1]] = xml_info(open(path, "rb").read())
                except Exception as error:
                    entry["xml"][path.rsplit("/", 1)[-1]] = {"error": repr(error)}
        report[book_id] = entry
    json.dump(report, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
