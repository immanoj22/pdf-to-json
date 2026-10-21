"""TableFormer as a second reader of text-owning tables (optional accuracy-models extra).

Measured in Step 14b on the reference tables of five books (report, Task 2), two uses help
and none makes a book worse; replacing our grid by TableFormer's where our evidence is weak
made a book worse in every variant, so it is not used for structure:

- **Header rows**: where our grid found no header evidence, TableFormer's column-header
  rows (the leading rows it marks as column headers) become the table's header rows.
- **Second opinion**: where the two structures disagree (structure-only tree edit
  similarity below ``DISAGREE``), the table is flagged for review. Nothing else changes.

The reader sees pixels only: the page is rendered through the Extractor, the table region
(padded) is cut out and turned upright by exact quarter turns so that the table's text runs
left to right. TableFormer's pixel boxes are mapped back to page coordinates. Readings are
cached per image (``tables.recognizers.ReadingCache``).
"""

import io

from book_core.evaluation.table_scoring import teds
from book_core.layout.frames import from_frame
from book_core.model.common import BBox

CROP_DPI = 150
PAD = 6.0  # points around a table region
DISAGREE = 0.8  # structure similarity below which the two readings disagree
HEADER_RULE = "header rows from TableFormer (no header evidence in the grid)"
DISAGREEMENT = "TableFormer reads a different structure (similarity {:.2f}); review"


def _direction(rotation):
    """The frame's text direction (dx, dy) in page coordinates (y down)."""
    a = from_frame(BBox(x0=0, y0=0, x1=0.001, y1=0.001), rotation)
    b = from_frame(BBox(x0=1, y0=0, x1=1.001, y1=0.001), rotation)
    return b.x0 - a.x0, b.y0 - a.y0


# Quarter turns of an image: (forward vector map, inverse pixel map with crop size W, H).
TURNS = {
    0: (lambda dx, dy: (dx, dy), lambda x, y, w, h: (x, y)),
    90: (lambda dx, dy: (dy, -dx), lambda x, y, w, h: (w - y, x)),
    180: (lambda dx, dy: (-dx, -dy), lambda x, y, w, h: (w - x, h - y)),
    270: (lambda dx, dy: (-dy, dx), lambda x, y, w, h: (y, h - x)),
}


def upright_crop(raster, box, rotation):
    """(PNG of the padded region turned upright, pixel -> page point function)."""
    from PIL import Image

    scale = raster.width / raster.page_width
    clip = BBox(
        x0=max(0.0, box.x0 - PAD), y0=max(0.0, box.y0 - PAD),
        x1=min(raster.page_width, box.x1 + PAD), y1=min(raster.page_height, box.y1 + PAD),
    )  # fmt: skip
    pixels = tuple(round(v * scale) for v in (clip.x0, clip.y0, clip.x1, clip.y1))
    dx, dy = _direction(rotation) if rotation else (1.0, 0.0)
    turn = max(TURNS, key=lambda t: TURNS[t][0](dx, dy)[0])
    with Image.open(io.BytesIO(raster.png)) as page:
        image = page.convert("RGB").crop(pixels)
    width, height = image.size
    if turn:
        image = image.transpose(
            {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
             270: Image.Transpose.ROTATE_270}[turn]
        )  # fmt: skip
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    inverse = TURNS[turn][1]

    def to_page(x, y):
        px, py = inverse(x, y, width, height)
        return pixels[0] / scale + px / scale, pixels[1] / scale + py / scale

    return buffer.getvalue(), to_page


def reading_cells(reading, to_page):
    """[(row, column, row span, column span, column header, page box)] and header rows."""
    cells = []
    for cell in reading["cells"]:
        corners = [to_page(cell["box"][0], cell["box"][1]), to_page(cell["box"][2], cell["box"][3])]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        cells.append((cell["row"], cell["column"], cell["row_span"], cell["column_span"],
                      cell["column_header"],
                      BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))))  # fmt: skip
    marked = {c[0] for c in cells if c[4]}
    header_rows = 0
    while header_rows in marked:
        header_rows += 1
    return cells, header_rows


def agreement(table, cells):
    """Structure-only similarity of our grid and TableFormer's (1.0: the same tree)."""
    ours = {"cells": [(c.row, c.column, c.row_span, c.column_span, c.header, frozenset())
                      for c in table.cells]}  # fmt: skip
    theirs = {"cells": [(r, c, rs, cs, h, frozenset()) for r, c, rs, cs, h, _ in cells]}
    if not theirs["cells"]:
        theirs["cells"] = [(0, 0, 1, 1, False, frozenset())]
    return teds(ours, theirs)


class TableReader:
    """TableFormer readings of a page's tables: {table id: (cells, header rows)}."""

    def __init__(self, source, extractor, cache, dpi=CROP_DPI):
        self.source, self.extractor, self.cache, self.dpi = source, extractor, cache, dpi

    @property
    def identity(self):
        return {**self.cache.reader.identity, "crop_dpi": self.dpi, "pad": PAD}

    def __call__(self, number, tables):
        if not tables:
            return {}
        raster = self.extractor.render_page(self.source, number, self.dpi)
        out = {}
        for table in tables:
            png, to_page = upright_crop(raster, table.bbox, table.rotation)
            out[table.id] = reading_cells(self.cache.read(png), to_page)
        return out


def apply(table, cells, header_rows):
    """The record with the measured uses applied: header rows where the grid found no header
    evidence, and the disagreement flag. Returns (update dict, statistics)."""
    from book_core.tables.records import header_references

    update, stats = {}, {}
    similarity = agreement(table, cells)
    flags = list(table.review_flags)
    if similarity < DISAGREE:
        flags.append(DISAGREEMENT.format(similarity))
        stats["disagreements"] = 1
    evidence = table.structure_evidence.get("header")
    if evidence == "no header evidence" and 0 < header_rows < len(table.rows):
        cells_out = []
        for cell in table.cells:
            role = cell.role
            if cell.row < header_rows:
                role = "column_header"
            elif role == "column_header":
                role = "data"
            cells_out.append(cell.model_copy(update={"header": cell.row < header_rows,
                                                     "role": role}))  # fmt: skip
        references = header_references(cells_out, header_rows, table.row_header_columns)
        update["cells"] = [
            c.model_copy(update={"header_cell_ids": [cells_out[h].id for h in references[k]]})
            for k, c in enumerate(cells_out)
        ]
        update["header_rows"] = header_rows
        flags.append(HEADER_RULE)
        stats["header_rows"] = 1
    if flags != list(table.review_flags):
        update["review_flags"] = flags
    return update, stats
