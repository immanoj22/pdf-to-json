"""Append explicitly supplied human-agent decisions for already viewed fixed targets."""
import datetime,json,sys
from evaluation_routes import BASE,ROOT,write_new
from fixed_sampling import append_judgment

def main(book,decision_file):
    decisions=json.loads((ROOT/decision_file).read_text('utf8'))
    for family, verdicts in decisions.items():
        packets=[]
        for p in (BASE/'audit'/book/'packets').glob('*_targets.json'):
            data=json.loads(p.read_text('utf8'))
            if data['family']==family:packets=data['targets'];break
        assert packets and set(map(int,verdicts))<=set(range(len(packets)))
        for i,d in verdicts.items():
            r=packets[int(i)]
            append_judgment({'judgment_id':book+':'+family+':'+r['target_id'],
                'book_id':book,'family':family,'target_id':r['target_id'],
                'crop_paths':r['crop_paths'],'context_paths':r['context_paths']+d.get('extra_context_paths',[]),
                'selected_evidence':r['selected_evidence'],
                'agent_verdict':d['verdict'],'notes':d['notes'],
                'viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print(book,'explicit supplied decisions appended')

if __name__=='__main__':main(*sys.argv[1:])
