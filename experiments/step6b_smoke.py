"""CPU-only optional-candidate smokes on synthetic assets; no PDF or gold reads.

Only checkpoints from the permissive primary-source audit can be downloaded.
Every selected weight is pinned by repository revision and SHA256. Model code
comes from installed packages, never a downloaded Python implementation.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import time
import traceback
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b"
CACHE = ROOT / ".cache/step6b/models/hf"
AUDIT = OUT / "dependency_audit.json"
CANDIDATES = {
    "formula": "PaddlePaddle/PP-FormulaNet-L_safetensors",
    "tatr": "microsoft/table-transformer-structure-recognition",
    "tableformer": "docling-project/docling-models",
    "ocr_det": "PaddlePaddle/PP-OCRv5_mobile_det_safetensors",
    "ocr_rec": "PaddlePaddle/latin_PP-OCRv5_mobile_rec_safetensors",
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "smolvlm": "HuggingFaceTB/SmolVLM-256M-Instruct",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure() -> None:
    for key, path in {
        "HF_HOME": CACHE,
        "HF_HUB_CACHE": CACHE / "hub",
        "TORCH_HOME": ROOT / ".cache/step6b/torch",
        "XDG_CACHE_HOME": ROOT / ".cache/step6b/xdg",
    }.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def model_files(key: str, *, download: bool) -> tuple[Path, dict]:
    """Fetch only declarative assets; use audited hashes for all model weights."""
    audit = json.loads(AUDIT.read_text("utf8"))
    row = next(row for row in audit["models"] if row["candidate"] == CANDIDATES[key])
    if row["license_status"] != "permissive_owner_model_card":
        raise ValueError("Checkpoint has no affirmative permissive license audit")
    repo, revision = row["candidate"], row["revision"]
    local = CACHE / repo.replace("/", "--") / revision
    local.mkdir(parents=True, exist_ok=True)
    weights = row["weights"]
    if key == "tableformer":
        weights = [w for w in weights if "/fast/" in w["file"]]
        assets = ["model_artifacts/tableformer/fast/tm_config.json"]
    else:
        # This metadata fetch cannot substitute a mutable main revision.
        url = f"https://huggingface.co/api/models/{repo}/revision/{revision}"
        metadata = json.load(urllib.request.urlopen(url, timeout=45))
        if metadata["sha"] != revision:
            raise ValueError("Repository revision mismatch")
        suffixes = (".json", ".txt", ".model", ".tiktoken", ".jinja")
        assets = [
            r["rfilename"]
            for r in metadata["siblings"]
            if "/" not in r["rfilename"] and r["rfilename"].endswith(suffixes)
        ]
    weight_map = {w["file"]: w for w in weights}
    manifest = []
    for name in sorted(set(assets) | set(weight_map)):
        target = local / name
        expected = weight_map.get(name, {}).get("sha256")
        if not target.exists():
            if not download:
                raise FileNotFoundError(f"Missing pinned asset: {name}; use --download")
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
            temporary = target.with_suffix(target.suffix + ".partial")
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    out.write(chunk)
            if expected and sha256(temporary) != expected:
                temporary.unlink()
                raise ValueError(f"Checkpoint checksum mismatch: {name}")
            temporary.replace(target)
        actual = sha256(target)
        if expected and actual != expected:
            raise ValueError(f"Checkpoint checksum mismatch: {name}")
        manifest.append({"file": name, "bytes": target.stat().st_size, "sha256": actual})
    return local, {
        "repo": repo,
        "revision": revision,
        "weight_license": row["weight_license"],
        "code_license": row["code_license"],
        "primary_url": row["weight_license_primary_url"],
        "local_path": local.relative_to(ROOT).as_posix(),
        "files": manifest,
    }


def fixtures() -> dict:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=28)
    table = Image.new("RGB", (640, 320), "white")
    draw = ImageDraw.Draw(table)
    for x in [20, 320, 620]:
        draw.line((x, 20, x, 300), fill="black", width=3)
    for y in [20, 110, 205, 300]:
        draw.line((20, y, 620, y), fill="black", width=3)
    for text, x, y in [
        ("Item", 45, 45),
        ("Value", 345, 45),
        ("A", 45, 140),
        ("1", 345, 140),
        ("B", 45, 235),
        ("2", 345, 235),
    ]:
        draw.text((x, y), text, font=font, fill="black")
    line = Image.new("RGB", (640, 64), "white")
    ImageDraw.Draw(line).text((8, 10), "Hello mundo 123", font=font, fill="black")
    shape = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(shape).rectangle((48, 48, 208, 208), fill="red")
    formula = Image.new("RGB", (360, 100), "white")
    formula_draw = ImageDraw.Draw(formula)
    formula_draw.text((20, 30), "E = mc", font=ImageFont.load_default(size=42), fill="black")
    formula_draw.text((153, 15), "2", font=ImageFont.load_default(size=24), fill="black")
    for name, im in {
        "table": table,
        "ocr_line": line,
        "red_square": shape,
        "formula": formula,
    }.items():
        im.save(OUT / f"synthetic_{name}.png")
    return {"table": table, "ocr_line": line, "red_square": shape, "formula": formula}


def inference(key: str, local: Path | None, images: dict, threads: int) -> dict:
    import torch

    torch.set_num_threads(threads)
    torch.manual_seed(0)
    if key == "torch_classifier":
        x = torch.tensor(
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [2.0, 0.0],
                [0.0, 2.0],
                [2.0, 2.0],
                [3.0, 3.0],
            ]
        )
        y = torch.tensor([[0.0], [0.0], [0.0], [1.0], [1.0], [1.0], [1.0], [1.0]])
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.SGD(model.parameters(), lr=0.2)
        for _ in range(400):
            optimizer.zero_grad()
            loss = torch.nn.functional.binary_cross_entropy_with_logits(model(x), y)
            loss.backward()
            optimizer.step()
        probability = torch.sigmoid(model(x)).detach().flatten()
        predicted = (probability >= 0.5).int().tolist()
        expected = y.flatten().int().tolist()
        assert torch.isfinite(probability).all() and predicted == expected
        return {
            "expected_labels": expected,
            "observed_labels": predicted,
            "probabilities": probability.tolist(),
            "loss": float(loss.detach()),
            "meaning": "Runtime fit smoke only; no production classifier or learned corpus rule",
        }
    if key == "tableformer":
        import numpy as np
        from docling_ibm_models.tableformer.data_management.tf_predictor import TFPredictor

        config_dir = local / "model_artifacts/tableformer/fast"
        config = json.loads((config_dir / "tm_config.json").read_text("utf8"))
        config["model"]["save_dir"] = str(config_dir)
        predictor = TFPredictor(config, device="cpu", num_threads=threads)
        page = {"image": np.asarray(images["table"]), "tokens": [], "width": 640, "height": 320}
        with torch.inference_mode():
            result = predictor.multi_table_predict(
                page, [[20.0, 20.0, 620.0, 300.0]], do_matching=False
            )
        details = result[0]["predict_details"]
        return {
            "expected": {"rows": 3, "columns": 2},
            "observed": {"rows": details.get("num_rows"), "columns": details.get("num_cols")},
            "cell_candidates": len(result[0]["tf_responses"]),
            "meaning": "Synthetic table topology smoke; no source text assigned or copied",
        }
    if key in {"tatr", "ocr_det", "ocr_rec"}:
        from transformers import (
            AutoConfig,
            AutoImageProcessor,
            AutoModelForObjectDetection,
            AutoModelForTextRecognition,
            TableTransformerForObjectDetection,
        )

        processor = AutoImageProcessor.from_pretrained(local, local_files_only=True)
        if key == "tatr":
            config = AutoConfig.from_pretrained(local, local_files_only=True)
            config.use_pretrained_backbone = False
            model, loading_info = TableTransformerForObjectDetection.from_pretrained(
                local,
                config=config,
                local_files_only=True,
                output_loading_info=True,
            )
            image = images["table"]
        elif key == "ocr_det":
            model = AutoModelForObjectDetection.from_pretrained(local, local_files_only=True)
            image = images["ocr_line"]
        else:
            model = AutoModelForTextRecognition.from_pretrained(local, local_files_only=True)
            image = images["ocr_line"]
        model = model.to("cpu").eval()
        inputs = processor(images=image, return_tensors="pt")
        with torch.inference_mode():
            outputs = model(**inputs)
        if key == "ocr_rec":
            result = processor.post_process_text_recognition(outputs)
            return {
                "expected_text": "Hello mundo 123",
                "observed": result,
                "observed_exact_match": result[0].get("text") == "Hello mundo 123",
                "meaning": "Synthetic crop only; normal digital text was never OCRed",
            }
        if key == "tatr":
            result = processor.post_process_object_detection(
                outputs,
                threshold=0.5,
                target_sizes=torch.tensor([image.size[::-1]]),
            )[0]
            labels = [model.config.id2label[int(i)] for i in result["labels"]]
            return {
                "expected": {"table_rows": 3, "table_columns": 2},
                "observed_labels": labels,
                "loading_info": loading_info,
                "scores": result["scores"].tolist(),
                "boxes": result["boxes"].tolist(),
                "meaning": "Topology candidates only; no semantic table decisions",
            }
        # Paddle detector postprocessing requires additional optional OpenCV/Shapely dependencies.
        result = processor.post_process_object_detection(
            outputs, target_sizes=torch.tensor([image.size[::-1]])
        )
        return {
            "expected": "one synthetic text line",
            "observed": jsonable(result),
            "meaning": "Synthetic detector smoke only",
        }
    if key == "minilm":
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(local, local_files_only=True)
        model = AutoModel.from_pretrained(local, local_files_only=True).to("cpu").eval()
        texts = [
            "The child reads a book.",
            "El niño lee un libro.",
            "The child turns the next page.",
            "Volcanic rocks cool beneath the ocean.",
        ]
        inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        with torch.inference_mode():
            hidden = model(**inputs).last_hidden_state
        mask = inputs["attention_mask"].unsqueeze(-1)
        pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        similarity = pooled @ pooled.T
        assert torch.isfinite(similarity).all()
        return {
            "synthetic_strings": texts,
            "embedding_shape": list(pooled.shape),
            "cosine_similarity": similarity.tolist(),
            "expected": "translation similarity exceeds unrelated-topic similarity",
            "observed_expected_relation": bool(similarity[0, 1] > similarity[0, 3]),
            "meaning": "Multilingual similarity evidence; not validated paragraph continuation",
        }
    if key == "formula":
        from transformers import AutoModelForImageTextToText, AutoProcessor

        processor = AutoProcessor.from_pretrained(local, local_files_only=True)
        model = (
            AutoModelForImageTextToText.from_pretrained(
                local,
                local_files_only=True,
                dtype=torch.float32,
            )
            .to("cpu")
            .eval()
        )
        inputs = processor(images=images["formula"], return_tensors="pt")
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=64, do_sample=False)
        observed = processor.post_process(generated, skip_special_tokens=True)
        return {
            "expected_latex": r"E = m c^{2}",
            "observed_latex": observed,
            "warnings": [
                "ftfy not installed; optional Unicode cleanup skipped",
                "max_new_tokens64 overrides checkpoint max_length1537",
            ],
            "tokens": generated.tolist(),
            "meaning": "Synthetic image formula smoke only; no book equations converted",
        }
    if key == "smolvlm":
        from transformers import AutoModelForImageTextToText, AutoProcessor

        processor = AutoProcessor.from_pretrained(local, local_files_only=True)
        model = (
            AutoModelForImageTextToText.from_pretrained(
                local,
                local_files_only=True,
                dtype=torch.float32,
                attn_implementation="eager",
            )
            .to("cpu")
            .eval()
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": "Describe the shape and its color."},
                ],
            }
        ]
        prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = processor(text=prompt, images=[images["red_square"]], return_tensors="pt")
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=16, do_sample=False)
        continuation = generated[:, inputs["input_ids"].shape[1] :]
        observed = processor.batch_decode(continuation, skip_special_tokens=True)[0]
        return {
            "expected": "a red square",
            "observed": observed,
            "new_tokens": int(continuation.shape[1]),
            "warnings": (
                ["pad_token_id outside declared text vocabulary; generation completed"]
                if model.config.pad_token_id is not None
                and not 0 <= model.config.pad_token_id < model.config.text_config.vocab_size
                else []
            ),
            "meaning": "Local visual-description smoke; generated text is untrusted model evidence",
        }
    raise ValueError(key)


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, set):
        return [jsonable(v) for v in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=[*CANDIDATES, "torch_classifier"], required=True)
    parser.add_argument(
        "--download", action="store_true", help="Download only audited pinned assets"
    )
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.threads < 1:
        raise ValueError("threads must be positive")
    configure()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = {
        "candidate": args.candidate,
        "time_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "device": "cpu",
        "threads": args.threads,
        "scope": "synthetic-only optional dependency smoke; no PDF/gold/hold-out access",
        "versions": {
            p: importlib.metadata.version(p)
            for p in ["torch", "torchvision", "transformers", "numpy", "Pillow"]
        },
    }
    try:
        local, checkpoint = (
            (None, None)
            if args.candidate == "torch_classifier"
            else model_files(
                args.candidate,
                download=args.download,
            )
        )
        result["checkpoint"] = checkpoint
        images = fixtures()
        inference_start = time.perf_counter()
        result["result"] = jsonable(inference(args.candidate, local, images, args.threads))
        result["model_stage_seconds"] = time.perf_counter() - inference_start
        result["timing_scope"] = (
            "Cold model stage includes imports, model load, preprocessing and CPU inference"
        )
        result["status"] = "completed"
    except Exception as error:
        result["status"] = "error"
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()
    result["wall_seconds"] = time.perf_counter() - started
    path = OUT / f"smoke_{args.candidate}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8", newline="\n")
    gc.collect()
    print(
        json.dumps(
            {
                "candidate": args.candidate,
                "status": result["status"],
                "wall_seconds": result["wall_seconds"],
                "out": path.relative_to(ROOT).as_posix(),
            }
        )
    )


if __name__ == "__main__":
    main()
