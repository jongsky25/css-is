"""Three-source, counterbalanced memory diagnosis. Never release acceptance."""
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

if __package__:
    from .memory_audit import SCENARIOS, MOUNTS, BUDGET
else:
    from memory_audit import SCENARIOS, MOUNTS, BUDGET

ORIGINAL='1c964dc'
CURRENT='f700187'
ORDER=('original','current','candidate','candidate','current','original')


def read_cohort(path):
    rows=json.loads((path/'application/False-warm.json').read_text())
    if len(rows)!=5 or {r['run'] for r in rows}!=set(range(5)):
        raise ValueError('Incomplete or duplicate cohort')
    for r in rows:
        if (r['seconds']!=30 or r['mobile'] is not False or r['cache']!='warm'
                or r['chromium']!='156.0.8078.47' or r['errors']
                or set(r['scenarios'])!=set(SCENARIOS)
                or [n['mount'] for n in r['navigation_trend']]!=list(MOUNTS)):
            raise ValueError('Invalid cohort protocol or application errors')
    points={}
    for name in [*SCENARIOS,*('navigation_'+str(m) for m in MOUNTS)]:
        selected=[next(n for n in r['navigation_trend'] if n['mount']==int(name.split('_')[1]))
                  if name.startswith('navigation_') else r['scenarios'][name] for r in rows]
        counts=[p['renderer_process_count'] for p in selected]
        if len(set(counts))!=1 or min(counts)<=0:
            raise ValueError('Invalid renderer counts: '+name)
        points[name]={'renderer_counts':counts}
        for metric in ('renderer_rss_sum_bytes','js_heap_bytes'):
            values=[p[metric] for p in selected]
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values):
                raise ValueError('Invalid memory values')
            points[name][metric]={'samples':values,'median':statistics.median(values)}
    return points


def compare(before,after):
    records=[]
    for name,a in before.items():
        b=after[name]
        matched=a['renderer_counts']==b['renderer_counts']
        for metric in ('renderer_rss_sum_bytes','js_heap_bytes'):
            delta=b[metric]['median']-a[metric]['median']
            records.append({'checkpoint':name,'metric':metric,'before':a[metric],
                'after':b[metric],'renderer_counts':[a['renderer_counts'],b['renderer_counts']],
                'matched_renderer_counts':matched,'median_delta_bytes':delta,
                'within_10_mib':delta<=BUDGET})
    valid=len(records)==26 and all(r['matched_renderer_counts'] for r in records)
    return {'status':'inconclusive' if not valid else ('passed' if all(r['within_10_mib'] for r in records) else 'application_regression'),
            'coverage':'warm desktop only','acceptance':False,'records':records,
            'failures':[r for r in records if not r['within_10_mib']]}


def main():
    root=Path.cwd();out=root/'avatar-verification/lifecycle-candidate'
    out.mkdir(parents=True,exist_ok=False)
    roots={'candidate':root};saved={};cohorts=[]
    result={'acceptance':False,'budget_bytes':BUDGET,'order':ORDER,
        'method':'Five full 30-second warm-desktop samples per cohort. Original/current/candidate then candidate/current/original. No concurrent analysis, tracing, GC, extra cache flushing or sample filtering. Candidate shares geometry observation and releases it on discarded pages.',
        'cohorts':cohorts,'comparisons':[]}
    try:
        for arm,ref in [('original',ORIGINAL),('current',CURRENT)]:
            folder=root.parent/('avatar-lifecycle-'+arm)
            subprocess.run(['git','worktree','add','--detach',str(folder),ref],check=True)
            roots[arm]=folder;saved[arm]={}
            for name in ('test_avatar_baseline_browser.py','avatar_browser_fixture.py'):
                dest=folder/'tests'/name
                saved[arm][dest]=dest.read_bytes() if dest.exists() else None
                dest.write_bytes((root/'tests'/name).read_bytes())
        for index,arm in enumerate(ORDER):
            dest=out/f'{index}-{arm}';dest.mkdir()
            env=dict(os.environ,CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',
                CSS_AVATAR_PIN_RENDERER='0',CSS_AVATAR_MEMORY_DIAGNOSTIC='1',CSS_AVATAR_RUNS='5',
                CSS_AVATAR_SECONDS='30',CSS_AVATAR_OUT=str(dest/'application'))
            with (dest/'runner.txt').open('w') as stream:
                code=subprocess.run([sys.executable,'-m','pytest',
                    'tests/test_avatar_baseline_browser.py::test_real_application_baseline[warm-desktop]',
                    '-s','--junitxml='+str(dest/'junit.xml')],cwd=roots[arm],env=env,
                    stdout=stream,stderr=subprocess.STDOUT).returncode
            cohort={'index':index,'arm':arm,'exit_code':code,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=roots[arm],text=True).strip()}
            raw=dest/'application/False-warm.json'
            if raw.exists():cohort['raw_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
            try:cohort['points']=read_cohort(dest)
            except (OSError,KeyError,ValueError,TypeError) as exc:cohort['invalid_reason']=repr(exc)
            cohorts.append(cohort)
            (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
            print('COHORT',index,arm,'exit',code,'valid',not cohort.get('invalid_reason'),flush=True)
        pairs=[('original-to-candidate-forward',0,2),('original-to-candidate-reverse',5,3),
               ('current-to-candidate-forward',1,2),('current-to-candidate-reverse',4,3),
               ('original-to-current-forward',0,1),('original-to-current-reverse',5,4),
               ('original-repeat',0,5),('current-repeat',1,4),('candidate-repeat',2,3)]
        for name,a,b in pairs:
            if 'points' not in cohorts[a] or 'points' not in cohorts[b]:
                verdict={'status':'inconclusive','acceptance':False}
            else:verdict=compare(cohorts[a]['points'],cohorts[b]['points'])
            result['comparisons'].append({'name':name,'before_index':a,'after_index':b,**verdict})
            print('COMPARISON',name,verdict['status'],'failures',len(verdict.get('failures',[])),flush=True)
        result['measurement_complete']=len(cohorts)==6 and all(not c['exit_code'] and 'points' in c for c in cohorts)
        result['candidate_targeted_budget_passed']=result['measurement_complete'] and all(c['status']=='passed' for c in result['comparisons'][:2])
        (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:
        for arm,files in saved.items():
            for path,original in files.items():
                if original is None:path.unlink(missing_ok=True)
                else:path.write_bytes(original)
            subprocess.run(['git','worktree','remove',str(roots[arm])],check=True)
    return 0 if result.get('measurement_complete') else 1

if __name__=='__main__':sys.exit(main())
