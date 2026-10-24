"""Format already-recorded counts and registered development gaps for the report."""
import json
from pathlib import Path
from evaluation_routes import BASE,EVIDENCE,ROOT,write_new

def interval(v):
    return 'unestimated' if v is None else '['+','.join(f'{x:.4f}' for x in v)+']'

def main():
    r=json.loads((EVIDENCE/'results_v2.json').read_text('utf8'));s=r['uncertainty']
    lines=['### Review workload by kind','',
      'Counts cover the complete books. Flags may repeat the same target; rates use',
      '612 ENT pages and 317 Mideast pages. Math has no review list.','',
      '| Kind | ENT items | ENT /page | Mideast items | Mideast /page |','|---|---:|---:|---:|---:|']
    a=r['books']['ent_textbook']['M17']['workload']['by_kind'];b=r['books']['mideast']['M17']['workload']['by_kind']
    for k in sorted(set(a)|set(b)):
        lines.append(f'| {k} | {a.get(k,0)} | {a.get(k,0)/612:.4f} | {b.get(k,0)} | {b.get(k,0)/317:.4f} |')
    lines += ['', '### Flag correctness: fixed strata, not pooled book precision','',
      'ENT sampling is restricted to the located reference scope. A cautious flag',
      'without a demonstrated defect is kept separate from a definite wrong-role',
      'warning. The error-share denominator below includes definite false and',
      'cautious cases, but excludes unclear and unresolved requirements. Wilson',
      'intervals are conditional on these adjudications, with within-page correlation.',
      'No eligible scoped character flags were found despite 330 whole-book flags.','',
      '| ENT kind | Sample | Real error | Definite false | Cautious | Unclear / requirement | Error share; Wilson 95% |',
      '|---|---:|---:|---:|---:|---:|---|']
    for row in s['agent_samples']:
        if row['book_id']!='ent_textbook' or not row['family'].startswith('flag:'):continue
        v=row['verdicts'];t=v.get('true_error',0);c=v.get('cautious_not_demonstrated_error',0)
        f=sum(n for k,n in v.items() if k.startswith('false_warning'));u=row['sample']-t-c-f
        share='unmeasured' if row['adjudicated_ratio'] is None else f"{t}/{t+c+f}={row['adjudicated_ratio']:.4f}; {interval(row['wilson_95'])}"
        lines.append(f"| {row['family'].split(':')[1]} | {row['sample']} | {t} | {f} | {c} | {u} | {share} |")
    lines += ['', 'Mideast uses descriptive counts only; these do not estimate flag precision.','',
      '| Mideast kind | Sample | Corresponding error | Definite false | Cautious | Unclear / requirement |',
      '|---|---:|---:|---:|---:|---:|']
    for row in s['agent_samples']:
        if row['book_id']!='mideast' or not row['family'].startswith('flag:'):continue
        v=row['verdicts'];t=sum(n for k,n in v.items() if k.startswith('true'));c=v.get('cautious_not_demonstrated_error',0)
        f=sum(n for k,n in v.items() if k.startswith('false_warning'));u=row['sample']-t-c-f
        lines.append(f"| {row['family'].split(':')[1]} | {row['sample']} | {t} | {f} | {c} | {u} |")
    lines += ['', 'Every sampled flag retains its specific reason. A real role error does not',
      'make an unrelated missing-caption-link warning correct. Alt-text requirements',
      'remain unresolved; they are not counted as demonstrated semantic defects.',
      'Three Mideast must-check OCR warnings target one page, not three independent',
      'errors. ENT structure warning positives also include duplicate targets on the',
      'same erroneous owner. These samples cannot be pooled or weighted into a',
      'whole-book safety percentage.','']
    report=ROOT/'docs/step18_report.md';text=report.read_text('utf8');assert text.count('<!-- GENERATED_SAMPLE_TABLES -->')==1
    report.write_text(text.replace('<!-- GENERATED_SAMPLE_TABLES -->','\n'.join(lines)),encoding='utf8',newline='\n')
    vals=[
      ('M04','page_f1',.933408,.85,.95),('M04','chained_f1',.933371,.90,.95),
      ('M04','page_exact',1429/1774,.68,.90),('M04','chained_exact',1428/1774,.68,.90),
      ('M05','main',.893759,.96,1),('M05','tau',.787519,.92,1),('M05','anchor',.5,.55,.90),('M05','within_float',.998498,.94,1),
      ('M06','item_f1',1,.85,.92),('M06','item_exact',1,.70,.85),('M06','list_boundary_f1',1,.50,.70),
      ('M07','precision',1,.88,1),('M07','recall',10/11,.65,1),('M07','structure_TEDS',.9701,.80,.98),('M07','full_TEDS',.9701,.78,.95),
      ('M10','figure_page_precision',31/41,.50,.93),('M10','figure_page_recall',31/35,.60,.95),('M10','caption_coverage',17/20,.30,.65),
      ('M11','reference_link_precision',.5,.95,1),('M12','heading_precision',50/75,.60,.97),('M12','heading_recall',48/66,.73,.93),('M12','level_exact',18/48,.75,.87),
      ('M13','body_label',1,.99,1),('M16','visible_bold',1,.75,1),('M16','visible_italic',1,.75,1),('M16','visible_super',19/20,.75,1),('M16','visible_math',1/7,.75,1),
      ('M17','review_items_per_page',1918/612,.3,4)]
    out={'meaning':'ENT hold-out minus registered planning endpoints, not significance tests. Higher better except workload; conditional coverage limitations in report/results.','rows':[{'metric_id':m,'component':k,'holdout':v,'lower':lo,'upper':hi,'gap_to_lower':v-lo,'gap_to_upper':v-hi} for m,k,v,lo,hi in vals],
      'mideast_workload_only':{'items_per_page':698/317,'band':[0,5],'gap_to_endpoints':[698/317,698/317-5]},
      'math_accuracy':'unmeasured after code failure','unmeasured_components':'Retained in registry/results; no comparable truth means no numeric gap.'}
    write_new(EVIDENCE/'measurement_evidence/development_gaps.json',out)
    print('Report tables and numeric gap ledger saved',flush=True)

if __name__=='__main__':main()
