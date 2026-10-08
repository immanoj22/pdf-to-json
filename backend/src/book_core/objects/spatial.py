"""Bounding-box spatial index; path commands are retained inside drawing groups."""

import networkx as nx
from shapely import LineString, Point, STRtree, box

from book_core.objects.models import ObjectRelation


def geometry(bbox):
    if bbox is None:
        return None
    if bbox.x0 == bbox.x1 and bbox.y0 == bbox.y1:
        return Point(bbox.x0, bbox.y0)
    if bbox.x0 == bbox.x1 or bbox.y0 == bbox.y1:
        return LineString(((bbox.x0, bbox.y0), (bbox.x1, bbox.y1)))
    return box(bbox.x0, bbox.y0, bbox.x1, bbox.y1)


class SpatialIndex:
    def __init__(self, objects):
        self.objects = objects
        self.positions = []
        self.geometries = []
        for i, obj in enumerate(objects):
            value = geometry(obj.bbox)
            if value is not None:
                self.positions.append(i)
                self.geometries.append(value)
        self.tree = STRtree(self.geometries)

    def query(self, bbox, distance=0):
        value = geometry(bbox)
        if value is None:
            return []
        indices = self.tree.query(value, predicate="dwithin", distance=distance)
        return [self.positions[int(i)] for i in indices]


def build_graph(objects, compounds, candidate_limit=250_000, edge_limit=200_000):
    graph = nx.DiGraph()
    graph.add_nodes_from((obj.id, {"object": obj}) for obj in objects)
    index = SpatialIndex(objects)
    complete = True
    edge_count = 0
    checked = 0
    diagnostics = []

    def add(a, b, kind):
        nonlocal edge_count
        if graph.has_edge(a, b):
            graph[a][b]["kinds"].add(kind)
        else:
            graph.add_edge(a, b, kinds={kind})
            edge_count += 1

    for i, obj in enumerate(objects):
        if obj.kind in {"clip", "group"} or obj.bbox is None:
            continue
        own = geometry(obj.bbox)
        for j in index.query(obj.bbox):
            if j <= i or objects[j].kind in {"clip", "group"}:
                continue
            checked += 1
            if checked > candidate_limit or edge_count > edge_limit:
                complete = False
                break
            other = objects[j]
            target = geometry(other.bbox)
            if own.equals(target):
                add(obj.id, other.id, "overlaps")
                add(other.id, obj.id, "overlaps")
            elif own.covers(target):
                add(obj.id, other.id, "contains")
            elif target.covers(own):
                add(other.id, obj.id, "contains")
            elif own.touches(target):
                add(obj.id, other.id, "touches")
                add(other.id, obj.id, "touches")
            else:
                add(obj.id, other.id, "overlaps")
                add(other.id, obj.id, "overlaps")
            if obj.paint_sequences and other.paint_sequences:
                a, b = max(obj.paint_sequences), max(other.paint_sequences)
                if a > b:
                    add(obj.id, other.id, "drawn_above")
                elif b > a:
                    add(other.id, obj.id, "drawn_above")
        if not complete:
            diagnostics.append(
                "Spatial relation safety budget reached; all objects retained, graph incomplete"
            )
            break
    for compound in compounds:
        for member in compound.member_ids:
            add(member, compound.id, "member_of")
    relations = [
        ObjectRelation(source=a, target=b, kinds=sorted(data["kinds"]))
        for a, b, data in graph.edges(data=True)
    ]
    return graph, relations, complete, diagnostics, checked
