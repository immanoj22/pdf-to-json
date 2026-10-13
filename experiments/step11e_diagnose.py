"""Read-only diagnosis of the frozen four-book fallback credit decisions."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step11c_identity import BOOKS

from book_core.cache_store import read_json
from book_core.layout.evidence import (
    ROTATED_STRUCTURE_LINES,
    box_gap,
    credit_like,
    isolated_rotated,
    line_text,
    page_body_style,
    rotation_key,
    text_lines,
)
from book_core.layout.frames import right_angle
from book_core.layout.models import PageLayout
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.reference.xml_reader import load_tree

OUT = ROOT / "experiments/out/step11e"
BASE = ROOT / "experiments/out/step11d/before"


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8", newline="\n"
    )


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf8")


def normalized(text):
    return "".join(c.casefold() for c in unicodedata.normalize("NFKC", text) if c.isalnum())


def freeze_provenance():
    if (OUT / "baseline.json").exists():
        raise ValueError("The pre-change provenance is frozen; use the committed capture")
    assert git("rev-parse", "HEAD").startswith("90a544a")
    assert not git("diff", "HEAD")
    free = shutil.disk_usage(ROOT).free
    estimate = 1412 * 12 * 1024 * 1024
    assert free - estimate >= 10_000_000_000
    write(
        "baseline.json",
        {
            "revision": git("rev-parse", "HEAD").strip(),
            "status": git("status", "--porcelain=v1", "--untracked-files=all"),
            "settings_sha256": hashlib.sha256(
                (ROOT / ".vscode/settings.json").read_bytes()
            ).hexdigest(),
            "disk_free_bytes": free,
            "estimate_bytes": estimate,
            "remaining_after_estimate_bytes": free - estimate,
            "baseline": "experiments/out/step11d/before",
            "approved_books": BOOKS,
        },
    )


def reference_contexts():
    """Resolve deepest containers; equal text lengths do not imply equal roles."""
    inventory = json.loads((OUT / "diagnosis/fallback_credits.json").read_text("utf8"))
    root, _ = load_tree(reference_path("spanish_xml").read_bytes())
    parents = {child: parent for parent in root.iter() for child in parent}
    markers, last = {}, None
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.endswith("pagenum"):
            last = "".join(element.itertext())
        markers[element] = last
    rows = []
    for row in inventory["rows"]:
        if row["checker_pass"]:
            continue
        query = normalized(row["text"])
        matches = [
            element
            for element in root.iter()
            if query in normalized("".join(element.itertext()))
            and not any(query in normalized("".join(child.itertext())) for child in element)
        ]
        witnesses = []
        for element in matches:
            ancestors, current = [], element
            while current is not None:
                ancestors.append({"tag": current.tag, "attributes": current.attrib})
                current = parents.get(current)
            witnesses.append(
                {
                    "preceding_reference_page_marker": markers[element],
                    "ancestors": ancestors,
                    "text": "".join(element.itertext()),
                }
            )
        row["reference_containers"] = witnesses[0]["ancestors"] if witnesses else []
        row["reference_matches"] = witnesses
        rows.append({"physical_page": row["page"], "line_id": row["line_id"], "matches": witnesses})
    write("diagnosis/fallback_credits.json", inventory)
    write("diagnosis/reference_contexts.json", rows)
    group_contexts()


def group_contexts():
    inventory = json.loads((OUT / "diagnosis/fallback_credits.json").read_text("utf8"))
    result = []
    for row in inventory["rows"]:
        if row["checker_pass"]:
            continue
        baseline = json.loads((BASE / f"{row['book']}.json").read_text("utf8"))
        key = baseline["keys"]["layout"]
        layout = verified_read(
            ROOT / ".cache/step7/layout" / key / f"{row['page']}.json", PageLayout, key
        )
        line = next(line for line in layout.lines if line.id == row["line_id"])
        regions = {lid: region for region in layout.regions for lid in region.line_ids}
        members = [
            {
                "line_id": other.id,
                "rotation": other.rotation,
                "region_id": regions[other.id].id,
                "region_type": regions[other.id].type,
                "band_id": regions[other.id].band_id,
            }
            for other in text_lines(layout.lines)
            if not other.horizontal and rotation_key(other) == rotation_key(line)
        ]
        result.append(
            {"book": row["book"], "page": row["page"], "line_id": line.id, "members": members}
        )
    write("diagnosis/groups.json", result)


def main():
    freeze_provenance()
    history = {}
    for name, start, end in (
        ("pipeline.py", 590, 596),
        ("invariants.py", 125, 147),
        ("evidence.py", 160, 195),
    ):
        path = "backend/src/book_core/layout/" + name
        history[name] = {
            "log": git("log", "--oneline", "--", path),
            "blame": git("blame", "90a544a", "-L", f"{start},{end}", "--", path),
        }
    write("diagnosis/history.json", history)
    root, repairs = load_tree(reference_path("spanish_xml").read_bytes())
    reference = normalized("".join(root.itertext()))
    rows = []
    for book in BOOKS:
        baseline = json.loads((BASE / f"{book}.json").read_text("utf8"))
        archive = json.loads(
            (ROOT / f"experiments/out/step11c/archive/{book}.json").read_text("utf8")
        )
        for number in baseline["pages"]:
            key = baseline["keys"]["layout"]
            layout = verified_read(
                ROOT / ".cache/step7/layout" / key / f"{number}.json", PageLayout, key
            )
            fallback = [
                r
                for r in layout.regions
                if r.type == "credit_candidate"
                and r.reasons == ["Rotated small text outside figures"]
            ]
            if not fallback:
                continue
            source = ExtractedPage.model_validate(
                read_json(Path(archive["output"]) / f"page_{int(number):06d}.json.gz")["source"]
            )
            body = page_body_style(layout.lines, source.store)
            figures = [b.bbox for b in layout.blocks if b.kind == "figure"]
            groups = Counter(
                rotation_key(item) for item in text_lines(layout.lines) if not item.horizontal
            )
            by_id = {item.id: item for item in layout.lines}
            for region in fallback:
                line = by_id[region.line_ids[0]]
                scope = (
                    groups[rotation_key(line)] >= ROTATED_STRUCTURE_LINES
                    and right_angle(rotation_key(line)) is not None
                )
                evidence = credit_like(line, layout.lines, figures, body[1] if body else None)
                text = line_text(line, source.store)
                query = normalized(text)
                # Exact normalized presence, followed by long leading/trailing witnesses.
                queries = [query, query[:80], query[-80:]]
                rows.append(
                    {
                        "book": book,
                        "page": int(number),
                        "line_id": line.id,
                        "text": text,
                        "font_size": line.font_size,
                        "body_size": body[1] if body else None,
                        "relative_size": line.font_size / body[1] if body else None,
                        "rotation_group_lines": groups[rotation_key(line)],
                        "checker_scope": scope,
                        "full_credit_evidence": evidence,
                        "checker_pass": not scope or evidence,
                        "isolated": isolated_rotated(line, layout.lines),
                        "figure_distance_font_units": min(
                            (box_gap(line.bbox, b) / line.font_size for b in figures), default=None
                        ),
                        "reference_witnesses": [
                            {"query": q, "present": q in reference} for q in queries
                        ]
                        if book == "spanish_us_history" and scope and not evidence
                        else None,
                    }
                )
        print(
            book,
            Counter(
                (r["checker_pass"], r["full_credit_evidence"]) for r in rows if r["book"] == book
            ),
            flush=True,
        )
    write(
        "diagnosis/fallback_credits.json",
        {
            "rows": rows,
            "counts": {
                book: {
                    "fallback_total": sum(r["book"] == book for r in rows),
                    "checker_pass": sum(r["book"] == book and r["checker_pass"] for r in rows),
                    "full_evidence_pass": sum(
                        r["book"] == book and r["full_credit_evidence"] for r in rows
                    ),
                    "violations": sum(r["book"] == book and not r["checker_pass"] for r in rows),
                }
                for book in BOOKS
            },
        },
    )
    reference_contexts()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", action="store_true")
    args = parser.parse_args()
    (reference_contexts if args.references else main)()
