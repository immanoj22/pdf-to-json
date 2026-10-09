"""Probe object API shapes/counts without dumping page data or modifying PDFs."""
import json
from pathlib import Path
import pymupdf
root=Path(__file__).resolve().parents[1]
for name in ["science_dissolving","background_worksheet","colored_box","complex_map"]:
    with pymupdf.open(root/"experiments/fixtures"/f"{name}.pdf") as d:
        p=d[0]
        imgs=p.get_image_info(hashes=True,xrefs=True)
        logs=p.get_bboxlog(layers=True)
        drawings=p.get_drawings(extended=True)
        trace=p.get_texttrace()
        out={"fixture":name,"images":len(imgs),"image_sample":{k:(v.hex() if isinstance(v,bytes) else v) for k,v in imgs[0].items()} if imgs else {},
             "log_sample":logs[:3],"drawing_types":{},
             "drawing_sample":[{k:(list(v) if isinstance(v,pymupdf.Rect) else v) for k,v in x.items() if k not in {"items"}} for x in drawings[:4]],
             "trace_sample":[{k:v for k,v in t.items() if k not in {"chars"}} for t in trace[:2]],
             "trace_glyph":trace[0]["chars"][0] if trace else None}
        for x in drawings:out["drawing_types"][x["type"]]=out["drawing_types"].get(x["type"],0)+1
        print(json.dumps(out,default=str))
