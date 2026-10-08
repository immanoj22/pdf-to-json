"""Provisional review gold, annotated after visual inspection. Never read found roles."""
import json
from pathlib import Path
from book_core.objects.models import ObjectAnalysis

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"experiments/out/step3"
GOLD=ROOT/"backend/tests/gold"
GOLD.mkdir(parents=True,exist_ok=True)

def area(obj):
    b=obj.bbox
    return (b.x1-b.x0)*(b.y1-b.y0) if b else 0

def item(obj,expected,note,protect=False,uncertain=False):
    return {"object_id":obj.id,"kind":obj.kind,
            "bbox":obj.bbox.model_dump() if obj.bbox else None,
            "expected_role":None if uncertain else expected,
            "review_required":uncertain,"note":note,
            "protect_backdrop":protect}

def nearest(objects,target):
    def distance(obj):
        b=obj.bbox
        return sum(abs(a-c) for a,c in zip((b.x0,b.y0,b.x1,b.y1),target,strict=True)) if b else float("inf")
    return min(objects,key=distance)

for name in sorted(path.stem for path in (ROOT/"experiments/fixtures").glob("*.pdf")):
    analysis=ObjectAnalysis.model_validate_json((OUT/f"{name}_overlay.json").read_text("utf-8"))
    native=analysis.native.objects
    drawings=[obj for obj in native if obj.kind=="drawing" and obj.bbox]
    images=[obj for obj in native if obj.kind=="image"]
    shadings=[obj for obj in native if obj.kind=="shading"]
    selected=[]
    if name=="background_worksheet":
        selected.append(item(max(shadings,key=area),"background","Yellow page-size gradient backdrop",True))
        rectangle=nearest([obj for obj in drawings if obj.fill],(36,18,666,837))
        selected.append(item(rectangle,"background","Solid underpaint beneath the page gradient",True))
        photo=max(images,key=lambda obj:obj.paint_sequences[0])
        selected.append(item(photo,"content_image","Visible astronaut photo"))
        earliest=min(images,key=lambda obj:obj.paint_sequences[0])
        selected.append(item(earliest,None,"Larger nested placement extends above photo; hidden/overpainted asset needs human review",uncertain=True))
    elif name=="colored_box":
        selected.extend(item(obj,"container","Gradient reading-strategy callout behind text",True) for obj in shadings)
        selected.append(item(images[0],"content_image","Archaeological photo"))
        banner=nearest([obj for obj in drawings if obj.fill],(36,18,666,79))
        selected.append(item(banner,"background","Cyan banner underpaint; local backdrop is currently conservative",True))
        grid=max(analysis.compounds,key=lambda obj:area(obj) if obj.bbox.y0>200 else 0)
        selected.append(item(grid,None,"Geometric line grid; do not infer table semantics here",uncertain=True))
    elif name=="column_26":
        ellipse=nearest([obj for obj in drawings if obj.fill],(236,413,410,586))
        selected.append(item(ellipse,"container","Light-blue quote backdrop"))
        selected.append(item(images[0],"decorative","Narrow image strip outside the printed TrimBox"))
        banner=nearest([obj for obj in drawings if obj.fill],(18,18,666,79))
        selected.append(item(banner,"background","Cyan banner backdrop"))
    elif name=="column_100":
        panel=nearest([obj for obj in drawings if obj.fill],(72,73,313,130))
        selected.append(item(panel,"container","Light-blue explanatory box above chart"))
        bars=[obj for obj in drawings if obj.fill and obj.bbox.y0>140 and obj.bbox.y1<242
              and 120<obj.bbox.x0<280 and (obj.bbox.x1-obj.bbox.x0)<20
              and (obj.bbox.y1-obj.bbox.y0)>15]
        selected.extend(item(obj,"figure_part","Native filled bar in the visibly rendered chart") for obj in bars[:3])
        selected.append(item(max(analysis.compounds,key=area),None,
                             "Chart-line compound; figure grouping deferred",uncertain=True))
    elif name=="complex_cards":
        selected.extend(item(obj,"content_image","Visible portrait") for obj in images)
        panel=nearest([obj for obj in drawings if obj.fill],(111,547,612,604))
        selected.append(item(panel,"container","Light-blue explanatory backdrop above portrait cards"))
        selected.append(item(max(analysis.compounds,key=area),None,"Card/frame compound, role ambiguous",uncertain=True))
    elif name=="complex_map":
        selected.append(item(images[0],"content_image","Raster terrain/map base, with labels retained separately"))
        legend=nearest([obj for obj in drawings if obj.fill],(429,334,563,407))
        selected.append(item(legend,"container","White legend box with visible labels"))
        complex_path=max(drawings,key=lambda obj:len(obj.path_items))
        selected.append(item(complex_path,None,"Dense clipped vector artwork; fine-grained role ambiguous",uncertain=True))
    elif name=="complex_sidebar":
        selected.append(item(shadings[0],"background","Yellow full-page gradient backdrop",True))
        selected.append(item(images[0],"content_image","Football player photo"))
        box=nearest([obj for obj in drawings if obj.fill],(72,73,590,602))
        selected.append(item(box,"container","White activity-panel backdrop"))
    else:
        lookup={obj.id:obj for obj in native}
        candidates=[obj for obj in analysis.compounds if
                    all(lookup[member].kind=="shading" for member in obj.member_ids)]
        selected.extend(item(obj,"figure_part","Visually inspected molecular/nuclear cluster; primitive compound only")
                        for obj in sorted(candidates,key=lambda obj:len(obj.member_ids),reverse=True)[:3])
        panel=max([obj for obj in drawings if obj.fill],key=area)
        selected.append(item(panel,None,"Large colored panel may be callout, visual panel or page decoration; review",uncertain=True))
    # Deduplicate an object selected through two independent visual cues.
    selected=list({obj["object_id"]:obj for obj in selected}.values())
    value={"fixture":name,"source_sha256":analysis.native.page.source_sha256,
           "annotation_method":"Provisional manual visual inspection by assistant; awaiting user review",
           "human_approved":False,"overlay":f"experiments/out/step3/{name}_overlay.png",
           "scope":"Main-object review sample; not exhaustive or independent production accuracy",
           "objects":selected}
    (GOLD/f"roles_{name}.json").write_text(json.dumps(value,indent=2),encoding="utf-8")
    print(name,len(selected))

