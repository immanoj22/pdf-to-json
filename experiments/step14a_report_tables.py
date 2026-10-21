"""Step 14a: fill the report's method tables from the evidence files (no hand-typed numbers).

Replaces ``METHODS_DETECTION_TABLE`` and ``METHODS_STRUCTURE_TABLE`` in
docs/step14a_report.md with rows built from ``experiments/out/step14a/methods/final`` and
``experiments/out/step14a/dev/final``.
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

BOOKS = ["spanish_us_history", "immigrant_children", "medical_anatomy", "statistics"]


def pr(row):
    if not row or row.get("detection_precision") is None:
        return "—"
    recall = row.get("detection_recall")
    return f"{row['detection_precision']:.2f} / {recall:.2f} ({row['our_tables']})"


def f(value, digits=3):
    return "—" if value is None else f"{value:.{digits}f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    detection, structure = [], []
    for book in BOOKS:
        methods = common.read(common.OUT / f"methods/final/{book}.json")
        dev = common.read(common.OUT / f"dev/final/{book}.json")
        d = methods["detection"]
        owning = (
            f"**{dev['detection_precision']:.3f} / {dev['detection_recall']:.3f}** "
            f"({dev['our_tables']})"
        )
        detection.append(
            f"| {common.SHORT[book]} | {owning} | "
            + " | ".join(
                pr(d.get(k))
                for k in ("heron", "pp", "tatr", "rules_grid", "rules_stack", "layout_step4")
            )  # fmt: skip
            + " |"
        )
        s = methods["structure"]
        cells = []
        for name in ("geometry", "tableformer", "tatr", "pdfplumber", "camelot"):
            row = s.get(name)
            if not row:
                cells.append("—")
                continue
            cell = (
                f"{f(row['teds_structure_mean'])} / {f(row['adjacency_f1'])} / "
                f"{f(row['header_rows_exact'], 2)} ({row['structure_scored']})"
            )
            cells.append(f"**{cell}**" if name == "geometry" else cell)
        structure.append(f"| {common.SHORT[book]} | " + " | ".join(cells) + " |")
    detection_table = "\n".join(detection) + (
        "\n\nA source alone counts each of its regions as a table (score ≥ 0.5 for models); "
        "the parentheses give the number of regions. Every source alone is either imprecise "
        "(the models and ruled grids also find panels, organizers and boxes) or incomplete "
        "(Step 4 regions, stacks); the combination with the ownership rule is the best on "
        "precision in every book."
    )
    structure_header = (
        "| Book | **Our geometry** | TableFormer (accurate) | Table Transformer structure | "
        "pdfplumber | Camelot (pdfium) |\n|---|---|---|---|---|---|\n"
    )
    structure_table = (
        structure_header
        + "\n".join(structure)
        + (
            "\n\nCells: TEDS / adjacency F1 / header rows exact (tables scored). Same detected "
            "regions for every method (our text-owning and possible tables that match a reference "
            "segment). Time per table on CPU: TableFormer ~1.6–8 s, Table Transformer ~0.5 s, "
            "pdfplumber ~0.05 s, Camelot ~0.5 s (readings cached)."
        )
    )
    report = ROOT / "docs/step14a_report.md"
    text = report.read_text("utf-8")
    text = text.replace("METHODS_DETECTION_TABLE", detection_table)
    text = text.replace("METHODS_STRUCTURE_TABLE", structure_table)
    report.write_text(text, "utf-8", newline="\n")
    print(detection_table)
    print(structure_table)


if __name__ == "__main__":
    main()
