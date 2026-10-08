"""Compact review tables from the immutable Step 4b experiment manifest."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4b"


def ratio(value):
    return f"{value['regions_agree_certain']}/{value['regions_certain']}"


def band_values(bands, field):
    return ", ".join(str(b[field]) for b in bands) or "-"


def main():
    manifest = json.loads((OUT / "manifest.json").read_text("utf-8"))
    pages = manifest["pages"]
    lines = [
        "| Fixture | Own type agreement | Heron | PP | Fused |",
        "|---|---:|---:|---:|---:|",
    ]
    for page in pages:
        if "gold" not in page:
            continue
        gold = page["gold"]
        lines.append(
            f"| {page['page']} | {ratio(gold['own'])} | "
            f"{ratio(gold['models']['heron'])} | "
            f"{ratio(gold['models']['pp_doclayoutv3'])} | {ratio(gold['fused'])} |"
        )
    lines.extend(
        [
            "",
            "Certain gold items only; unchanged evaluator. Gold remains unapproved.",
            "",
            "| Page | Own/fused columns per band | Heron x components | PP x components | "
            "Heron disagreements | PP disagreements |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for page in pages:
        diag = page["model_band_diagnostics"]
        lines.append(
            f"| {page['page']} | {band_values(page['own_bands'], 'own_columns')} | "
            f"{band_values(diag['heron'], 'spatial_text_components')} | "
            f"{band_values(diag['pp_doclayoutv3'], 'spatial_text_components')} | "
            f"{page['disagreements']['heron']['total']} | "
            f"{page['disagreements']['pp_doclayoutv3']['total']} |"
        )
    lines.extend(
        [
            "",
            "Band sequence is pipeline order with page/callout/rotated scopes; not reading order. "
            "Full scopes, lanes, component intervals, and lane support are in manifest.json. "
            "Model bands/columns are N/A; x components are diagnostics only.",
            "",
            "| Page without gold | Heron statuses | PP statuses | Overlay |",
            "|---|---|---|---|",
        ]
    )
    for page in pages:
        if "gold" in page:
            continue

        def statuses(name, current_page=page):
            return (
                ", ".join(
                    f"{key}: {value}"
                    for key, value in current_page["disagreements"][name]["by_status"].items()
                )
                or "-"
            )

        lines.append(
            f"| {page['page']} | {statuses('heron')} | {statuses('pp_doclayoutv3')} | "
            f"[png]({Path(page['overlay']).name}) |"
        )
    repeat = [comparison for p in pages for comparison in p["repeat_cpu_tolerance"].values()]
    boundary = sum(
        len(c["boundary_expected_only"]) + len(c["boundary_actual_only"]) for c in repeat
    )
    lines.extend(
        [
            "",
            f"CPU repeats: {sum(c['passed'] for c in repeat)}/{len(repeat)} tolerance gates pass; "
            f"{boundary} boundary unmatched observations.",
        ]
    )
    (OUT / "report_tables.md").write_text("\n".join(lines) + "\n", "utf-8")


if __name__ == "__main__":
    main()
