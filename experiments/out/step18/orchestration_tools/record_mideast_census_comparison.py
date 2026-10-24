"""Record the agent's comparison after all 20 original pages were actually viewed.

The source observations were saved before examining output typing. Mideast has
no reference: all counts here remain descriptive, with no accuracy rate.
"""
import datetime,json,re,unicodedata
from collections import Counter
from evaluation_routes import BASE,write_new
from fixed_sampling import append_judgment

def norm(s):return re.sub(r'\W','',unicodedata.normalize('NFKC',s).lower())

def main():
    rows=json.loads((BASE/'audit/mideast/packets/census_output.json').read_text('utf8'))
    assert len(rows)==20
    output=[]
    counts=Counter()
    for r in rows:
        o=r['source_observation'];p=r['page'];occ=[]
        for h in o['headings']:
            hits=[x for x in r['all_text_records'] if norm(h['text'])==norm(x['text'])]
            assert len(hits)==1,(p,h,hits)
            hit=hits[0];verdict='correct' if hit['type']=='heading' else 'missed_heading_typed_'+str(hit['type'])
            counts['source_standalone_headings']+=1
            counts['heading_correct' if verdict=='correct' else 'heading_missed']+=1
            occ.append({'source_occurrence':h,'output':hit,'agent_verdict':verdict,
                'relevant_review': [x for x in r['review'] if x.get('unit')==hit['owner'] and x['kind'] in {'heading','structure'}]})
        for header in o['running_headers']:
            hits=[x for x in r['typed_candidates'] if any(norm(t['text'])==norm(header['text']) for t in x['text'])]
            assert len(hits)==1,(p,header,hits)
            counts['spurious_heading_from_running_header']+=1
            occ.append({'source_occurrence':header,'output':hits[0],'agent_verdict':'running_header_typed_heading',
                'relevant_review':[x for x in r['review'] if x.get('unit')==hits[0]['id'] and x['kind'] in {'heading','structure'}]})
        fs=[f for f in r['furniture'] if f.get('kind')=='folio' and f['content']['text'].strip()==o['printed_folio']]
        assert len(fs)==1,(p,fs)
        counts['source_folios']+=1;counts['folio_retained_as_furniture']+=1
        assert not o['footnotes'] and not o['glossary_definition_entries']
        comparison={'page':p,'occurrences':occ,'folio':{'output_id':fs[0]['id'],'agent_verdict':'correct_folio_furniture'},
            'footnotes':{'visible':0,'spurious_output':0},'glossary_definitions':{'visible':0,'spurious_output':0},
            'run_in_labels':o.get('run_in_labels',[]),'notes':'Run-in lead-ins retained separately, not forced into standalone heading counts. No rate or safety recall inferred for Mideast.'}
        output.append(comparison)
        append_judgment({'judgment_id':f'mideast:page_census:{p}', 'book_id':'mideast','family':'page_census','target_id':str(p),
            'crop_paths':o['crop_paths'],'context_paths':o['context_paths'],
            'agent_verdict':'descriptive_typing_comparison','source_first_observation':o,'comparison':comparison,
            'notes':'Original page viewed before output typing. Running header/section-heading confusions recorded; folio retained. No independent verification or Mideast accuracy claim.',
            'viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    write_new(BASE/'audit/mideast/census_comparison.json',{'book_id':'mideast','pages':20,'counts':counts,'comparisons':output,
        'status':'descriptive only; agent judgments not independently verified','accuracy_rates':None,'safety_recall':None,
        'zero_denominator_note':'No visible footnote or glossary/definition entry in this sample; no perfect score inferred.'})
    print(dict(counts))

if __name__=='__main__':main()
