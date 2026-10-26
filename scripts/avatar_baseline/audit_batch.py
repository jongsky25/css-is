"""Independently audit retained batch evidence without rerunning measurements.

The archive must be extracted before use. No thresholds or raw files are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

from verification_result import frame_pass, validate_samples, pytest_evidence


def audit(root, kinds, repository):
    root = Path(root)
    def read(name):
        return json.loads((root/name).read_text())
    def check(condition, message):
        if not condition:
            raise ValueError(message)
    phases = {p: read(p+'/assessment.json') for p in ['batch-functional','focused','runtime','matrix']}
    source = phases['matrix']['source_commit']
    for phase, data in phases.items():
        check(data['status']=='passed' and data['gates'] and all(data['gates'].values()), phase+' gates')
        check(not data['harness_errors'] and all(data['environment_checks'].values()), phase+' environment')
        check(data['source_commit']==source and data['expected_chromium']=='156.0.8078.47', phase+' source/browser')
        check(data['chromium'].split()[1]==data['expected_chromium'],phase+' actual browser')
        check(data['callback_budget_ms']==50 and data['frame_budget_ms']==33.3,phase+' budgets')
        check(data['batch_kinds']==kinds, phase+' species cohort')
        hashes={**data['source_sha256'],**{'templates/_avatar_species/'+k+'.html':v for k,v in data['species_sha256'].items()}}
        for file,expected in hashes.items():
            actual=hashlib.sha256(subprocess.check_output(['git','show',source+':'+file],cwd=repository)).hexdigest()
            check(actual==expected,phase+' source file '+file)
    manifest=read('review-manifest.json');hashed=0;traces=0
    check(str(manifest['source_commit'])==source,'manifest source')
    for file,expected in manifest['files'].items():
        path=root/file
        if path.exists():
            with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            check(actual==expected['sha256'] and path.stat().st_size==expected['bytes'],'artifact hash '+file)
            hashed+=1
        else:
            check(file.endswith('.json.gz'),'missing non-trace evidence '+file);traces+=1
    visual=read('batch-functional/static-preview-visual/assessment.json')
    check(visual['all_pixel_identical'] and visual['cells']==4896 and len(visual['sheets'])==51,'static visual completeness')
    for row in visual['sheets']:
        actual=hashlib.sha256((root/'batch-functional/static-preview-visual'/row['file']).read_bytes()).hexdigest()
        check(row['pixel_identical'] and actual==row['preview_sha256']==row['reference_sha256'],'static PNG '+row['file'])
    for name,n in [('browser-regressions',8),('care',len(kinds)),('native-behavior',1),('seasonal-live-refresh',1)]:
        check(pytest_evidence(root/'batch-functional'/(name+'.xml'),n),'functional JUnit '+name)
    callbacks=[];frames=[]
    for phase in ['focused','runtime','matrix']:
        control=read(phase+'/control/empty-control.json')['samples']
        check(len(control)==6 and {(r['cpu'],r['run']) for r in control}=={(cpu,n) for cpu in [1,4] for n in range(3)},phase+' empty controls')
        check(all(r['actions'] and r['scenario']['frame_count'] and r['max_empty_callback_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in control),phase+' control timing')
    for kind in kinds:
        native=read(f'focused/native/{kind}/native-control.json')
        validate_samples(native['samples'],5)
        check(native['source_commit']==source and native['after_only'],'native source '+kind)
        check({(r['version'],r['run']) for r in native['samples']}=={('after',n) for n in range(5)},'native identities '+kind)
        for row in native['samples']:
            check(not row['errors'] and frame_pass(row['scenario']['frame_p95_ms']),'native frame '+kind)
            frames.append(row['scenario']['frame_p95_ms'])
        focused=read(f'focused/traces/{kind}/summary.json')
        validate_samples(focused['samples'],10)
        check(focused['source_commit']==source and focused['runtime_sha256']==phases['focused']['source_sha256']['static/js/avatars.js'],'focused source '+kind)
        check({(r['version'],r['run']) for r in focused['samples']}=={(v,n) for v in ['before','after'] for n in range(5)},'focused identities '+kind)
        pair={a:read(f'runtime/{a}/{kind}/summary.json') for a in ['before','after']}
        check(pair['before']['source_commit'].startswith('5b580d9') and pair['after']['source_commit']==source,'runtime source '+kind)
        check(pair['before']['runtime_sha256']!=pair['after']['runtime_sha256'] and pair['after']['runtime_sha256']==phases['runtime']['source_sha256']['static/js/avatars.js'],'runtime control '+kind)
        for arm,data in pair.items():
            validate_samples(data['samples'],5)
            check(data['after_only'] and {(r['version'],r['run']) for r in data['samples']}=={('after',n) for n in range(5)},'runtime identities '+kind)
        for cohort in [focused['samples'],pair['before']['samples'],pair['after']['samples']]:
            check(all(not r['trace_data_loss'] and r['owned_call_count'] and not r['errors'] for r in cohort),'trace completeness '+kind)
        for row in [r for r in focused['samples'] if r['version']=='after']+pair['after']['samples']:
            check(row['max_owned_call_wall_ms']<=50 and frame_pass(row['scenario']['frame_p95_ms']),'trace timing '+kind)
            callbacks.append(row['max_owned_call_wall_ms']);frames.append(row['scenario']['frame_p95_ms'])
    environments={a:read(f'matrix/{a}/application/environment.json') for a in ['before','after']}
    check(environments['before']['source_commit'].startswith('1c964dc') and environments['after']['source_commit']==source,'matrix source identities')
    check(all(e['chromium']=='156.0.8078.47' for e in environments.values()),'matched matrix browser')
    check(environments['before']['source_sha256']['static/js/avatars.js']!=environments['after']['source_sha256']['static/js/avatars.js'],'matrix original runtime')
    comparison=read('matrix/after/comparison.json')
    check(comparison['complete'] and all(comparison['gates'].values()),'matrix comparison')
    check(comparison['css_js_gzip_delta_bytes']<=15*1024,'code transfer')
    memory=[];timing=[]
    for group in comparison['groups']:
        key=f"{group['mobile']}-{group['cache']}"
        arms={a:read(f'matrix/{a}/application/{key}.json') for a in ['before','after']}
        for arm,rows in arms.items():
            check(len(rows)==5 and {r['run'] for r in rows}==set(range(5)),'matrix identities '+key+arm)
            for row in rows:
                check(row['seconds']>=30 and row['chromium']=='156.0.8078.47' and row['mobile']==group['mobile'] and row['cache']==group['cache'] and row['cpu_rate']==(4 if group['mobile'] else 1),'matrix protocol '+key)
                check(not row['errors'] and not row['external_attempts'] and len(row['picker_selected'])==16,'matrix actions/errors '+key)
        check(group['home_encoded_delta']<=30*1024 and group['picker_encoded_delta']<=120*1024,'document transfer '+key)
        for scenario,metrics in group['scenarios'].items():
            counts={a:{r['scenarios'][scenario]['renderer_process_count'] for r in rows} for a,rows in arms.items()}
            check(len(counts['before'])==1 and counts['before']==counts['after'] and min(counts['before'])>0,'renderer counts '+key+scenario)
            for metric,limit in [('renderer_rss_sum_bytes',10485760),('js_heap_bytes',10485760),('lcp_ms',100)]:
                if metric not in metrics:continue
                samples={a:[r['scenarios'][scenario][metric] for r in rows] for a,rows in arms.items()}
                medians={a:statistics.median(xs) for a,xs in samples.items()};delta=medians['after']-medians['before']
                check(delta==metrics[metric]['median_delta'] and delta<=limit,'raw median '+key+scenario+metric)
                record=dict(group=key,scenario=scenario,metric=metric,samples=samples,medians=medians,delta=delta)
                (memory if metric!='lcp_ms' else timing).append(record)
            if 'interaction_duration_per_run_median_ms' in metrics:
                sample_medians={a:[statistics.median([e['duration'] for e in r['scenarios'][scenario]['events'] if e['interaction']]) for r in rows if any(e['interaction'] for e in r['scenarios'][scenario]['events'])] for a,rows in arms.items()}
                check(all(sample_medians.values()),'missing interaction samples '+key+scenario)
                delta=statistics.median(sample_medians['after'])-statistics.median(sample_medians['before'])
                check(delta==metrics['interaction_duration_per_run_median_ms']['median_delta'] and delta<=20,'raw interaction delta '+key+scenario)
        if group['mobile']:
            for row in arms['after']:
                value=row['scenarios']['home_interaction']['frame_p95_ms'];check(frame_pass(value),'mobile frame '+key);frames.append(value)
    check(len(comparison['groups'])==4,'all matrix groups')
    return {'status':'passed','source_commit':source,'species':kinds,'retained_hashes_verified':hashed,'trace_hashes_retained_only':traces,'static_cells':4896,'matrix_samples':40,'max_owned_callback_ms':max(callbacks),'max_frame_p95_ms':max(frames),'memory':memory,'lcp':timing,'release_ready':False,'limits':{'callback_ms':50,'frame_p95_ms':33.3,'memory_growth_bytes':10485760},'limitations':['No physical mobile device','RSS includes shared pages','Trace bytes retained remotely, not locally rehashed','Lifecycle release findings remain pending increment 5']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);p.add_argument('--kinds',required=True);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        result=audit(a.evidence,a.kinds.split(','),a.repo)
    except Exception as error:
        result={'status':'inconclusive','error':repr(error),'release_ready':False}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['memory','lcp']}))
    sys.exit(0 if result['status']=='passed' else 1)
