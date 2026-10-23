"""Audit identity and published continuation targets in final book JSONs, read-only."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.assembly.schema import Book, iter_units


def inspect(book):
    units = list(iter_units(book.content))
    ids = Counter(u.id for u in units)
    index = {u.id: u for u in units}
    defects = []
    for uid, count in ids.items():
        if count > 1:
            defects.append(["duplicate_unit", uid, count])
    for unit in units:
        for side, opposite in (("continues_to", "continues_from"),
                               ("continues_from", "continues_to")):
            link = getattr(unit, side)
            if link is None:
                continue
            target = index.get(link.unit)
            reverse = getattr(target, opposite, None)
            if reverse is None or reverse.unit != unit.id:
                defects.append(["broken_continuation", unit.id, side, link.unit])
    known = set(ids) | {f.id for f in book.furniture or []} | {s.id for s in book.suppressed or []}
    for unit in units:
        for field in ("captions", "credits", "text", "notes"):
            known.update(t.id for t in getattr(unit, field, []) if hasattr(t, "id"))
        title = getattr(unit, "title", None)
        if title is not None:
            known.add(title.id)
    reviews = book.review.items if book.review else []
    unresolved = Counter(r.kind for r in reviews if r.unit and r.unit not in known)
    reviewed = {r.unit for r in reviews}
    defects.extend(["uncertain_unit_without_review", u.id, u.type] for u in units
                   if u.review_status != "ok" and u.id not in reviewed)
    return {"units": len(units), "defects": defects,
            "unresolved_review_unit_ids_by_kind": dict(unresolved),
            "unresolved_review_examples": [r.model_dump() for r in reviews
                                            if r.unit and r.unit not in known][:5]}


if __name__ == "__main__":
    result = {}
    for path in (ROOT / "experiments/out/step17/final/performance").glob("*.json"):
        record = json.loads(path.read_text("utf-8"))["run"]
        book = Book.model_validate_json((Path(record["book_json"]) / "book.json").read_bytes())
        result[path.stem] = inspect(book)
        print(path.stem, {k: v for k, v in result[path.stem].items()
                          if k != "unresolved_review_examples"}, flush=True)
    (ROOT / "experiments/out/step17/final/contract_check.json").write_text(
        json.dumps(result, indent=1) + "\n", "utf-8")
    sys.exit(1 if any(row["defects"] for row in result.values()) else 0)
