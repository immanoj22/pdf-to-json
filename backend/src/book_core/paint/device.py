"""Read-only MuPDF paint audit and occurrence-specific render suppression.

The original PDF is never modified, redacted or saved. MuPDF's
interpreter resolves nested form resources/CTMs and emits effective device state.
Unsupported clips, masks, blend modes, groups and optional layers fail closed.
"""

import math

import pymupdf
from pymupdf import mupdf as m


def rect_tuple(rect):
    return tuple(float(getattr(rect, k)) for k in ("x0", "y0", "x1", "y1"))


def intersect(a, b):
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


class PathWalker(m.FzPathWalker2):
    def __init__(self, matrix):
        super().__init__()
        self.matrix = m.FzMatrix(matrix)
        self.items = []
        self.current = None
        self.start = None
        self.contours = 0
        for name in ("moveto", "lineto", "curveto", "closepath"):
            getattr(self, "use_virtual_" + name)()

    def point(self, x, y):
        p = m.fz_transform_point(m.FzPoint(x, y), self.matrix)
        return p.x, p.y

    def moveto(self, _ctx, x, y):
        self.current = self.start = self.point(x, y)
        self.contours += 1

    def lineto(self, _ctx, x, y):
        end = self.point(x, y)
        self.items.append(("l", self.current, end))
        self.current = end

    def curveto(self, _ctx, x1, y1, x2, y2, x3, y3):
        end = self.point(x3, y3)
        self.items.append(("c", self.current, self.point(x1, y1), self.point(x2, y2), end))
        self.current = end

    def closepath(self, _ctx):
        if self.current != self.start:
            self.items.append(("l", self.current, self.start))
        self.current = self.start


def path_core(path, matrix):
    walker = PathWalker(matrix)
    # SWIG's director uses the arbitrary callback argument to recover the walker.
    m.ll_fz_walk_path(path, walker.m_internal, walker.m_internal)
    if walker.contours != 1 or walker.current != walker.start:
        return None
    items = walker.items
    if len(items) == 4 and all(i[0] == "l" for i in items):
        points = [i[1] for i in items]
        xs, ys = sorted({p[0] for p in points}), sorted({p[1] for p in points})
        if len(xs) == len(ys) == 2 and all((a[0] == b[0]) != (a[1] == b[1]) for _, a, b in items):
            return xs[0], ys[0], xs[1], ys[1]
    # Exact rounded-rectangle core, not a path bounding-box fill guess.
    from book_core.paint.paths import core

    return core(items)


PAINT = {
    "fill_path",
    "stroke_path",
    "fill_text",
    "stroke_text",
    "ignore_text",
    "fill_shade",
    "fill_image",
    "fill_image_mask",
}
METHODS = (
    *sorted(PAINT),
    "clip_path",
    "clip_stroke_path",
    "clip_text",
    "clip_stroke_text",
    "clip_image_mask",
    "pop_clip",
    "begin_mask",
    "end_mask",
    "begin_group",
    "end_group",
    "begin_tile",
    "end_tile",
    "render_flags",
    "set_default_colorspaces",
    "begin_layer",
    "end_layer",
    "begin_structure",
    "end_structure",
    "begin_metatext",
    "end_metatext",
)


class PaintDevice(m.FzDevice2):
    def __init__(self, target=None, suppress=None, record=True):
        super().__init__()
        self.target = target
        self.suppress = suppress or {}
        self.record = record
        self.seq = 0
        self.events = []
        self.clips = []
        self.groups = []
        self.layers = []
        self.tiles = []
        self.errors = []
        self.suppressed = 0
        for name in METHODS:
            getattr(self, "use_virtual_" + name)()

    def state(self):
        return {
            "clips": [dict(v) for v in self.clips],
            "groups": [dict(v) for v in self.groups],
            "layers": list(self.layers),
            "tiles": list(self.tiles),
        }

    def forward(self, name, args):
        if self.target is None:
            return 0 if name == "begin_tile" else None
        actual = {"end_mask": "end_mask_tr", "begin_tile": "begin_tile_tid"}.get(name, name)
        # Call the pointer-preserving binding: the public Python fill_text
        # convenience overload converts colours to a four-element tuple.
        return getattr(m._mupdf, "ll_fz_" + actual)(self.target.m_internal, *args)

    def text_items(self, text, matrix):
        rows = []
        span, index = text.head, 0
        while span:
            wrapper = m.FzTextSpan(span)
            font = wrapper.font()
            for i in range(span.len):
                item = wrapper.items(i)
                trm = wrapper.trm()
                trm.e, trm.f = item.x, item.y
                transformed = m.fz_concat(trm, m.FzMatrix(matrix))
                origin = m.fz_transform_point(m.FzPoint(item.x, item.y), m.FzMatrix(matrix))
                box = (
                    rect_tuple(m.fz_bound_glyph(font, item.gid, transformed))
                    if item.gid >= 0
                    else None
                )
                rows.append(
                    {
                        "index": [index, i],
                        "unicode": item.ucs,
                        "glyph_id": item.gid,
                        "raw_code_or_cid": item.cid,
                        "origin": [origin.x, origin.y],
                        "bbox": box,
                        "font": pymupdf.JM_font_name(font),
                        "font_size": math.hypot(transformed.a, transformed.b),
                    }
                )
            span, index = span.next, index + 1
        return rows

    def without(self, text, omitted):
        result = m.FzText()
        span, index = text.head, 0
        while span:
            wrapper = m.FzTextSpan(span)
            for i in range(span.len):
                item = wrapper.items(i)
                if (index, i) in omitted:
                    self.suppressed += 1
                    continue
                trm = wrapper.trm()
                trm.e, trm.f = item.x, item.y
                result.fz_show_glyph_aux(
                    wrapper.font(),
                    trm,
                    item.adv,
                    item.gid,
                    item.ucs,
                    item.cid,
                    span.wmode,
                    span.bidi_level,
                    span.markup_dir,
                    span.language,
                )
            span, index = span.next, index + 1
        return result

    def dispatch(self, name, args):
        if name in PAINT:
            if self.record:
                row = {"seqno": self.seq, "kind": name, "state": self.state()}
                if name in {"fill_text", "stroke_text", "ignore_text"}:
                    mi = 2 if name == "stroke_text" else 1
                    row["glyphs"] = self.text_items(args[0], args[mi])
                    row["alpha"] = args[-2] if name != "ignore_text" else None
                if name == "fill_path":
                    row["core"] = path_core(args[0], args[2])
                    row["alpha"] = args[-2]
                    row["even_odd"] = args[1]
                    row["overprint"] = bool(args[-1].op)
                self.events.append(row)
            omitted = self.suppress.get(self.seq)
            self.seq += 1
            if omitted and name in {"fill_text", "stroke_text"}:
                replacement = self.without(args[0], omitted)
                return self.forward(name, (replacement.m_internal, *args[1:]))
            return self.forward(name, args)
        if self.record:
            if name.startswith("clip_"):
                core = path_core(args[0], args[2]) if name == "clip_path" else None
                self.clips.append({"kind": name, "core": core})
            elif name == "pop_clip":
                self.clips.pop()
            elif name == "begin_mask":
                self.clips.append({"kind": "mask_paint", "core": None})
            elif name == "end_mask":
                assert self.clips[-1]["kind"] == "mask_paint"
                self.clips[-1] = {"kind": "active_soft_mask", "core": None}
            elif name == "begin_group":
                self.groups.append(
                    {
                        "isolated": args[2],
                        "knockout": args[3],
                        "blendmode": args[4],
                        "alpha": args[5],
                    }
                )
            elif name == "end_group":
                self.groups.pop()
            elif name == "begin_layer":
                self.layers.append(args[0])
            elif name == "end_layer":
                self.layers.pop()
            elif name == "begin_tile":
                self.tiles.append(args[-2])
            elif name == "end_tile":
                self.tiles.pop()
        return self.forward(name, args)


def callback(name):
    def call(self, _ctx, *args):
        try:
            return self.dispatch(name, args)
        except Exception as error:
            self.errors.append(f"{name}: {type(error).__name__}: {error}")
            raise

    return call


for _name in METHODS:
    setattr(PaintDevice, _name, callback(_name))


def inspect_page(page):
    device = PaintDevice()
    m.fz_run_page(page.this, device, m.FzMatrix(), m.FzCookie())
    m.fz_close_device(device)
    assert not device.errors, device.errors
    assert not (device.clips or device.groups or device.layers or device.tiles), device.state()
    return device.events


def render(page, clip, scale=2, suppress=None):
    # PyMuPDF's public page renderer first records a display list. Forward through
    # the same recording step: direct draw-device rendering can round differently.
    display = m.fz_new_display_list(m.FzRect(*page.rect))
    target = m.fz_new_list_device(display)
    device = PaintDevice(target, suppress, record=False)
    m.fz_run_page(page.this, device, m.FzMatrix(), m.FzCookie())
    m.fz_close_device(device)
    m.fz_close_device(target)
    assert not device.errors, device.errors
    pixmap = pymupdf.JM_pixmap_from_display_list(
        display, pymupdf.Matrix(scale, scale), m.fz_device_rgb(), False, clip, None
    )
    return pixmap, device.suppressed
