"""Persist explicitly adjudicated source-page occurrences; not an evaluator change."""
import datetime,json,re,unicodedata
from collections import Counter
from evaluation_routes import BASE,write_new
from fixed_sampling import append_judgment
def norm(s):return re.sub(r'\W','',unicodedata.normalize('NFKC',s).lower())
# These decisions follow actual original-page views and subsequent output inspection.
correct={25:['competency'],7:['preface'],50:['case_answers'],31:['chapter1','competencies','anatomy','external','auricle'],35:['checkpoint','middle','parts','boundaries'],33:['external'],45:['physiology','components'],15:['ack','reviewers'],48:['electrical','highlights'],13:['simulations'],42:['corti']}
split={1:['book_title'],3:['book_title'],31:['section1'],48:['geniculate']}
overrides={(42,'perilymph'):'dc8964ca01cb0840',(41,'membranous'):'fbd08e81a4e3a84b',(33,'critical2'):'12ddbd8248ed80f4',(33,'critical3'):'e7b7fa5de9c0c1a7',(35,'objective1'):'e2820ec403ac3a1a',(35,'objective2'):'d458799514518873'}
spurious={3:['8b1f293c2dbd67a7','41e8a93ae7293a26'],7:['f836e7d4d5301d78'],31:['2a4ee4f753f1c27d']}
rows=json.loads((BASE/'audit/ent_textbook/packets/census_output.json').read_text('utf8'))
out=[];counts=Counter();errors=[]
for r in rows:
 p=r['page'];o=r['source_observation'];occ=[]
 ts=list({(x['owner'],x['text']):x for x in r['all_text_records']}.values())
 def relevant(ids,kinds):return [f for f in r['review'] if f.get('unit') in ids and f['kind'] in kinds]
 for h in o['headings']:
  lid=h['local_id'];s=norm(h['text'])
  if lid in correct.get(p,[]):v='correct_standalone_heading'
  elif lid in split.get(p,[]):v='split_heading_or_title'
  else:v='missed_standalone_heading'
  hits=sorted([t for t in ts if s in norm(t['text'])],key=lambda t:(len(t['text']),t['owner'] or ''))
  if (p,lid) in overrides:hits=[t for t in ts if t['owner']==overrides[p,lid]]
  if v=='correct_standalone_heading':hits=[t for t in hits if t['type']=='heading'][:1]
  elif v=='split_heading_or_title':
   hits=[t for t in ts if t['type']=='heading' and norm(t['text']) and norm(t['text']) in s]
  else:
   hits=[t for t in hits if t['type'] not in {None,'text'}][:1]
  assert hits,(p,h,v)
  ids={t['owner'] for t in hits};flags=relevant(ids,{'heading','structure','caption'})
  x={'target_id':f'{p}:heading:{lid}','source_occurrence':h,'agent_verdict':v,'output_evidence':hits,'relevant_flags':flags}
  counts['source_standalone_headings']+=1;counts[v]+=1;occ.append(x)
  if v!='correct_standalone_heading':errors.append({**x,'page':p,'source_first':o['source_first']})
 for sid in spurious.get(p,[]):
  hit=next(t for t in r['typed_candidates'] if t['id']==sid)
  x={'target_id':f'{p}:spurious_heading:{sid}','agent_verdict':'spurious_heading_metadata_or_attribution','output_evidence':hit,'relevant_flags':relevant({sid},{'heading','structure'})}
  counts[x['agent_verdict']]+=1;occ.append(x);errors.append({**x,'page':p,'source_first':o['source_first']})
 for fn in o['footnotes']:
  hit=next(t for t in ts if norm(fn['text']) in norm(t['text']))
  x={'target_id':f'{p}:footnote:{fn["local_id"]}','source_occurrence':fn,'agent_verdict':'missed_footnote_merged_into_paragraph','output_evidence':hit,'relevant_flags':relevant({hit['owner']},{'footnote','structure'})}
  counts['source_footnotes']+=1;counts[x['agent_verdict']]+=1;occ.append(x);errors.append({**x,'page':p,'source_first':o['source_first']})
 for t in r['typed_candidates']:
  if t['type']=='footnote' and not o['footnotes']:
   x={'target_id':f'{p}:spurious_footnote:{t["id"]}','agent_verdict':'table_cell_wrongly_typed_footnote','output_evidence':t,'relevant_flags':relevant({t['id']},{'footnote','table'})}
   counts[x['agent_verdict']]+=1;occ.append(x);errors.append({**x,'page':p,'source_first':o['source_first']})
 folio=None
 if o['printed_folio'] is not None:
  fs=[f for f in r['furniture'] if f.get('kind')=='folio' and f['content']['text'].strip()==o['printed_folio']]
  counts['source_visible_folios']+=1
  if fs:v='correct_folio_furniture';e=fs
  else:
   assert p==17
   e=[t for t in ts if '\nxvii\n' in t['text']];assert len(e)==1
   v='folio_in_body_not_furniture'
  counts[v]+=1;folio={'agent_verdict':v,'output_evidence':e}
  if v!='correct_folio_furniture':errors.append({'target_id':f'{p}:folio','page':p,'source_first':o['source_first'],**folio,'relevant_flags':relevant({e[0]['owner']},{'structure'})})
 comparison={'page':p,'source_first':o['source_first'],'occurrences':occ,'folio':folio,'run_in_labels_unresolved':o.get('run_in_labels',[]),'formal_glossary_visible':0,'notes':'Run-in parent labels remain ambiguous. Title fragments and false headings are separate errors; no double counting of repeated traversal appearances.'}
 out.append(comparison)
 append_judgment({'judgment_id':f'ent_textbook:page_census:{p}','book_id':'ent_textbook','family':'page_census','target_id':str(p),'crop_paths':o['crop_paths'],'context_paths':o['context_paths'],'agent_verdict':'source_census_typing_comparison','source_observation':o,'comparison':comparison,'notes':'Actual source views and subsequent typing comparison. Page 42 had prior output exposure and is excluded from source-first recall stratum. Agent judgment is not independent verification.','viewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
write_new(BASE/'audit/ent_textbook/census_comparison.json',{'counts':counts,'comparisons':out,'error_occurrences':errors,'source_first_pages':19,'prior_exposure_pages':[42],'formal_glossary_denominator':0,'ambiguities':'Standalone vs parent list lead-ins not forced. Four genuine notes on p45 merge to one paragraph. Five p29 table cell footnote nodes are false positives; correlated within a table. Source occurrence recall must be page clustered and must exclude p42 for source-first estimates.','independently_verified':False})
print(dict(counts))
