"""Step 4b evidence experiment; never writes gold or modifies native ownership.

Gold type matching delegates unchanged to layout_gold.evaluate. Detectors do not predict
bands or columns: text-box x components and existing-lane coverage are diagnostics.
Native rendering and extraction use the Extractor contract.
"""

from __future__ import annotations

import argparse
import io
import json
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont
from reference_paths import reference_path

from book_core.caching import code_digest
from book_core.evaluation.layout_gold import area, box, evaluate, passes
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.frames import to_frame
from book_core.layout.invariants import INVARIANTS
from book_core.layout.invariants import check as invariant_check
from book_core.layout.pipeline import LAYOUT_VERSION, analyze_layout
from book_core.ledger.accounting import check as ledger_check
from book_core.ledger.tokenization import token_counter
from book_core.objects.analysis import cached_repetition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step4b"
CACHE = ROOT / ".cache/objects"
MODEL_CACHE = ROOT / ".cache/models"
WEIGHTS = ROOT / ".cache/huggingface"
PHASE0_SCALE = 1.0
UNSEEN = ROOT / "experiments/out/step4av/candidates.json"
FROZEN = ROOT / "backend/tests/fixtures/expected_counters.json"
TEXT_LANE_TYPES = {"main_text", "sidebar"}
COLOR = {"own": "#0072b2", "heron": "#d55e00", "pp_doclayoutv3": "#009e73"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def box_values(box):
    return [round(v, 3) for v in (box.x0, box.y0, box.x1, box.y1)]


def intersection(a, b):
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def line_text(line, analysis):
    return "".join(analysis.native.page.store.spans[sid].raw_text for sid in line.span_ids)


def configured_source(key):
    if key == "art_index_pdf":
        return reference_path("downloads") / "docbook xml index sample/docbook index input.pdf"
    if key == "canadian_index_pdf":
        return reference_path("downloads") / "9780802027962.pdf"
    return reference_path(key)


def retained_counter(page):
    """Read native source truth through the Extractor, without learned detections."""
    counter = Counter()
    for line in page.store.lines:
        if page.geometry.content_bbox.contains_center(line.bbox):
            counter.update(token_counter(page.store.raw_line_text(line)))
    return counter


def structural_signature(layout):
    signature = {
        field: [item.model_dump(mode="json") for item in getattr(layout, field)]
        for field in ("lines", "blocks", "scopes", "bands")
    }
    signature["regions"] = [
        {
            key: region.model_dump(mode="json")[key]
            for key in (
                "id",
                "type",
                "bbox",
                "scope_id",
                "band_id",
                "lane_index",
                "line_ids",
                "object_ids",
                "child_region_ids",
                "proposed_type",
            )
        }
        for region in layout.regions
    ]
    return signature


def band_summary(layout, detection=None):
    """Own bands plus diagnostic model support; no generated model bands or columns.

    A model box participates if at least half its area lies within the own band.
    X intervals join when their overlap reaches half the smaller width. A spanning
    box can yield one component over several own lanes. These counts are evidence,
    never column predictions. Rotated scopes use their existing orthonormal frame.
    """
    scopes = {scope.id: scope for scope in layout.scopes}
    result = []
    for band in layout.bands:
        scope = scopes[band.scope_id]
        frame_band = to_frame(band.bbox, scope.rotation)
        row = {
            "band_id": band.id,
            "scope_kind": scope.kind,
            "scope_rotation": scope.rotation,
            "bbox": box_values(band.bbox),
            "own_columns": band.column_count,
            "own_lanes": [lane.kind for lane in band.lanes],
            "own_lane_x": [[lane.x0, lane.x1] for lane in band.lanes],
        }
        if detection is not None:
            matched = [
                region
                for region in detection.regions
                if region.type in TEXT_LANE_TYPES
                and intersection(region.bbox, band.bbox) >= 0.5 * max(area(region.bbox), 1.0)
            ]
            intervals = []
            for region in matched:
                framed = to_frame(region.bbox, scope.rotation)
                intervals.append((max(framed.x0, frame_band.x0), min(framed.x1, frame_band.x1)))
            components = [[i] for i in range(len(intervals))]
            while True:
                merged = False
                for index, component in enumerate(components):
                    for other in components[index + 1 :]:
                        joins = any(
                            max(
                                0.0,
                                min(intervals[a][1], intervals[b][1])
                                - max(intervals[a][0], intervals[b][0]),
                            )
                            >= 0.5
                            * min(
                                intervals[a][1] - intervals[a][0], intervals[b][1] - intervals[b][0]
                            )
                            for a in component
                            for b in other
                        )
                        if joins:
                            component.extend(other)
                            components.remove(other)
                            merged = True
                            break
                    if merged:
                        break
                if not merged:
                    break
            supported = [
                sum(
                    max(0.0, min(x1, lane.x1) - max(x0, lane.x0))
                    >= 0.5 * min(x1 - x0, lane.x1 - lane.x0)
                    for x0, x1 in intervals
                )
                for lane in band.lanes
            ]
            row.update(
                {
                    "model_bands": None,
                    "model_columns": None,
                    "spatial_text_components": len(components),
                    "component_x": [
                        [min(intervals[i][0] for i in c), max(intervals[i][1] for i in c)]
                        for c in components
                    ],
                    "text_regions_per_own_lane": supported,
                    "text_region_ids": [region.id for region in matched],
                }
            )
        result.append(row)
    return result


def region_gold(layout, regions, gold):
    """Use the exact existing gold evaluator; model scopes and bands are undefined."""
    proxy = SimpleNamespace(scopes=layout.scopes, bands=[], regions=regions)
    result = evaluate(proxy, gold)
    return {
        key: result[key]
        for key in (
            "regions_certain",
            "regions_agree_certain",
            "regions_uncertain",
            "regions",
        )
    }


def line_model_evidence(layout, analysis, detections):
    """Diagnostic only; native text stays in its own region with existing span ids."""
    own = {lid: region for region in layout.regions for lid in region.line_ids}
    result = []
    for line in layout.lines:
        if line.blank or not line.inside_content:
            continue
        row = {
            "line_id": line.id,
            "span_ids": line.span_ids,
            "diagnostic_text": line_text(line, analysis),
            "bbox": box_values(line.bbox),
            "own_type": own[line.id].type,
            "own_region_id": own[line.id].id,
            "models": {},
        }
        for detection in detections:
            covered = [
                region
                for region in detection.regions
                if intersection(region.bbox, line.bbox) >= 0.5 * max(area(line.bbox), 1.0)
            ]
            row["models"][detection.detector] = [
                {
                    "region_id": r.id,
                    "label": r.raw_label,
                    "type": r.type,
                    "confidence": r.confidence,
                    "bbox": box_values(r.bbox),
                    "emission_index": r.emission_index,
                }
                for r in covered
            ]
        result.append(row)
    return result


def overlay(raster, layout, fusion, output):
    """Same-scale panels expose all regions and flag all fusion disagreements."""
    base = Image.open(io.BytesIO(raster.png)).convert("RGB")
    header = 68
    width, height = base.size
    panels = [("own", layout.regions)] + [(d.detector, d.regions) for d in fusion.detections]
    canvas = Image.new("RGB", (width * len(panels), height + header), "white")
    font = ImageFont.load_default(size=11)
    review_own = {rid for c in fusion.disagreements for rid in c.own_region_ids}
    review_model = {rid for c in fusion.disagreements for rid in c.model_region_ids}
    scale_x, scale_y = width / raster.page_width, height / raster.page_height
    for index, (name, regions) in enumerate(panels):
        panel = base.copy()
        draw = ImageDraw.Draw(panel)
        for number, region in enumerate(regions):
            bbox = region.bbox
            rect = (bbox.x0 * scale_x, bbox.y0 * scale_y, bbox.x1 * scale_x, bbox.y1 * scale_y)
            flagged = region.id in (review_own if name == "own" else review_model)
            color = COLOR.get(name, "#990099")
            draw.rectangle(rect, outline=color, width=3 if flagged else 1)
            label = f"{'!' if flagged else ''}{number} {region.type}"
            pos = (max(0, rect[0]), max(0, rect[1] - 12))
            draw.rectangle(draw.textbbox(pos, label, font=font), fill="white")
            draw.text(pos, label, fill=color, font=font)
        canvas.paste(panel, (width * index, header))
        top = ImageDraw.Draw(canvas)
        top.text(
            (width * index + 8, 8),
            f"{name} | {len(regions)} regions",
            fill=COLOR.get(name, "black"),
            font=font,
        )
        top.text(
            (width * index + 8, 24),
            "! / thick outline: disagreement; thin: agreement",
            fill="black",
            font=font,
        )
        top.text(
            (width * index + 8, 40),
            "All sources retained; numbers are diagnostic IDs, not order",
            fill="black",
            font=font,
        )
    canvas.save(output)


def phase0_diagnostics(name, layout, detections, line_evidence):
    result = {}
    if name == "science_dissolving":
        gold = json.loads(
            (ROOT / "backend/tests/gold/columns_science_dissolving.json").read_text("utf-8")
        )
        panels = [box(r["bbox"]) for r in gold["regions"] if r["type"] == "figure"]
        frame = box(
            [
                min(r.x0 for r in panels),
                min(r.y0 for r in panels),
                max(r.x1 for r in panels),
                max(r.y1 for r in panels),
            ]
        )
        result["composite_figure"] = {
            "target": "Extent of three unchanged gold molecular panels",
            "target_bbox": box_values(frame),
            "own_figure_region_ids": [
                r.id
                for r in layout.regions
                if r.type == "figure" and intersection(r.bbox, frame) > 0
            ],
            "model_parts": {
                d.detector: [
                    r.model_dump(mode="json")
                    for r in d.regions
                    if r.type == "figure" and intersection(r.bbox, frame) >= 0.5 * area(r.bbox)
                ]
                for d in detections
            },
            "fusion_kept_all_own_candidates": True,
            "note": "Baseline has three panel candidates; no composite parent is added.",
        }
    if name == "complex_map":
        gold = json.loads((ROOT / "backend/tests/gold/columns_complex_map.json").read_text("utf-8"))
        result["definition_evidence"] = {
            item["note"]: [
                row
                for row in line_evidence
                if intersection(box(row["bbox"]), box(item["bbox"]))
                >= 0.5 * max(area(box(row["bbox"])), 1.0)
            ]
            for item in gold["regions"]
            if "glossary" in item["note"].casefold()
        }
        result["note"] = (
            "Targets are unchanged Step 4a gold glossary boxes. "
            "Missing model boxes never omit native text."
        )
    if name == "complex_cards":
        result["card_order"] = {
            "status": "not_evaluated_at_step4b",
            "reason": "Reading order is ignored; emission indices are diagnostic only.",
            "phase0_reference": "experiments/out/layout_model_results.json",
            "emission_diagnostic": [
                row
                for row in line_evidence
                if "1954" in row["diagnostic_text"] or "1955" in row["diagnostic_text"]
            ],
        }
    return result


def run_page(name, source, candidate, detectors, args, frozen):
    from book_core.detection import DetectionInput
    from book_core.detection.cache import detect_cached
    from book_core.layout.fusion import fuse_regions

    started = time.perf_counter()
    extractor = PyMuPDFExtractor(device="cpu")
    layout, analysis = analyze_layout(
        source, 1, extractor, cached_repetition(source, extractor, CACHE), CACHE
    )
    expected = frozen.get(name)
    if candidate:
        original = extractor.extract_object_page(
            configured_source(candidate["source_key"]), candidate["physical_page"]
        )
        expected = retained_counter(original.page)
    document, ledger = provision_page(analysis.native.page)
    ledger_before = ledger.model_dump(mode="json")
    spans_before = analysis.native.page.store.model_dump(mode="json")
    before = structural_signature(layout)
    baseline_path = ROOT / f"experiments/out/step4afix/{name}_regions.json"
    baseline = json.loads(baseline_path.read_text("utf-8"))
    baseline_equal = all(baseline[field] == before[field] for field in ("bands", "scopes"))
    if not baseline_equal:
        raise AssertionError(f"{name}: bands or lanes changed from Step 4a-fix")
    text = ledger_check(document, ledger, expected)
    raster = extractor.render_page(source, 1, dpi=round(72 * PHASE0_SCALE))
    page_input = DetectionInput.from_raster(analysis.native.page.source_sha256, 1, raster)
    detections = [detect_cached(page_input, detector, MODEL_CACHE) for detector in detectors]
    repeated = {}
    if candidate is None and args.device == "cpu" and (args.repeat_gold or args.prior_repeats):
        from book_core.detection.comparison import compare

        for detector, expected_detection in zip(detectors, detections, strict=True):
            if args.repeat_gold:
                actual_detection = detector.detect(page_input)
                repeat_method = "uncached_inference"
            else:
                from book_core.detection import DetectionResult

                repeat_path = args.out / f"{name}_{detector.name}_repeat.json"
                actual_detection = DetectionResult.model_validate_json(
                    repeat_path.read_text("utf-8")
                )
                repeat_method = "verified_prior_uncached_inference"
            comparison = compare(expected_detection, actual_detection)
            repeated[detector.name] = comparison.model_dump(mode="json")
            repeated[detector.name]["passed"] = comparison.passed
            repeated[detector.name]["method"] = repeat_method
            write_json(
                args.out / f"{name}_{detector.name}_repeat.json",
                actual_detection.model_dump(mode="json"),
            )
            if not comparison.passed:
                raise AssertionError(
                    f"{name}: repeated CPU {detector.name} exceeds model tolerance"
                )
    fusion = fuse_regions(
        layout,
        detections,
        analysis=analysis,
        iou_threshold=args.fusion_iou,
        agreement_gain=args.agreement_gain,
    )
    if before != structural_signature(fusion.layout):
        raise AssertionError(f"{name}: fusion changed geometry, membership, types, bands or lanes")
    if ledger_before != ledger.model_dump(
        mode="json"
    ) or spans_before != analysis.native.page.store.model_dump(mode="json"):
        raise AssertionError(f"{name}: detection or fusion modified ledger or span store")
    violations = invariant_check(fusion.layout, analysis)
    if any(violations.values()) or not text.passing:
        raise AssertionError(f"{name}: exact text or invariant gate failed")
    stem = args.out / name
    own_path = stem.with_name(name + "_own.json")
    fused_path = stem.with_name(name + "_fused.json")
    lines_path = stem.with_name(name + "_line_evidence.json")
    write_json(own_path, layout.model_dump(mode="json"))
    write_json(fused_path, fusion.model_dump(mode="json"))
    png = stem.with_name(name + "_disagreements.png")
    overlay(raster, layout, fusion, png)
    lines = line_model_evidence(layout, analysis, detections)
    write_json(lines_path, lines)
    row = {
        "page": name,
        "source": relative(source),
        "covers": candidate["covers"] if candidate else "gold fixture",
        "overlay": relative(png),
        "own_json": relative(own_path),
        "fused_json": relative(fused_path),
        "line_evidence": relative(lines_path),
        "text_gate": {**text.model_dump(mode="json"), "passing": text.passing},
        "invariants": {key: len(value) for key, value in violations.items()},
        "structural_equality": True,
        "baseline_bands_lanes_equality": baseline_equal,
        "ledger_equality": True,
        "repeat_cpu_tolerance": repeated,
        "own_bands": band_summary(layout),
        "fused_bands": band_summary(fusion.layout),
        "model_band_diagnostics": {d.detector: band_summary(layout, d) for d in detections},
        "models": {
            d.detector: {
                "regions": len(d.regions),
                "types": dict(Counter(r.type for r in d.regions)),
                "provenance": d.provenance.model_dump(mode="json"),
            }
            for d in detections
        },
        "disagreements": {
            d.detector: {
                "total": sum(c.detector == d.detector for c in fusion.disagreements),
                "by_status": dict(
                    Counter(c.status for c in fusion.disagreements if c.detector == d.detector)
                ),
                "agreements": sum(
                    c.detector == d.detector and c.status == "agreement" for c in fusion.comparisons
                ),
            }
            for d in detections
        },
        "phase0_diagnostics": phase0_diagnostics(name, layout, detections, lines),
        "seconds": time.perf_counter() - started,
    }
    gold_path = ROOT / f"backend/tests/gold/columns_{name}.json"
    if gold_path.exists():
        gold = json.loads(gold_path.read_text("utf-8"))
        own_result, fused_result = evaluate(layout, gold), evaluate(fusion.layout, gold)
        if not passes(own_result) or not passes(fused_result):
            raise AssertionError(f"{name}: certain gold band or column gate failed")
        row["gold"] = {
            "human_approved": gold["human_approved"],
            "own": own_result,
            "fused": fused_result,
            "models": {d.detector: region_gold(layout, d.regions, gold) for d in detections},
            "own_band_gate": True,
            "fused_band_gate": True,
        }
    write_json(stem.with_name(name + "_metrics.json"), row)
    print(
        name,
        "ledger",
        text.expected_missing_token_count,
        text.expected_extra_token_count,
        "disagreements",
        {k: v["total"] for k, v in row["disagreements"].items()},
        flush=True,
    )
    return row


def main():
    from book_core.detection import HeronDetector, PPDocLayoutV3Detector
    from book_core.detection.comparison import DetectionTolerance

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--fusion-iou", type=float, default=0.5)
    parser.add_argument("--agreement-gain", type=float, default=0.1)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["heron", "pp_doclayoutv3"],
        default=["heron", "pp_doclayoutv3"],
    )
    parser.add_argument("--pages", nargs="*", help="Explicit fixture names for diagnostic reruns")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--repeat-gold",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run uncached second CPU inference on each gold fixture",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.prior_repeats = False
    prior_manifest = args.out / "manifest.json"
    if not args.repeat_gold and prior_manifest.exists():
        prior = json.loads(prior_manifest.read_text("utf-8"))
        args.prior_repeats = (
            prior.get("producer_sha256") == code_digest("detection")
            and prior.get("layout_producer_sha256") == code_digest("layout")
            and prior.get("layout_version") == LAYOUT_VERSION
            and prior.get("threshold") == args.threshold
            and prior.get("device_policy") == args.device
        )
    constructors = {"heron": HeronDetector, "pp_doclayoutv3": PPDocLayoutV3Detector}
    detectors = [
        constructors[name](threshold=args.threshold, device=args.device, cache_dir=WEIGHTS)
        for name in args.models
    ]
    frozen_data = json.loads(FROZEN.read_text("utf-8"))
    frozen = {row["fixture"]: Counter(row["counter"]) for row in frozen_data["cases"]}
    pages = [
        (path.stem, path, None) for path in sorted((ROOT / "experiments/fixtures").glob("*.pdf"))
    ]
    pages.extend(
        (row["id"], ROOT / f"experiments/fixtures_unseen/{row['id']}.pdf", row)
        for row in json.loads(UNSEEN.read_text("utf-8"))
    )
    if args.pages:
        selected = set(args.pages)
        pages = [row for row in pages if row[0] in selected]
        if selected != {row[0] for row in pages}:
            parser.error("An explicit --pages fixture name does not exist")
    manifest = {
        "producer_sha256": code_digest("detection"),
        "layout_producer_sha256": code_digest("layout"),
        "layout_version": LAYOUT_VERSION,
        "fusion_iou": args.fusion_iou,
        "fusion_agreement_gain": args.agreement_gain,
        "repeat_cpu_tolerance": DetectionTolerance().model_dump(mode="json"),
        "model_identity": {
            d.name: {
                "repo_id": d.repo_id,
                "revision": d.revision,
                "dependencies": d.dependency_versions,
            }
            for d in detectors
        },
        "threshold": args.threshold,
        "device_policy": args.device,
        "model_scale": PHASE0_SCALE,
        "model_dpi": round(72 * PHASE0_SCALE),
        "model_band_metric": (
            "No model bands/columns predicted. Spatial text x-components "
            "and own lane support are diagnostic only."
        ),
        "gold_type_metric": (
            "Unchanged layout_gold.evaluate with own scopes and detector regions; "
            "uncertain gold excluded."
        ),
        "model_order": "Ignored; emission indices are diagnostic only.",
        "pages": [],
    }
    for name, source, candidate in pages:
        if not source.exists():
            raise FileNotFoundError(f"Missing fixture {source}; run recreate_unseen_fixtures.py")
        manifest["pages"].append(run_page(name, source, candidate, detectors, args, frozen))
        write_json(args.out / "manifest.json", manifest)
    manifest["gate"] = {
        "pages": len(manifest["pages"]),
        "missing": sum(p["text_gate"]["missing_token_count"] for p in manifest["pages"]),
        "extra": sum(p["text_gate"]["extra_token_count"] for p in manifest["pages"]),
        "invariants": {
            key: sum(p["invariants"][key] for p in manifest["pages"]) for key in INVARIANTS
        },
        "expected_counter_pages": sum(
            p["text_gate"]["expected_missing_token_count"] is not None for p in manifest["pages"]
        ),
        "expected_missing": sum(
            p["text_gate"]["expected_missing_token_count"] or 0 for p in manifest["pages"]
        ),
        "expected_extra": sum(
            p["text_gate"]["expected_extra_token_count"] or 0 for p in manifest["pages"]
        ),
        "fusion_structural_changes": 0,
        "gold_fixture_passes": sum("gold" in p for p in manifest["pages"]),
    }
    write_json(args.out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
