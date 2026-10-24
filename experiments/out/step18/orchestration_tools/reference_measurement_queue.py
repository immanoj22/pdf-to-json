"""Serial guarded scoring of the reviewed, pre-registered ENT input scope."""
import datetime,json,subprocess,sys
from evaluation_routes import BASE,ROOT

def main():
    dest=BASE/'reference_measurement_queue_v1';dest.mkdir(exist_ok=False)
    jobs=[('ent_table_input_v1','table_reference_evidence_scoped.py',['ent_textbook']),
        ('ent_published_metrics_v1','published_reference_metrics_scoped.py',['ent_textbook']),
        ('ent_figures_v1','ent_figure_reference_metrics_scoped.py',[]),
        ('ent_heading_folio_v1','ent_heading_folio_metrics_scoped.py',[]),
        ('ent_styles_v1','ent_style_reference_metrics_scoped.py',[]),
        ('ent_continuity_v1','continuity_reference_metrics_scoped.py',['ent_textbook']),
        ('ent_samples_v1','prepare_visual_populations_scoped.py',['ent_textbook']),
        ('ent_render_v1','render_selected_targets.py',['ent_textbook'])]
    state={'jobs':[],'start_time':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    for label,script,args in jobs:
        row={'job_id':label,'script':script,'arguments':args};state['jobs'].append(row)
        state['current_job']=label;state['outcome']='running'
        (dest/'live.json').write_text(json.dumps(state,indent=1),encoding='utf8')
        with (dest/(label+'.log')).open('x',encoding='utf8') as s:
            p=subprocess.run([sys.executable,'-B','-u',str(BASE/'evaluation_guard.py'),label,str(BASE/script),*args],cwd=ROOT,stdout=s,stderr=subprocess.STDOUT)
        row['exit_code']=p.returncode
        if p.returncode:
            state['outcome']='stopped_after_measurement_failure';break
    else:state['outcome']='completed_awaiting_visual_judgments'
    state['end_time']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (dest/'live.json').write_text(json.dumps(state,indent=1),encoding='utf8')

if __name__=='__main__':main()
