"""Read-only single-page invisible-stream counterfactual with frozen whole-book context."""

# ruff: noqa: E402
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import BOOKS, CACHE
from step8_run import CACHE8
from step9_run import CACHE9, navigation_map
from step10_run import CACHE10
from step11c_run import model_digest
from step11d2_hidden import OUT, write
from step11d2_markers import frozen_book as load_book
from step11d2_markers import frozen_evidence as evidence_for

from book_core.furniture.apply import apply_page
from book_core.furniture.cache import page_furniture
from book_core.layout.pipeline import build_layout
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.paragraphs.cache import detector_for, load_page
from book_core.paragraphs.page import build_page
from book_core.reading_order.builder import build_reading_order
from book_core.run_context import source_session
from book_core.settings import Settings
from book_core.structure.decide import decide_book
from book_core.structure.evidence import token_owners
from book_core.structure.features import page_evidence
from book_core.structure.models import BookStructure


def run(book, number):
    diagnosis = json.loads((OUT / f"{book}_{number}.json").read_text("utf8"))
    hidden = {
        r["span_id"]
        for r in diagnosis["pages"][0]["candidate_spans"]
        if r.get("render_test", {}).get("no_pixel_change") and not r["trimbox_excluded"]
    }
    keys = json.loads((OUT.parent / f"before/{book}.json").read_text("utf8"))["keys"]
    with source_session(reference_path(BOOKS[book][0])):
        loaded = load_book(book)
        source, extractor, inputs, furniture, furniture_key, paragraphs, artifact, _ = loaded
        evidence, _, _ = evidence_for(book, loaded)
        analysis = verified_read(
            CACHE / "analysis" / keys["analysis"] / f"{number}.json",
            ObjectAnalysis,
            keys["analysis"],
        )
        native = analysis.native
        page = native.page
        baseline_layout, baseline_order = inputs(page)
        baseline_furniture = page_furniture(page, inputs, furniture, furniture_key, CACHE8)
        baseline_paragraphs = load_page(paragraphs, number, CACHE9)
        structure_key = keys["lists"]["structure_decision_key"]
        structure = verified_read(
            CACHE10 / "structure/book" / f"{structure_key}.json",
            BookStructure,
            structure_key,
        )
        navigation = navigation_map(artifact).get(number)
        profile = {"pitch_by_size": paragraphs.book.profile["pitch_by_size"], "compounds": {}}
        detector, _ = detector_for(
            Settings(), paragraphs.book.profile["language_threshold"]["resolved_minimum_letters"]
        )
        rebuilt = build_page(
            page,
            baseline_layout,
            baseline_furniture,
            profile,
            inputs.vocabulary,
            navigation,
            detector,
        )
        assert model_digest(rebuilt) == model_digest(baseline_paragraphs), (
            "Frozen profile must reproduce the baseline page exactly before counterfactual"
        )
        before = decide_book(evidence, structure.config)
        assert before["headings"] == structure.headings
        objects = []
        for obj in native.objects:
            if obj.id in hidden:
                assert obj.render_info
                obj = obj.model_copy(
                    update={
                        "render_info": [
                            r.model_copy(update={"render_type": 3}) for r in obj.render_info
                        ]
                    }
                )
            objects.append(obj)
        projected = analysis.model_copy(
            update={"native": native.model_copy(update={"objects": objects})}
        )
        assert projected.native.page == native.page
        layout = build_layout(projected, extractor.render_page(source, number, dpi=144))
        order = build_reading_order(layout, page.store, inputs.vocabulary)
        old_roles = {r.line_id: r for r in baseline_furniture.roles}
        span_roles = {
            sid: old_roles[line.id] for line in baseline_layout.lines for sid in line.span_ids
        }
        roles = []
        for line in layout.lines:
            prior = [span_roles[sid] for sid in line.span_ids]
            assert len({r.role for r in prior}) == 1, "Ambiguous frozen furniture role"
            roles.append(prior[0].model_copy(update={"line_id": line.id}))
        furnished = apply_page(
            page, layout, order, roles, baseline_furniture.marker, inputs.vocabulary
        )
        built = build_page(
            page, layout, furnished, profile, inputs.vocabulary, navigation, detector
        )
        old_evidence = next(p for p in evidence["pages"] if p["page"] == number)
        assert not old_evidence["navigation"], "Navigation needs full regeneration on this page"
        row = page_evidence(page, layout, built, furnished, token_owners(page, layout), [])
        variant = copy.deepcopy(evidence)
        variant["pages"] = [row if p["page"] == number else p for p in variant["pages"]]
        after = decide_book(variant, structure.config)

        def headings(result, units):
            texts = {u["unit"]: u["text"] for u in units}
            return [
                {"decision": h.model_dump(mode="json"), "unit_text": [texts[u] for u in h.unit_ids]}
                for h in result["headings"]
                if h.page == number
            ]

        write(
            OUT.parent / f"counterfactual_{book}_{number}.json",
            {
                "page": number,
                "source_sha256": inputs.digest,
                "confirmed_hidden_span_ids": sorted(hidden),
                "method": "In-memory render-mode projection into existing invisible streams; "
                "rebuild layout/order/furniture view/paragraphs/page evidence and decide all "
                "book headings; freeze other pages and book furniture/profile context",
                "baseline_page_paragraphs_exact": True,
                "baseline_book_headings_exact": True,
                "native_store_unchanged": True,
                "invisible_spans": sorted(
                    {sid for line in layout.lines if not line.visible for sid in line.span_ids}
                ),
                "before": headings(before, old_evidence["units"]),
                "after": headings(after, row["units"]),
                "before_unit_kinds": {u.id: u.kind for u in baseline_paragraphs.units},
                "after_unit_kinds": {u.id: u.kind for u in built.units},
                "after_page_evidence": row,
                "limitation": "Single-page intervention with frozen book context; implementation "
                "must separately measure changes to book profiles and other pages",
            },
        )
        print(
            "counterfactual headings",
            len(headings(before, old_evidence["units"])),
            len(headings(after, row["units"])),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    parser.add_argument("--page", type=int, required=True)
    args = parser.parse_args()
    run(args.book, args.page)
