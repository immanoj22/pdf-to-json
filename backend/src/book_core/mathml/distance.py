"""Zhang–Shasha ordered tree edit distance (unit costs) between expression trees, and the
character-level edit distance used for symbol accuracy."""

from book_core.mathml.tree import labels


def _postorder(tree):
    nodes, lefts = [], []

    def walk(node):
        _, children = labels(node)
        first = None
        for child in children:
            index = walk(child)
            if first is None:
                first = lefts[index]
        nodes.append(labels(node)[0])
        lefts.append(first if first is not None else len(nodes) - 1)
        return len(nodes) - 1

    walk(tree)
    return nodes, lefts


def tree_distance(a, b):
    """Insertions, deletions and relabelings turning tree ``a`` into tree ``b``."""
    la, ra = _postorder(a)
    lb, rb = _postorder(b)
    n, m = len(la), len(lb)

    def keyroots(lefts):
        seen, roots = set(), []
        for i in range(len(lefts) - 1, -1, -1):
            if lefts[i] not in seen:
                roots.append(i)
                seen.add(lefts[i])
        return sorted(roots)

    distance = [[0] * m for _ in range(n)]
    for i in keyroots(ra):
        for j in keyroots(rb):
            li, lj = ra[i], rb[j]
            rows, cols = i - li + 2, j - lj + 2
            forest = [[0] * cols for _ in range(rows)]
            for x in range(1, rows):
                forest[x][0] = forest[x - 1][0] + 1
            for y in range(1, cols):
                forest[0][y] = forest[0][y - 1] + 1
            for x in range(1, rows):
                for y in range(1, cols):
                    ia, jb = li + x - 1, lj + y - 1
                    if ra[ia] == li and rb[jb] == lj:
                        forest[x][y] = min(
                            forest[x - 1][y] + 1,
                            forest[x][y - 1] + 1,
                            forest[x - 1][y - 1] + (la[ia] != lb[jb]),
                        )
                        distance[ia][jb] = forest[x][y]
                    else:
                        fx, fy = ra[ia] - li, rb[jb] - lj
                        forest[x][y] = min(
                            forest[x - 1][y] + 1,
                            forest[x][y - 1] + 1,
                            forest[fx][fy] + distance[ia][jb],
                        )
    return distance[n - 1][m - 1]


def sequence_distance(a, b):
    """Levenshtein distance between two sequences."""
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]
