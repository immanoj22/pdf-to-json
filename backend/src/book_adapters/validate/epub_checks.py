"""ePub checks, run on the written .epub file itself (re-read from disk):

1. Package: ``mimetype`` first and stored, ``container.xml``, the package document (version,
   identifier, title, language, modified), manifest files exist and every file is listed,
   spine, navigation document, cover image.
2. XHTML: every page is well-formed, has a title, a language, unique ids, linked style sheets
   that exist, images that exist with an ``alt``.
3. Navigation: contents, page list (complete, in order) and landmarks resolve; ``<guide>``.
4. Links: internal links resolve to a file and an id; no image is unused.
5. Jaypee rules (guideline EPUB items 1-5) and ePub 3 requirements from the profile.
6. Lossless: every content token is written once and in order (the DocBook check's coverage,
   order and character-change logic on the ledger), and the pages re-read from the .epub hold
   exactly the ledger's tokens.
7. EPUBCheck, when Java and the EPUBCheck jar are available; otherwise "not run".
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

from ..engine.text import TOKEN_RE
from . import lossless

NS = {
    "x": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
}
X = "{http://www.w3.org/1999/xhtml}"
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"
XML_PARSER = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
INLINE_TAGS = frozenset({"a", "b", "i", "u", "em", "strong", "sup", "sub", "br"})
MODIFIED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
BLUE = re.compile(r"(?i)^(blue|#0000ff|#00f|#0000ee|#0645ad|rgb\(\s*0\s*,\s*0\s*,\s*255\s*\))$")
CHECK_ITEMS = {
    "package": "ePub 3 package",
    "xhtml": "ePub 3 content documents",
    "navigation": "ePub 3 navigation",
    "links": "ePub 3 links",
    "cover": "epub item 1",
    "link_colour": "epub item 2",
    "half_title": "epub item 3",
    "guide": "epub item 4",
    "toc_two_way": "epub item 5",
    "alt_text": "alt text",
    "accessibility": "ePub accessibility metadata",
    "page_list": "ePub 3 page list",
    "css": "style sheets",
}


class Findings:
    def __init__(self):
        self.checks: dict[str, dict] = {
            name: {"item": item, "checked": 0, "violations": 0, "examples": []}
            for name, item in CHECK_ITEMS.items()
        }

    def check(self, name: str, ok: bool, example: str = ""):
        c = self.checks[name]
        c["checked"] += 1
        if not ok:
            c["violations"] += 1
            if len(c["examples"]) < 10:
                c["examples"].append(example)

    @property
    def violations(self) -> int:
        return sum(c["violations"] for c in self.checks.values())


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _resolve(base: str, href: str) -> tuple[str, str | None]:
    path, _, frag = href.partition("#")
    if not path:
        return base, frag or None
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), path)), frag or None


def _is_inline(el) -> bool:
    name = local(el)
    if name in INLINE_TAGS:
        return True
    if name == "span":
        return (el.get("class") or "").startswith("f-") or el.get(EPUB_TYPE) == "pagebreak"
    return False


def xhtml_tokens(root) -> list[str]:
    """Tokens of a content page in reading order: grouped by block, as the ledger groups
    them. Printed labels written from attributes (span.label), the MathML tree (but not its
    plain-text annotation) and navigation are not source text."""
    body = root.find("x:body", NS)
    segments: list[tuple[int, str]] = []

    def block_of(el):
        while el is not None and _is_inline(el):
            el = el.getparent()
        return id(el)

    def walk(el, skip: bool):
        if not isinstance(el.tag, str):
            return
        name = local(el)
        if name == "math":
            for ann in el.iter("{http://www.w3.org/1998/Math/MathML}annotation"):
                if ann.get("encoding") == "text/plain":
                    segments.append((id(ann), "".join(ann.itertext())))
            return
        here = skip or (name == "span" and "label" in (el.get("class") or "").split())
        if el.text and not here:
            segments.append((block_of(el), el.text))
        for child in el:
            walk(child, here)
            if child.tail and not here:
                segments.append((block_of(el), child.tail))

    if body is not None:
        walk(body, False)
    out: list[str] = []
    group: list[str] = []
    current = None
    for key, text in segments:
        if key != current and group:
            out += TOKEN_RE.findall("".join(group))
            group = []
        current = key
        group.append(text)
    if group:
        out += TOKEN_RE.findall("".join(group))
    return out


def find_epubcheck(explicit: str | os.PathLike | None = None) -> Path | None:
    """The EPUBCheck jar: the given path, $EPUBCHECK_JAR, or tools/epubcheck anywhere above
    this package (also under .cache/tools)."""
    candidates: list[Path] = []
    for value in (explicit, os.environ.get("EPUBCHECK_JAR")):
        if value:
            candidates.append(Path(value).expanduser())
    for parent in Path(__file__).resolve().parents:
        for sub in ("tools/epubcheck", ".cache/tools/epubcheck"):
            base = parent / sub
            if base.is_dir():
                candidates += sorted(base.rglob("epubcheck.jar"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_epubcheck(epub: Path, jar: str | os.PathLike | None = None, timeout: int = 600) -> dict:
    """Run EPUBCheck; ``{"status": "not run", "reason": ...}`` when Java or the jar is
    missing."""
    java = shutil.which("java")
    jar_path = find_epubcheck(jar)
    if java is None:
        return {"status": "not run", "reason": "no Java runtime found (java is not on PATH)"}
    if jar_path is None:
        return {
            "status": "not run",
            "reason": "EPUBCheck jar not found (set EPUBCHECK_JAR or epubcheck_jar in the settings)",  # noqa: E501
        }
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "epubcheck.json"
        try:
            proc = subprocess.run(  # noqa: S603 (fixed argument list, no shell)
                [java, "-jar", str(jar_path), str(epub), "--json", str(report), "--quiet"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "not run", "reason": f"EPUBCheck did not finish in {timeout} s"}
        if not report.is_file():
            return {
                "status": "not run",
                "reason": "EPUBCheck wrote no report: " + (proc.stderr or proc.stdout)[:300],
            }
        data = json.loads(report.read_text("utf-8"))
    messages = data.get("messages") or []
    sev = Counter(m.get("severity") for m in messages)
    version = (data.get("checker") or {}).get("checkerVersion")
    items = [
        {
            "id": m.get("ID"),
            "severity": m.get("severity"),
            "message": m.get("message"),
            "locations": [
                f"{loc.get('path')}:{loc.get('line')}" for loc in (m.get("locations") or [])[:3]
            ],
        }
        for m in messages
        if m.get("severity") in ("ERROR", "FATAL", "WARNING")
    ]
    return {
        "status": "run",
        "version": version,
        "errors": sev.get("ERROR", 0) + sev.get("FATAL", 0),
        "warnings": sev.get("WARNING", 0),
        "messages": items[:100],
    }


# --------------------------------------------------------------------------- our checks


def check_epub(epub: Path, profile_cfg: dict, delivery, doc, book, ledger) -> dict:
    zf = zipfile.ZipFile(epub)
    names = zf.namelist()
    f = Findings()
    parsed: dict[str, etree._Element] = {}

    def parse(name: str):
        if name not in parsed:
            try:
                parsed[name] = etree.fromstring(zf.read(name), XML_PARSER)
            except etree.XMLSyntaxError as exc:
                parsed[name] = None
                f.check("xhtml", False, f"{name}: not well-formed: {exc}")
        return parsed[name]

    # ---- package
    info0 = zf.infolist()[0] if names else None
    f.check(
        "package",
        bool(info0)
        and info0.filename == "mimetype"
        and info0.compress_type == zipfile.ZIP_STORED
        and zf.read("mimetype") == b"application/epub+zip",
        "mimetype is not the first member, stored, with 'application/epub+zip'",
    )
    container = parse("META-INF/container.xml") if "META-INF/container.xml" in names else None
    f.check("package", container is not None, "META-INF/container.xml missing")
    package_path = None
    if container is not None:
        rf = container.find(".//c:rootfile", NS)
        package_path = rf.get("full-path") if rf is not None else None
    f.check("package", bool(package_path) and package_path in names, "package document missing")
    opf = parse(package_path) if package_path in names else None
    counts: dict = {"files": len(names)}
    if opf is None:
        return _finish(f, counts, {"error": "no package document"}, zf, delivery, doc, ledger, None)
    f.check("package", opf.get("version") == "3.0", f"package version {opf.get('version')!r}")
    ident = opf.find("opf:metadata/dc:identifier", NS)
    f.check(
        "package",
        ident is not None and ident.get("id") == opf.get("unique-identifier") and bool(ident.text),
        "unique-identifier does not name a dc:identifier",
    )
    f.check("package", opf.find("opf:metadata/dc:title", NS) is not None, "dc:title missing")
    f.check("package", opf.find("opf:metadata/dc:language", NS) is not None, "dc:language missing")
    mod = [
        m
        for m in opf.findall("opf:metadata/opf:meta", NS)
        if m.get("property") == "dcterms:modified"
    ]
    f.check(
        "package",
        len(mod) == 1 and bool(MODIFIED_RE.match(mod[0].text or "")),
        "dcterms:modified missing or not CCYY-MM-DDThh:mm:ssZ",
    )
    base = posixpath.dirname(package_path)
    manifest = {}
    ids = Counter()
    for item in opf.findall("opf:manifest/opf:item", NS):
        ids[item.get("id")] += 1
        path = posixpath.normpath(posixpath.join(base, item.get("href")))
        manifest[item.get("id")] = (path, item.get("media-type"), item.get("properties") or "")
        f.check("package", path in names, f"manifest file missing: {path}")
    f.check("package", all(n == 1 for n in ids.values()), "manifest ids are not unique")
    listed = {p for p, _, _ in manifest.values()} | {package_path}
    extra = [
        n for n in names if n != "mimetype" and not n.startswith("META-INF/") and n not in listed
    ]
    f.check("package", not extra, f"files not in the manifest: {extra[:5]}")
    spine = [i.get("idref") for i in opf.findall("opf:spine/opf:itemref", NS)]
    f.check("package", all(i in manifest for i in spine), "spine item not in the manifest")
    f.check(
        "package",
        all(manifest[i][1] == "application/xhtml+xml" for i in spine if i in manifest),
        "spine holds a non-XHTML item",
    )
    navs = [p for p, _, props in manifest.values() if "nav" in props.split()]
    f.check("package", len(navs) == 1, f"{len(navs)} navigation documents (need 1)")
    covers = [p for p, _, props in manifest.values() if "cover-image" in props.split()]
    f.check("package", len(covers) <= 1, "more than one cover image")
    spine_paths = [manifest[i][0] for i in spine if i in manifest]
    counts.update(
        spine=len(spine_paths),
        xhtml=sum(1 for p, mt, _ in manifest.values() if mt == "application/xhtml+xml"),
        images=sum(1 for p, mt, _ in manifest.values() if mt.startswith("image/")),
        css=sum(1 for p, mt, _ in manifest.values() if mt == "text/css"),
    )

    # ---- XHTML pages
    pages: dict[str, etree._Element] = {}
    for path, mt, _ in manifest.values():
        if mt != "application/xhtml+xml" or path not in names:
            continue
        root = parse(path)
        if root is None:
            continue
        pages[path] = root
        f.check("xhtml", local(root) == "html", f"{path}: root is not html")
        title = root.find("x:head/x:title", NS)
        f.check(
            "xhtml", title is not None and bool((title.text or "").strip()), f"{path}: no title"
        )
        f.check(
            "xhtml",
            bool(root.get("lang")) and bool(root.get("{http://www.w3.org/XML/1998/namespace}lang")),
            f"{path}: lang/xml:lang missing",
        )
        seen = Counter(e.get("id") for e in root.iter() if isinstance(e.tag, str) and e.get("id"))
        dup = [i for i, n in seen.items() if n > 1]
        f.check("xhtml", not dup, f"{path}: duplicate id {dup[:3]}")
        for link in root.findall("x:head/x:link", NS):
            target = _resolve(path, link.get("href"))[0]
            f.check("css", target in names, f"{path}: style sheet {target} missing")
        f.check(
            "css",
            bool(root.findall("x:head/x:link", NS)),
            f"{path}: links no style sheet",
        )
    ids_in = {
        path: {e.get("id") for e in root.iter() if isinstance(e.tag, str) and e.get("id")}
        for path, root in pages.items()
    }

    # ---- images
    referenced: set[str] = set()
    placeholder = (profile_cfg.get("_alt_placeholder") or "").strip()
    alt_missing = alt_placeholder = 0
    for path, root in pages.items():
        for img in root.iter(X + "img"):
            target = _resolve(path, img.get("src") or "")[0]
            referenced.add(target)
            f.check("xhtml", target in names, f"{path}: image {target} missing")
            has_alt = img.get("alt") is not None
            f.check("alt_text", has_alt, f"{path}: img without alt")
            if has_alt and not img.get("alt").strip():
                alt_missing += 1
            if placeholder and img.get("alt", "").strip() == placeholder:
                alt_placeholder += 1
    for path, mt, _ in manifest.values():
        if mt.startswith("image/"):
            f.check("links", path in referenced, f"image not used by any page: {path}")
    counts["alt_text_placeholders"] = alt_placeholder
    counts["alt_text_empty"] = alt_missing

    # ---- links
    link_count = 0
    for path, root in pages.items():
        for a in root.iter(X + "a"):
            href = a.get("href")
            if not href or re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
                continue
            link_count += 1
            target, frag = _resolve(path, href)
            ok = target in pages and (frag is None or frag in ids_in.get(target, ()))
            f.check("links", ok, f"{path}: link {href!r} does not resolve")
    counts["internal_links"] = link_count

    # ---- navigation, page list, landmarks
    nav_root = pages.get(navs[0]) if navs else None
    toc_entries: list[tuple[str, str | None, str]] = []
    if nav_root is None:
        f.check("navigation", False, "no navigation document")
    else:
        nav_path = navs[0]
        navs_by_type = {n.get(EPUB_TYPE): n for n in nav_root.iter(X + "nav")}
        f.check("navigation", "toc" in navs_by_type, "navigation document has no toc nav")
        for kind in ("toc", "page-list", "landmarks"):
            nav = navs_by_type.get(kind)
            if nav is None:
                continue
            for a in nav.iter(X + "a"):
                target, frag = _resolve(nav_path, a.get("href"))
                ok = target in pages and (frag is None or frag in ids_in.get(target, ()))
                f.check("navigation", ok, f"{kind} entry {a.get('href')!r} does not resolve")
                if kind == "toc":
                    toc_entries.append((target, frag, "".join(a.itertext()).strip()))
        counts["nav_entries"] = len(toc_entries)
        # page list: complete and in spine order
        want = []
        for p in spine_paths:
            if p in pages:
                for s in pages[p].iter(X + "span"):
                    if s.get(EPUB_TYPE) == "pagebreak":
                        want.append((p, s.get("id"), s.get("title")))
        pl = navs_by_type.get("page-list")
        have = []
        if pl is not None:
            for a in pl.iter(X + "a"):
                target, frag = _resolve(nav_path, a.get("href"))
                have.append((target, frag, "".join(a.itertext()).strip()))
        if profile_cfg["nav"]["page_list"]:
            f.check(
                "page_list",
                have == want,
                f"page list differs from page breaks ({len(have)} vs {len(want)})",
            )
            for _, sid, label in want:
                f.check("page_list", bool(label), f"page break {sid} has no label")
        counts["page_list"] = len(have)
        counts["page_breaks"] = len(want)
        lm = navs_by_type.get("landmarks")
        counts["landmarks"] = len(list(lm.iter(X + "a"))) if lm is not None else 0
        if profile_cfg["nav"]["landmarks"]:
            f.check("navigation", lm is not None, "no landmarks nav")
            if lm is not None:
                types = [a.get(EPUB_TYPE) for a in lm.iter(X + "a")]
                f.check("navigation", "bodymatter" in types, "landmarks have no bodymatter")

    # ---- guide (item 4)
    guide = opf.find("opf:guide", NS)
    refs = guide.findall("opf:reference", NS) if guide is not None else []
    counts["guide_references"] = len(refs)
    if profile_cfg["guide"]["enabled"]:
        f.check("guide", len(refs) > 0, "package has no <guide> references")
    for ref in refs:
        target = _resolve(package_path, ref.get("href"))[0]
        f.check("guide", target in names, f"guide reference {ref.get('href')!r} does not resolve")

    # ---- cover (item 1)
    cover_pages = [
        p
        for p, r in pages.items()
        if any(e.get(EPUB_TYPE) == "cover" for e in r.iter(X + "section"))
    ]
    f.check("cover", len(cover_pages) <= 1, f"{len(cover_pages)} cover pages (front cover only)")
    for p, r in pages.items():
        types = " ".join(e.get(EPUB_TYPE) or "" for e in r.iter() if isinstance(e.tag, str))
        title = (r.findtext("x:head/x:title", namespaces=NS) or "") + " " + posixpath.basename(p)
        f.check(
            "cover",
            not re.search(r"(?i)(back|inside)[ _-]?cover", types + " " + title),
            f"{p}: an inside-cover or back-cover page",
        )
    if profile_cfg["cover"]["mode"] == "front_only":
        f.check("cover", len(covers) == len(cover_pages), "cover image and cover page do not agree")

    # ---- link colour (item 2)
    css_text = ""
    for path, mt, _ in manifest.values():
        if mt == "text/css" and path in names:
            text = zf.read(path).decode("utf-8")
            css_text += text
            f.check(
                "css",
                text.count("{") == text.count("}") and "@LINK_COLOUR@" not in text,
                f"{path}: unbalanced or unreplaced",
            )
    rule = re.search(r"(?s)(?:^|[}\s])a\s*\{([^}]*)\}", css_text)
    colour = re.search(r"(?i)(?<![-\w])color\s*:\s*([^;}]+)", rule.group(1)) if rule else None
    f.check("link_colour", colour is not None, "no `a { color: ... }` rule in the style sheets")
    if colour:
        f.check(
            "link_colour",
            not BLUE.match(colour.group(1).strip()),
            f"links are blue: {colour.group(1)}",
        )
    inline_colour = [
        p
        for p, r in pages.items()
        for a in r.iter(X + "a")
        if "color" in (a.get("style") or "").lower()
    ]
    f.check("link_colour", not inline_colour, "inline colour on a link")

    # ---- half title (item 3)
    heading = profile_cfg["half_title"]["heading"]
    for p, r in pages.items():
        if any(e.get(EPUB_TYPE) == "halftitlepage" for e in r.iter(X + "section")):
            h1 = r.find(".//x:h1", NS)
            f.check(
                "half_title",
                h1 is not None and "".join(h1.itertext()).strip() == heading,
                f"{p}: heading is not {heading!r}",
            )
            f.check(
                "half_title",
                (r.findtext("x:head/x:title", namespaces=NS) or "").strip() == heading,
                f"{p}: <title> is not {heading!r}",
            )
    if nav_root is not None:
        for a in nav_root.iter(X + "a"):
            f.check(
                "half_title",
                not re.search(r"(?i)\bhalftitle\b", "".join(a.itertext())),
                f"navigation label {''.join(a.itertext())!r}",
            )
    f.check(
        "half_title",
        not re.search(
            r"(?i)\bhalftitle\b",
            "\n".join((r.findtext("x:head/x:title", namespaces=NS) or "") for r in pages.values()),
        ),
        "a page <title> says 'Halftitle'",
    )

    # ---- two-way TOC links (item 5)
    nav_cfg = profile_cfg["nav"]
    toc_file = profile_cfg["package"]["toc_file"]
    toc_doc = None
    if toc_file:
        toc_doc = next((p for p in pages if p.endswith("/" + toc_file) or p == toc_file), None)
    return_mode = nav_cfg["toc_return"]
    if return_mode != "none":
        heading_ids = {}
        for target, frag, _text in toc_entries:
            heading_ids[(target, frag)] = True
        returns = 0
        for target, frag, text in toc_entries:
            root = pages.get(target)
            h = None
            if root is not None and frag:
                h = next(
                    (e for e in root.iter() if isinstance(e.tag, str) and e.get("id") == frag), None
                )
            link = None
            if h is not None:
                link = next(
                    (a for a in h.iter(X + "a") if "toc-return" in (a.get("class") or "").split()),
                    None,
                )
            ok = link is not None
            if ok:
                returns += 1
                dest, dfrag = _resolve(target, link.get("href"))
                good_dest = dest in pages and (
                    toc_doc is None or dest == toc_doc or dest == navs[0]
                )
                if return_mode == "container":
                    good_dest = good_dest and dfrag == nav_cfg["toc_container_id"]
                else:
                    good_dest = (
                        good_dest and dfrag in ids_in.get(dest, ()) and dfrag == f"toc-{frag}"
                    )
                ok = good_dest
            f.check(
                "toc_two_way", ok, f"heading {text!r} ({target}#{frag}) has no valid return link"
            )
        counts["toc_return_links"] = returns
    if toc_doc is not None:
        f.check(
            "toc_two_way",
            any(
                e.get("id") == nav_cfg["toc_container_id"]
                for e in pages[toc_doc].iter()
                if isinstance(e.tag, str)
            ),
            f"{toc_doc} has no #{nav_cfg['toc_container_id']} container",
        )

    # ---- accessibility metadata
    if profile_cfg["accessibility"]["enabled"]:
        props = {m.get("property"): m.text for m in opf.findall("opf:metadata/opf:meta", NS)}
        for prop in (
            "schema:accessMode",
            "schema:accessModeSufficient",
            "schema:accessibilityFeature",
            "schema:accessibilityHazard",
            "schema:accessibilitySummary",
        ):
            f.check("accessibility", prop in props, f"{prop} missing")
        features = [
            m.text
            for m in opf.findall("opf:metadata/opf:meta", NS)
            if m.get("property") == "schema:accessibilityFeature"
        ]
        has_math = any(
            local(e) == "math" for r in pages.values() for e in r.iter() if isinstance(e.tag, str)
        )
        f.check(
            "accessibility",
            has_math == ("MathML" in features),
            "MathML feature does not match the content",
        )
        f.check(
            "accessibility",
            "alternativeText" not in features or (alt_placeholder == 0 and alt_missing == 0),
            "alternativeText is claimed but images lack real alt text",
        )
        counts["accessibility_features"] = sorted(features)
    counts["element_counts"] = _element_counts(pages)
    used = Counter()
    for r in pages.values():
        for e in r.iter():
            for c in (e.get("class") or "").split() if isinstance(e.tag, str) else ():
                used[c] += 1
    counts["css_classes_used"] = dict(sorted(used.items()))
    counts["css_classes_unstyled"] = sorted(
        c for c in used if not re.search(r"\." + re.escape(c) + r"(?![\w-])", css_text)
    )
    return _finish(f, counts, None, zf, delivery, doc, ledger, (pages, spine_paths))


def _has_content_images(pages) -> bool:
    return any(True for r in pages.values() for img in r.iter(X + "img"))


def _element_counts(pages) -> dict[str, int]:
    c = Counter()
    for r in pages.values():
        for e in r.iter():
            if isinstance(e.tag, str):
                c[local(e)] += 1
    return dict(sorted(c.items()))


def _finish(f: Findings, counts: dict, error, zf, delivery, doc, ledger, parsed) -> dict:
    result = {
        "violations": f.violations,
        "checks": f.checks,
        "counts": counts,
    }
    if parsed is None:
        result["lossless"] = {"missing": 0, "extra": 0, "error": "package unreadable"}
        return result
    pages, spine_paths = parsed
    cov = lossless.coverage(doc, ledger)
    actual: list[str] = []
    for path in spine_paths:
        if path in pages and path not in delivery.generated_files:
            actual += xhtml_tokens(pages[path])
    expected = lossless._ledger_tokens(ledger)
    if expected == actual:
        out = {"xhtml_tokens": len(actual), "matches_ledger": True, "differences": 0}
    else:
        import difflib

        sm = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
        diffs = [op for op in sm.get_opcodes() if op[0] != "equal"]
        out = {
            "xhtml_tokens": len(actual),
            "ledger_tokens": len(expected),
            "matches_ledger": False,
            "differences": len(diffs),
            "xml_extra": sum(
                j2 - j1 for op, i1, i2, j1, j2 in diffs if op in ("insert", "replace")
            ),
            "xml_missing": sum(
                i2 - i1 for op, i1, i2, j1, j2 in diffs if op in ("delete", "replace")
            ),
            "examples": [
                {
                    "op": op,
                    "ledger": expected[i1 : min(i2, i1 + 8)],
                    "xml": actual[j1 : min(j2, j1 + 8)],
                }
                for op, i1, i2, j1, j2 in diffs[:10]
            ],
        }
    result["lossless"] = {
        "missing": cov["missing"] + out.get("xml_missing", 0),
        "extra": cov["extra"] + out.get("xml_extra", 0),
        "coverage": cov,
        "order": lossless.order(ledger),
        "output": out,
        "split_words": lossless.split_words(doc, actual),
        "character_changes": lossless.character_changes(doc, ledger),
        "generated_text": Counter(e.note for e in ledger.entries if e.kind == "generated"),
        "settings_text": sorted({e.note for e in ledger.entries if e.kind == "settings"}),
    }
    return result
