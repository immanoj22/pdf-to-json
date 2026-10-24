"""Package existing measurements without changing or replacing frozen results."""
import datetime,json,shutil
from collections import Counter,defaultdict
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,sha,write_new

def read(p):return json.loads(Path(p).read_text('utf8'))
def unmeasured(reason):return {'status':'unmeasured','reason':reason}

def main():
    registry=read(BASE/'registered_metric_registry.json');stats=read(BASE/'audit/assessment_statistics.json')
    metrics={};resources={};descriptives={}
    for book in ['ent_textbook','mideast']:
        r=read(BASE/f'evaluations/{book}/robustness.json');pub=read(BASE/f'evaluations/{book}/published_reference_metrics.json')
        data=read(EVIDENCE/book/'book.json')
        import step17_json_eval as frozen
        nodes=[n for t in data['content'] for n,*_ in frozen.walk(t)]
        figs=[n for n in nodes if n.get('type')=='figure']
        desc={'figure_nodes':len(figs),'figure_kinds':dict(Counter(n['kind'] for n in figs)),
            'image_formats':dict(Counter(n['image']['format'] for n in figs)),
            'figure_source':dict(Counter(n.get('source') for n in figs)),
            'exported_image_bytes':sum(n['image']['bytes'] for n in figs),
            'figure_text_units':r['M10_descriptive']['assembly_counts'].get('figure_text_units',0),
            'converted_vs_extracted_images':unmeasured('Publication format/source fields do not preserve an independently verified converted-versus-original-byte export denominator.'),
            'continuity_counts':dict(Counter(n['type']+':'+n['continues_to']['kind'] for n in nodes if n.get('continues_to')))}
        descriptives[book]=desc
        m={f'M{i:02}':unmeasured('No matching independent reference is registered for this book.') for i in range(1,19)}
        m.update(M01=r['M01'],M02=r['M02'],M03=r['M03'],M05={'reference':unmeasured('No matching reference registered'),'internal_order':pub['main_flow_order_vs_archive']},M10={'descriptive':desc,'reference':unmeasured('No matching reference registered')},M11={'descriptive_counts':desc['continuity_counts'],'reference':unmeasured('No matching reference registered')},M12={'reference':unmeasured('No matching reference registered'),'census':read(BASE/f'audit/{book}/census_comparison.json')},M13={'reference':unmeasured('No matching reference registered'),'typing_census':read(BASE/f'audit/{book}/census_comparison.json'),'variant_check':stats['typing_variant_check'][book]},M14=r['M14_descriptive'],M15=r['M15_descriptive'],M16={'agent_samples':[x for x in stats['agent_samples'] if x['book_id']==book and x['family'].startswith('style:')],'reference':unmeasured('No matching reference registered')},M17={'workload':r['M17_workload'],'sampled_flag_observations':[x for x in stats['agent_samples'] if x['book_id']==book and x['family'].startswith('flag:')],'safety_recall':unmeasured('No matching reference; descriptive observations are not safety accuracy.')},M18=r['M18'])
        m['M11']['agent_diagnostics']=[x for x in stats['agent_samples'] if x['book_id']==book and x['family'].startswith('continuity:')]
        if book=='ent_textbook':
            fig=read(BASE/'evaluations/ent_textbook/figure_reference_metrics.json');hf=read(BASE/'evaluations/ent_textbook/heading_folio_reference_metrics.json')
            m.update(M04=pub['paragraphs'],M05={'reference':pub['reading_order'],'internal_order':pub['main_flow_order_vs_archive'],'detailed_coverage':read(BASE/'audit/ent_textbook/error_taxonomies/reading_order_detail.json')},M06=pub['lists']['list_items'],M07=pub['tables'],M08=pub['joined_tables'],M09={'status':'not_applicable','reason':'Registered ENT reference contains no math; whole-book emitted math is not reference truth.'},M10={'reference':fig,'descriptive':desc,'printed_label_accuracy':unmeasured('Frozen figure reader produced no independent printed-label counts; label metrics repeat the page-count proxy. Retain raw proxy, do not call it label accuracy.')},M12={'reference':hf['headings'],'census':read(BASE/'audit/ent_textbook/census_comparison.json')},M13={'index':pub['lists']['index'],'definitions':pub['lists']['definitions'],'bibliography':pub['lists']['bibliography'],'cross_page_entries':pub['lists']['cross_page_entries'],'published_labels_raw':hf['published_page_labels'],'front_label_accuracy':unmeasured('Reference FM identifiers are not printed Roman page labels.'),'typing_census':read(BASE/'audit/ent_textbook/census_comparison.json'),'variant_check':stats['typing_variant_check'][book]})
            m['M11']['reference']=read(BASE/'evaluations/ent_textbook/continuity_reference/ent_textbook.json')
            m['M16']['reference']=read(BASE/'evaluations/ent_textbook/reference_styles/ent_textbook.json')
            m['M16']['publication_parity']=read(BASE/'evaluations/ent_textbook/reference_styles/publication_span_parity.json')
            m['M17']['safety_recall']=stats['source_first_safety']
        metrics[book]=m
        resources[book]={'source_bytes':98420075 if book=='ent_textbook' else 112997873,'readable_copy_bytes':sum(p.stat().st_size for p in (EVIDENCE/book).glob('*') if p.is_file()),'attempt':r['attempt']}
    failed=read(BASE/'evaluations/math_holdout/failed_book_metrics.json');metrics['math_holdout']=failed['metrics']
    metrics['math_holdout']['M01']['precise_failure_stage']=failed['failure_classification']['actual_stage']
    for m in metrics.values():assert set(m)=={x['metric_id'] for x in registry['metrics']}
    result={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze_commit':'8d6a0b0036db3f28dd8b671a2950ceca9918a680','preregistration_commit':'781eb222273461c084a85cc0aef767c25f952796','addendum_commit':'ba8897c05fea63aa903a1b56dd4a72404cde4018','metric_registry':registry,'books':metrics,'resources_supplement':resources,'uncertainty':stats,'owner_audit':{'population':559,'selected':20,'status':'pending owner re-judgment; agent judgments not independently verified'},'no_fixes':True}
    write_new(EVIDENCE/'results.json',result)
    write_new(EVIDENCE/'math_holdout/README.txt.json',{'status':'no complete publication','source_sha256':'7bfd1ff40e044124fb32abada59fb6604f2f412a448a3e417c246f3352fa04bb','freeze_commit':result['freeze_commit'],'reason':'Layout PageLayout validation failed on physical page 348 after 347 validated layouts. No book.json, manifest or review-list can truthfully be copied; no placeholder publication fabricated.'})
    with (EVIDENCE/'math_holdout/README.txt').open('x',encoding='utf8') as s:
        s.write('OpenStax Algebra and Trigonometry 1e (math_holdout)\nFrozen converter: '+result['freeze_commit']+'\nSource SHA-256: 7bfd1ff40e044124fb32abada59fb6604f2f412a448a3e417c246f3352fa04bb\nProfile: default 1.0.0; cbf9a8369859f4cd43c58370b2db3f5d9988ea21e6544b4cef4a23ddcfb2216d\nRun date: 2026-10-24\nFAILED: layout validation on page 348; 347 validated layouts. No complete archive/publication exists. No book.json/review_list.json/manifest.json fabricated. See results.json and preserved attempt evidence. No retry or code fix.\n')
    # Every source receipt/decision is copied verbatim. No images, original PDFs,
    # reference XML, model files, caches or publication assets are copied.
    roots=['audit','evaluation_jobs','evaluations','reference_measurement_queue_v1','post_conversion_queue_v2_read_access']
    allowed={'.json','.jsonl','.md','.diff','.log','.txt','.py','.gz'}
    copies=[]
    for root in roots:
        for p in sorted((BASE/root).rglob('*')):
            if not p.is_file() or p.suffix.lower() not in allowed or 'reference_work' in p.parts:continue
            # raw target packets can contain long repeated node subtrees; the
            # complete judgment register and sample populations retain identities.
            if 'packets' in p.parts and p.name.endswith('_targets.json'):continue
            target=EVIDENCE/'measurement_evidence'/p.relative_to(BASE)
            target.parent.mkdir(parents=True,exist_ok=True)
            assert not target.exists();shutil.copyfile(p,target)
            copies.append({'path':target.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    for p in sorted((BASE/'samples').rglob('*.json')):
        t=EVIDENCE/'measurement_evidence'/p.relative_to(BASE);t.parent.mkdir(parents=True,exist_ok=True);assert not t.exists();shutil.copyfile(p,t)
        copies.append({'path':t.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    for p in sorted(BASE.glob('*.py')):
        t=EVIDENCE/'orchestration_tools'/p.name;t.parent.mkdir(parents=True,exist_ok=True);assert not t.exists();shutil.copyfile(p,t)
        copies.append({'path':t.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    for folder in ['ent_textbook_attempt1','ent_textbook_attempt2','math_holdout_attempt1','mideast_attempt1','retry_preparation']:
        for p in sorted((BASE/folder).rglob('*')):
            if not p.is_file() or p.suffix.lower() not in allowed or p.name=='future_seal_metadata_notes.json':continue
            if 'live' in p.name or p.stat().st_size>5_000_000:continue
            t=EVIDENCE/'measurement_evidence'/p.relative_to(BASE);t.parent.mkdir(parents=True,exist_ok=True);assert not t.exists();shutil.copyfile(p,t)
            copies.append({'path':t.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    for p in sorted(BASE.glob('*.json')):
        t=EVIDENCE/'measurement_evidence'/p.name;t.parent.mkdir(parents=True,exist_ok=True);assert not t.exists();shutil.copyfile(p,t)
        copies.append({'path':t.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    write_new(EVIDENCE/'measurement_evidence/copy_manifest_v1.json',{'copied_verbatim':copies,'images_copied':0,'reference_originals_copied':0,'helper_scope':'Invocation, data routing, monitoring, presentation and reporting only. Frozen functions and converter files unchanged.','large_full_attempt_manifests_retained_locally':'retry_preparation/attempt1_manifest.json and copy_manifest.json if over size bound; checksums/summary receipts retained.'})
    print('All 18 metric rows retained per book; evidence packaged',len(copies),flush=True)

if __name__=='__main__':main()
