"""Table scoring against table gold: detection, structure-only TEDS, cell adjacency, headers.

Tables are compared per page segment (a reference table spanning pages is one segment per
page, as our tables are per page). A grid is ``{"cells": [(row, column, row_span,
column_span, header, frozenset(tokens))]}`` with tokens ``(page, ordinal)``.

- **Detection**: our table matches a reference segment when it holds at least half of the
  segment's located cell tokens and at least half of its own tokens belong to the segment
  (cells, title or notes); matching is one-to-one, best overlap first.
- **TEDS (structure only)**: tree edit distance between the two grids as trees (table, rows,
  cells labelled by their spans; text ignored), ``1 - distance / max(size)`` (Zhong et al.).
- **Cell adjacency F1**: horizontal and vertical neighbour relations between non-empty
  cells (the next non-empty cell to the right / below), our cells named by the reference
  cell holding most of their tokens (Göbel et al., ICDAR 2013).
- **Header accuracy**: matched segments whose header row count is exact, and per located
  token whether it is in a header cell on both sides.
"""

from __future__ import annotations

from collections import Counter, defaultdict


def gold_segments(rows):
    """{(table, page): grid} of every located reference table, with title/note tokens."""
    segments = {}
    for t in rows:
        if not t["located"]:
            continue
        for page in t["pages"]:
            starts = sorted(
                {c["row"] for c in t["cells"] if any(p == page for p, _ in c["tokens"])}
            )
            if not starts:
                continue
            lo, hi = starts[0], starts[-1]
            cells = []
            for c in t["cells"]:
                if lo <= c["row"] <= hi:
                    tokens = frozenset((p, o) for p, o in c["tokens"] if p == page)
                    cells.append(
                        (
                            c["row"] - lo,
                            c["column"],
                            c["row_span"],
                            c["column_span"],
                            c["header"],
                            tokens,
                        )  # fmt: skip
                    )
            extra = frozenset(
                (p, o) for p, o in t["title"]["tokens"] + t["notes"]["tokens"] if p == page
            )
            segments[(t["table"], page)] = {
                "cells": cells,
                "header_rows": max(0, t["header_rows"] - lo),
                "extra": extra,
                "rows": hi - lo + 1,
                "columns": t["columns"],
                "problems": t["problems"],
            }
    return segments


def tokens_of(grid):
    return frozenset(tok for cell in grid["cells"] for tok in cell[5])


def match(gold, ours):
    """One-to-one matches [(gold key, our key, overlap)] by token overlap (see module)."""
    pairs = []
    for gkey, g in gold.items():
        gt = tokens_of(g)
        if not gt:
            continue
        for okey, o in ours.items():
            if okey[0] != gkey[1]:  # our keys are (page, index)
                continue
            ot = tokens_of(o)
            common = len(gt & ot)
            if not common or common < 0.5 * len(gt):
                continue
            own = len(ot & (gt | g["extra"]))
            if ot and own < 0.5 * len(ot):
                continue
            pairs.append((common, gkey, okey))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    used_g, used_o, found = set(), set(), []
    for common, gkey, okey in pairs:
        if gkey in used_g or okey in used_o:
            continue
        used_g.add(gkey)
        used_o.add(okey)
        found.append((gkey, okey, common))
    return found


# --- tree edit distance (Zhang-Shasha) ------------------------------------------------


class _Tree:
    def __init__(self, label, children=()):
        self.label, self.children = label, list(children)


def grid_tree(grid):
    rows = defaultdict(list)
    for row, column, row_span, column_span, _, _ in grid["cells"]:
        rows[row].append((column, row_span, column_span))
    return _Tree(
        "table",
        [
            _Tree("row", [_Tree(("cell", rs, cs)) for _, rs, cs in sorted(rows[r])])
            for r in sorted(rows)
        ],
    )


def _postorder(tree):
    """Labels in post-order and the leftmost leaf index of each node."""
    labels, leftmost = [], []

    def walk(node):
        first = None
        for child in node.children:
            leaf = walk(child)
            first = leaf if first is None else first
        labels.append(node.label)
        leftmost.append(first if first is not None else len(labels) - 1)
        return leftmost[-1]

    walk(tree)
    return labels, leftmost


def tree_distance(a, b):
    """Zhang-Shasha edit distance, unit insert/delete, rename 1 when labels differ."""
    la, ka = _postorder(a)
    lb, kb = _postorder(b)
    keys_a = sorted({max(i for i in range(len(la)) if ka[i] == k) for k in set(ka)})
    keys_b = sorted({max(j for j in range(len(lb)) if kb[j] == k) for k in set(kb)})
    tree = [[0] * len(lb) for _ in range(len(la))]
    for i in keys_a:
        for j in keys_b:
            li, lj = ka[i], kb[j]
            m, n = i - li + 2, j - lj + 2
            forest = [[0] * n for _ in range(m)]
            for x in range(1, m):
                forest[x][0] = forest[x - 1][0] + 1
            for y in range(1, n):
                forest[0][y] = forest[0][y - 1] + 1
            for x in range(1, m):
                for y in range(1, n):
                    ii, jj = li + x - 1, lj + y - 1
                    if ka[ii] == li and kb[jj] == lj:
                        forest[x][y] = min(
                            forest[x - 1][y] + 1,
                            forest[x][y - 1] + 1,
                            forest[x - 1][y - 1] + (la[ii] != lb[jj]),
                        )
                        tree[ii][jj] = forest[x][y]
                    else:
                        p, q = ka[ii] - li, kb[jj] - lj
                        forest[x][y] = min(
                            forest[x - 1][y] + 1,
                            forest[x][y - 1] + 1,
                            forest[p][q] + tree[ii][jj],
                        )
    return tree[len(la) - 1][len(lb) - 1]


def _size(tree):
    return 1 + sum(_size(child) for child in tree.children)


def teds(gold, ours):
    a, b = grid_tree(gold), grid_tree(ours)
    return 1.0 - tree_distance(a, b) / max(_size(a), _size(b))


# --- cell adjacency ----------------------------------------------------------------------


def _relations(cells):
    """{(a, b, direction)} between non-empty cells (indexes into cells)."""
    occupied = {}
    for index, (row, column, rs, cs, _, tokens) in enumerate(cells):
        if not tokens:
            continue
        for r in range(row, row + rs):
            for c in range(column, column + cs):
                occupied[(r, c)] = index
    found = set()
    if not occupied:
        return found
    max_r = max(r for r, _ in occupied)
    max_c = max(c for _, c in occupied)
    for (r, c), index in occupied.items():
        for dr, dc, direction in ((0, 1, "h"), (1, 0, "v")):
            rr, cc = r + dr, c + dc
            while rr <= max_r and cc <= max_c:
                other = occupied.get((rr, cc))
                if other is not None and other != index:
                    found.add((index, other, direction))
                    break
                if other == index:
                    rr, cc = rr + dr, cc + dc
                    continue
                rr, cc = rr + dr, cc + dc
    return found


def adjacency(gold, ours):
    """(true positives, ours, gold) relation counts after naming our cells."""
    owner = {}
    for index, cell in enumerate(gold["cells"]):
        for token in cell[5]:
            owner[token] = index
    names = {}
    for index, cell in enumerate(ours["cells"]):
        votes = Counter(owner[t] for t in cell[5] if t in owner)
        if votes:
            names[index] = votes.most_common(1)[0][0]
    gold_rel = _relations(gold["cells"])
    our_rel = set()
    for a, b, d in _relations(ours["cells"]):
        if a in names and b in names and names[a] != names[b]:
            our_rel.add((names[a], names[b], d))
        else:
            our_rel.add((("unnamed", a), ("unnamed", b), d))
    return len(gold_rel & our_rel), len(our_rel), len(gold_rel)


def header_tokens(gold, ours):
    """(agree, total) over located tokens: in a header cell on both sides or on neither."""
    g = {t: cell[4] for cell in gold["cells"] for t in cell[5]}
    o = {t: cell[4] for cell in ours["cells"] for t in cell[5]}
    common = set(g) & set(o)
    return sum(g[t] == o[t] for t in common), len(common)


def score(gold, ours, skip_problem_tables=True):
    """Per book: detection P/R/F1, mean TEDS, adjacency P/R/F1, header accuracy."""
    pairs = match(gold, ours)
    detected = len(pairs)
    tp = fp = 0
    structure = []
    rel = Counter()
    header_exact = header_total = 0
    head_agree = head_total = 0
    for gkey, okey, _ in pairs:
        g, o = gold[gkey], ours[okey]
        if skip_problem_tables and g["problems"]:
            continue
        structure.append(teds(g, o))
        t, n_ours, n_gold = adjacency(g, o)
        rel["tp"] += t
        rel["ours"] += n_ours
        rel["gold"] += n_gold
        header_total += 1
        header_exact += g["header_rows"] == o.get("header_rows", 0)
        a, n = header_tokens(g, o)
        head_agree += a
        head_total += n
    del tp, fp
    gold_n = sum(1 for g in gold.values() if tokens_of(g))
    ours_n = len(ours)
    precision = detected / ours_n if ours_n else None
    recall = detected / gold_n if gold_n else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    ap = rel["tp"] / rel["ours"] if rel["ours"] else None
    ar = rel["tp"] / rel["gold"] if rel["gold"] else None
    af = 2 * ap * ar / (ap + ar) if ap and ar else None

    def r(value):
        return None if value is None else round(value, 4)

    return {
        "reference_segments": gold_n,
        "our_tables": ours_n,
        "matched": detected,
        "detection_precision": r(precision),
        "detection_recall": r(recall),
        "detection_f1": r(f1),
        "structure_scored": len(structure),
        "teds_structure_mean": r(sum(structure) / len(structure)) if structure else None,
        "teds_exact_share": r(sum(s >= 0.9999 for s in structure) / len(structure))
        if structure
        else None,
        "adjacency_precision": r(ap),
        "adjacency_recall": r(ar),
        "adjacency_f1": r(af),
        "header_rows_exact": r(header_exact / header_total) if header_total else None,
        "header_token_accuracy": r(head_agree / head_total) if head_total else None,
        "matches": [[list(g), list(o), n] for g, o, n in pairs],
    }
