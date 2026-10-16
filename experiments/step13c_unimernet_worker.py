"""UniMERNet worker for the Step 13c comparison; runs ONLY in the side CPython 3.12 environment.

Called as a subprocess by ``step13c_unimernet.py`` (main environment): reads a JSON list of
PNG paths, writes one JSON line per image ({"path", "latex", "seconds"}). The model is built
from the installed ``unimernet`` 0.2.3 package (unpatched) with the pinned tiny weights; the
checkpoint is read with ``torch.load(weights_only=True)`` (tensors only, no pickled code).

Usage (side environment):
  .cache/side_envs/unimernet/Scripts/python.exe step13c_unimernet_worker.py \
      --weights <snapshot dir> --images list.json --out readings.jsonl
"""

import argparse
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    import torch
    from omegaconf import OmegaConf
    from PIL import Image
    from unimernet.models.unimernet.unimernet import UniMERModel
    from unimernet.processors.formula_processor import FormulaImageEvalProcessor

    torch.set_num_threads(args.threads)
    weights = Path(args.weights)
    config = OmegaConf.create(
        {
            "model_name": "unimernet",
            "model_config": {"model_name": str(weights), "max_seq_len": 1536},
            "tokenizer_name": "nougat",
            "tokenizer_config": {"path": str(weights)},
        }
    )
    model = UniMERModel(
        model_name=config.model_name,
        model_config=config.model_config,
        tokenizer_name=config.tokenizer_name,
        tokenizer_config=config.tokenizer_config,
    )
    checkpoint = torch.load(weights / "unimernet_tiny.pth", map_location="cpu", weights_only=True)
    state = checkpoint.get("model", checkpoint)
    missing, unexpected = model.load_state_dict(state, strict=False)
    model.eval()
    processor = FormulaImageEvalProcessor(image_size=[192, 672])
    done = set()
    out = Path(args.out)
    if out.exists():
        done = {json.loads(row)["path"] for row in out.read_text("utf-8").splitlines() if row}
    paths = [p for p in json.loads(Path(args.images).read_text("utf-8")) if p not in done]
    with out.open("a", encoding="utf-8") as stream:
        if not done:
            header = {
                "path": None,
                "missing_keys": sorted(missing),
                "unexpected_keys": sorted(unexpected),
                "torch": torch.__version__,
            }
            stream.write(json.dumps(header) + "\n")
        for path in paths:
            started = time.perf_counter()
            image = Image.open(path).convert("RGB")
            pixels = processor(image).unsqueeze(0)
            with torch.inference_mode():
                result = model.generate({"image": pixels})
            stream.write(
                json.dumps(
                    {
                        "path": path,
                        "latex": result["pred_str"][0],
                        "seconds": round(time.perf_counter() - started, 3),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            stream.flush()


if __name__ == "__main__":
    main()
