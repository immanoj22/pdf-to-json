import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
script = root / 'layout_models.py'
code = script.read_text(encoding='utf-8-sig')
code = code.replace('def run_model(model_key: str, sources: list[Path], repeats: int) -> dict:', 'def run_model(model_key: str, sources: list[Path], repeats: int, wait_for_extraction: bool = False) -> dict:')
code = code.replace('    from transformers import AutoImageProcessor, AutoModelForObjectDetection', '    from transformers import AutoImageProcessor, AutoModelForObjectDetection\n    from huggingface_hub import try_to_load_from_cache')
code = code.replace("    result['model_revision'] = getattr(model.config, '_commit_hash', None)", "    cached_config = try_to_load_from_cache(repo, 'config.json')\n    result['model_revision'] = getattr(model.config, '_commit_hash', None) or (Path(cached_config).parent.name if isinstance(cached_config, str) else None)")
old = "    marker = ROOT / 'out' / 'EXTRACTION_DONE'\n    if not marker.exists():\n        print('Waiting for extractor benchmark marker before warmup/timing', flush=True)\n    while not marker.exists():\n        time.sleep(1)"
new = "    if wait_for_extraction:\n        marker = ROOT / 'out' / 'EXTRACTION_DONE'\n        if not marker.exists():\n            print('Waiting for extractor benchmark marker before warmup/timing', flush=True)\n        while not marker.exists():\n            time.sleep(1)"
code = code.replace(old, new)
code = code.replace("    parser.add_argument('--threads', type=int, default=4)", "    parser.add_argument('--threads', type=int, default=4)\n    parser.add_argument('--wait-for-extraction', action='store_true', help='Gate warmup/timing on out/EXTRACTION_DONE when benchmarks run concurrently.')")
code = code.replace('item = run_model(model_key, sources, args.repeats)', 'item = run_model(model_key, sources, args.repeats, args.wait_for_extraction)')
script.write_text(code, encoding='utf-8')
results_path = root / 'out' / 'layout_model_results.json'
results = json.loads(results_path.read_text(encoding='utf-8'))
assets = json.loads((root / 'out' / 'layout_model_assets.json').read_text(encoding='utf-8'))
by_model = {item['model']:item for item in assets}
for model in results['models']:
    asset = by_model[model['model']]['safetensors_files'][0]
    model['model_revision'] = Path(asset['path']).parent.name
    model['weights_bytes'] = asset['bytes']
results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print('Recorded revisions/weights and made optional timing gate reproducible.')
