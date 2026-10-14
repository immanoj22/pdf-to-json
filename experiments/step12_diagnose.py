"""Step 12 diagnosis: geometry of the main failure classes before any rule.

For reference captions read in callout/main streams, credits in separate credit streams and
figure-internal tokens in paragraph-like units: the distance from the unit's region to the
nearest figure on the page (in font sizes), and for lines inside figure boxes, the derived
gold kind of their tokens.
"""

# ruff: noqa: E402
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step12_reference as reference
from step12_measure import gold_tokens, inside, load

OUT = ROOT / "experiments/out/step12/diagnosis"


def gap(a, b):
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return max(dx, dy)


def bucket(value):
    for limit in (0, 1, 2, 4, 8, 16):
        if value <= limit:
            return f"<={limit}"
    return ">16" if value != float("inf") else "no figure"


def main(book):
    from book_core.evaluation.furniture import token_lines
    from book_core.paragraphs.text import unit_text

    inv = reference.inventory(book)
    gold, pages, _, _ = load(book)
    owner, credit_units = gold_tokens(gold, inv)
    rows = defaultdict(Counter)
    examples = defaultdict(list)
    for page, layout, built in pages():
        number = page.geometry.page
        figures = [r for r in layout.regions if r.type == "figure"]
        stream_of = {lid: s for s in built.order.streams for lid in s.line_ids}
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        region_of = {lid: r for r in layout.regions for lid in r.line_ids}
        lines = {line.id: line for line in layout.lines}
        kinds_of_unit = defaultdict(Counter)
        for ordinal, lid in enumerate(token_lines(page, layout)):
            if lid is None:
                continue
            hit = owner.get((number, ordinal))
            unit = unit_of[lid]
            tag = "unaligned" if hit is None else ("credit" if hit[0] in credit_units else hit[1])
            kinds_of_unit[unit.id][tag] += 1
        for unit in built.units:
            tags = kinds_of_unit.get(unit.id)
            if not tags:
                continue
            tag = tags.most_common(1)[0][0]
            body = sum(v for k, v in tags.items() if k not in {"image_description", "unaligned"})
            if tags["image_description"] and body:
                rows["unit mixes figure-internal and other reference tokens"][
                    f"{unit.kind}:{'minority' if tags['image_description'] < body else 'majority'}"
                ] += 1
                if len(examples["unit mixes figure-internal and other reference tokens"]) < 12:
                    examples["unit mixes figure-internal and other reference tokens"].append(
                        {
                            "page": number,
                            "tags": dict(tags),
                            "kind": unit.kind,
                            "text": unit_text(page.store, layout, unit)[:100],
                        }
                    )
            stream = stream_of[unit.line_ids[0]]
            boxes = [lines[x].bbox for x in unit.line_ids]
            font = sorted(lines[x].font_size for x in unit.line_ids)[len(boxes) // 2] or 1
            distance = (
                min((min(gap(b, f.bbox) for b in boxes) for f in figures), default=float("inf"))
                / font
            )
            region = region_of[unit.line_ids[0]]
            key = f"{tag} | {stream.kind}:{unit.kind} | {region.type}"
            if tag in {"caption", "credit", "image_description"} and stream.kind != "figure":
                rows[key][bucket(distance)] += 1
                if len(examples[key]) < 4:
                    examples[key].append(
                        {
                            "page": number,
                            "distance_font_sizes": round(distance, 2)
                            if distance != float("inf")
                            else None,
                            "lines": len(unit.line_ids),
                            "text": unit_text(page.store, layout, unit)[:100],
                        }
                    )
            inside_figure = any(
                inside(f.bbox, lines[x].bbox) for x in unit.line_ids for f in figures
            )
            if (
                inside_figure
                and region.type != "figure"
                and unit.kind in {"paragraph", "list_item"}
            ):
                rows["inside figure box, not embedded"][tag] += 1
                if len(examples["inside figure box, not embedded"]) < 12:
                    examples["inside figure box, not embedded"].append(
                        {
                            "page": number,
                            "gold": tag,
                            "region": region.type,
                            "text": unit_text(page.store, layout, unit)[:100],
                        }
                    )
    result = {
        k: {"distance": dict(v), "examples": examples[k]}
        for k, v in sorted(rows.items(), key=lambda kv: -sum(kv[1].values()))
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{book}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    for k, v in result.items():
        print(sum(v["distance"].values()), k, v["distance"])


if __name__ == "__main__":
    main(sys.argv[1])
