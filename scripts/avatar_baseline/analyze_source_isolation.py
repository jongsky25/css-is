"""Validate every source-screen sample and evaluate predeclared comparisons."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

if __package__:
    from .memory_audit import SCENARIOS,MOUNTS,BUDGET
    from .lifecycle_candidate import compare
else:
    from memory_audit import SCENARIOS,MOUNTS,BUDGET
    from lifecycle_candidate import compare

ORDER=('current','geometry','preview','svg','svg','preview','geometry','current')


def points(rows, samples=2):
    if len(rows)!=samples or {r['run'] for r in rows}!=set(range(samples)):raise ValueError('Incomplete source cohort')
    for row in rows:
        if (row['seconds']!=30 or row['mobile'] is not False or row['cache']!='warm' or
            row['chromium']!='156.0.8078.47' or row['errors'] or set(row['scenarios'])!=set(SCENARIOS) or
            [p['mount'] for p in row['navigation_trend']]!=list(MOUNTS)):
            raise ValueError('Invalid source-screen protocol')
    result={}
    for key in [*SCENARIOS,*('navigation_'+str(m) for m in MOUNTS)]:
        selected=[next(p for p in r['navigation_trend'] if p['mount']==int(key.split('_')[1])) if key.startswith('navigation_') else r['scenarios'][key] for r in rows]
        counts=[p['renderer_process_count'] for p in selected]
        if len(set(counts))!=1 or min(counts)<=0:raise ValueError('Invalid renderer counts')
        result[key]={'renderer_counts':counts}
        for metric in ['renderer_rss_sum_bytes','js_heap_bytes']:
            values=[p[metric] for p in selected]
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('Invalid memory observation')
            result[key][metric]={'samples':values,'median':statistics.median(values)}
    return result


def qualifies(pair):
    if pair['status']=='inconclusive' or any(not r['within_10_mib'] for r in pair['records']):return False
    selected=[r for r in pair['records'] if r['metric']=='renderer_rss_sum_bytes' and r['checkpoint'] in ['navigation_10','navigation_20']]
    return len(selected)==2 and all(r['median_delta_bytes']<=-5*1024*1024 for r in selected)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    root=args.root;repo=Path(__file__).resolve().parents[2]
    plan=json.loads((root/'experiment.json').read_text())
    validation=plan.get('observer_validation',False)
    order=('current','geometry','geometry','current') if validation else ORDER
    samples=5 if validation else 2
    if (plan['order']!=list(order) or plan['samples_per_arm']!=samples or
        plan['cohorts']!=[{'index':i,'arm':arm,'exit_code':0} for i,arm in enumerate(order)]):
        raise ValueError('Incomplete experiment')
    cohorts=[];verified=0
    for i,arm in enumerate(order):
        folder=root/f'{i}-{arm}';env=json.loads((folder/'environment.json').read_text())
        for name,digest in env['source_sha256'].items():
            changed=root/'variants'/arm/name
            if changed.exists():
                data=changed.read_bytes()
                if validation:
                    expected=subprocess.check_output(['git','show','f700187:'+name],cwd=repo)
                    if arm=='geometry' and name=='static/js/avatars.js':
                        expected=expected.replace(b'if (window.ResizeObserver) {',b'if (false && window.ResizeObserver) {',1)
                    if data!=expected:raise ValueError('Unexpected observer intervention: '+name)
            elif name.startswith('tests/'):data=(repo/name).read_bytes()
            else:data=subprocess.check_output(['git','show','f700187:'+name],cwd=repo)
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch: '+name)
            verified+=1
        raw=folder/'False-warm.json';cohorts.append({'index':i,'arm':arm,'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'points':points(json.loads(raw.read_text()),samples)})
    comparisons=[];candidates={}
    for arm,first,second in ([('geometry',1,2)] if validation else [('geometry',1,6),('preview',2,5),('svg',3,4)]):
        pairs=[]
        for order,a,b in [('forward',0,first),('reverse',len(order)-1,second)]:
            pair={'arm':arm,'order':order,**compare(cohorts[a]['points'],cohorts[b]['points'])}
            pair['screen_qualifies']=qualifies(pair);pairs.append(pair);comparisons.append(pair)
        candidates[arm]=all(p['screen_qualifies'] for p in pairs)
    repeat=compare(cohorts[0]['points'],cohorts[-1]['points'])
    result={'acceptance':False,'samples_per_arm':samples,'source_hashes_verified':verified,'cohorts':cohorts,'comparisons':comparisons,
        'current_repeat':repeat,'screen_candidates':candidates,
        'limits':'Warm desktop source isolation only. Not proof of causality or acceptance. Every candidate must repeat in five-sample original/current/candidate cohorts with no budget waiver.'}
    (root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'source_hashes_verified':verified,'screen_candidates':candidates,'current_repeat_status':repeat['status']},indent=2))


if __name__=='__main__':main()
