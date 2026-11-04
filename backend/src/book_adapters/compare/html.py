"""The compare report as one HTML page (no scripts, no external files)."""

from __future__ import annotations

import html

STYLE = """
:root { --fg:#1d1d1f; --bg:#ffffff; --muted:#5f6368; --line:#d9dce1; --head:#f3f4f6;
  --adapter:#8a4b00; --stage1:#1a5fb4; --source:#3d6b35; --check:#9b1c1c; }
@media (prefers-color-scheme: dark) { :root { --fg:#e8eaed; --bg:#16181b; --muted:#a6abb3;
  --line:#3a3f45; --head:#22262a; --adapter:#f0a35e; --stage1:#7fb0ff; --source:#8fd17f;
  --check:#ff8a80; } }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg);
  margin: 0 auto; padding: 16px; max-width: 1100px; }
table { border-collapse: collapse; margin: 8px 0 20px; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 4px 8px; text-align: left;
  vertical-align: top; }
th { background: var(--head); } td.n { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); } h1 { font-size: 20px; } h2 { font-size: 16px; margin-top: 24px; }
.label { font-weight: 600; } .l-adapter { color: var(--adapter); }
.l-stage-1 { color: var(--stage1); }
.l-source { color: var(--source); } .l-check, .l-reference { color: var(--check); }
.wrap { overflow-x: auto; }
"""


def _e(value) -> str:
    return html.escape(str(value))


def _table(head: list[str], rows: list[list], numeric: set[int] = frozenset()) -> str:
    out = ["<div class='wrap'><table><tr>" + "".join(f"<th>{_e(h)}</th>" for h in head) + "</tr>"]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cls = " class='n'" if i in numeric else ""
            cells.append(f"<td{cls}>{cell}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table></div>")
    return "\n".join(out)


def page(title: str, sections: list[tuple[str, str]], intro: str = "") -> str:
    body = "\n".join(f"<h2>{_e(h)}</h2>\n{content}" for h, content in sections)
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title><style>{STYLE}</style></head><body>"
        f"<h1>{_e(title)}</h1>{intro}\n{body}\n</body></html>\n"
    )


def compare_html(result: dict, ours: str, reference: str) -> str:
    def lab(name):
        cls = "l-" + name.lower().replace(" ", "-")
        return f"<span class='label {cls}'>{_e(name)}</span>"

    biggest = _table(
        ["Element", "Ours", "Reference", "Difference", "Label", "Why"],
        [
            [_e(d["element"]), d["ours"], d["reference"], f"{d['diff']:+d}", lab(d["label"]),
             _e(d["why"])]
            for d in result["biggest_differences"]
        ],
        {1, 2, 3},
    )  # fmt: skip
    key = _table(
        ["Element", "Ours", "Reference", "Difference"],
        [[_e(k), v["ours"], v["reference"], f"{v['diff']:+d}"]
         for k, v in result["key_elements"].items()],
        {1, 2, 3},
    )  # fmt: skip
    links = _table(
        ["Link kind", "Ours", "Reference"],
        [[_e(k), v["ours"], v["reference"]] for k, v in result["links"].items()],
        {1, 2},
    )
    boxes = _table(
        ["Box kind", "Ours", "Reference"],
        [[_e(k), v["ours"], v["reference"]] for k, v in result["sidebars"].items()],
        {1, 2},
    )
    split = result["paragraph_splits"]
    split_rows = [
        [_e(x["cause"]), _e(x["end_of_first"]), _e(x["start_of_second"])] for x in split["examples"]
    ]
    splits = (
        f"<p>Our consecutive paragraphs that the reference holds in one: "
        f"{_e(split['ours_split_reference_one'] or 0)}. Reference consecutive paragraphs that "
        f"ours holds in one: {split['ours_one_reference_split']}.</p>"
        + _table(["Cause", "End of the first", "Start of the second"], split_rows)
    )
    wf = result["well_formed"]
    wf_rows = []
    for side in ("ours", "reference"):
        if wf[side] == "all":
            wf_rows.append([side, f"all {wf['files_checked'][side]} files well-formed", ""])
        else:
            for file, err in wf[side].items():
                wf_rows.append([side, _e(file), _e(err)])
    files = result["files"]
    file_text = (
        f"<p>{files['common']} files in both. Only ours: {len(files['only_ours'])}. "
        f"Only the reference: {len(files['only_reference'])}.</p>"
        + _table(
            ["Only ours", "Only the reference"],
            [["<br>".join(_e(f) for f in files[k][:40]) for k in ("only_ours", "only_reference")]],
        )
    )
    info = result["page_info"]
    intro = (
        f"<p class='muted'>Ours: {_e(ours)}<br>Reference: {_e(reference)}<br>"
        f"Main files: {_e(' / '.join(result['main_files']))}. page_info.xml equal: "
        f"{'yes' if info['equal'] else 'no'}.</p>"
    )
    return page(
        "Delivery compare",
        [
            ("Biggest differences", biggest),
            ("Key elements", key),
            ("Links by kind", links),
            ("Boxes (sidebar)", boxes),
            ("Paragraph splits", splits),
            ("Well-formedness", _table(["Delivery", "File", "Error"], wf_rows)),
            ("Files", file_text),
        ],
        intro,
    )
