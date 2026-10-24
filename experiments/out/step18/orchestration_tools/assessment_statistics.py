"""Uncertainty/count attribution for unchanged Step 18 scores and manual records."""
import json,math,random
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
from evaluation_routes import BASE,EVIDENCE,route,write_new

def wilson(c,n):
    if not n:return None
    z=1.959963984540054;p=c/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half,mid+half]

def bootstrap(rows,stat):
    rng=random.Random(20261024);vals=[]
    for _ in range(1000):
        sample=[rows[rng.randrange(len(rows))] for _ in rows];v=stat(sample)
        if v is not None:vals.append(v)
    vals.sort()
    return {'seed':20261024,'resamples':1000,'valid_resamples':len(vals),'clusters':len(rows),'interval_95':[vals[int(.025*(len(vals)-1))],vals[int(.975*(len(vals)-1))]] if vals else None}

def ratio(rows,a,b):
    den=sum(r[b] for r in rows);return sum(r[a] for r in rows)/den if den else None

def main():
    run,_,_=route('ent_textbook')
    import step14a_common as common
    import step17_json_eval as frozen
    import book_core.evaluation.derived_harness as harness
    from book_core.evaluation.paragraphs import reference_tokens
    from book_core.evaluation.reading_order import _pairs
    data=json.loads((EVIDENCE/'ent_textbook/book.json').read_text('utf8'))
    scope=set(json.loads((EVIDENCE/'ent_textbook/alignment_evidence/scope_mapping.json').read_text('utf8'))['accuracy_pages'])
    lines,spans,units=frozen.json_view(data)
    owner,views=frozen.owners_of('ent_textbook',lines,spans,run['pages'])
    owner={k:v for k,v in owner.items() if k[0] in scope};views={p:v for p,v in views.items() if p in scope}
    gold=common.derived_gold('ent_textbook')
    prior=json.loads((BASE/'evaluations/ent_textbook/published_reference_metrics.json').read_text('utf8'))
    statistics={'method':'Wilson 95% binomial; 1000 page-cluster resamples with replacement, seed 20261024. Within-book uncertainty, not independent books or baseline uncertainty.','paragraphs':{}}
    seq,_=reference_tokens(gold)
    for label,kinds in [('per_page',{'column'}),('chained',{'column','page'})]:
        root=frozen.chains(data,kinds);logical={t:root(u) for t,u in owner.items()}
        scored=[(p,o,u) for p,o,u in seq if (p,o) in logical]
        counts={p:{'page':p,'tp':0,'fp':0,'fn':0,'pairs':0} for p in scope}
        for (p,o,u),(q,v,w) in zip(scored,scored[1:]):
            ref=u!=w;ours=logical[p,o]!=logical[q,v];r=counts[q]
            r['pairs']+=1;r['tp']+=ref and ours;r['fp']+=ours and not ref;r['fn']+=ref and not ours
        def f1(rs):
            t=sum(r['tp'] for r in rs);den=2*t+sum(r['fp']+r['fn'] for r in rs)
            return 2*t/den if den else None
        assert round(f1(list(counts.values())),6)==prior['paragraphs'][label]['boundary_f1']
        statistics['paragraphs'][label]={'page_contributions':list(counts.values()),'boundary_f1':bootstrap(list(counts.values()),f1),'cross_page_pair_policy':'Attribute boundary pair to its second endpoint page; preserves every original pair and aggregate.','exact_match_interval':'not estimated: frozen aggregate exposes no page-attributed exact logical-unit contribution; units can cross pages.'}
    captured={};original=harness.evaluate
    def capture(gs,outputs,**kwargs):
        result=original(gs,outputs,**kwargs);captured.update(detail=result,output=outputs['ent_textbook']);return result
    harness.evaluate=capture
    result=frozen.reading_order('ent_textbook',owner,data,views);assert result==prior['reading_order']
    detail=captured['detail']['books']['ent_textbook']['reading_order'];per=[]
    on=defaultdict(list)
    for u in gold.units:
        for p,f,n in u['pdf']:
            if p in scope:on[p].append((u['unit'],range(f,f+n)))
    for p,view in captured['output'].pages.items():
        merged=defaultdict(list)
        for u,ts in on[p]:merged[u].extend(ts)
        rank={t:i for i,t in enumerate(view.main)};main=next((s for s,v in view.streams.items() if v['kind']=='main'),None)
        placed={u:Counter(view.stream_of.get(t) for t in ts).most_common(1)[0][0] for u,ts in merged.items()}
        ms=sorted(u for u,s in placed.items() if s==main)
        positions=[median(rank[t] for t in merged[u] if t in rank) for u in ms]
        c,d=_pairs(positions);ic=ip=anchors=0
        for sid,info in view.streams.items():
            members=sorted(u for u,s in placed.items() if s==sid)
            if not members or info['kind']=='main':continue
            if len(members)>1:
                a,b=_pairs([median(info['tokens'].index(t) for t in merged[u] if view.stream_of.get(t)==sid) for u in members]);ic+=a;ip+=a+b
            anchors+=info['anchor'] is not None
        wrong=sum(r['page']==p for r in detail['anchor_misses'])
        per.append({'page':p,'correct':c,'pairs':c+d,'tau_num':c-d,'inner_correct':ic,'inner_pairs':ip,'anchors':anchors,'anchor_correct':anchors-wrong})
    for key,a,b in [('main_flow','correct','pairs'),('kendall_tau','tau_num','pairs'),('float_anchors','anchor_correct','anchors'),('within_floats','inner_correct','inner_pairs')]:
        assert round(ratio(per,a,b),6)==prior['reading_order'][key]
    statistics['reading_order']={'page_contributions':per,**{key:bootstrap(per,lambda rs,a=a,b=b:ratio(rs,a,b)) for key,a,b in [('main_flow','correct','pairs'),('kendall_tau','tau_num','pairs'),('float_anchors','anchor_correct','anchors'),('within_floats','inner_correct','inner_pairs')]}}
    tab=defaultdict(list)
    for row in prior['tables']['matched_detail']:
        if not row['structural_score_excluded']:tab[row['gold_key'][1]].append(row)
    statistics['tables']={k:bootstrap(list(tab.values()),lambda groups,k=k:sum(r[k] for g in groups for r in g)/sum(len(g) for g in groups)) for k in ['teds','teds_full']}
    statistics['tables']['clusters_note']='Matched reference-page clusters only; 10/11 detected segments. Joined-table interval not estimated: one multi-page table.'
    judgments=[json.loads(s) for s in (BASE/'audit/judgments.jsonl').read_text('utf8').splitlines()]
    grouped=defaultdict(list)
    for r in judgments:grouped[r['book_id'],r['family']].append(r)
    audit=[]
    for (book,fam),rs in grouped.items():
        cs=Counter(r['agent_verdict'] for r in rs);rec={'book_id':book,'family':fam,'sample':len(rs),'verdicts':dict(cs),'independently_verified':False}
        if book=='ent_textbook' and fam.startswith(('style:','continuity:','flag:')):
            if fam.startswith('flag:'):
                c=cs['true_error']+cs['true_page_error'];w=sum(v for k,v in cs.items() if k.startswith(('false_warning','cautious_')))
            else:c=cs['correct'];w=cs['wrong']
            rec.update(correct=c,wrong=w,unclear_or_requirement=len(rs)-c-w,adjudicated_ratio=c/(c+w) if c+w else None,wilson_95=wilson(c,c+w),conservative_correct_all=c/len(rs),conservative_wilson_95=wilson(c,len(rs)))
        audit.append(rec)
    statistics['agent_samples']=audit
    census=json.loads((BASE/'audit/ent_textbook/census_comparison.json').read_text('utf8'))
    source=[r for r in census['comparisons'] if r['source_first']]
    errors=[r for r in census['error_occurrences'] if r['source_first']]
    # Original candidate flags remain verbatim. A missing-caption-link flag
    # cannot capture wrong heading typing merely because it shares an owner.
    dedup={};strict_rows=[]
    for e in errors:
        kind='footnote' if 'footnote' in e['agent_verdict'] else 'folio' if 'folio' in e['agent_verdict'] else 'heading'
        ev=e['output_evidence'];ev=ev if isinstance(ev,list) else [ev]
        ids=sorted({x.get('owner') or x.get('id') for x in ev if x.get('owner') or x.get('id')})
        flags=[f for f in e['relevant_flags'] if f['kind'] in ({'structure','heading'} if kind=='heading' else {'footnote','table','structure'} if kind=='footnote' else {'structure'})]
        key=(e['page'],kind,tuple(ids))
        row=dedup.setdefault(key,{'page':e['page'],'class':kind,'owner_ids':ids,'source_occurrence_ids':[],'captured':False,'capture_flags':[]})
        row['source_occurrence_ids'].append(e['target_id']);row['captured']|=bool(flags);row['capture_flags'].extend(flags)
        strict_rows.append({'target_id':e['target_id'],'class':kind,'captured':bool(flags),'candidate_flags':e['relevant_flags'],'accepted_flags':flags})
    safety={}
    for kind in ['heading','footnote','folio']:
        rs=[r for r in dedup.values() if r['class']==kind];c=sum(r['captured'] for r in rs)
        pages=[{'page':p['page'],'correct':sum(r['captured'] for r in rs if r['page']==p['page']),'total':sum(r['page']==p['page'] for r in rs)} for p in source]
        safety[kind]={'captured':c,'errors':len(rs),'false_negatives':len(rs)-c,'recall':c/len(rs) if rs else None,'wilson_95':wilson(c,len(rs)),'page_bootstrap':bootstrap(pages,lambda x:ratio(x,'correct','total')),'rows':rs}
    statistics['source_first_safety']={'pages':19,'excluded_prior_exposure':[42],'deduplication':'within family by physical page and sorted owning-unit IDs; merged source occurrences retained as child IDs. No pooling across families.','strict_flag_decisions':strict_rows,'families':safety,'glossary':{'denominator':0,'recall':None},'agent_judgments_independently_verified':False}
    # Check every emitted type/role, including the actual glossary_entry type
    # omitted by the first presentation shortlist. Raw role counts retained.
    variants={}
    for book in ['ent_textbook','mideast']:
        d=json.loads((EVIDENCE/book/'book.json').read_text('utf8'));cr=json.loads((BASE/f'audit/{book}/packets/census_output.json').read_text('utf8'));ps={r['page'] for r in cr}
        allnodes=[n for t in d['content'] for n,*_ in frozen.walk(t)]
        candidates=[{'id':n.get('id'),'type':n.get('type'),'role':n.get('role'),'pages':n.get('pages')} for n in allnodes if any(s in str(n.get('type',''))+' '+str(n.get('role','')) for s in ['gloss','definition','footnote']) and ps.intersection(n.get('pages') or [])]
        variants[book]={'census_pages':sorted(ps),'all_typing_variants':candidates,'whole_book_types':dict(Counter(n.get('type') for n in allnodes))}
    statistics['typing_variant_check']=variants
    write_new(BASE/'audit/assessment_statistics.json',statistics)
    print('Uncertainty, strict relevant-flag decisions, typing variants complete',flush=True)

if __name__=='__main__':main()
