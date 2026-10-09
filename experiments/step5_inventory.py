"""Step 5 Part 1: read-only inventory and pairing verification of PDF/XML references.

Every configured reference location is scanned; files are hashed and deduplicated. Each XML is
parsed with the standard library only (repairs are in memory, never written back), described by
dialect, generator signature and page markers, and matched against every distinct source PDF by
benchmark-token overlap. Pairs with page markers are verified page by page with rare-token votes.
No file outside this project is written.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from reference_paths import PROJECT_ROOT, private_file_names, reference_path

from book_core.extraction.cache import CachedExtractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ledger.tokenization import token_counter

OUT = PROJECT_ROOT / "experiments/out/step5"
CACHE = PROJECT_ROOT / ".cache/step5/native"
SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "site-packages", "__pycache__"}
MIN_XML_BYTES = 20_000
RARE_DF = 3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def walk(root: Path, suffixes: set[str]):
    if not root.exists():
        return
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.suffix.lower() in suffixes:
                yield entry


# ---------------------------------------------------------------- XML reading (in memory only)


def parse_xml(data: bytes) -> tuple[ET.Element | None, list[str], str | None]:
    """Parse with recorded, in-memory repairs; the source file is never modified."""
    attempts = [(data, [])]
    lines = data.split(b"\n", 6)
    if b'""' in b"\n".join(lines[:6]):
        fixed = b"\n".join(line.replace(b'""', b'"') for line in lines[:6])
        if len(lines) > 6:
            fixed += b"\n" + lines[6]
        attempts.append((fixed, ["doubled quote delimiters in opening lines"]))
    body = re.sub(rb"^\s*<\?xml[^>]*\?>", b"", data)
    attempts.append((b"<inspection>" + body + b"</inspection>", ["top-level fragments wrapped"]))
    error = None
    for candidate, applied in attempts:
        try:
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_pis=True))
            parser.feed(candidate)
            return parser.close(), applied, None
        except ET.ParseError as exc:
            error = error or str(exc)
    return None, [], error


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1] if isinstance(tag, str) else ""


def events(element: ET.Element):
    """Document-order text and page-marker events; attribute text is not reading text."""
    if element.tag is ET.ProcessingInstruction:
        text = element.text or ""
        match = re.match(r"page\s+value=\"([^\"]*)\"", text)
        if match:
            yield "page", match.group(1)
        return
    if element.tag is ET.Comment:
        return
    if local(element.tag) == "pagenum":
        yield "page", "".join(element.itertext()).strip() or element.get("page", "")
        return
    if element.text:
        yield "text", element.text
    for child in element:
        yield from events(child)
        if child.tail:
            yield "text", child.tail


def describe_xml(root: ET.Element, raw: bytes) -> dict:
    tags = Counter(local(node.tag) for node in root.iter() if isinstance(node.tag, str))
    ids = [
        value
        for node in root.iter()
        if isinstance(node.tag, str)
        for key, value in node.attrib.items()
        if local(key) == "id"
    ]
    id_families = Counter(re.sub(r"[0-9a-f]{6,}|\d+", "#", value) for value in ids)
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if local(root.tag) == "inspection" and len(root):
        namespace = root[0].tag[1:].split("}")[0] if root[0].tag.startswith("{") else ""
    doctype = re.search(rb"<!DOCTYPE[^>]*>", raw[:2000])
    pis = re.findall(rb"<\?(?!xml )([a-zA-Z-]+)[^>]*\?>", raw[:4000])
    isbns = sorted({m.decode() for m in re.findall(rb"97[89][-\d]{10,16}", raw)})[:8]
    return {
        "root": local(root.tag),
        "namespace": namespace,
        "doctype": doctype.group().decode("utf8", "replace") if doctype else None,
        "leading_processing_instructions": sorted({p.decode() for p in pis}),
        "root_attributes": {local(k): v for k, v in root.attrib.items()},
        "top_tags": tags.most_common(25),
        "id_families": id_families.most_common(6),
        "isbn_like": isbns,
        "has_ns0_prefix": raw.find(b"<ns0:") >= 0,
    }


def dialect(info: dict) -> str:
    ns, root = info["namespace"], info["root"]
    if "daisy.org/z3986" in ns or root == "dtbook":
        return "DTBook 2005-3 (NIMAS)"
    if "docbook.org" in ns:
        return "DocBook 5"
    tags = dict(info["top_tags"])
    if root == "level1" or "level1" in tags:
        return "DTBook-like fragment (no dtbook root/namespace)"
    if root == "book" and info["root_attributes"].get("profile") == "internal-standard":
        return "DocBook-like internal profile (no namespace)"
    if root == "inspection":
        return "Fragments (DocBook-like, no root)"
    return "other"


def generator_signature(info: dict) -> list[str]:
    """Evidence only: id patterns and serialisation marks of the old project's writers."""
    marks = []
    families = " ".join(family for family, _ in info["id_families"])
    if "src-yaml-" in families:
        marks.append("old backend YAML writer ids (src-yaml-#)")
    if "generated-" in families or re.search(r"\bsrc-#", families):
        marks.append("old backend generated/src ids")
    if info["root_attributes"].get("profile") == "internal-standard":
        marks.append("old backend internal-standard profile")
    if info["has_ns0_prefix"]:
        marks.append("ElementTree ns0 serialisation (old pdf_to_xml writer)")
    if "oxygen" in info["leading_processing_instructions"]:
        marks.append("oXygen editor schema PIs (publisher workflow)")
    if "NIMAS#-" in families or "NIMAS" in families:
        marks.append("publisher NIMAS ids")
    if re.search(r"\bb-#", families) and "oxygen" in info["leading_processing_instructions"]:
        marks.append("Bloomsbury xml:id scheme")
    return marks


def xml_stream(root: ET.Element) -> tuple[Counter, list[tuple[str | None, Counter]]]:
    """Whole-document counter and per-page-marker segments (marker precedes its page)."""
    total = Counter()
    segments: list[tuple[str | None, Counter]] = [(None, Counter())]
    for kind, value in events(root):
        if kind == "page":
            segments.append((value, Counter()))
        else:
            tokens = token_counter(value)
            total.update(tokens)
            segments[-1][1].update(tokens)
    return total, segments


# ---------------------------------------------------------------- PDF evidence


def pdf_pages(path: Path, extractor: CachedExtractor) -> list[Counter]:
    pages = []
    for page in extractor.extract_pages(path):
        counter = Counter()
        for line in page.store.lines:
            if page.geometry.content_bbox.contains_center(line.bbox):
                counter.update(token_counter(page.store.raw_line_text(line)))
        pages.append(counter)
    return pages


def verify_pages(segments, pages: list[Counter], keep_rows: bool = False) -> dict:
    """Rare-token votes place each marker segment; report order, offsets and folio evidence."""
    df = Counter()
    for counter in pages:
        df.update(counter.keys())
    index = defaultdict(list)
    for number, counter in enumerate(pages, 1):
        for token in counter:
            if df[token] <= RARE_DF:
                index[token].append(number)
    placed = []
    for ordinal, (label, counter) in enumerate(segments):
        if label is None or counter.total() < 5:
            continue
        votes = Counter()
        for token in counter:
            for number in index.get(token, ()):
                votes[number] += 1 / math.log2(1 + df[token])
        if not votes:
            continue
        best, _ = votes.most_common(1)[0]
        overlap = (counter & pages[best - 1]).total() / counter.total()
        folio = label.strip()
        placed.append(
            {
                "ordinal": ordinal,
                "label": folio,
                "page": best,
                "overlap": overlap,
                "folio_on_page": bool(folio) and pages[best - 1][folio] > 0,
            }
        )
    tails: list[int] = []
    for row in placed:  # longest non-decreasing subsequence length
        position = next((i for i, v in enumerate(tails) if v > row["page"]), len(tails))
        if position == len(tails):
            tails.append(row["page"])
        else:
            tails[position] = row["page"]
    offsets = Counter(row["page"] - row["ordinal"] for row in placed)
    overlaps = sorted(row["overlap"] for row in placed)
    return {
        "placements": placed if keep_rows else None,
        "markers": sum(1 for label, _ in segments if label is not None),
        "segments_placed": len(placed),
        "monotonic_fraction": round(len(tails) / len(placed), 4) if placed else None,
        "dominant_offset": offsets.most_common(3),
        "median_segment_overlap": round(overlaps[len(overlaps) // 2], 4) if overlaps else None,
        "folio_on_matched_page_fraction": (
            round(sum(r["folio_on_page"] for r in placed) / len(placed), 4) if placed else None
        ),
        "distinct_pages_matched": len({row["page"] for row in placed}),
    }


# Candidate pairs named in Phase 0 (name, XML SHA-256, PDF SHA-256); verified, not assumed.
CANDIDATE_PAIRS = [
    (
        "spanish_us_history_758 / NIMAS DTBook",
        "a16f3ed0646e1923ebf02109a977fa78fabd06858d943703765947abe09a89f5",
        "de9d916687ecbe556f7a01f1d871048ec89f362ae5c4b399bd08098b1fddc951",
    ),
    (
        "spanish_us_history_300_excerpt / NIMAS DTBook",
        "a16f3ed0646e1923ebf02109a977fa78fabd06858d943703765947abe09a89f5",
        "089904b798c8354eba521b8ef6138810d48f5dc9d88c8c64bdc82cf229701a53",
    ),
    (
        "immigrant_children_331 / Bloomsbury DocBook",
        "b8be7a91bcf2385a4f0415e4cef84cd0534bc547373d4ea3e3f7405e59ab6acd",
        "4825a40c9905048df0cee7eb173802438e5c7b71fe2d768255dc09314baa593f",
    ),
    (
        "art_therapy_index_9 / DocBook index fragments",
        "6313f7705615bd431812acfec93cdca0a2d6ea0b2a5acad9e843fd4659b18d3f",
        "d13497d3d53938a07e29963e48d96c0d25ae83d09db3fef534c3a013e5952525",
    ),
    (
        "us_history_tema1_86 / NIMAS T01 excerpt",
        "3e4409c889fd96186112dd2a8f19c078c4388ed505c54b15f6fa21446731f090",
        "0254f39a07377877c3c32a71118aa4d7371101c4135c539addeeee6dcdbef098",
    ),
    (
        "world_history_tema1_48 / NIMAS T01 excerpt (profile pairing)",
        "3e4409c889fd96186112dd2a8f19c078c4388ed505c54b15f6fa21446731f090",
        "94339161b82bea9bfd265a9c1e91a723d60859bf6f3d8812641bc48d3a802e17",
    ),
]


# ---------------------------------------------------------------- discovery


def discover():
    downloads = reference_path("downloads")
    roots = {
        "old_root": reference_path("old_root"),
        "legacy_upgrade": reference_path("legacy_upgrade"),
        "old_original": reference_path("old_original"),
    }
    private = private_file_names()
    skipped = 0
    xmls: dict[str, dict] = {}
    pdfs: dict[str, dict] = {}

    def add(table, digest, record):
        entry = table.setdefault(digest, {**record, "locations": []})
        entry["locations"].append(record["location"])

    for key in ("spanish_xml", "partial_xml"):
        path = reference_path(key)
        if path.exists():
            add(xmls, sha256(path), {"location": str(path), "bytes": path.stat().st_size})
    for key in ("spanish_pdf", "science_pdf", "small_pdf"):
        path = reference_path(key)
        if path.exists():
            add(pdfs, sha256(path), {"location": str(path), "bytes": path.stat().st_size})
    for path in sorted(downloads.glob("*")) + sorted(downloads.glob("*/*")):
        if path.name in private:
            skipped += 1
            continue
        if path.suffix.lower() == ".xml":
            add(xmls, sha256(path), {"location": str(path), "bytes": path.stat().st_size})
        elif path.suffix.lower() == ".pdf":
            add(pdfs, sha256(path), {"location": str(path), "bytes": path.stat().st_size})
    archives = []
    for archive in sorted(downloads.glob("*.zip")):
        if archive.name in private:
            continue
        members = []
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                suffix = Path(info.filename).suffix.lower()
                member = {"name": info.filename, "bytes": info.file_size}
                if suffix in {".xml", ".pdf"} and info.file_size <= 64 << 20:
                    data = bundle.read(info)
                    member["sha256"] = hashlib.sha256(data).hexdigest()
                    location = f"{archive}!{info.filename}"
                    table = xmls if suffix == ".xml" else pdfs
                    add(table, member["sha256"], {"location": location, "bytes": info.file_size})
                if suffix in {".xml", ".pdf"} or len(members) < 12:
                    members.append(member)
        archives.append(
            {
                "archive": str(archive),
                "member_count": len(bundle.infolist()),
                "members_listed": members,
            }
        )
    seen: set[Path] = set()
    for root in roots.values():
        for path in walk(root, {".xml", ".pdf"}):
            if path in seen or path.name in private:
                continue
            seen.add(path)
            size = path.stat().st_size
            if path.suffix.lower() == ".xml" and size >= MIN_XML_BYTES:
                add(xmls, sha256(path), {"location": str(path), "bytes": size})
            elif path.suffix.lower() == ".pdf" and size >= MIN_XML_BYTES:
                add(pdfs, sha256(path), {"location": str(path), "bytes": size})
    return xmls, pdfs, archives, skipped


def read_member(location: str) -> bytes:
    if "!" in location and location.split("!", 1)[0].lower().endswith(".zip"):
        archive, name = location.split("!", 1)
        with zipfile.ZipFile(archive) as bundle:
            return bundle.read(name)
    return Path(location).read_bytes()


def pdf_summary(location: str) -> tuple[int | None, str]:
    """Page count and opening text, used only to recognise non-source renders."""
    import pymupdf

    try:
        if "!" in location:
            doc = pymupdf.open(stream=read_member(location), filetype="pdf")
        else:
            doc = pymupdf.open(location)
        with doc:
            text = " ".join(doc[i].get_text()[:200] for i in range(min(2, doc.page_count)))
            return doc.page_count, " ".join(text.split())[:240]
    except Exception:  # noqa: BLE001 - inventory records unreadable inputs
        return None, ""


def non_source_reason(record: dict) -> str | None:
    text = record["first_text"]
    if text.startswith("range-"):
        return "XML-debug render of a generated XML (attribute/layout text)"
    if "DocBook XML Specification" in text or "DocBook XML: Specification" in text:
        return "Bloomsbury DocBook specification, a rule reference"
    return None


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    xmls, pdfs, archives, private_skipped = discover()
    print(f"unique XML {len(xmls)}, unique PDF {len(pdfs)}", flush=True)
    for record in pdfs.values():
        record["pages"], record["first_text"] = pdf_summary(record["locations"][0])
        record["non_source"] = non_source_reason(record)
    # Source books: distinct PDFs that are not XML-rendering debug artefacts.
    extractor = CachedExtractor(PyMuPDFExtractor("cpu"), CACHE)
    sources = {}
    for digest, record in sorted(pdfs.items(), key=lambda item: -(item[1]["pages"] or 0)):
        on_disk = [location for location in record["locations"] if "!" not in location]
        if not on_disk or not record["pages"] or record["non_source"]:
            continue
        location = on_disk[0]
        print("extract", record["pages"], location, flush=True)
        pages = pdf_pages(Path(location), extractor)
        record["native_tokens"] = sum(counter.total() for counter in pages)
        sources[digest] = pages
    totals = {digest: sum(pages, Counter()) for digest, pages in sources.items()}
    for record in xmls.values():
        raw = read_member(record["locations"][0])
        root, repairs, error = parse_xml(raw)
        record["parse_error"] = error
        record["in_memory_repairs"] = repairs
        if root is None:
            continue
        info = describe_xml(root, raw)
        record.update(info)
        record["dialect"] = dialect(info)
        record["generator_marks"] = generator_signature(info)
        total, segments = xml_stream(root)
        record["xml_tokens"] = total.total()
        record["page_markers"] = sum(1 for label, _ in segments if label is not None)
        labels = [label for label, _ in segments if label is not None]
        record["page_marker_first_last"] = [labels[:3], labels[-3:]] if labels else None
        matches = []
        for pdf_digest, pdf_total in totals.items():
            common = (total & pdf_total).total()
            matches.append(
                {
                    "pdf_sha256": pdf_digest,
                    "xml_tokens_in_pdf": round(common / max(total.total(), 1), 4),
                    "pdf_tokens_in_xml": round(common / max(pdf_total.total(), 1), 4),
                }
            )
        matches.sort(key=lambda m: -(m["xml_tokens_in_pdf"] + m["pdf_tokens_in_xml"]))
        record["best_pdf_matches"] = matches[:2]
        best = matches[0] if matches else None
        if best and record["page_markers"] and best["xml_tokens_in_pdf"] > 0.5:
            record["page_verification"] = verify_pages(segments, sources[best["pdf_sha256"]])
        print(record["locations"][0], record["dialect"], best, flush=True)
    pairs = []
    for name, xml_digest, pdf_digest in CANDIDATE_PAIRS:
        if xml_digest not in xmls or pdf_digest not in sources:
            pairs.append({"name": name, "available": False})
            continue
        root, _, _ = parse_xml(read_member(xmls[xml_digest]["locations"][0]))
        total, segments = xml_stream(root)
        pdf_total = totals[pdf_digest]
        common = (total & pdf_total).total()
        pairs.append(
            {
                "name": name,
                "available": True,
                "xml_sha256": xml_digest,
                "pdf_sha256": pdf_digest,
                "pdf_pages": len(sources[pdf_digest]),
                "xml_tokens": total.total(),
                "pdf_tokens": pdf_total.total(),
                "xml_tokens_in_pdf": round(common / max(total.total(), 1), 4),
                "pdf_tokens_in_xml": round(common / max(pdf_total.total(), 1), 4),
                "pages": verify_pages(segments, sources[pdf_digest], keep_rows=True),
            }
        )
    report = {
        "pairs": pairs,
        "method": (
            "Read-only. XML parsed in memory by stdlib ElementTree; benchmark tokens are "
            "case-sensitive NFKC [\\p{L}\\p{M}\\p{N}]+ over element text (attributes excluded). "
            "PDF tokens are retained native lines (TrimBox centre) through the Extractor. "
            f"Page verification places each marker segment by rare-token votes (df<={RARE_DF})."
        ),
        "private_files_skipped": private_skipped,
        "xml": xmls,
        "pdf": pdfs,
        "archives": archives,
    }
    (OUT / "inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
