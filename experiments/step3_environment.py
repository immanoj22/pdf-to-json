"""Installed wheel/license evidence, with a CPU import check."""
import importlib
import importlib.metadata as metadata
import json
import platform
from pathlib import Path

from book_core.device import resolve_device

root=Path(__file__).resolve().parents[1]
names=[("shapely","shapely"),("networkx","networkx"),("numpy","numpy"),
       ("opencv-python-headless","cv2")]
rows=[]
for name,module in names:
    distribution=metadata.distribution(name)
    imported=importlib.import_module(module)
    files=[str(file) for file in distribution.files or []
           if "license" in str(file).lower() or "copying" in str(file).lower()]
    rows.append({"package":name,"version":distribution.version,
                 "import_version":imported.__version__,
                 "license_expression":distribution.metadata.get("License-Expression"),
                 "license":distribution.metadata.get("License"),
                 "classifiers":[s for s in distribution.metadata.get_all("Classifier",[]) if "License" in s],
                 "license_files":files})
out=root/"experiments/out/step3"
out.mkdir(parents=True,exist_ok=True)
result={"python":platform.python_version(),"platform":platform.platform(),
        "resolved_device":resolve_device().model_dump(),"packages":rows,
        "imagehash":"Not needed: use native exact image digests; no perceptual matching claim"}
(out/"dependencies.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
