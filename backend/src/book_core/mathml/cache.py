"""Book-level MathML stage after equations: every equation region gets an equation record.

Passes over the book (page records are written once every page is decided; a partial cache
is recomputed):

1. **Image path**: every region is rendered through the Extractor (only its own marks kept)
   and read by the formula recognizer (cached per image); drawn glyph occurrences are
   collected.
2. **Shape table**: unit height and descent of every drawn shape from its occurrences; each
   shape is rasterized alone and read once (isolated reading).
3. **Context votes**: provisional drawn readings (isolated labels) are aligned with image
   readings of the same character count; aligned characters vote per shape and position.
4. **Records**: final shape labels; text, drawn and image readings of every region; checks,
   agreement, confidence, review status, the default output (client settings), reference-
   style parts for mixed expressions and image fallbacks for ``must_check`` equations.

No earlier stage reads these records: units, lines, order, spans and the ledger are
unchanged. Text-set math stays text by default (its MathML is stored only).
"""

import hashlib
import importlib.metadata as metadata
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import cv2
import lxml.etree
import numpy as np
import pymupdf

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.equations.cache import text_size
from book_core.extraction.fingerprints import stable_id
from book_core.figures.cache import write_bytes
from book_core.figures.names import assign_names
from book_core.mathml import decide as decision
from book_core.mathml import images as imaging
from book_core.mathml import layout, paths, shapes
from book_core.mathml.checks import fold
from book_core.mathml.models import (
    BookMath,
    FallbackImage,
    MathPart,
    PageMath,
    ShapeRecord,
)
from book_core.mathml.symbols import TextSymbols, is_rule
from book_core.mathml.tree import leaves, sourced

VERSION = "mathml-1"
CONFIG = {
    "layout": layout.CONFIG,
    "shapes": shapes.CONFIG,
    "decide": decision.CONFIG,
    "image": {"pad": imaging.PAD, "mask_margin": imaging.MASK_MARGIN},
}
LOADED_DIGEST = code_digest("mathml")
NO_MODELS = (
    "formula recognition is unavailable (models extra not installed): the image path and "
    "the drawn shape readings are missing; drawn equations cannot be read"
)


def _fold_text(text):
    return "".join(c for ch in text for c in fold(ch))


def mathml_fingerprint(equations_key, native_key, settings, recognizer_identity=None):
    return stable_id(
        equations_key,
        native_key,
        json.dumps(recognizer_identity or {}, sort_keys=True),
        code_digest("mathml"),
        VERSION,
        json.dumps(CONFIG, sort_keys=True),
        settings.model_dump_json(),
        "pymupdf-" + pymupdf.VersionBind,
        "opencv-" + cv2.__version__,
        "lxml-" + ".".join(map(str, lxml.etree.LXML_VERSION)),
        "latex2mathml-" + _version("latex2mathml"),
        "sympy-" + _version("sympy"),
    )


def _version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not-installed"


class _Book:
    """Per-page inputs of the stage with the book's text size."""

    def __init__(self, pages, native_of, equations_of):
        self.pages, self.native_of, self.equations_of = pages, native_of, equations_of

    def each(self):
        for page in self.pages():
            number = page.geometry.page
            equations = self.equations_of(number)
            if not equations.regions:
                yield page, None, equations, {}, None
                continue
            native = self.native_of(number)
            objects = {o.id: o for o in native.objects}
            yield page, native, equations, objects, TextSymbols(page, native)


def _region_box(region):
    return (region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1)


def _image_reading(region, readings, recognizer_name):
    found = readings.get(region.id)
    if found is None:
        return None
    return paths.image_path(found["latex"], recognizer_name, found.get("truncated", False))


def _votes(position, image, signature_of, chars_by_id, votes):
    """Aligned characters of equal-length readings vote for drawn shapes."""
    if position is None or position.tree is None or image is None or image.tree is None:
        return False
    left = sourced(position.tree)
    right = [c for c in "".join(leaves(image.tree)) if not c.isspace()]
    if len(left) != len(right):
        return False
    for (_, source), char in zip(left, right, strict=True):
        signature = signature_of.get(source)
        if signature is None:
            continue
        votes[signature][chars_by_id[source]][char] += 1
    return True


def book_size_of(pages):
    """The equations stage's book text size: the median of the pages' median span sizes."""
    sizes = [size for page in pages() if (size := text_size(page))]
    return statistics.median(sizes) if sizes else 10.0


def collect(book, reader, renderer, book_size):
    """Pass 1: image readings of every region and the drawn glyph occurrences.

    Returns (readings {region id: reading}, heights {signature: [height]}, rows (glyphs of
    each region), representative {signature: [((height, page, id), object)]}, occurrences).
    """
    readings, heights, rows = {}, defaultdict(list), []
    representative, occurrences = defaultdict(list), Counter()
    for page, _native, equations, objects, text in book.each():
        number = page.geometry.page
        for region in equations.regions:
            if reader is not None:
                png = renderer.crop(
                    number,
                    _region_box(region),
                    imaging.region_marks(region, objects, text),
                    book_size,
                    imaging.region_direction(region, text),
                )
                readings[region.id] = reader.read(png)
            items = []
            for oid in region.object_ids:
                obj = objects.get(oid)
                if obj is None or obj.bbox is None or is_rule(obj, book_size):
                    continue
                signature = shapes.shape_of(obj)
                if signature is None:
                    continue
                box = (obj.bbox.x0, obj.bbox.y0, obj.bbox.x1, obj.bbox.y1)
                heights[signature].append(box[3] - box[1])
                occurrences[signature] += 1
                items.append((signature, box))
                representative[signature].append(((box[3] - box[1], number, oid), obj))
            if items:
                rows.append(items)
    return readings, heights, rows, representative, occurrences


def isolated_readings(representative, reader):
    """Pass 2: {signature: (characters, italic, LaTeX)} from each shape's median-height
    occurrence rasterized alone."""
    isolated = {}
    for signature, found in sorted(representative.items()):
        ordered = sorted(found, key=lambda item: item[0])
        obj = ordered[len(ordered) // 2][1]
        if reader is None:
            isolated[signature] = (None, None, None)
            continue
        latex_source = reader.read(shapes.rasterize(obj))["latex"]
        chars, italic = shapes.isolated_reading(latex_source)
        isolated[signature] = (chars, italic, latex_source)
    return isolated


def provisional_table(isolated, units, descents):
    labels = {
        s: shapes.ShapeLabel(char=c, italic=i, confidence=shapes.ISOLATED_CONFIDENCE)
        for s, (c, i, _) in isolated.items()
    }
    return shapes.ShapeTable(labels, units, descents)


def context_votes(book, provisional, readings, recognizer_name, book_size):
    """Pass 3: {signature: {position class: Counter(char)}} from equal-length readings."""
    votes = defaultdict(lambda: defaultdict(Counter))
    for _page, _native, equations, objects, text in book.each():
        for region in equations.regions:
            if not region.object_ids:
                continue
            pairs = paths.drawn_symbols(region, objects, provisional, book_size)
            signature_of = {s.id: sig for s, sig in pairs if sig is not None}
            chars = [s for s, _ in pairs if s.kind == "char" and s.char is not None]
            position_of = {s.id: paths.position(s, chars) for s, _ in pairs if s.kind == "char"}
            reading = paths.drawn_path(region, objects, text, provisional, book_size)
            image = _image_reading(region, readings, recognizer_name)
            _votes(reading, image, signature_of, position_of, votes)
    return votes


def final_table(isolated, votes, units, descents):
    labels = {
        signature: shapes.decide(chars, latex_source, italic, votes.get(signature, {}), _fold_text)
        for signature, (chars, italic, latex_source) in isolated.items()
    }
    return shapes.ShapeTable(labels, units, descents), labels


def region_record(
    region, objects, text, table, labels, readings, recognizer_name, settings, book_size
):
    """Pass 4: the equation record of one region (without its fallback image)."""
    position, used_shapes = None, []
    if region.object_ids:
        position = paths.drawn_path(region, objects, text, table, book_size)
        used_shapes = position.shapes
    elif region.span_refs:
        position = paths.text_path(region, text)
    image = _image_reading(region, readings, recognizer_name)
    confidences = [labels[s].confidence for s in used_shapes if s in labels]
    record = decision.decide(
        region, position, image, settings, min(confidences) if confidences else None
    )
    if region.source == "mixed" and settings.mixed_expressions == "reference":
        record = _reference_parts(record, region, objects, table, book_size)
    return record


def analyze_book_mathml(
    source,
    pages,
    native_of,
    equations_of,
    page_labels,
    keys,
    cache_dir,
    total,
    settings,
    extractor,
    reader=None,
):
    """MathML records for every page; returns (key, BookMath).

    ``equations_of(number)``: the page's PageEquations; ``page_labels``: {page: (label,
    label source)} for image names; ``keys``: {equations, native}; ``reader``: a
    ``RecognitionCache`` or None (image path off or unavailable).
    """
    assert_producer_unchanged("mathml", LOADED_DIGEST)
    identity = reader.recognizer.identity if reader is not None else None
    key = mathml_fingerprint(keys["equations"], keys["native"], settings, identity)
    directory = Path(cache_dir) / "mathml" / key
    page_paths = {n: directory / f"{n}.json" for n in range(1, total + 1)}
    book_path = directory / "book.json"
    if book_path.exists() and all(p.exists() for p in page_paths.values()):
        return key, read_model(book_path, BookMath, key)
    book = _Book(pages, native_of, equations_of)
    digest = None
    for page in pages():
        digest = page.source_sha256
    book_size = book_size_of(pages)
    diagnostics = [] if reader is not None else [NO_MODELS]
    recognizer_name = identity["recognizer"] if identity else None
    renderer = imaging.RegionImages(extractor, source, settings.recognition_dpi)
    readings, heights, rows, representative, occurrences = collect(
        book, reader, renderer, book_size
    )
    units = shapes.unit_heights(heights)
    descents = shapes.descents(rows, units, book_size)
    isolated = isolated_readings(representative, reader)
    representative.clear()
    provisional = provisional_table(isolated, units, descents)
    votes = context_votes(book, provisional, readings, recognizer_name, book_size)
    table, labels = final_table(isolated, votes, units, descents)

    # Pass 4: records; image names are a whole-book decision (collisions in book order).
    decided, naming = {}, []
    for page, _native, equations, objects, text in book.each():
        number = page.geometry.page
        decided[number] = []
        for n, region in enumerate(equations.regions, start=1):
            record = region_record(
                region,
                objects,
                text,
                table,
                labels,
                readings,
                recognizer_name,
                settings,
                book_size,
            )
            if record.review_status == "must_check":
                label, label_source = page_labels.get(number, (None, "none"))
                naming.append((record.equation_id, number, label, label_source, n))
            decided[number].append(record)
    names = assign_names(
        naming,
        SimpleNamespace(
            name_pattern=settings.fallback_pattern,
            unlabelled_pattern=settings.fallback_unlabelled_pattern,
        ),
    )

    # Pass 5: fallback images and page records.
    inputs = {
        "equations_key": keys["equations"],
        "native_key": keys["native"],
        "producer": LOADED_DIGEST,
        "configuration": json.dumps(CONFIG, sort_keys=True),
        "settings": settings.model_dump_json(),
        "version": VERSION,
    }
    images_dir = directory / "images"
    fallback_renderer = imaging.RegionImages(extractor, source, settings.fallback_dpi)
    by_path, by_review, by_output, by_agreement = Counter(), Counter(), Counter(), Counter()
    image_files = []
    for page, _native, equations, objects, text in book.each():
        number = page.geometry.page
        regions = {r.id: r for r in equations.regions}
        final = []
        for record in decided.pop(number):
            if record.equation_id in names:
                stem, label, _inferred, reasons = names[record.equation_id]
                region = regions[record.equation_id]
                png = fallback_renderer.crop(
                    number,
                    _region_box(region),
                    imaging.region_marks(region, objects, text),
                    book_size,
                    imaging.region_direction(region, text),
                )
                pixels = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
                file_name = f"{stem}.png"
                write_bytes(images_dir / file_name, png)
                image_files.append(file_name)
                source_of_label = page_labels.get(number, (None, "none"))[1]
                record = record.model_copy(
                    update={
                        "fallback_image": FallbackImage(
                            file_name=file_name,
                            dpi=settings.fallback_dpi,
                            width=int(pixels.shape[1]),
                            height=int(pixels.shape[0]),
                            sha256=hashlib.sha256(png).hexdigest(),
                            bytes=len(png),
                            page_label=label,
                            label_source=source_of_label if label else "none",
                            flags=reasons,
                        )
                    }
                )
            by_path[record.path or "none"] += 1
            by_review[record.review_status] += 1
            by_output[record.output] += 1
            by_agreement[record.agreement] += 1
            final.append(record)
        page_record = PageMath(
            source_sha256=page.source_sha256,
            page=number,
            version=VERSION,
            equations=final,
            cache_key_inputs=inputs,
        )
        assert_producer_unchanged("mathml", LOADED_DIGEST)
        write_model(page_paths[number], page_record, key)
    book_record = BookMath(
        source_sha256=digest,
        pages=total,
        version=VERSION,
        config=CONFIG,
        settings=settings.model_dump(mode="json"),
        recognizers={"image": identity} if identity else {},
        equations=sum(by_review.values()),
        by_path=dict(by_path),
        by_review=dict(by_review),
        by_output=dict(by_output),
        by_agreement=dict(by_agreement),
        shapes={
            s: ShapeRecord(
                **labels[s].record(),
                occurrences=occurrences[s],
                unit_height=units.get(s),
                descent=descents.get(s),
            )
            for s in sorted(labels)
        },
        images=sorted(image_files),
        diagnostics=diagnostics,
        cache_key_inputs=inputs,
    )
    write_model(book_path, book_record, key)
    return key, book_record


def _reference_parts(record, region, objects, table, book_size):
    """Reference style for a mixed expression: MathML only for its drawn parts (groups of
    drawn objects separated by the expression's text characters on the line)."""
    if record.review_status == "must_check":
        return record
    pairs = paths.drawn_symbols(region, objects, table, book_size)
    groups = _drawn_groups([s for s, _ in pairs], record)
    parts = []
    for group in groups:
        sub = SimpleNamespace(object_ids=[s.id for s in group], span_refs=[])
        reading = paths._layout("drawn", group)
        if reading.tree is None:
            return record.model_copy(
                update={"flags": sorted({*record.flags, "a drawn part could not be read alone"})}
            )
        from book_core.mathml import markup

        parts.append(
            MathPart(
                object_ids=sub.object_ids,
                mathml=markup.write(reading.tree, region.presentation == "display"),
                latex=reading.latex,
            )
        )
    if not parts:
        return record
    return record.model_copy(update={"parts": parts, "output": "mathml_parts"})


def _drawn_groups(symbols, record):
    """Drawn symbols split where the chosen reading's sources pass through text characters."""
    order = [s for s in record.sources if s is not None]
    drawn = {s.id: s for s in symbols}
    groups, current = [], []
    for source in order:
        if source in drawn:
            if drawn[source] not in current:
                current.append(drawn[source])
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    placed = {s.id for g in groups for s in g}
    rest = [s for s in symbols if s.id not in placed]
    if rest:  # fraction bars and other marks without a character join the nearest group
        for symbol in rest:
            if not groups:
                groups.append([symbol])
                continue
            nearest = min(
                groups,
                key=lambda g: min(abs(symbol.cx - m.cx) + abs(symbol.cy - m.cy) for m in g),
            )
            nearest.append(symbol)
    return groups


def load_page(cache_dir, key, number):
    return read_model(Path(cache_dir) / "mathml" / key / f"{number}.json", PageMath, key)


def image_path(cache_dir, key, file_name):
    return Path(cache_dir) / "mathml" / key / "images" / file_name
