"""Isolated Phase 0 CPU layout-model experiment; not converter implementation."""
from __future__ import annotations
import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import statistics
import time
import traceback

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.cache'
for key, value in {
    'HF_HOME': CACHE / 'huggingface',
    'HUGGINGFACE_HUB_CACHE': CACHE / 'huggingface' / 'hub',
    'TORCH_HOME': CACHE / 'torch',
    'XDG_CACHE_HOME': CACHE,
    'HF_HUB_DISABLE_SYMLINKS_WARNING': '1',
}.items():
    os.environ[key] = str(value)

MODELS = {
    'heron': 'docling-project/docling-layout-heron',
    'pp_doclayoutv3': 'PaddlePaddle/PP-DocLayoutV3_safetensors',
}

def file_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob('*') if item.is_file()) if path.exists() else 0

def inventory() -> dict:
    packages = []
    for dist in metadata.distributions():
        data = dist.metadata
        license_value = data.get('License-Expression') or data.get('License') or ''
        packages.append({
            'name': data.get('Name'), 'version': dist.version,
            'license_expression': data.get('License-Expression', ''),
            'license_metadata': license_value,
            'license_classifiers': [x for x in data.get_all('Classifier', []) if x.startswith('License ::')],
        })
    import torch
    return {
        'python': platform.python_version(), 'python_executable': os.sys.executable,
        'packages': sorted(packages, key=lambda x: x['name'].lower()),
        'torch_cuda_available': torch.cuda.is_available(),
        'torch_cuda_build': torch.version.cuda,
        'device_used': 'cpu', 'torch_threads': torch.get_num_threads(),
        'venv_logical_file_bytes': file_bytes(ROOT / '.venv-layout'),
        'cache_logical_file_bytes': file_bytes(CACHE),
    }

def save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def draw_overlay(source: Path, detections: list[dict], model_key: str) -> str:
    from PIL import Image, ImageDraw
    canvas = Image.open(source).convert('RGB')
    draw = ImageDraw.Draw(canvas)
    colors = ['#ff4b4b', '#0085ff', '#00943d', '#bf00c9', '#ff8800', '#00a2b8']
    for item in detections:
        box = tuple(item['bbox_pixels'])
        color = colors[item['index'] % len(colors)]
        draw.rectangle(box, outline=color, width=3)
        label = f"{item['index']+1} {item['label']} {item['score']:.2f}"
        xy = (max(0, box[0]), max(0, box[1]-13))
        text_box = draw.textbbox(xy, label)
        draw.rectangle(text_box, fill='white')
        draw.text(xy, label, fill=color)
        if item.get('polygon_pixels'):
            polygon = [tuple(point) for point in item['polygon_pixels']]
            draw.line(polygon + [polygon[0]], fill=color, width=2)
    target = ROOT / 'out' / f"{source.stem.removesuffix('_page')}_{model_key}_overlay.png"
    canvas.save(target)
    return target.relative_to(ROOT.parent).as_posix()

def run_model(model_key: str, sources: list[Path], repeats: int, wait_for_extraction: bool = False) -> dict:
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForObjectDetection
    from huggingface_hub import try_to_load_from_cache
    repo = MODELS[model_key]
    result = {'model': model_key, 'repo_id': repo, 'device': 'cpu', 'reading_order_provided': model_key == 'pp_doclayoutv3', 'fixtures': []}
    start = time.perf_counter()
    revision = {'heron': '8f39ad3c0b4c58e9c2d2c84a38465abf757272d8', 'pp_doclayoutv3': 'e4f489dc536556fc1be02b973ba06756e0d4a2ac'}[model_key]
    processor = AutoImageProcessor.from_pretrained(repo, revision=revision)
    model = AutoModelForObjectDetection.from_pretrained(repo, revision=revision).to('cpu').eval()
    result['model_download_and_load_seconds'] = time.perf_counter()-start
    result['parameter_count'] = sum(p.numel() for p in model.parameters())
    cached_config = try_to_load_from_cache(repo, 'config.json')
    result['model_revision'] = getattr(model.config, '_commit_hash', None) or (Path(cached_config).parent.name if isinstance(cached_config, str) else None)
    result['labels'] = model.config.id2label
    print(f"Loaded {model_key}: {result['model_download_and_load_seconds']:.2f}s", flush=True)
    if not sources:
        return result
    if wait_for_extraction:
        marker = ROOT / 'out' / 'EXTRACTION_DONE'
        if not marker.exists():
            print('Waiting for extractor benchmark marker before warmup/timing', flush=True)
        while not marker.exists():
            time.sleep(1)
    with Image.open(sources[0]) as first:
        warm_inputs = processor(images=first.convert('RGB'), return_tensors='pt')
    start = time.perf_counter()
    with torch.inference_mode():
        _ = model(**warm_inputs)
    result['warmup_seconds'] = time.perf_counter()-start
    for source in sources:
        with Image.open(source) as raw:
            image = raw.convert('RGB')
        elapsed, infer_elapsed = [], []
        detections = []
        for _ in range(repeats):
            start = time.perf_counter()
            inputs = processor(images=image, return_tensors='pt')
            inference_start = time.perf_counter()
            with torch.inference_mode():
                outputs = model(**inputs)
            infer_elapsed.append(time.perf_counter()-inference_start)
            processed = processor.post_process_object_detection(outputs, target_sizes=[image.size[::-1]], threshold=0.5)[0]
            elapsed.append(time.perf_counter()-start)
        polygons = processed.get('polygon_points')
        for idx, (score, label, box) in enumerate(zip(processed['scores'], processed['labels'], processed['boxes'])):
            label_id = int(label.item())
            detection = {
                'index': idx, 'label_id': label_id,
                'label': model.config.id2label.get(label_id, model.config.id2label.get(str(label_id), str(label_id))),
                'score': round(float(score.item()), 6),
                'bbox_pixels': [round(float(x), 3) for x in box.tolist()],
                'reading_order': idx+1 if model_key == 'pp_doclayoutv3' else None,
            }
            if polygons is not None:
                detection['polygon_pixels'] = polygons[idx].tolist()
            detections.append(detection)
        fixture = {
            'fixture_id': source.stem.removesuffix('_page'),
            'render_path': source.relative_to(ROOT.parent).as_posix(),
            'image_width': image.width, 'image_height': image.height,
            'runtime_seconds_median': statistics.median(elapsed),
            'inference_seconds_median': statistics.median(infer_elapsed),
            'runtime_seconds_samples': elapsed,
            'threshold': 0.5, 'detections': detections,
            'overlay_path': draw_overlay(source, detections, model_key),
        }
        result['fixtures'].append(fixture)
        print(f"{model_key} {fixture['fixture_id']}: {len(detections)} regions, {fixture['runtime_seconds_median']:.3f}s", flush=True)
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', choices=list(MODELS), default=list(MODELS))
    parser.add_argument('--images', default='*_page.png')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--wait-for-extraction', action='store_true', help='Gate warmup/timing on out/EXTRACTION_DONE when benchmarks run concurrently.')
    args = parser.parse_args()
    import torch
    torch.set_num_threads(args.threads)
    sources = sorted((ROOT / 'out').glob(args.images))
    results = {
        'experiment': 'phase0_layout_cpu',
        'timing_scope': 'processor + model inference + postprocess; image loading, model loading and overlay rendering excluded',
        'region_order_note': 'Heron emitted detection order is not reading order; PP V3 emitted order is model-provided reading order.',
        'model_environment_before': inventory(), 'models': [],
    }
    for model_key in args.models:
        try:
            item = run_model(model_key, sources, args.repeats, args.wait_for_extraction)
        except Exception as exc:
            item = {'model': model_key, 'repo_id': MODELS[model_key], 'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc()}
            print(item['traceback'], flush=True)
        results['models'].append(item)
        save_json(ROOT / 'out' / 'layout_model_results.json', results)
    results['model_environment_after'] = inventory()
    save_json(ROOT / 'out' / 'layout_model_results.json', results)
    save_json(ROOT / 'out' / 'layout_environment_final.json', results['model_environment_after'])

if __name__ == '__main__':
    main()

