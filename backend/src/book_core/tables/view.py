"""The final unit view with tables: lines a table owns leave their units.

The lists-stage units are unchanged in their cache. In the final view a unit keeps only its
lines outside tables; where a table interrupts a unit, the unit is cut there (each part
keeps its lines in order and the joins between consecutive kept lines). The first part
keeps the unit's id and its link to the previous page; the last part keeps its link to the
next page. A unit whose lines all moved into a table is removed. Every line of the page is
then in exactly one unit or one table (``ownership``).
"""

from book_core.extraction.fingerprints import stable_id


def unit_view(units, tables):
    """(units of the final view, removed unit ids, {new part id: source unit id})."""
    owned = {lid for table in tables for lid in table.line_ids}
    if not owned:
        return list(units), [], {}
    final, removed, parts_of = [], [], {}
    for unit in units:
        if not owned & set(unit.line_ids):
            final.append(unit)
            continue
        runs, current = [], []
        for lid in unit.line_ids:
            if lid in owned:
                if current:
                    runs.append(current)
                current = []
            else:
                current.append(lid)
        if current:
            runs.append(current)
        if not runs:
            removed.append(unit.id)
            continue
        for k, run in enumerate(runs):
            pairs = set(zip(run, run[1:], strict=False))
            joins = [j for j in unit.joins if (j.previous_line_id, j.next_line_id) in pairs]
            if len(joins) != len(run) - 1:
                # Lines are consecutive in the unit, so their joins exist; keep the chain.
                raise ValueError("A unit part lost a join between consecutive lines")
            part_id = unit.id if k == 0 else stable_id(unit.id, "part outside tables", k)
            update = {"line_ids": run, "joins": joins}
            if k > 0:
                update["continues_from"] = None
                parts_of[part_id] = unit.id
            if k < len(runs) - 1:
                update["continues_to"] = None
            final.append(unit.model_copy(update={**update, "id": part_id}))
    return final, removed, parts_of


def ownership(layout_line_ids, units, tables):
    """Problems: lines in no owner, or in more than one (units and tables together)."""
    seen = {}
    for unit in units:
        for lid in unit.line_ids:
            seen[lid] = seen.get(lid, 0) + 1
    for table in tables:
        for lid in table.line_ids:
            seen[lid] = seen.get(lid, 0) + 1
    problems = [f"line {lid} owned {n} times" for lid, n in seen.items() if n != 1]
    problems += [f"line {lid} has no owner" for lid in layout_line_ids if lid not in seen]
    problems += [f"unknown line {lid}" for lid in seen if lid not in set(layout_line_ids)]
    return problems


def without_figures(figures, ids):
    """A page's figure records without the named figures (table pieces): reading indexes
    renumbered, credit proposals to them dropped (as for figures converted to equations)."""
    ids = set(ids)
    if not ids & {f.id for f in figures.figures}:
        return figures
    kept = [f for f in figures.figures if f.id not in ids]
    own = sorted((f for f in kept if f.page == figures.page), key=lambda f: f.anchor.reading_index)
    index = {f.id: i for i, f in enumerate(own, 1)}
    kept = [
        f.model_copy(update={"anchor": f.anchor.model_copy(update={"reading_index": index[f.id]})})
        if f.id in index
        else f
        for f in kept
    ]
    credits = [
        c.model_copy(
            update={"proposed_figure_ids": [i for i in c.proposed_figure_ids if i not in ids]}
        )
        for c in figures.page_credits
    ]
    return figures.model_copy(update={"figures": kept, "page_credits": credits})
