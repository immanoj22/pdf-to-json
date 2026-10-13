"""Attach explicit explanations to every changed metric without exclusions."""

from step11e_run import OUT, read, write


def reason(path):
    if path in {
        "/cache_key_inputs/paragraph_book_key",
        "/cache_key_inputs/structure_decision_key",
        "/gates/paragraph_book_key",
    }:
        return "Upstream layout producer changed; downstream keys carry the changed upstream key."
    if path == "/seconds":
        return "Measured evaluation duration; separate run with concurrent verification activity."
    if path.startswith("/paragraphs/"):
        field = path.rsplit("/", 1)[-1]
        if field in {"boundary_f1", "boundary_precision"}:
            return (
                "Page 724 reference paragraph 832 is split at alfombra,/también: one additional "
                "false positive boundary. The existing paragraph stage acts on the credit lines "
                "inserted into main flow by reading order after the layout downgrade."
            )
        if field in {"exact_unit_match", "exact_units", "exact"}:
            return (
                "Page 724 reference paragraph 832 loses its exact match; deterministic regression."
            )
        if field in {"units_split", "split"}:
            return (
                "Page 724 reference paragraph 832 changes from one piece to two. Reference credit "
                "unit 839 changes from three pieces to two, remains split, and offsets the extra "
                "piece in split_errors but not in units_split."
            )
    if path.startswith("/reading_order/"):
        if path.endswith("/anchors_by_kind/credit") or path.endswith("/float_anchors"):
            return (
                "Pages 324, 350 and 361 each lose one correctly anchored credit stream from the "
                "scored float denominator when its text enters main flow. No new anchor miss in "
                "the four-page comparison; three correct observations are removed."
            )
        if path.endswith("/within_floats"):
            return (
                "Page 724 credit tokens leave a figure stream: six concordant within-float "
                "reference pairs leave the denominator (changed-page subset 41/44 to 35/38)."
            )
        if path.endswith("/kendall_tau") or path.endswith("/main_flow"):
            return (
                "The stream majority changes for four reference units on the four edited pages, "
                "adding main-flow comparisons. On page 724 the inserted credit splits the quote "
                "order and adds two discordant reference-unit pairs; pooled ratios also reflect "
                "the added concordant pairs on the other three pages. This is not a uniform gain."
            )
    raise ValueError("Unexplained changed metric: " + path)


def main():
    comparison = read(OUT / "comparison.json")
    rows = {}
    for book, result in comparison.items():
        changes = []
        for change in result["metric_changes"]:
            if book != "spanish_us_history":
                assert change["path"] in {
                    "/cache_key_inputs/paragraph_book_key",
                    "/cache_key_inputs/structure_decision_key",
                    "/gates/paragraph_book_key",
                    "/seconds",
                }, (book, change)
            changes.append({**change, "reason": reason(change["path"])})
        rows[book] = changes
    effects = read(OUT / "effects.json")
    changed = effects["changed_reference_units"]
    assert set(changed) == {"832", "839"}
    assert changed["832"]["before"]["exact"] and not changed["832"]["after"]["exact"]
    assert len(changed["832"]["before"]["pieces"]) == 1
    assert len(changed["832"]["after"]["pieces"]) == 2
    assert len(changed["839"]["before"]["pieces"]) == 3
    assert len(changed["839"]["after"]["pieces"]) == 2
    for view in ("step11", "step9", "nearest", "end"):
        before, after = [version["reading_order"][view] for version in effects["versions"]]
        assert before["anchor_misses"] == after["anchor_misses"]
        assert (
            before["float_anchors"]["anchored_streams"] - after["float_anchors"]["anchored_streams"]
            == 3
        )
        assert before["within_floats"]["pairs"] - after["within_floats"]["pairs"] == 6
    write(
        "metric_explanations.json",
        {
            "comparison_has_no_metric_exclusions": True,
            "changes": rows,
            "accuracy_gate": "FAIL",
            "cause": "Deterministic page 724 paragraph split and main-flow order regression.",
            "no_noise_exception_applied": True,
            "additional_product_changes": False,
        },
    )
    lines = [
        "# Every changed metric",
        "",
        "No metric fields are excluded. See effects.json for the stage and token witnesses.",
        "",
    ]
    for book, changes in rows.items():
        lines += [f"## {book}", "", "| Path | Before | After | Reason |", "|---|---|---|---|"]
        lines.extend(
            f"| `{row['path']}` | `{row['before']}` | `{row['after']}` | {row['reason']} |"
            for row in changes
        )
        lines.append("")
    (OUT / "metric_changes.md").write_text("\n".join(lines), encoding="utf8", newline="\n")
    print({book: len(changes) for book, changes in rows.items()})


if __name__ == "__main__":
    main()
