"""Presentation-only packets for the registered fixed samples; creates no verdicts."""
import json
from pathlib import Path
import sys
from collections import Counter
from evaluation_routes import BASE, ROOT, EVIDENCE, finished, write_new
from prepare_visual_populations import texts

def main(book):
    finished()
    data=json.loads((EVIDENCE/book/'book.json').read_text('utf8'))
    from step17_json_eval import walk
    nodes=[n for top in data['content'] for n,*_ in walk(top)]
    node_by_id={n['id']:n for n in nodes if n.get('id')}
    receipt=json.loads((BASE/'audit'/book/'render_receipt.json').read_text('utf8'))
    dest=BASE/'audit'/book/'packets'
    dest.mkdir(exist_ok=False)
    observations=BASE/'audit'/book/'source_census_observations.jsonl'
    if observations.exists():
        obs=[json.loads(s) for s in observations.read_text('utf8').splitlines()]
        assert len(obs)==20, 'Finish source-first observations before reading output typing'
        pages={r['page'] for r in obs}
        census=[]
        for o in obs:
            p=o['page']
            ns=[n for n in nodes if p in (n.get('pages') or [])]
            def content(n):
                return [{'path':path,'text':t['text']} for t,owner,ps,ctx,path in texts(n)]
            census.append({'page':p,'source_observation':o,
                'typed_candidates':[{'id':n.get('id'),'type':n.get('type'),'level':n.get('level'),
                    'role':n.get('role'),'text':content(n),'boxes':n.get('boxes')} for n in ns if n.get('type') in {'heading','footnote','definition','definition_list','glossary','page_number'}],
                'furniture':[n for n in data.get('furniture') or [] if n.get('page')==p],
                'all_text_records':[{'owner':owner.get('id'),'type':owner.get('type'),'path':path,'text':t['text']}
                    for n in ns for t,owner,ps,ctx,path in texts(n)],
                'review':[r for r in data.get('review',{}).get('items',[]) if r.get('page')==p]})
        write_new(dest/'census_output.json',census)
    from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    families=sorted({r['family'] for r in receipt['targets'] if r['family']!='page_census'})
    for fi,family in enumerate(families):
        rows=[r for r in receipt['targets'] if r['family']==family]
        enriched=[]
        for i,r in enumerate(rows):
            e=r['selected_evidence']
            unit=e.get('unit') or e.get('from_unit')
            n=node_by_id.get(unit,{})
            to=node_by_id.get(e.get('to_unit'),{})
            enriched.append({**r,'index':i,'owning_output':n,'to_output':to})
        write_new(dest/f'{fi:02d}_targets.json',{'family':family,'targets':enriched})
        for start in range(0,len(rows),4):
            panels=[]
            for i,r in enumerate(rows[start:start+4],start):
                e=r['selected_evidence']
                label=f"{i} {family} p{e.get('pages') or e.get('page')} {e.get('text','')[:90]}"
                crops=[]
                for path in r['crop_paths']:
                    im=Image.open(ROOT/path).convert('RGB')
                    # Preserve sufficient readable detail; full contexts/crops remain separately available.
                    im.thumbnail((1250,1050))
                    crops.append(im)
                h=80+sum(im.height+8 for im in crops)
                panel=Image.new('RGB',(1300,h),'white'); draw=ImageDraw.Draw(panel)
                draw.text((8,8),label,font=font,fill='black')
                draw.text((8,35),r['target_id'][:135],font=font,fill='black')
                y=75
                for im in crops: panel.paste(im,(8,y));y+=im.height+8
                panels.append(panel)
            sheet=Image.new('RGB',(2600,sum(max(p.height for p in panels[j:j+2]) for j in range(0,len(panels),2))),'#cccccc')
            y=0
            for j in range(0,len(panels),2):
                for k,panel in enumerate(panels[j:j+2]): sheet.paste(panel,(k*1300,y))
                y+=max(p.height for p in panels[j:j+2])
            sheet.save(dest/f'{fi:02d}_{start:03d}.png')
    write_new(dest/'index.json',{'families':families,'family_counts':Counter(r['family'] for r in receipt['targets']),
        'presentation_only':True,'judgments_generated':0})
    print(book,'presentation packets ready; no judgments generated',flush=True)

if __name__=='__main__':main(sys.argv[1])
