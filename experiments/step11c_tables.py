"""Render measured Step 11c tables; never extracts or scores a book."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step11c"
BOOKS = {
    "spanish_us_history": "Book 1 — Spanish US history (758 pages)",
    "immigrant_children": "Book 2 — Immigrant children (331 pages)",
    "art_therapy_index": "Book 3 — Art-therapy index (9 pages; anecdotal)",
    "medical_anatomy": "Book 4 — Medical anatomy (314 pages; development)",
}
STAGES = (
    "native",
    "analysis",
    "layout",
    "reading_order",
    "furniture",
    "paragraphs",
    "structure_evidence",
    "structure",
    "lists",
)


def load(path):
    return json.loads((OUT / path).read_text("utf8"))


def pair(before, after, field, scale=1):
    return f"{before[field] / scale:.2f} → {after[field] / scale:.2f}"


def observed_peak(row):
    # Include OS process high-water marks: the aggregate sampler can miss short spikes.
    return max(
        row["peak_tree_rss_bytes"],
        row["total"]["peak_rss_bytes"],
        *(worker["peak_rss_bytes"] for worker in row["worker_processes"].values()),
    )


def cache_tables():
    before, after = load("before/cached_reads.json"), load("after/cached_reads.json")
    lines = []
    for book, title in BOOKS.items():
        lines += [f"### {title}", "", "All pairs are **before → after**.", ""]
        lines += [
            "| Stage | Wall s | CPU s | Peak RSS MiB | Cache MiB | KiB/page |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for stage in STAGES:
            old, new = before[book][stage], after[book][stage]
            cells = [stage.replace("_", " ")]
            for field, scale in (
                ("wall_seconds", 1),
                ("cpu_seconds", 1),
                ("peak_rss_bytes", 1024**2),
                ("cache_bytes", 1024**2),
                ("cache_bytes_per_page", 1024),
            ):
                cells.append(pair(old, new, field, scale))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def full_runs():
    lines = [
        "| Book | Workers | Wall s | CPU s | Observed peak RSS MiB | PDF hashes | Source reads |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for book in BOOKS:
        for workers in (1,):
            row = load(f"performance/{book}_workers{workers}.json")
            lines.append(
                f"| {book} | {workers} | {row['total']['wall_seconds']:.2f} | "
                f"{row['total_cpu_seconds']:.2f} | {observed_peak(row) / 1024**2:.2f} | "
                f"{row['source_hashes']} | {row['source_reads']} |"
            )
    return "\n".join(lines) + "\n"


def book300():
    lines = [
        "| Mode | Workers | Wall s | CPU s | Observed peak RSS MiB | "
        "Intermediate MiB | Final MiB | PDF hashes | Source reads |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, workers in (("development", 1), ("production", 2)):
        row = load(f"book300/{mode}_workers{workers}.json")
        intermediate = sum(stage.get("cache_bytes", 0) for stage in row["stages"].values())
        final = sum(p.stat().st_size for p in Path(row["output"]).iterdir())
        condition = (
            "cold"
            if mode == "production"
            or row["stages"]["native"].get("source_reads", 0) == row["pages"]
            else "resumed"
        )
        lines.append(
            f"| {mode} ({condition}) | {workers} | {row['total']['wall_seconds']:.2f} | "
            f"{row['total_cpu_seconds']:.2f} | {observed_peak(row) / 1024**2:.2f} | "
            f"{intermediate / 1024**2:.2f} | {final / 1024**2:.2f} | "
            f"{row['source_hashes']} | {row['source_reads']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    text = cache_tables() + "\n" + full_runs() + "\n" + book300()
    (OUT / "tables.md").write_text(text, "utf8")
    print(text, end="")
