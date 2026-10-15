"""Provisional math gold from a math-scoring reference (always human_approved = false).

The reference is read with a math-only dialect profile (``reference_dialects/
math_dialects.json``): every equation becomes a *slot* between the reference text tokens
around it, and the reference text is aligned to the retained PDF tokens with the unchanged
reference aligner. An equation is then located on the PDF from its aligned neighbours: the
native objects (vector glyphs, images) and unaligned PDF tokens that lie in PDF order between
the last aligned token before the slot and the first aligned token after it.

This module only reads evidence. Element names come from the profile data; nothing here is
converter source, and the dialect is never used for headings, paragraphs or lists.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from book_core.ledger.tokenization import TOKEN_PATTERN, line_tokens
from book_core.model.common import BBox
from book_core.model.spans import ExtractedPage
from book_core.reference.aligner import AlignmentResult
from book_core.reference.dialects import SYNTHETIC_CONTAINER, Dialect
from book_core.reference.xml_reader import Element, ReferenceDocument, XmlToken

MATH_GOLD_VERSION = "math-gold-1"
PROFILE = Path(__file__).resolve().parents[3] / "reference_dialects" / "math_dialects.json"
# Located objects must be glyph-scale: at most this many median text sizes tall.
GLYPH_HEIGHT_SIZES = 8.0
# An object belongs to a line when its centre lies in the line band widened by this share.
LINE_BAND_SHARE = 0.25


def profile_data(path: Path = PROFILE) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def profile_sha256(data: Mapping) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _namespace(tag) -> str:
    return tag[1:].split("}", 1)[0] if isinstance(tag, str) and tag.startswith("{") else ""


def dialect_of(spec: Mapping) -> Dialect:
    kind_of = {name: kind for kind, names in spec["unit_kinds"].items() for name in names}
    return Dialect(
        name=spec["name"],
        detect=spec.get("detect", {}),
        page_marker_elements=frozenset(spec["page_marker_elements"]),
        inline_elements=frozenset(spec["inline_elements"]),
        kind_of=kind_of,
        containers=frozenset(spec["containers"]),
        sectioning=frozenset(spec["sectioning"]),
        list_containers=frozenset(spec["list_containers"]),
        table_containers=frozenset(spec["table_containers"]),
        row_elements=frozenset(spec["row_elements"]),
        declared_heading_levels={},
        zones=dict(spec["zones"]),
    )


@dataclass(frozen=True)
class MathSlot:
    """One reference equation in reference order; tokens are reference token indices."""

    index: int
    module: str
    ordinal: int  # equation ordinal inside its module
    path: str
    anchor_id: str | None  # nearest id attribute on the equation or an ancestor
    presentation: str  # inline | display
    token_before: int  # last reference token before the slot, -1 when none
    token_after: int  # first reference token after the slot, len(tokens) when none
    unit: int  # enclosing reference unit element
    contexts: tuple[str, ...]
    mathml_sha256: str
    leaf_text: str


@dataclass
class MathReference:
    document: ReferenceDocument
    slots: list[MathSlot]
    mathml: dict[int, str]  # canonical serialization per slot
    sources: dict[str, str]  # module -> SHA-256 of its file
    profile_sha256: str


def _canonical_math(node: ET.Element) -> str:
    """Namespace-free canonical serialization (element order and text are kept)."""

    def build(item: ET.Element) -> ET.Element:
        copy = ET.Element(_local(item.tag), {_local(k): v for k, v in sorted(item.attrib.items())})
        copy.text = (item.text or "").strip() or None
        for child in item:
            if isinstance(child.tag, str):
                copy.append(build(child))
        return copy

    return ET.tostring(build(node), encoding="unicode")


def read_math_reference(root: Path, data: Mapping | None = None) -> MathReference:
    """Read a collection in its declared module order; equations become slots."""
    data = data or profile_data()
    spec = data["dialects"][0]
    collection, math = spec["collection"], spec["math"]
    dialect = dialect_of(spec)
    root = Path(root)
    collection_files = sorted((root / "collections").glob("*.xml"))
    if len(collection_files) != 1:
        raise ValueError("Expected exactly one collection file")
    tree = ET.parse(collection_files[0]).getroot()
    sequence: list[tuple[str, object]] = []
    for node in tree.iter():
        if _namespace(node.tag) != collection["namespace"]:
            continue
        if _local(node.tag) == collection["module_element"]:
            sequence.append(("module", node.get(collection["module_attribute"])))
        elif _local(node.tag) == collection["subcollection_element"]:
            title = next(
                (
                    child
                    for child in node
                    if _local(child.tag) == collection["title_element"]
                    and _namespace(child.tag) == collection["title_namespace"]
                ),
                None,
            )
            if title is not None and title.text:
                sequence.append(("title", title.text))
    excluded = set(spec["excluded_elements"])
    context_of = {name: kind for kind, names in spec["context_kinds"].items() for name in names}
    elements: list[Element] = []
    pieces: list[tuple[str, int]] = []  # owner -1: hard boundary; -2: slot
    slot_drafts: list[dict] = []
    sources: dict[str, str] = {}
    mathml: dict[int, str] = {}

    def add(name, parent, path, depth, counts, attributes) -> tuple[int, str]:
        counts[name] = counts.get(name, 0) + 1
        own = f"{path}/{name}[{counts[name]}]"
        elements.append(Element(len(elements), name, own, parent, depth, attributes))
        return len(elements) - 1, own

    def leaves(node: ET.Element) -> str:
        return " ".join(
            "".join(item.itertext()).strip()
            for item in node.iter()
            if _local(item.tag) in math["leaf_elements"] and "".join(item.itertext()).strip()
        )

    def visit(node, index, own, depth, module, ids, ordinals):
        inline = elements[index].name in dialect.inline_elements
        if not inline:
            pieces.append(("", -1))
        if node.text:
            pieces.append((node.text, index))
        counts: dict[str, int] = {}
        for child in node:
            if not isinstance(child.tag, str):
                if child.tail:
                    pieces.append((child.tail, index))
                continue
            name = _local(child.tag)
            if name in excluded:
                pass
            elif _namespace(child.tag) == math["namespace"] and name == math["element"]:
                chain = [index, *_chain_of(index)]
                names = [elements[i].name for i in chain]
                display = child.get(math["display_attribute"]) in math["display_values"] or any(
                    n in math["display_containers"] for n in names
                )
                serial = _canonical_math(child)
                slot = len(slot_drafts)
                mathml[slot] = serial
                slot_drafts.append(
                    {
                        "module": module,
                        "ordinal": ordinals[0],
                        "path": f"{own}/{name}[{ordinals[0] + 1}]",
                        "anchor_id": child.get("id")
                        or next((ids[i] for i in chain if ids.get(i)), None),
                        "presentation": "display" if display else "inline",
                        "element": index,
                        "contexts": tuple(
                            sorted({context_of[n] for n in names if n in context_of})
                        ),
                        "mathml_sha256": hashlib.sha256(serial.encode()).hexdigest(),
                        "leaf_text": unicodedata.normalize("NFKC", leaves(child)),
                    }
                )
                ordinals[0] += 1
                pieces.append(("", -1))
                pieces.append(("", -2 - slot))
                pieces.append(("", -1))
            else:
                attributes = {_local(k): v for k, v in child.attrib.items()}
                child_index, child_path = add(name, index, own, depth + 1, counts, attributes)
                if child.get("id"):
                    ids[child_index] = child.get("id")
                visit(child, child_index, child_path, depth + 1, module, ids, ordinals)
            if child.tail:
                pieces.append((child.tail, index))
        if not inline:
            pieces.append(("", -1))

    def _chain_of(index):
        chain, parent = [], elements[index].parent
        while parent is not None:
            chain.append(parent)
            parent = elements[parent].parent
        return chain

    top, top_path = add(SYNTHETIC_CONTAINER, None, "", 0, {}, {})
    counts: dict[str, int] = {}
    for kind, value in sequence:
        if kind == "title":
            title, _ = add("title", top, top_path, 1, counts, {})
            pieces.append(("", -1))
            pieces.append((value, title))
            pieces.append(("", -1))
            continue
        path = root / collection["module_path"].format(module=value)
        raw = path.read_bytes()
        sources[value] = hashlib.sha256(raw).hexdigest()
        module_root = ET.fromstring(raw)
        name = _local(module_root.tag)
        index, own = add(name, top, f"{top_path}/{value}", 1, {}, {})
        visit(module_root, index, own, 1, value, {}, [0])

    tokens: list[XmlToken] = []
    run_text: list[str] = []
    run_owner: list[int] = []
    slot_tokens: dict[int, int] = {}

    def flush():
        text = "".join(run_text)
        for match in TOKEN_PATTERN.finditer(text):
            tokens.append(XmlToken(len(tokens), match.group(), run_owner[match.start()], 0))
        run_text.clear()
        run_owner.clear()

    for text, owner in pieces:
        if owner <= -2:
            flush()
            slot_tokens[-2 - owner] = len(tokens)
            continue
        if owner < 0:
            flush()
            continue
        normalized = unicodedata.normalize("NFKC", text)
        run_text.append(normalized)
        run_owner.extend([owner] * len(normalized))
    flush()
    element_tuple = tuple(elements)
    units = tuple(dialect.unit_of(token.element, element_tuple) for token in tokens)
    document = ReferenceDocument(
        sha256=hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode() + collection_files[0].read_bytes()
        ).hexdigest(),
        dialect=dialect,
        repairs=(),
        elements=element_tuple,
        tokens=tuple(tokens),
        markers=(),
        segment_count=1,
        units=units,
    )
    slots = [
        MathSlot(
            index=number,
            module=draft["module"],
            ordinal=draft["ordinal"],
            path=draft["path"],
            anchor_id=draft["anchor_id"],
            presentation=draft["presentation"],
            token_before=slot_tokens[number] - 1,
            token_after=slot_tokens[number],
            unit=dialect.unit_of(draft["element"], element_tuple),
            contexts=draft["contexts"],
            mathml_sha256=draft["mathml_sha256"],
            leaf_text=draft["leaf_text"],
        )
        for number, draft in enumerate(slot_drafts)
    ]
    return MathReference(document, slots, mathml, sources, profile_sha256(data))


# --- PDF side --------------------------------------------------------------------------


@dataclass(frozen=True)
class PageObjectBox:
    """A native non-text object (drawing or image) as the gold sees it."""

    id: str
    kind: str
    bbox: BBox
    shape: str = "other"  # outline | bar | image | other


def object_shape(obj) -> str:
    """A filled outline (a drawn glyph), a thin horizontal bar, an image, or other art."""
    if obj.kind == "image":
        return "image"
    if obj.kind != "drawing" or obj.fill is None or obj.bbox is None:
        return "other"
    operators = [item.operator for item in obj.path_items]
    height, width = obj.bbox.y1 - obj.bbox.y0, obj.bbox.x1 - obj.bbox.x0
    if operators in (["re"], ["l"], ["qu"]) and width > 3 * height:
        return "bar"
    if "c" in operators or len(operators) >= 4:
        return "outline"
    return "other"


@dataclass
class PageGeometry:
    page: int
    token_boxes: list[BBox]  # per retained token ordinal
    token_lines: list[int]  # retained line ordinal per token
    line_boxes: list[BBox]
    median_size: float
    objects: list[PageObjectBox] = field(default_factory=list)
    object_position: dict[str, int] = field(default_factory=dict)  # tokens preceding it


def token_geometry(page: ExtractedPage) -> tuple[list[BBox], list[int], list[BBox], float]:
    """Approximate token boxes from their owning spans (character share of the span width)."""
    store = page.store
    boxes: list[BBox] = []
    token_lines: list[int] = []
    line_boxes: list[BBox] = []
    sizes = [span.size for span in store.spans.values() if span.raw_text.strip()]
    for line in store.lines:
        raw = store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        ordinal = len(line_boxes)
        line_boxes.append(line.bbox)
        offsets, start = {}, 0
        for sid in line.span_ids:
            length = len(store.spans[sid].raw_text)
            offsets[sid] = (start, start + length)
            start += length
        normalized = unicodedata.normalize("NFKC", raw)
        matches = list(TOKEN_PATTERN.finditer(normalized))
        found = list(line_tokens(store, line))
        scale = len(raw) / max(1, len(normalized))
        for token, match in zip(found, matches, strict=True):
            parts = []
            for sid in token.span_ids:
                span = store.spans[sid]
                first, last = offsets[sid]
                width = span.bbox.x1 - span.bbox.x0
                length = max(1, last - first)
                a = min(max(match.start() * scale, first), last) - first
                b = min(max(match.end() * scale, first), last) - first
                parts.append(
                    BBox(
                        x0=span.bbox.x0 + width * a / length,
                        y0=span.bbox.y0,
                        x1=span.bbox.x0 + width * max(b, a) / length,
                        y1=span.bbox.y1,
                    )
                )
            boxes.append(
                BBox(
                    x0=min(p.x0 for p in parts),
                    y0=min(p.y0 for p in parts),
                    x1=max(p.x1 for p in parts),
                    y1=max(p.y1 for p in parts),
                )
                if parts
                else line.bbox
            )
            token_lines.append(ordinal)
    return boxes, token_lines, line_boxes, statistics.median(sizes) if sizes else 10.0


def _center(box: BBox) -> tuple[float, float]:
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def place_objects(geometry: PageGeometry) -> None:
    """Position of each object in PDF token order: the count of tokens that precede it.

    An object on a text line follows the tokens of that line whose centre lies left of its
    centre (writing direction of these books; a later step generalises it). An object between
    lines follows the last token of the nearest line above that overlaps it horizontally.
    """
    by_line: dict[int, list[int]] = defaultdict(list)
    for ordinal, line in enumerate(geometry.token_lines):
        by_line[line].append(ordinal)
    for item in geometry.objects:
        cx, cy = _center(item.bbox)
        # Text beside an equation is often split into separate native lines around it, so
        # every line whose band holds the object's centre is considered (a visual band).
        band = []
        for number, box in enumerate(geometry.line_boxes):
            pad = (box.y1 - box.y0) * LINE_BAND_SHARE
            if box.y0 - pad <= cy <= box.y1 + pad:
                band.extend(by_line[number])
        if band:
            left = [o for o in band if _center(geometry.token_boxes[o])[0] < cx]
            if left:
                nearest = max(left, key=lambda o: _center(geometry.token_boxes[o])[0])
                geometry.object_position[item.id] = nearest + 1
            else:
                first = min(band, key=lambda o: _center(geometry.token_boxes[o])[0])
                geometry.object_position[item.id] = first
            continue
        above = [
            number
            for number, box in enumerate(geometry.line_boxes)
            if box.y1 <= cy and min(box.x1, item.bbox.x1) > max(box.x0, item.bbox.x0)
        ]
        if above:
            line = max(above, key=lambda n: geometry.line_boxes[n].y1)
            if by_line[line]:
                geometry.object_position[item.id] = by_line[line][-1] + 1
                continue
        below = [
            number
            for number, box in enumerate(geometry.line_boxes)
            if box.y0 >= cy and by_line[number]
        ]
        if below:
            line = min(below, key=lambda n: geometry.line_boxes[n].y0)
            geometry.object_position[item.id] = by_line[line][0]
        else:
            geometry.object_position[item.id] = len(geometry.token_boxes)


def glyph_scale(item: PageObjectBox, geometry: PageGeometry) -> bool:
    """A drawn glyph or image at text scale holding no text (bars are joined separately)."""
    height = item.bbox.y1 - item.bbox.y0
    return (
        item.shape in {"outline", "image"}
        and height <= GLYPH_HEIGHT_SIZES * geometry.median_size
        and not any(item.bbox.contains_center(box) for box in geometry.line_boxes)
    )


def _bars(bars, glyph_items, size):
    """Bars with glyphs right above and below (fractions) or right below (overlines)."""
    chosen = []
    for bar in bars:
        box = bar.bbox
        above = below = False
        for item in glyph_items:
            if min(item.bbox.x1, box.x1) - max(item.bbox.x0, box.x0) <= 0:
                continue
            if 0 <= box.y0 - item.bbox.y1 <= 1.2 * size:
                above = True
            elif 0 <= item.bbox.y0 - box.y1 <= 1.2 * size:
                below = True
        if below and (above or box.y1 - box.y0 <= 0.2 * size):
            chosen.append(bar)
    return chosen


@dataclass
class GoldEquation:
    slot: int
    module: str
    path: str
    anchor_id: str | None
    presentation: str
    contexts: list[str]
    mathml_sha256: str
    leaf_text: str
    status: str
    page: int | None = None
    bbox: list[float] | None = None
    object_ids: list[str] = field(default_factory=list)
    token_ordinals: list[int] = field(default_factory=list)  # unaligned PDF tokens in the gap
    anchors: list[list[int]] = field(default_factory=list)  # [page, ordinal] before / after
    anchor_confidence: float = 0.0
    shared_gap: int = 1
    geometric_presentation: str | None = None
    method: str = ""
    glyphs_expected: int = 0
    glyph_count_fits: bool | None = None
    # Scoring uses verified rows: located and drawn with as many glyphs as the reference
    # equation has leaf characters (a manual check found the others unreliable).
    verified: bool = False


def _anchor(result: AlignmentResult, start: int, step: int, limit: int):
    index, seen = start, 0
    while 0 <= index < len(result.xml_page) and seen < limit:
        if result.xml_page[index] >= 0:
            return (
                result.pages[result.xml_page[index]],
                result.xml_ordinal[index],
                result.xml_confidence[index],
                abs(index - start),
            )
        index += step
        seen += 1
    return None


def locate(
    reference: MathReference,
    result: AlignmentResult,
    geometry: Mapping[int, PageGeometry],
    *,
    anchor_reach: int = 6,
) -> list[GoldEquation]:
    """Locate every slot; ``status`` names why a slot could not be located."""
    pdf_free = {
        page: [x < 0 for x in result.pdf_xml[index]] for index, page in enumerate(result.pages)
    }
    drafts: list[GoldEquation] = []
    gaps: dict[tuple, list[int]] = defaultdict(list)
    for slot in reference.slots:
        gold = GoldEquation(
            slot=slot.index,
            module=slot.module,
            path=slot.path,
            anchor_id=slot.anchor_id,
            presentation=slot.presentation,
            contexts=list(slot.contexts),
            mathml_sha256=slot.mathml_sha256,
            leaf_text=slot.leaf_text,
            status="",
        )
        drafts.append(gold)
        before = _anchor(result, slot.token_before, -1, anchor_reach)
        after = _anchor(result, slot.token_after, 1, anchor_reach)
        if before is None or after is None:
            gold.status = "anchor_unaligned"
            continue
        if before[0] != after[0]:
            gold.anchors = [list(before[:2]), list(after[:2])]
            if after[0] != before[0] + 1:
                gold.status = "anchors_on_different_pages"
                continue
            # A page break inside the gap: the equation ends one page or opens the next.
            tail = geometry.get(before[0])
            head = geometry.get(after[0])
            sides = []
            if tail is not None:
                sides.append((before[0], before[1], len(tail.token_boxes)))
            if head is not None:
                sides.append((after[0], -1, after[1]))
            holding = [
                side
                for side in sides
                if any(
                    side[1] < geometry[side[0]].object_position.get(item.id, -2) <= side[2]
                    and glyph_scale(item, geometry[side[0]])
                    for item in geometry[side[0]].objects
                )
            ]
            if len(holding) != 1:
                gold.status = "anchors_on_different_pages"
                continue
            gold.page = holding[0][0]
            skipped = before[3] + after[3]
            gold.anchor_confidence = round(min(before[2], after[2]) * 0.8 * (0.9**skipped), 4)
            gaps[holding[0]].append(slot.index)
            continue
        if before[1] >= after[1]:
            gold.status = "anchor_order_conflict"
            gold.anchors = [list(before[:2]), list(after[:2])]
            continue
        gold.page = before[0]
        gold.anchors = [list(before[:2]), list(after[:2])]
        # Skipped reference tokens lower confidence: the gap may hold their text.
        skipped = before[3] + after[3]
        gold.anchor_confidence = round(min(before[2], after[2]) * (0.9**skipped), 4)
        gaps[(gold.page, before[1], after[1])].append(slot.index)
    for (page, first, last), members in gaps.items():
        page_geometry = geometry.get(page)
        if page_geometry is None:
            for slot in members:
                drafts[slot].status = "page_geometry_missing"
            continue
        in_gap = [
            item
            for item in page_geometry.objects
            if first < page_geometry.object_position.get(item.id, -1) <= last
        ]
        objects = [item for item in in_gap if glyph_scale(item, page_geometry)]
        objects += _bars(
            [item for item in in_gap if item.shape == "bar"], objects, page_geometry.median_size
        )
        free = [o for o in range(first + 1, last) if pdf_free[page][o]]
        # Unaligned text in a gap is equation text only when it sits with the drawn glyphs,
        # or, without glyphs, when there is no more of it than the equation's own leaves.
        size = page_geometry.median_size
        if objects:
            union = BBox(
                x0=min(i.bbox.x0 for i in objects) - 2 * size,
                y0=min(i.bbox.y0 for i in objects) - 0.5 * size,
                x1=max(i.bbox.x1 for i in objects) + 2 * size,
                y1=max(i.bbox.y1 for i in objects) + 0.5 * size,
            )
            free = [o for o in free if union.contains_center(page_geometry.token_boxes[o])]
        else:
            leaves = sum(len(TOKEN_PATTERN.findall(drafts[slot].leaf_text)) for slot in members)
            if len(free) > max(3, 2 * leaves):
                for slot in members:
                    drafts[slot].status = "gap_text_ambiguous"
                continue
        if not objects and not free:
            for slot in members:
                drafts[slot].status = "nothing_in_gap"
            continue
        groups = _components(objects, free, page_geometry)
        by_count = False
        if len(groups) > len(members) == 1:
            # One equation, several groups: keep the only group whose glyph count matches
            # the equation's leaf characters; otherwise the gap stays unresolved.
            expected = _expected_glyphs(drafts[members[0]].leaf_text)
            fitting = [
                g
                for g in groups
                if _count_fits(len(g[0]) + len(g[1]), expected)
                and sum(item.shape == "outline" for item in g[0]) >= 0.7 * (len(g[0]) + len(g[1]))
            ]
            groups = fitting if len(fitting) == 1 else None
            by_count = groups is not None
        elif len(groups) != len(members):
            groups = (
                _split(objects, free, page_geometry, len(members))
                if len(groups) < len(members)
                else None
            )
        if groups is None:
            for slot in members:
                drafts[slot].status = "gap_scattered"
            continue
        for slot, (group_objects, group_tokens) in zip(members, groups, strict=True):
            gold = drafts[slot]
            gold.shared_gap = len(members)
            boxes = [item.bbox for item in group_objects] + [
                page_geometry.token_boxes[o] for o in group_tokens
            ]
            if not boxes:
                gold.status = "shared_gap_unsplit"
                continue
            gold.status = "located"
            gold.object_ids = sorted(item.id for item in group_objects)
            gold.token_ordinals = group_tokens
            gold.bbox = [
                round(min(b.x0 for b in boxes), 2),
                round(min(b.y0 for b in boxes), 2),
                round(max(b.x1 for b in boxes), 2),
                round(max(b.y1 for b in boxes), 2),
            ]
            gold.method = (
                ("vector" if group_objects else "")
                + ("+" if group_objects and group_tokens else "")
                + ("text" if group_tokens else "")
            )
            if len(members) > 1:
                gold.anchor_confidence = round(gold.anchor_confidence * 0.8, 4)
            if by_count:
                gold.method += "/chosen_by_glyph_count"
                gold.anchor_confidence = round(gold.anchor_confidence * 0.7, 4)
            gold.glyphs_expected = _expected_glyphs(gold.leaf_text)
            gold.glyph_count_fits = _count_fits(
                len(group_objects) + len(group_tokens), gold.glyphs_expected
            )
            gold.verified = gold.glyph_count_fits
            gold.geometric_presentation = _geometric_presentation(
                BBox(x0=gold.bbox[0], y0=gold.bbox[1], x1=gold.bbox[2], y1=gold.bbox[3]),
                page_geometry,
                set(group_tokens),
            )
    return drafts


COMPONENT_GAP = 1.2  # median text sizes between parts of one equation
COUNT_TOLERANCE = 0.25


def _expected_glyphs(leaf_text: str) -> int:
    """Drawn characters an equation needs at least: its non-space leaf characters."""
    return sum(1 for character in leaf_text if not character.isspace())


def _count_fits(found: int, expected: int) -> bool:
    return expected > 0 and abs(found - expected) <= max(1, COUNT_TOLERANCE * expected)


def _components(objects, free, geometry):
    """Connected groups of gap items (glyphs and tokens), in PDF order."""
    items = [("object", item, geometry.object_position[item.id], item.bbox) for item in objects]
    items += [("token", o, o, geometry.token_boxes[o]) for o in free]
    reach = COMPONENT_GAP * geometry.median_size
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            dx = max(0.0, max(a[3].x0, b[3].x0) - min(a[3].x1, b[3].x1))
            dy = max(0.0, max(a[3].y0, b[3].y0) - min(a[3].y1, b[3].y1))
            if dx <= reach and dy <= reach:
                parent[find(j)] = find(i)
    groups: dict[int, list] = defaultdict(list)
    for i, item in enumerate(items):
        groups[find(i)].append(item)
    ordered = sorted(groups.values(), key=lambda g: min((row[2], row[3].x0) for row in g))
    return [
        ([row[1] for row in g if row[0] == "object"], [row[1] for row in g if row[0] == "token"])
        for g in ordered
    ]


def _split(objects, free, geometry, count):
    """Split one gap among ``count`` slots at its widest horizontal breaks, in PDF order."""
    items = [("object", item, geometry.object_position[item.id], item.bbox) for item in objects]
    items += [("token", o, o, geometry.token_boxes[o]) for o in free]
    band = max(1.0, geometry.median_size * 1.2)
    items.sort(key=lambda row: (row[2], row[3].y1 // band, row[3].x0))
    if count == 1:
        return [
            (
                [row[1] for row in items if row[0] == "object"],
                [row[1] for row in items if row[0] == "token"],
            )
        ]
    breaks = []
    for left, right in zip(items, items[1:], strict=False):
        same_band = min(left[3].y1, right[3].y1) > max(left[3].y0, right[3].y0)
        distance = right[3].x0 - left[3].x1 if same_band else float("inf")
        breaks.append(distance)
    chosen = sorted(sorted(range(len(breaks)), key=lambda i: -breaks[i])[: count - 1])
    if len(chosen) < count - 1:
        return [([], []) for _ in range(count)]
    groups, start = [], 0
    for cut in [*chosen, len(items) - 1]:
        part = items[start : cut + 1]
        groups.append(
            (
                [row[1] for row in part if row[0] == "object"],
                [row[1] for row in part if row[0] == "token"],
            )
        )
        start = cut + 1
    return groups


def _geometric_presentation(box: BBox, geometry: PageGeometry, own_tokens: set[int]) -> str:
    """Display when no other text shares the equation's vertical band."""
    for ordinal, token_box in enumerate(geometry.token_boxes):
        if ordinal in own_tokens:
            continue
        overlap = min(box.y1, token_box.y1) - max(box.y0, token_box.y0)
        if overlap > 0.5 * min(box.y1 - box.y0, token_box.y1 - token_box.y0):
            return "inline"
    return "display"


def coverage(gold: Sequence[GoldEquation]) -> dict:
    by_status: dict[str, int] = defaultdict(int)
    by_kind: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_context: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in gold:
        by_status[row.status] += 1
        by_kind[row.presentation][row.status] += 1
        for context in row.contexts or ["prose"]:
            by_context[context][row.status] += 1
    located = by_status.get("located", 0)
    verified = [row for row in gold if row.verified]
    return {
        "equations": len(gold),
        "located": located,
        "verified": len(verified),
        "verified_by_presentation": {
            kind: sum(1 for row in verified if row.presentation == kind)
            for kind in ("inline", "display")
        },
        "coverage": round(located / max(1, len(gold)), 4),
        "by_status": dict(by_status),
        "by_presentation": {k: dict(v) for k, v in by_kind.items()},
        "by_context": {k: dict(v) for k, v in by_context.items()},
        "presentation_agreement": sum(
            1
            for row in gold
            if row.status == "located" and row.geometric_presentation == row.presentation
        ),
    }


def gold_rows(gold: Sequence[GoldEquation]) -> list[dict]:
    return [asdict(row) for row in gold]
