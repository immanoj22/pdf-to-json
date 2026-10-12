"""Second intake probe: identity, entity use, page-marker ranges, dialect detection, vocabulary."""

import collections
import json
import re
import sys
import zipfile

import pymupdf
from lingua import LanguageDetectorBuilder

sys.path.insert(0, sys.argv[1])  # backend/src
from book_core.evaluation.dialect_profiles import profile_digests  # noqa: E402
from book_core.reference.dialects import dialects_from_data  # noqa: E402
from book_core.reference.xml_reader import load_tree, local_name  # noqa: E402

DIALECTS_FILE = sys.argv[2]
REFS = json.load(open(sys.argv[3], encoding="utf-8"))
OUT = sys.argv[4]
DATA = json.load(open(DIALECTS_FILE, encoding="utf-8"))
DETECTOR = LanguageDetectorBuilder.from_all_languages().build()

common = DATA["common"]
KNOWN = set(common["inline_elements"]) | set(common["containers"]) | set(common["sectioning"])
KNOWN |= (
    set(common["list_containers"]) | set(common["table_containers"]) | set(common["row_elements"])
)
KNOWN |= {n for names in common["unit_kinds"].values() for n in names} | set(common["zones"])
for spec in DATA["dialects"]:
    KNOWN |= set(spec.get("page_marker_elements", []))


def first_line(doc, index):
    lines = [line.strip() for line in doc[index].get_text("text").splitlines() if line.strip()]
    return " | ".join(lines[:3])[:160]


def xml_summary(data):
    entities = collections.Counter(
        m.decode() for m in re.findall(rb"&([A-Za-z][A-Za-z0-9._-]*);", data)
    )
    entities = {k: v for k, v in entities.items() if k not in {"amp", "lt", "gt", "quot", "apos"}}
    page_pis = re.findall(rb'<\?page\s+value="([^"]*)"', data)
    result = {"named_entities": sum(entities.values()), "entity_names": sorted(entities)[:15]}
    if page_pis:
        result["page_pi"] = {
            "count": len(page_pis),
            "first": page_pis[0].decode(),
            "last": page_pis[-1].decode(),
            "roman": sum(bool(re.fullmatch(rb"[ivxlcdm]+", p)) for p in page_pis),
        }
    try:
        root, repairs = load_tree(data)
        dialect = dialects_from_data(DATA).detect(root)
        tags = collections.Counter(local_name(e.tag) for e in root.iter() if isinstance(e.tag, str))
        result.update(
            reader="ok",
            repairs=[r.kind for r in repairs],
            dialect=dialect.name,
            unknown_elements={t: c for t, c in sorted(tags.items()) if t not in KNOWN},
        )
    except Exception as error:
        result.update(reader=f"failed: {error!r}"[:300])
    return result


def langs(texts):
    counter = collections.Counter()
    for text in texts:
        for r in DETECTOR.detect_multiple_languages_of(text):
            counter[r.language.iso_code_639_3.name.lower()] += len(
                text[r.start_index : r.end_index].split()
            )
    total = sum(counter.values()) or 1
    return {k: round(v / total, 3) for k, v in counter.most_common(3)}


report = {"profile_digests": profile_digests(DATA)}
for book_id, spec in REFS.items():
    entry = {}
    if "pdf" in spec:
        doc = pymupdf.open(spec["pdf"])
        entry["pdf_first_pages"] = [first_line(doc, i) for i in range(min(4, doc.page_count))]
    if "archive" in spec:
        archive = zipfile.ZipFile(spec["archive"])
        texts, with_text, image_only, pages = [], 0, 0, 0
        idents = []
        for name in sorted(n for n in archive.namelist() if n.lower().endswith(".pdf")):
            part = pymupdf.open(stream=archive.read(name), filetype="pdf")
            if not idents:
                idents = [first_line(part, i) for i in range(part.page_count)]
            for i in range(part.page_count):
                pages += 1
                text = part[i].get_text("text")
                if len(text.strip()) >= 50:
                    with_text += 1
                elif part[i].get_images():
                    image_only += 1
                if i % 8 == 0 and len(text) > 200:
                    texts.append(text)
        entry["archive_pdf"] = {
            "pages": pages,
            "pages_with_text": with_text,
            "pages_image_only": image_only,
            "languages": langs(texts),
            "first_part_pages": idents,
        }
        for name in archive.namelist():
            if name.lower().endswith(".xml"):
                entry[name] = xml_summary(archive.read(name))
    for path in spec.get("xml", []):
        entry[path.rsplit("/", 1)[-1]] = xml_summary(open(path, "rb").read())
    report[book_id] = entry
json.dump(report, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
