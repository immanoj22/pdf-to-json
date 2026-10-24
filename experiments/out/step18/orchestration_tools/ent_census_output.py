"""Presentation-only census routing after all fixed original pages were viewed."""
import json
from collections import Counter
from evaluation_routes import BASE,EVIDENCE,write_new,finished
from prepare_visual_populations import texts
from step17_json_eval import walk
finished()
book='ent_textbook'
obs=[json.loads(s) for s in (BASE/'audit'/book/'source_census_observations.jsonl').read_text('utf8').splitlines()]
assert len(obs)==20 and len({x['page'] for x in obs})==20
data=json.loads((EVIDENCE/book/'book.json').read_text('utf8'))
nodes=[n for top in data['content'] for n,*_ in walk(top)]
rows=[]
for o in obs:
 p=o['page'];ns=[n for n in nodes if p in (n.get('pages') or [])]
 def content(n):return [{'path':path,'text':t['text']} for t,owner,ps,ctx,path in texts(n)]
 rows.append({'page':p,'source_observation':o,
  'typed_candidates':[{'id':n.get('id'),'type':n.get('type'),'level':n.get('level'),'role':n.get('role'),'text':content(n),'boxes':n.get('boxes')} for n in ns if n.get('type') in {'heading','footnote','definition','definition_list','glossary','page_number'}],
  'all_node_type_roles':dict(Counter(str((n.get('type'),n.get('role'))) for n in ns)),
  'furniture':[n for n in data.get('furniture') or [] if n.get('page')==p],
  'all_text_records':[{'owner':owner.get('id'),'type':owner.get('type'),'path':path,'text':t['text']} for n in ns for t,owner,ps,ctx,path in texts(n)],
  'review':[r for r in data.get('review',{}).get('items',[]) if r.get('page')==p]})
write_new(BASE/'audit'/book/'packets/census_output.json',rows)
print('20 fixed page output packets created after source observations; no judgments generated')
