"""Run on the target Windows PC. Synthetic model diagnostics, never a sealed-book rerun.

Default requires real DirectML kernels, not just a package/provider listing. --cpu-onnx
checks export on a development machine and explicitly does not certify AMD hardware.
"""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from collections import Counter
from importlib import metadata
from pathlib import Path

from book_core.caching import code_digest
from book_core.device import resolve_device
from book_core.directml import TableTransformerSession
from book_core.tables.recognizers import TATRDetector, TATRStructure, _tatr_load


def sample(size):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for row in range(5):
        y = 30 + row * 32
        draw.line((20, y, size[0] - 20, y), fill="black", width=2)
        if row < 4:
            draw.text((30, y + 8), f"Row {row}       Value {row * 7}", fill="black")
    draw.rectangle((20, 30, size[0] - 20, 158), outline="black", width=2)
    return image


def measure(model_type, args):
    import numpy as np
    import torch

    processor, model = _tatr_load(
        model_type.repo_id,
        model_type.default_revision,
        args.model_cache,
        not args.download_models,
    )
    session, shapes, times = None, [], {"pytorch_cpu": [], "onnx": []}
    first_graph_seconds = None
    threshold = 0.5 if model_type is TATRDetector else model_type.threshold
    for size in [(320, 240), (400, 260)]:
        inputs = processor(images=sample(size), return_tensors="pt")
        if session is None:
            start = time.perf_counter()
            session = TableTransformerSession(
                model,
                inputs,
                providers=["CPUExecutionProvider"] if args.cpu_onnx else None,
                profile_prefix=args.out.parent / f"{model_type.name}_ort",
                threshold=threshold,
            )
            first_graph_seconds = time.perf_counter() - start
        output = session.run(model, inputs)  # Includes real-input numerical guard.
        with torch.inference_mode():
            expected = model(**inputs)

        # Also compare the decisions exposed to the converter, including threshold effects.
        def post(value, target_size=size[::-1]):
            return processor.post_process_object_detection(
                value, threshold=threshold, target_sizes=[target_size]
            )[0]

        a, b = post(expected), post(output)
        np.testing.assert_array_equal(a["labels"].numpy(), b["labels"].numpy())
        np.testing.assert_allclose(
            a["boxes"].numpy(), b["boxes"].numpy(), rtol=1e-4, atol=0.05
        )
        shapes.append(
            {
                "pixels": list(size),
                "tensor": list(inputs["pixel_values"].shape),
                "objects": len(a["labels"]),
                "parity": "passed",
            }
        )
        # Exclude export, shape guards and first-run setup from warm timings.
        for _ in range(args.repeats):
            start = time.perf_counter()
            with torch.inference_mode():
                model(**inputs)
            times["pytorch_cpu"].append(time.perf_counter() - start)
            start = time.perf_counter()
            session.run(model, inputs)
            times["onnx"].append(time.perf_counter() - start)
    profile_path = Path(session.session.end_profiling())
    profile = json.loads(profile_path.read_text("utf-8"))
    placement = Counter(
        row.get("args", {}).get("provider")
        for row in profile
        if row.get("cat") == "Node" and row.get("args", {}).get("provider")
    )
    if not args.cpu_onnx and placement["DmlExecutionProvider"] == 0:
        raise RuntimeError("No model kernels executed on DirectML")
    return {
        "repository": model_type.repo_id,
        "revision": model_type.default_revision,
        "shapes": shapes,
        "providers": session.session.get_providers(),
        "kernel_event_counts": dict(placement),
        "profile": str(profile_path),
        "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "export_and_session_seconds": first_graph_seconds,
        "warm_seconds": times,
        "warm_median_cpu_over_onnx": statistics.median(times["pytorch_cpu"])
        / statistics.median(times["onnx"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--download-models", action="store_true")
    parser.add_argument("--cpu-onnx", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.out.exists():
        parser.error("Use a new --out path to preserve earlier receipts")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "failed",
        "mode": "CPU export diagnostic" if args.cpu_onnx else "DirectML",
        "python": sys.version,
        "platform": platform.platform(),
        "producer": code_digest("table_models"),
        "models": {},
    }
    try:
        import torch

        result["dependencies"] = {
            name: metadata.version(name)
            for name in ["torch", "transformers", "onnx", "onnxruntime-directml"]
        }
        result["cpu_threads"] = torch.get_num_threads()
        if not args.cpu_onnx:
            resolution = resolve_device("directml", allow_directml=True)
            result["resolution"] = resolution.model_dump()
            if resolution.resolved != "directml":
                raise RuntimeError(resolution.fallback_reason)
        for model_type in [TATRDetector, TATRStructure]:
            print(f"Checking {model_type.name} ...", flush=True)
            result["models"][model_type.name] = measure(model_type, args)
        result["status"] = "passed"
    except Exception as error:  # noqa: BLE001 - persist a failed hardware-check receipt
        result["error"] = f"{type(error).__name__}: {error}"
    args.out.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    print(f"{result['status']}: {args.out}", flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
