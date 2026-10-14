"""Step 12: reference figure inventory per book (evaluation data; the XML is read only).

Walks the registered reference XML in document order, keeps the page of the last preceding
page marker (marker paths are mapped to PDF pages by the committed derived gold), and records
each figure-like element with its images, captions, credits and image descriptions. Element
names below are evaluation vocabulary for the four registered dialects, never converter
source. Credits are the reference's credit-class inline spans; their enclosing unit path is
recorded so derived-gold units can be matched.
"""

# ruff: noqa: E402
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path

from book_core.reference.xml_reader import load_tree, local_name

GOLD = ROOT / "backend/tests/gold_derived"
XML_KEYS = {
    "spanish_us_history": "spanish_xml",
    "immigrant_children": "immigrant_xml",
    "art_therapy_index": "art_index_xml",
    "medical_anatomy": "medical_xml",
}
# Evaluation vocabulary: figure containers and their parts in the registered dialects.
FIGURE_ELEMENTS = {"imggroup", "figure", "informalfigure"}
IMAGE_ELEMENTS = {"img", "imagedata"}
CAPTION_ELEMENTS = {"caption"}
DESCRIPTION_ELEMENTS = {"prodnote", "textobject"}
METADATA_PARENTS = {"info"}


def _markers(book):
    rows = json.loads((GOLD / book / "page_markers.json").read_text("utf-8"))
    return {row["path"]: row for row in rows}


def _text(node):
    return " ".join("".join(node.itertext()).split())


def inventory(book):
    """Reference figures in document order with their PDF page (or None)."""
    root, _ = load_tree(reference_path(XML_KEYS[book]).read_bytes())
    markers = _markers(book)
    figures, credits, loose_images = [], [], []
    state = {"page": None, "label": None, "low": False}

    def visit(node, path, ancestors):
        counts = Counter()
        for child in node:
            if not isinstance(child.tag, str):
                continue
            name = local_name(child.tag)
            counts[name] += 1
            child_path = f"{path}/{name}[{counts[name]}]"
            marker = markers.get(child_path)
            if marker is not None:
                # Unlocated markers keep their aligned page, flagged as low confidence.
                state["page"] = marker["pdf_page"]
                state["label"] = marker["label"]
                state["low"] = not marker.get("located", True) or marker.get("low_confidence")
            if name in FIGURE_ELEMENTS and not any(a in FIGURE_ELEMENTS for a in ancestors):
                figures.append(_figure(child, child_path, name, ancestors, state))
            elif name in IMAGE_ELEMENTS and not any(a in FIGURE_ELEMENTS for a in ancestors):
                # A media object outside any figure container (DocBook front matter, inline).
                loose_images.append(
                    {
                        "path": child_path,
                        "page": state["page"],
                        "label": state["label"],
                        "file": child.get("src") or child.get("fileref"),
                        "metadata": any(a in METADATA_PARENTS for a in ancestors),
                        "inline": "inlinemediaobject" in ancestors,
                    }
                )
            if name == "span" and child.get("class") == "credit":
                credits.append(
                    {
                        "unit_path": _unit_path(child_path),
                        "page": state["page"],
                        "label": state["label"],
                        "text": _text(child)[:160],
                        "in_figure": any(a in FIGURE_ELEMENTS for a in ancestors),
                    }
                )
            visit(child, child_path, [*ancestors, name])

    top = local_name(root.tag)
    visit(root, f"/{top}[1]", [top])
    return {"figures": figures, "credits": credits, "loose_images": loose_images}


def _unit_path(path):
    """The block element that owns an inline credit (its derived-gold unit path)."""
    parts = path.split("/")
    while parts and parts[-1].split("[")[0] in {"span", "strong", "em", "b", "i", "sup"}:
        parts.pop()
    return "/".join(parts)


def _figure(node, path, name, ancestors, state):
    images, captions, descriptions, titles = [], [], [], []
    for element in node.iter():
        local = local_name(element.tag)
        if local in IMAGE_ELEMENTS:
            images.append(element.get("src") or element.get("fileref"))
        elif local in CAPTION_ELEMENTS:
            captions.append(_text(element)[:200])
        elif local in DESCRIPTION_ELEMENTS:
            descriptions.append(_text(element)[:200])
    for child in node:
        if local_name(child.tag) == "title":
            titles.append(_text(child)[:200])
    return {
        "path": path,
        "element": name,
        "page": state["page"],
        "label": state["label"],
        "images": images,
        "captions": captions,
        "titles": titles,
        "descriptions": descriptions,
        "metadata": any(a in METADATA_PARENTS for a in ancestors),
        "low_confidence_page": bool(state["low"]),
    }


def summary(book, data=None):
    data = data or inventory(book)
    figures = data["figures"]
    per_page = defaultdict(lambda: Counter())
    for figure in figures:
        row = per_page[figure["page"]]
        row["figures"] += 1
        row["images"] += len(figure["images"])
        row["captions"] += len(figure["captions"]) + len(figure["titles"])
    for credit in data["credits"]:
        per_page[credit["page"]]["credits"] += 1
    for image in data["loose_images"]:
        per_page[image["page"]]["loose_images"] += 1
    uses = defaultdict(set)
    for figure in figures:
        for name in figure["images"]:
            uses[name].add(figure["page"])
    for image in data["loose_images"]:
        uses[image["file"]].add(image["page"])
    # A file placed on several pages is a shared icon, not a page image.
    repeated = {name for name, pages in uses.items() if len(pages) > 1}
    page_images = Counter()
    for name, pages in uses.items():
        if name not in repeated:
            page_images[next(iter(pages))] += 1
    for page, count in page_images.items():
        per_page[page]["page_images"] += count
    return {
        "distinct_page_images": sum(page_images.values()),
        "repeated_icon_files": len(repeated),
        "figures_low_confidence_page": sum(f["low_confidence_page"] for f in figures),
        "figures": len(figures),
        "figures_by_element": dict(Counter(f["element"] for f in figures)),
        "images_in_figures": sum(len(f["images"]) for f in figures),
        "figure_groups": sum(len(f["images"]) > 1 for f in figures),
        "captions": sum(len(f["captions"]) for f in figures),
        "titled_figures": sum(bool(f["titles"]) for f in figures),
        "described_figures": sum(bool(f["descriptions"]) for f in figures),
        "credits": len(data["credits"]),
        "credits_inside_figures": sum(c["in_figure"] for c in data["credits"]),
        "loose_images": len(data["loose_images"]),
        "loose_metadata_images": sum(i["metadata"] for i in data["loose_images"]),
        "loose_inline_images": sum(i["inline"] for i in data["loose_images"]),
        "figures_without_page": sum(f["page"] is None for f in figures),
        "pages_with_figures": sum(1 for p, r in per_page.items() if p and r["figures"]),
        "per_page": {str(p): dict(r) for p, r in sorted(per_page.items(), key=lambda x: x[0] or 0)},
    }


if __name__ == "__main__":
    for name in XML_KEYS:
        result = summary(name)
        print(name, {k: v for k, v in result.items() if k != "per_page"})
