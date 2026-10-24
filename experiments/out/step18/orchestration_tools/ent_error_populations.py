"""Present frozen scorer inputs/results for the registered error taxonomies.

No scorer replacement: capture the existing evaluator's returned detail and
enumerate its discordant pairs using the same published input view.
"""
import json
from collections import Counter,defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import median
from evaluation_routes import BASE,CACHES,EVIDENCE,ROOT,route,write_new
from fixed_sampling import select

def main():
    run,_,keys=route('ent_textbook')
    import step14a_common as common
    import step17_json_eval as frozen
    import book_core.evaluation.derived_harness as harness
    from ent_scope_bridge import require_scope_review
    mapping=json.loads((EVIDENCE/'ent_textbook/alignment_evidence/scope_mapping.json').read_text('utf8'))
    require_scope_review(mapping);scope=set(mapping['accuracy_pages'])
    data=json.loads((Path(run['book_json'])/'book.json').read_text('utf8'))
    lines,spans,units=frozen.json_view(data)
    owner,views=frozen.owners_of('ent_textbook',lines,spans,run['pages'])
    owner={k:v for k,v in owner.items() if k[0] in scope}
    views={p:v for p,v in views.items() if p in scope}
    original=harness.evaluate;captured={}
    def capture(golds,outputs,**kwargs):
        result=original(golds,outputs,**kwargs)
        captured.update(detail=result,output=outputs['ent_textbook'])
        return result
    harness.evaluate=capture
    score=frozen.reading_order('ent_textbook',owner,data,views)
    prior=json.loads((BASE/'evaluations/ent_textbook/published_reference_metrics.json').read_text('utf8'))
    assert score==prior['reading_order']
    gold=common.derived_gold('ent_textbook')
    dest=BASE/'audit/ent_textbook/error_taxonomies';dest.mkdir(exist_ok=False)
    write_new(dest/'reading_order_detail.json',captured['detail'])
    output=captured['output'];by_page=defaultdict(list)
    for unit in gold.units:
        for page,first,length in unit['pdf']:
            if page in scope:by_page[page].append((unit['unit'],range(first,first+length)))
    population={}
    for p,view in output.pages.items():
        merged=defaultdict(list)
        for uid,ts in by_page[p]:merged[uid].extend(ts)
        rank={t:i for i,t in enumerate(view.main)}
        main=next((s for s,v in view.streams.items() if v['kind']=='main'),None)
        placed={u:Counter(view.stream_of.get(t) for t in ts).most_common(1)[0][0] for u,ts in merged.items()}
        us=sorted(u for u,s in placed.items() if s==main)
        positions={u:median(rank[t] for t in merged[u] if t in rank) for u in us}
        for i,a in enumerate(us):
            for b in us[i+1:]:
                if positions[a]>positions[b]:population[f'order:{p}:{a}:{b}']={'page':p,'error_kind':'main_flow_inversion','reference_units':[a,b],'positions':[positions[a],positions[b]]}
    detail=captured['detail']['books']['ent_textbook']['reading_order']
    for i,r in enumerate(detail['anchor_misses']):population[f'anchor:{r["page"]}:{i}']={**r,'error_kind':'float_anchor'}
    selected=select('ent_textbook','taxonomy:M05',population)
    write_new(dest/'M05_selection.json',selected)
    # Heading matching repeats only the frozen evidence associations in order
    # to expose individual level disagreements absent from its aggregate JSON.
    from book_core.structure.evidence import _read
    from book_core.structure.models import BookStructure
    from book_core.objects.analysis import verified_read
    ev=_read(CACHES['ent_textbook']/'structure/evidence'/f'{keys["structure_evidence"]}.json.gz',keys['structure_evidence'])
    ut={u['unit']:[(p['page'],o) for o in u['token_ordinals']] for p in ev['pages'] if p['page'] in scope for u in p['units']}
    st=verified_read(CACHES['ent_textbook']/'structure/book'/f'{keys["structure"]}.json',BookStructure,keys['structure'])
    heads={h.id:h for h in st.headings if h.page in scope};tok={}
    for hid,h in heads.items():
        ts={t for uid in h.unit_ids for t in ut.get(uid,())}
        if h.run_in:ts=set(sorted(ts)[:max(1,h.evidence.get('run_in_tokens',1))])
        tok[hid]=ts
    held_by={t:hid for hid,ts in tok.items() for t in ts}
    population={};found=exact=0
    for u in gold.units:
        if u['kind']!='heading' or not u['pdf']:continue
        ts={(p,o) for p,f,n in u['pdf'] for o in range(f,f+n)}
        votes=Counter(held_by[t] for t in ts if t in held_by)
        row={'page':min(ts)[0],'reference_unit':u,'reference_level':u['heading_level']}
        if sum(votes.values())*2<len(ts):population[f'miss:{u["unit"]}']={**row,'error_kind':'missed_heading'};continue
        h=heads[votes.most_common(1)[0][0]];found+=1
        exact+=h.level==u['heading_level']
        if h.level!=u['heading_level']:population[f'level:{u["unit"]}:{h.id}']={**row,'error_kind':'heading_level','our_heading':h.model_dump(mode='json')}
    assert found==48 and exact==18
    selected=select('ent_textbook','taxonomy:M12',population)
    write_new(dest/'M12_selection.json',selected)
    # Existing frozen continuity error rows, without a new join heuristic.
    pop={}
    for name in ['all_column_rows','all_reference_cross_page_rows','all_link_rows']:
        rows=json.loads((BASE/f'evaluations/ent_textbook/continuity_reference/{name}.json').read_text('utf8'))
        for i,r in enumerate(rows):
            failed=r.get('joined') is False or r.get('correct') is False
            if failed:
                p=r.get('page') or r.get('from_page') or (r.get('pages') or [None])[0]
                pop[f'{name}:{i}']={**r,'page':p,'error_kind':name}
    selected=select('ent_textbook','taxonomy:M11',pop)
    write_new(dest/'M11_selection.json',selected)
    write_new(dest/'receipt.json',{'frozen_order_result_equal':True,'heading_found':found,'heading_level_exact':exact,'selected_families':['M05','M11','M12'],'no_judgments_generated':True})
    print('Frozen error populations selected before visual taxonomy judgments',flush=True)

if __name__=='__main__':main()
