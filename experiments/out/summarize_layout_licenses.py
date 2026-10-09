import json
from pathlib import Path
p=Path(__file__).resolve().parent / "layout_environment_final.json"
d=json.loads(p.read_text(encoding='utf-8'))
for item in d['packages']:
    license_value = item.get('license_expression') or item.get('license_metadata') or ','.join(item.get('license_classifiers',[]))
    print(f"{item['name']} {item['version']} | {license_value.splitlines()[0] if license_value else 'UNKNOWN'}")
