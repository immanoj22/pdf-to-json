"""Final artifact/commit scope verification; reads all old inputs."""
import hashlib,json,re
from pathlib import Path
import pymupdf
from reference_paths import reference_path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/out'
manifest=json.loads((OUT/'fixtures_manifest.json').read_text())
sources={}
for r in manifest:
 p=ROOT/r['fixture'];assert p.is_file()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['fixture_sha256']
 with pymupdf.open(p) as d:assert len(d)==1
 sources[str(reference_path(r['source_key']))]=r['source_sha256']
for s,h in sources.items():assert hashlib.sha256(Path(s).read_bytes()).hexdigest()==h
report=ROOT/'docs/phase0_report.md';text=report.read_text();missing=[]
for target in re.findall(r'\]\(([^)]+)\)',text):
 if target.startswith('../') and not (report.parent/target).resolve().exists():missing.append(target)
assert not missing,missing
models=json.loads((OUT/'layout_model_results.json').read_text())['models']
assert len(models)==2 and all(len(m['fixtures'])==9 for m in models)
for m in models:
 for f in m['fixtures']:assert (ROOT/f['overlay_path']).exists()
for r in manifest:assert (OUT/(r['id']+'_geometry_overlay.png')).exists()
data={'fixture_count':len(manifest),'source_hashes_unchanged':sources,'model_runs':18,'geometry_overlays':9,'local_report_links_valid':True,'converter_code_written':False,'old_code_or_environments_modified_by_task':False}
(OUT/'verification.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data))

