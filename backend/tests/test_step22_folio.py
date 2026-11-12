"""A page number set beside a running head is a label at the line end (the page number of a
book whose head carries it)."""


def test_a_page_number_set_beside_a_running_head_is_a_label_at_the_line_end():
    from types import SimpleNamespace

    from book_core.furniture.features import _edge_label, spaced_text

    def span(text, x0, x1):
        return SimpleNamespace(raw_text=text, size=9.0,
                               bbox=SimpleNamespace(x0=x0, x1=x1, y0=84.0, y1=96.0))

    head, number = span("SECTION 2: Upper Limb Blocks", 81.0, 196.0), span("12", 61.0, 72.0)
    assert spaced_text([head, number]) == "SECTION 2: Upper Limb Blocks 12"
    assert _edge_label(spaced_text([head, number]))[0] == "end"
    touching = span("12", 196.0, 205.0)  # adjacent spans of one word stay together
    assert spaced_text([head, touching]) == "SECTION 2: Upper Limb Blocks12"
