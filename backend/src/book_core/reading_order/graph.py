"""The reading order as a NetworkX graph with typed edges, plus its invariants.

Nodes are visual line ids, ``stream:<id>`` stream nodes, ``region:<id>`` figure/table nodes and
``page_start``. Sequence edges (next_in_lane, next_lane_in_band, next_band,
continues_across_column, next_in_stream) chain each stream's lines; anchored_after joins a
float stream to the main line it follows; belongs_to_figure/table and caption_of join lines to
their figure or table. ``check`` returns invariant violations and never repairs anything.
"""

import networkx as nx

from book_core.reading_order.models import PAGE_START, SEQUENCE_EDGES


def to_graph(order):
    graph = nx.MultiDiGraph(page=order.page, source_sha256=order.source_sha256)
    graph.add_node(PAGE_START, kind="page_start")
    for stream in order.streams:
        graph.add_node(f"stream:{stream.id}", kind="stream", stream_kind=stream.kind)
        for position, line in enumerate(stream.line_ids):
            graph.add_node(line, kind="line", stream=stream.id, position=position)
    for edge in order.edges:
        for node in (edge.source, edge.target):
            if node not in graph:
                graph.add_node(node, kind="region" if node.startswith("region:") else "unknown")
        graph.add_edge(
            edge.source, edge.target, key=edge.kind, kind=edge.kind, confidence=edge.confidence
        )
    return graph


def check(order, layout=None):
    """Violations of: every line once; streams are exact edge chains; anchors hit the main flow."""
    problems = []
    lines = [line for stream in order.streams for line in stream.line_ids]
    if len(lines) != len(set(lines)):
        problems.append("a line appears in more than one stream position")
    if layout is not None:
        expected = {line.id for line in layout.lines}
        if set(lines) != expected:
            missing = len(expected - set(lines))
            extra = len(set(lines) - expected)
            problems.append(
                f"stream lines differ from layout lines: {missing} missing, {extra} extra"
            )
    graph = to_graph(order)
    stream_of = order.stream_of()
    sequence = [(e.source, e.target) for e in order.edges if e.kind in SEQUENCE_EDGES]
    expected_pairs = {
        (a, b)
        for stream in order.streams
        for a, b in zip(stream.line_ids, stream.line_ids[1:], strict=False)
    }
    if set(sequence) != expected_pairs or len(sequence) != len(expected_pairs):
        problems.append("sequence edges do not exactly chain each stream's lines")
    if any(stream_of.get(a) != stream_of.get(b) for a, b in sequence):
        problems.append("a sequence edge crosses streams")
    chain = nx.DiGraph(sequence)
    if chain.number_of_nodes() and not nx.is_directed_acyclic_graph(chain):
        problems.append("sequence edges form a cycle")
    main = set(order.main.line_ids)
    anchors = {e.source: e.target for e in order.edges if e.kind == "anchored_after"}
    for stream in order.streams:
        if stream.anchor is None:
            continue
        target = anchors.get(f"stream:{stream.id}")
        if target is None:
            problems.append(f"float {stream.id[:12]} has no anchored_after edge")
        elif target != PAGE_START and target not in main:
            problems.append(f"float {stream.id[:12]} is anchored outside the main flow")
        elif target != (stream.anchor.after_line_id or PAGE_START):
            problems.append(f"float {stream.id[:12]} edge and anchor disagree")
    for source, target, kind in graph.edges(keys=True):
        if kind in {"belongs_to_figure", "belongs_to_table", "caption_of"}:
            if graph.nodes[source].get("kind") != "line" or not target.startswith("region:"):
                problems.append(f"{kind} must join a line to a region node")
    return problems
