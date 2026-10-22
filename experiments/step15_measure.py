"""Step 15 Task 1: content that crosses a page break, from the references, and today's handling.

On a final archive (default: the Step 14b final capture), per book:

- **Reference units crossing a page break** (tokens on two or more pages; the reference
  keeps them whole with a page marker inside): paragraphs, captions, list items, glossary
  terms/descriptions, index and bibliography entries. Each is *joined* when one chain of
  ours (a unit and its cross-page links) holds all its scored tokens, else *split*, with
  the failure class at the page break (below).
- **Book 1** splits every paragraph at a page break in its reference. There, a *reference
  continuation* is a pair of consecutive reference units of one kind, the first ending
  page p and the second starting page p + 1 (siblings in the reference tree, page credits
  between them skipped), where the first one's last line ends without a sentence end
  (approximation from the PDF text, stated in the report).
- **Our links**: each cross-page link of ours is *correct* when both sides hold the same
  reference unit (or a book-1 continuation pair), *wrong* when they hold different ones.
- **Tables**: reference tables on several pages; per page break, our tables on both pages
  (the one holding most of that page's reference cells) and whether ours is marked
  continued; classes for misses.

Failure classes at a break (A: our owner of the last token before it, B: of the first after):
``A outside the main flow``, ``B outside the main flow``, ``after A: <kinds>`` (main-flow
items after A on its page), ``before B: <kinds>``, ``kinds differ``, ``at both edges, no
link`` with the Step 9 candidate verdict (continues / neutral / breaks), style and indent,
and ``entry link dropped`` (the lists stage drops a Step 9 join between entries).

Usage: python step15_measure.py [--book NAME] [--capture experiments/out/step14b/final]
                                [--out measure/before]
"""

# ruff: noqa: E402
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import regex
import step14a_common as common
import step14b_common  # noqa: F401 - cache keys of the Step 14b final capture
import step15_common as c15
from step9_run import CACHE9

from book_core.objects.analysis import verified_read
from book_core.paragraphs.cache import BookParagraphResult

KINDS = ("paragraph", "caption", "list_item", "definition_term", "definition_description",
         "index_entry", "bibliography_entry")  # fmt: skip
SENTENCE_END = regex.compile(r"[.!?…:;。！？؟]\s*[\"'”’»)\]]*\s*$")
EXAMPLES = 6


def step9_candidates(book, capture):
    run = c15.capture_run(capture)(book)
    key = run["cache_keys"]["paragraphs"]
    result = verified_read(CACHE9 / "paragraphs/book" / f"{key}.json", BookParagraphResult, key)
    return {c["from_page"]: c for c in result.book.page_join_candidates}


def ordinals(unit):
    return [(p, o) for p, first, n in unit["pdf"] for o in range(first, first + n)]


def classify(pages, chain, a_page, a, b_page, b, candidates, dropped):
    """The failure class of a split between owner ``a`` (page a_page) and ``b``."""
    if chain.get(a, a) == chain.get(b, b):
        return "joined"
    va, vb = pages[a_page], pages[b_page]
    na, nb = c15.neighbours(va, a), c15.neighbours(vb, b)
    if na is None:
        return f"A outside the main flow ({va.stream.get(a, va.kind.get(a))})"
    if nb is None:
        return f"B outside the main flow ({vb.stream.get(b, vb.kind.get(b))})"
    after, before = na[0], nb[1]
    if after:
        kinds = sorted({k for _, k in after})
        return "after A: " + ("floats " if set(kinds) <= c15.FLOATS else "") + "+".join(kinds)
    if before:
        kinds = sorted({k for _, k in before})
        return "before B: " + ("floats " if set(kinds) <= c15.FLOATS else "") + "+".join(kinds)
    if b_page != a_page + 1:
        return "not consecutive pages"
    if (a_page, b_page) in dropped:
        return "entry link dropped (lists stage)"
    ka, kb = va.kind[a], vb.kind[b]
    if ka != kb:
        return f"kinds differ ({ka}->{kb})"
    found = candidates.get(a_page)
    if found is None:
        return "at both edges, no link (no Step 9 candidate)"
    why = [found.get("verdict")]
    if not found.get("same_style", True):
        why.append("style differs")
    if found.get("next_indented"):
        why.append("next indented")
    if found.get("joined"):
        why.append("Step 9 joined")
    return "at both edges, no link (" + ", ".join(str(w) for w in why) + ")"


def first_last(pages, tokens, page):
    owned = [(p, o) for p, o in tokens if p == page and o in pages[p].owner]
    return owned


def unit_rows(book, pages, chain, gold, candidates, dropped):
    rows = []
    for unit in gold.units:
        if unit["kind"] not in KINDS:
            continue
        tokens = [(p, o) for p, o in ordinals(unit) if o in pages[p].owner]
        on = sorted({p for p, _ in tokens})
        if len(on) < 2:
            continue
        breaks = []
        for p, q in zip(on, on[1:], strict=False):
            a = pages[p].owner[max(o for x, o in tokens if x == p)]
            b = pages[q].owner[min(o for x, o in tokens if x == q)]
            breaks.append((p, q, classify(pages, chain, p, a, q, b, candidates, dropped)))
        roots = {chain.get(pages[p].owner[o], pages[p].owner[o]) for p, o in tokens}
        rows.append({"unit": unit["unit"], "kind": unit["kind"], "pages": on,
                     "joined": len(roots) == 1,
                     "classes": [c for _, _, c in breaks if c != "joined"],
                     "breaks": breaks})  # fmt: skip
    return rows


def continuation_pairs(pages, gold):
    """Book-1 reference continuations: (first unit, second unit) across a page break.

    Siblings in the reference (same parent element, same kind): the second starts page p + 1,
    the first is the nearest earlier sibling ending page p whose last token lies in our main
    flow (the reference places page credits, which are separate streams of ours, between the
    halves), and the first one's last line ends without a sentence end."""
    siblings = defaultdict(list)
    for unit in gold.units:
        if unit["kind"] in KINDS:
            siblings[unit["path"].rsplit("/", 1)[0]].append(unit)
    pairs = []
    for group in siblings.values():
        group.sort(key=lambda u: u["unit"])
        spans = []
        for u in group:
            tokens = [(p, o) for p, o in ordinals(u) if o in pages[p].owner]
            spans.append(tokens)
        for k, u2 in enumerate(group):
            t2 = spans[k]
            if not t2:
                continue
            p2 = min(p for p, _ in t2)
            if max(p for p, _ in t2) != p2:
                continue
            u1 = t1 = None
            for j in range(k - 1, -1, -1):
                tj = spans[j]
                if not tj:
                    continue
                if max(p for p, _ in tj) != p2 - 1:
                    break
                last = max(o for p, o in tj if p == p2 - 1)
                view = pages[p2 - 1]
                if c15.neighbours(view, view.owner[last]) is not None:
                    u1, t1 = group[j], tj
                    break
            if u1 is None or u1["kind"] != u2["kind"] or min(p for p, _ in t1) != p2 - 1:
                continue
            p1 = p2 - 1
            last = max(o for p, o in t1 if p == p1)
            first = min(o for p, o in t2 if p == p2)
            tail = pages[p1].text(pages[p1].tokens[last][0]).rstrip()
            head = pages[p2].text(pages[p2].tokens[first][0]).lstrip()
            if not tail or not head or SENTENCE_END.search(tail):
                continue
            pairs.append((u1, u2, (p1, last), (p2, first)))
    return pairs


def pair_rows(pages, chain, pairs, candidates, dropped):
    rows = []
    for u1, u2, (p1, o1), (p2, o2) in pairs:
        a, b = pages[p1].owner[o1], pages[p2].owner[o2]
        cls = classify(pages, chain, p1, a, p2, b, candidates, dropped)
        rows.append({"units": [u1["unit"], u2["unit"]], "kind": u1["kind"], "pages": [p1, p2],
                     "joined": cls == "joined",
                     "classes": [] if cls == "joined" else [cls]})  # fmt: skip
    return rows


def our_links(pages, archive):
    """[(from page, from owner, to page, to owner, kind)] of every cross-page link."""
    record = archive.get("continuity")
    out = []
    if record is not None:
        for chain in record["chains"]:
            for brk in chain["breaks"]:
                out.append((brk["from_page"], brk["from_id"], brk["to_page"], brk["to_id"],
                            chain["kind"], brk.get("kind", "page")))  # fmt: skip
        return out
    for number, view in pages.items():
        for uid, (_, to) in view.links.items():
            if to and number + 1 in pages and to in pages[number + 1].kind:
                out.append((number, uid, number + 1, to, view.kind[uid], "page"))
    return out


def link_rows(pages, archive, gold, pairs):
    owner_ref = {}
    for unit in gold.units:
        if unit["kind"] in KINDS:
            for p, o in ordinals(unit):
                owner_ref[(p, o)] = unit["unit"]
    pair_set = {(u1["unit"], u2["unit"]) for u1, u2, _, _ in pairs}
    rows = []
    for fp, fid, tp, tid, kind, where in our_links(pages, archive):
        if pages[fp].kind.get(fid) == "table":
            continue
        left = Counter(owner_ref[(fp, o)] for o, w in pages[fp].owner.items()
                       if w == fid and (fp, o) in owner_ref)  # fmt: skip
        right = Counter(owner_ref[(tp, o)] for o, w in pages[tp].owner.items()
                        if w == tid and (tp, o) in owner_ref)  # fmt: skip
        if not left or not right:
            verdict = "unscored"
        else:
            # The reference units at the break: the last one of A, the first one of B.
            a = max(
                left,
                key=lambda u: max(
                    o
                    for o, w in pages[fp].owner.items()
                    if w == fid and owner_ref.get((fp, o)) == u
                ),
            )
            b = min(
                right,
                key=lambda u: min(
                    o
                    for o, w in pages[tp].owner.items()
                    if w == tid and owner_ref.get((tp, o)) == u
                ),
            )
            verdict = "correct" if a == b or (a, b) in pair_set else "wrong"
        rows.append({"from": [fp, fid[:12]], "to": [tp, tid[:12]], "kind": f"{where}:{kind}",
                     "verdict": verdict})  # fmt: skip
    return rows


def table_rows(pages, chain, book):
    rows = []
    for t in common.gold_tables(book):
        if len(t["pages"]) < 2 or not t["located"]:
            continue
        mine = {}
        for page in t["pages"]:
            view = pages[page]
            votes = Counter(view.owner.get(o) for c in t["cells"] for p, o in c["tokens"]
                            if p == page)  # fmt: skip
            votes = Counter({k: v for k, v in votes.items() if view.kind.get(k) == "table"})
            mine[page] = votes.most_common(1)[0][0] if votes else None
        for p, q in zip(t["pages"], t["pages"][1:], strict=False):
            a, b = mine[p], mine[q]
            if a is None or b is None:
                cls = "no table of ours on " + ("both pages" if a is None and b is None else
                                                "the first page" if a is None else
                                                "the second page")  # fmt: skip
            elif chain.get(a, a) == chain.get(b, b):
                cls = "joined"
            else:
                ta = next(x for x in pages[p].tables if x["id"] == a)
                tb = next(x for x in pages[q].tables if x["id"] == b)
                if len(ta["columns"]) != len(tb["columns"]):
                    cls = f"column count differs ({len(ta['columns'])}->{len(tb['columns'])})"
                elif ta["rotation"] != tb["rotation"]:
                    cls = "rotation differs"
                else:
                    cls = "not marked (edge or column proportions)"
            rows.append({"table": t["table"], "pages": [p, q], "class": cls})
    return rows


def our_table_links(pages, chain, book):
    """Our table continuation links scored against the reference tables on both pages."""
    gold_of = {}
    for t in common.gold_tables(book):
        for c in t["cells"]:
            for p, o in c["tokens"]:
                gold_of[(p, o)] = t["table"]
    out, wrong = Counter(), []
    for number, view in pages.items():
        for table in view.tables:
            to = table.get("continues_to")
            if not to or number + 1 not in pages:
                continue
            sides = []
            for page, tid in ((number, table["id"]), (number + 1, to["table_id"])):
                votes = Counter(gold_of.get((page, o)) for o, w in pages[page].owner.items()
                                if w == tid)  # fmt: skip
                votes.pop(None, None)
                sides.append(votes.most_common(1)[0][0] if votes else None)
            if None in sides:
                out["unscored"] += 1
            else:
                out["correct" if sides[0] == sides[1] else "wrong"] += 1
                if sides[0] != sides[1]:
                    wrong.append({"pages": [number, number + 1], "gold": sides,
                                  "tables": [table["id"][:12], to["table_id"][:12]]})  # fmt: skip
    return {**out, "wrong_examples": wrong}


def measure(book, capture, out, continuity=None):
    """``continuity``: a continuity record (development) scored in place of the archive's."""
    pages, archive = c15.book_view(book, str(capture))
    if continuity is not None:
        archive = {**archive, "continuity": common.read(continuity)}
    chain = c15.chains(pages, archive)
    result = {"book": book, "capture": str(capture)}
    if book != common.MATH_BOOK:
        gold = common.derived_gold(book)
        candidates = step9_candidates(book, capture)
        dropped = {(d["from_page"], d["to_page"])
                   for d in archive["lists"]["book"]["dropped_page_joins"]}  # fmt: skip
        rows = unit_rows(book, pages, chain, gold, candidates, dropped)
        pairs = continuation_pairs(pages, gold) if book == "spanish_us_history" else []
        result["reference_cross_page"] = summarize(rows)
        if pairs:
            result["reference_continuations_book1"] = summarize(pair_rows(
                pages, chain, pairs, candidates, dropped))  # fmt: skip
        columns = column_rows(book, pages, gold)
        result["column_splits"] = {"count": len(columns), "kinds": c15.count(columns, "kinds"),
                                   "joined": sum(r["joined"] for r in columns),
                                   "examples": columns[:EXAMPLES]}  # fmt: skip
        links = link_rows(pages, archive, gold, pairs)
        by = defaultdict(Counter)
        for r in links:
            by[r["kind"]][r["verdict"]] += 1
        result["our_links"] = {
            "count": len(links), "by_kind": {k: dict(v) for k, v in by.items()},
            "verdicts": c15.count(links, "verdict"),
            "wrong": [r for r in links if r["verdict"] == "wrong"][:20],
        }  # fmt: skip
    tables = table_rows(pages, chain, book)
    result["tables"] = {"breaks": len(tables), "classes": c15.count(tables, "class"),
                        "examples": [r for r in tables if r["class"] != "joined"][:EXAMPLES],
                        "our_links": our_table_links(pages, chain, book)}  # fmt: skip
    common.write(c15.OUT / out / f"{book}.json", result)
    brief = {k: v for k, v in result.items() if k not in {"book", "capture"}}
    print(book, json.dumps(brief, ensure_ascii=False)[:1500], flush=True)
    return result


def column_rows(book, pages, gold):
    """Reference units split inside one page at a column change: the second piece's first
    line starts right of and above the first piece's last line (horizontal text)."""
    rows = []
    for unit in gold.units:
        if unit["kind"] not in KINDS:
            continue
        tokens = [(p, o) for p, o in ordinals(unit) if o in pages[p].owner]
        for page in sorted({p for p, _ in tokens}):
            view = pages[page]
            seq = [view.owner[o] for p, o in tokens if p == page]
            for a, b in zip(seq, seq[1:], strict=False):
                if a == b or view.kind.get(a) == "table" or view.kind.get(b) == "table":
                    continue
                la = view.layout[view.units[a]["line_ids"][-1]]
                lb = view.layout[view.units[b]["line_ids"][0]]
                if lb.bbox.x0 >= la.bbox.x1 - 2 and lb.bbox.y0 < la.bbox.y0:
                    joined = view.links.get(a, (None, None))[1] == b
                    rows.append(
                        {
                            "unit": unit["unit"],
                            "page": page,
                            "kinds": f"{view.kind[a]}->{view.kind[b]}",
                            "joined": joined,
                        }
                    )
    return rows


def summarize(rows):
    by_kind = defaultdict(Counter)
    classes = Counter()
    examples = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]]["units"] += 1
        by_kind[r["kind"]]["joined"] += r["joined"]
        for c in r["classes"]:
            classes[c] += 1
            if len(examples[c]) < EXAMPLES:
                examples[c].append({"pages": r["pages"], "kind": r["kind"],
                                    "unit": r.get("unit", r.get("units"))})  # fmt: skip
    return {
        "units": len(rows),
        "joined": sum(r["joined"] for r in rows),
        "split": sum(not r["joined"] for r in rows),
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "classes": dict(classes.most_common()),
        "examples": dict(examples),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--capture", default=str(ROOT / "experiments/out/step14b/final"))
    parser.add_argument("--out", default="measure/before")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        measure(name, Path(args.capture), args.out)
