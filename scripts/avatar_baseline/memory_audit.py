"""Audit every retained scenario and navigation memory sample against 10 MiB.

No baseline subtraction beyond the declared median delta, GC, sample filtering,
or reinterpretation of RSS as private memory is permitted.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

SCENARIOS = ('home_idle','home_interaction','wellness_care','picker_growth',
             'seasonal_preview','offscreen','reduced_motion','background')
MOUNTS = (1,5,10,15,20)
BUDGET = 10 * 1024 * 1024


def audit_memory(before, after):
    records=[];gates={};environment={};errors={}
    for mobile in (False,True):
        for cache in ('cold','warm'):
            group=f'{mobile}-{cache}'
            try:
                arms={arm:json.loads((Path(folder)/(group+'.json')).read_text()) for arm,folder in [('before',before),('after',after)]}
                for arm,rows in arms.items():
                    if len(rows)!=5 or {r['run'] for r in rows}!=set(range(5)):
                        raise ValueError(arm+' incomplete/duplicate cohort')
                    if any(r['seconds']<30 or r['mobile']!=mobile or r['cache']!=cache for r in rows):
                        raise ValueError(arm+' mismatched protocol')
                    if any(set(r['scenarios'])!=set(SCENARIOS) for r in rows):
                        raise ValueError(arm+' missing/unexpected scenario')
                    if any([x['mount'] for x in r['navigation_trend']]!=list(MOUNTS) for r in rows):
                        raise ValueError(arm+' incomplete navigation sequence')
                browsers={r['chromium'] for rows in arms.values() for r in rows}
                if len(browsers)!=1 or not next(iter(browsers)):
                    raise ValueError('Mismatched or missing browser version')
                for scenario in [*SCENARIOS,*('navigation_'+str(m) for m in MOUNTS)]:
                    def point(row):
                        if scenario.startswith('navigation_'):
                            mount=int(scenario.split('_')[1])
                            return next(n for n in row['navigation_trend'] if n['mount']==mount)
                        return row['scenarios'][scenario]
                    points={arm:[point(r) for r in rows] for arm,rows in arms.items()}
                    counts={arm:[p['renderer_process_count'] for p in ps] for arm,ps in points.items()}
                    matched=(len(set(counts['before']))==1 and set(counts['before'])==set(counts['after']) and min(counts['before'])>0)
                    environment[group+'-'+scenario+'-renderer_counts']=matched
                    for metric in ('renderer_rss_sum_bytes','js_heap_bytes'):
                        samples={arm:[p[metric] for p in ps] for arm,ps in points.items()}
                        if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for values in samples.values() for v in values):
                            raise ValueError('Invalid memory measurement '+scenario+' '+metric)
                        medians={arm:statistics.median(values) for arm,values in samples.items()}
                        delta=medians['after']-medians['before'];key=group+'-'+scenario+'-'+metric
                        gates[key]=delta<=BUDGET
                        records.append({'group':group,'scenario':scenario,'metric':metric,'samples':samples,'medians':medians,'worst':{a:max(v) for a,v in samples.items()},'median_delta_bytes':delta,'renderer_counts':counts,'matched_renderer_counts':matched,'within_budget':delta<=BUDGET})
            except (KeyError,ValueError,TypeError,OSError) as error:
                errors[group]=repr(error)
    complete=len(records)==4*(len(SCENARIOS)+len(MOUNTS))*2
    environment['all_scenarios_and_navigation_complete']=complete
    status='inconclusive' if errors or not all(environment.values()) else ('passed' if all(gates.values()) else 'application_regression')
    return {'status':status,'budget_bytes':BUDGET,'gates':gates,'environment_checks':environment,'harness_errors':errors,'records':records,'failures':[r for r in records if not r['within_budget']],'release_ready':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=audit_memory(a.before,a.after);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'measurements':len(result['records']),'failures':len(result['failures']),'errors':result['harness_errors']}))
    raise SystemExit(0 if result['status']=='passed' else 1)
