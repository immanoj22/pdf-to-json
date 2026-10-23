"""Recorded visual judgments, entered only after inspecting every sampled crop/page."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out/step17b"


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", "utf-8")


rows = json.loads((OUT / "style_sample.json").read_text("utf-8"))
summary = defaultdict(Counter)
for row in rows:
    key, number = row["sample_id"].rsplit("-", 1)
    verdict, cause = "correct", "Printed weight/slope/script/underline agrees with detected range."
    n = int(number)
    if key == "spanish_us_history-underline" and n in {5, 6, 12}:
        verdict, cause = "wrong", "Checkmark glyph sits on the bottom edge of a filled rectangular label; that edge is not a text underline."
    if key == "spanish_us_history-underline" and n in {15, 16, 17, 19}:
        verdict, cause = "wrong", "Map river/boundary/graticule strokes coincide with the label baseline; no printed text underline."
    if key == "medical_anatomy-underline" and n in {5, 7, 8, 9, 11}:
        verdict, cause = "wrong", "Column-width section separator below a heading is encoded as text underline. Distinguishing a decorative rule from intentional heading underlining needs context."
    if key == "medical_anatomy-bold" and n == 17:
        verdict, cause = "unclear", "Single panel letter D: insufficient visual weight contrast to decide bold reliably."
    row.update(verdict=verdict, note=cause)
    summary[key][verdict] += 1
write("style_verdicts.json", rows)
write("style_summary.json", dict(summary))

fig = json.loads((OUT / "figure_sample.json").read_text("utf-8"))
fig_counts = Counter()
for i, row in enumerate(fig["rows"], 1):
    cause = "table_fragment"
    note = "Printed table cell (including header, bottom row or formula inside a table)."
    if i in {3, 15, 28, 29}:
        cause, note = "exercise_number", "Exercise/answer enumeration beside a formula, not a figure label or equation operand."
    elif i == 24:
        cause, note = "equation_part", "Formula exercise with a blank answer line."
    elif i == 27:
        cause, note = "prose_fragment", "The word 'proportion' introduces an inline formula; not an axis label or full paragraph."
    row.update(cause=cause, note=note)
    fig_counts[cause] += 1
fig["counts"] = {k: fig_counts[k] for k in ("axis_label", "table_fragment", "equation_part", "real_paragraph", "exercise_number", "prose_fragment")}
write("figure_verdicts.json", fig)

printed = {
    "spanish_us_history": {685: ["A"], 702: [], 719: ["W", "Y", "Z"]},
    "immigrant_children": {308: [], 318: [], 327: []},
    "art_therapy_index": {1: [], 5: [], 9: []},
    "medical_anatomy": {305: ["A", "B"], 310: ["M", "N"], 314: ["W", "X", "Y", "Z"]},
    "statistics": {869: list("ABCDEFGHILMNOPQRS"), 870: list("TUVZ"), 871: []},
}
index = json.loads((OUT / "index_sample.json").read_text("utf-8"))
for book, value in index.items():
    value["hand_count"] = [{"page": p, "printed_letters": chars, "printed_count": len(chars),
                            "json_dividers": [d for d in value["all_json_dividers"] if p in d["pages"]]}
                           for p, chars in printed[book].items()]
    if book == "statistics":
        value["note"] = "All three printed Index leaves inspected: two contain entries; physical 871 is blank apart from the running head."
write("index_hand_count.json", index)

write("part_a_visual_record.json", {
    "complete": True, "production_code_changed": False,
    "style_spans_inspected": len(rows), "figure_paragraphs_inspected": len(fig["rows"]),
    "index_pages_inspected": sum(len(v) for v in printed.values()),
    "limitations": ["Single visual reviewer; not independently double-annotated.",
                    "Uniform random spans, not independent pages or books; repeated content can be sampled.",
                    "Source-span boxes can include neighbouring characters; judged only the recorded text range.",
                    "Context census uses serialized semantic ownership, not exhaustive visual relabeling."],
    "inputs_sha256": hashlib.sha256((OUT / "inputs.json").read_bytes()).hexdigest(),
})
print(json.dumps({k: dict(v) for k, v in summary.items()}))
print(fig["counts"])
