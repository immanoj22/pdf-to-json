import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
out = root / 'out'
prior = json.loads((out / 'layout_model_results_heron.json').read_text(encoding='utf-8-sig'))
current = json.loads((out / 'layout_model_results.json').read_text(encoding='utf-8-sig'))
heron = [x for x in prior['models'] if x['model'] == 'heron']
pp = [x for x in current['models'] if x['model'] == 'pp_doclayoutv3']
current['models'] = heron + pp
current['model_environment_before'] = prior['model_environment_before']
current['measurement_notes'] = [
    'Interrupted initial Heron sample overlapping extraction was discarded; final Heron and PP samples are from fresh processes.',
    'PP first run required missing OpenCV backend; installed opencv-python-headless in isolated venv and reran PP only.',
    'Cache totals share experiments/.cache with other Phase 0 dependencies; venv size is layout-only.',
    'File-byte totals are sums of logical file lengths, not filesystem allocated clusters.',
]
(out / 'layout_model_results.json').write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding='utf-8')
environment = current['model_environment_after']
(root / 'requirements-layout.txt').write_text('\n'.join(f"{x['name']}=={x['version']}" for x in environment['packages'])+'\n', encoding='utf-8')
model_assets = []
for model in current['models']:
    cache_dir = root / '.cache' / 'huggingface' / 'hub' / ('models--' + model['repo_id'].replace('/', '--'))
    files = [{'path': str(p.relative_to(root.parent)).replace('\\', '/'), 'bytes': p.stat().st_size} for p in cache_dir.rglob('*.safetensors')]
    model_assets.append({'model': model['model'], 'safetensors_files': files})
(out / 'layout_model_assets.json').write_text(json.dumps(model_assets, indent=2), encoding='utf-8')
print(json.dumps({'venv_bytes':environment['venv_logical_file_bytes'], 'cache_bytes':environment['cache_logical_file_bytes'], 'cuda_available':environment['torch_cuda_available'], 'models':[{ 'model':m['model'], 'revision':m.get('model_revision'), 'parameter_count':m.get('parameter_count'), 'fixtures':len(m.get('fixtures',[]))} for m in current['models']], 'assets':model_assets}, indent=2))
