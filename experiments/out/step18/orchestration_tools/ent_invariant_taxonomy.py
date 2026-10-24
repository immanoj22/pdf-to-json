"""Fixed sample and source/layout evidence for all 42 registered I7 findings."""
import io,json,re
from evaluation_routes import BASE,CACHES,ROOT,route,sha,write_new
from fixed_sampling import select

def main():
    run,_,keys=route('ent_textbook')
    proof=json.loads((BASE/'evaluations/ent_textbook/inputs/after/ent_textbook_full_gates.json').read_text('utf8'))
    pop={}
    for p,inv in proof['invariants'].items():
        for kind,findings in inv.items():
            for i,f in enumerate(findings):pop[f'{p}:{kind}:{i}']={'page':int(p),'invariant':kind,'finding':f,'finding_index':i}
    assert len(pop)==42
    chosen=select('ent_textbook','taxonomy:M03',pop)
    from reference_paths import reference_path
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from PIL import Image,ImageDraw,ImageFont
    source=reference_path('ent_textbook_pdf');ext=PyMuPDFExtractor('cpu')
    dest=BASE/'audit/ent_textbook/invariant_taxonomy';dest.mkdir(exist_ok=False)
    rows=[]
    for i,t in enumerate(chosen['selected']):
        p=t['page'];r=ext.render_page(source,p,dpi=130)
        path=dest/f'page_{p:06d}.png';path.write_bytes(r.png)
        layout_path=CACHES['ent_textbook']/'layout'/keys['layout']/f'{p}.json'
        raw=json.loads(layout_path.read_text('utf8'))
        layout=raw.get('payload') or raw.get('data') or raw
        overlay=Image.open(io.BytesIO(r.png)).convert('RGB');draw=ImageDraw.Draw(overlay)
        # Layout data is retained verbatim; highlighted lane geometry only presents
        # the frozen finding. No recomputation or layout decision is made here.
        finding=t['finding'];m=re.search(r'edge lane (\d+)-(\d+)',finding)
        if m:
            sx=r.width/r.page_width
            draw.rectangle((float(m[1])*sx,0,float(m[2])*sx,r.height-1),outline='red',width=4)
        op=dest/f'overlay_{p:06d}.png';overlay.save(op)
        write_new(dest/f'layout_{p:06d}.json',layout)
        rows.append({**t,'index':i,'crop_paths':[op.relative_to(ROOT).as_posix()],
            'context_paths':[path.relative_to(ROOT).as_posix()],
            'layout_path':layout_path.relative_to(ROOT).as_posix(),'layout_sha256':sha(layout_path)})
    write_new(dest/'receipt.json',{'population_size':42,'selected_size':len(rows),'targets':rows,'source_sha256':sha(source),'no_judgments_generated':True})
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
    for start in range(0,len(rows),4):
        im=Image.new('RGB',(2500,3500),'#ddd');d=ImageDraw.Draw(im)
        for j,row in enumerate(rows[start:start+4]):
            image=Image.open(ROOT/row['crop_paths'][0]);image.thumbnail((1220,1660))
            x=(j%2)*1250;y=(j//2)*1750
            d.text((x+5,y+5),f"{row['index']} p{row['page']} {row['finding'][:75]}",font=font,fill='black')
            im.paste(image,(x+5,y+70))
        im.save(dest/f'sheet_{start:03d}.png')
    print('ENT I7 taxonomy source evidence prepared',flush=True)

if __name__=='__main__':main()
