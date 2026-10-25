"""Complete 2B verification on one fixed CI image; retain failures, no retries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

p=argparse.ArgumentParser();p.add_argument('phase',choices=['functional','focused','matrix']);a=p.parse_args()
root=Path.cwd();out=root/'avatar-verification'/a.phase;out.mkdir(parents=True,exist_ok=True)
python=sys.executable
base_env=dict(os.environ,CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0')
statuses={}
def run(name,args,*,cwd=root,extra=None):
    env=dict(base_env,**(extra or {}));log=out/f'{name}.txt'
    with log.open('w') as f:
        statuses[name]=subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    print(name,statuses[name],flush=True)
    return statuses[name]
def read(path):return json.loads(path.read_text())
def pytest(name,files,extra=None,cwd=root):return run(name,[python,'-m','pytest',*files,'-s'],extra=extra,cwd=cwd)
# The user accepted a0.3ms overrun; preserve original values and50ms callback limit.
def frame_pass(value):return value<=33.3+1e-8
meta={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
      'python':sys.version,'platform':__import__('platform').platform(),'cpu_count':os.cpu_count(),'affinity':sorted(os.sched_getaffinity(0)),'chromium':subprocess.check_output(['chromium','--version'],text=True).strip(),
      'frame_budget_ms':33.3,'original_frame_budget_ms':33,'callback_budget_ms':50,
      'frame_exception':'User accepted0.3ms frame overrun; no waiver for callbacks or larger stalls.',
      'source_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ['static/js/avatars.js','templates/_avatars.html']}}
(out/'environment.json').write_text(json.dumps(meta,indent=2))
gates={}
try:
    if a.phase=='functional':
        names=['motion_preference','chase_writes','geometry','pointer','static_preview','home_search_boot']
        files=['tests/test_avatar_motion_preference_browser.py','tests/test_avatar_chase_writes_browser.py','tests/test_avatar_geometry_browser.py','tests/test_avatar_pointer_browser.py','tests/test_avatar_static_preview_browser.py','tests/test_home_search_boot_browser.py']
        gates['browser_regressions']=pytest('browser-regressions',files,{'CSS_AVATAR_OUT':str(out/'functional/application')})==0
        gates['svg_equivalence']=run('svg-equivalence',[python,'scripts/avatar_baseline/check_lazy_equivalence.py','--out',str(out/'visual')])==0
        gates['native_visibility_touch_keyboard']=pytest('native-behavior',['tests/test_avatar_baseline_browser.py','-k','native_visibility_and_touch'],{'CSS_AVATAR_OUT':str(out/'native/application')})==0
        gates['persisted_plant_care']=pytest('care',['tests/test_avatar_baseline_browser.py','-k','plant_care_live_surfaces'],{'CSS_AVATAR_OUT':str(out/'care/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_PLANTS':'fern,mushroom,succulent'})==0
    elif a.phase=='focused':
        pytest('empty-control',['tests/test_avatar_throttle_control.py'],{'CSS_AVATAR_THROTTLE_DIAGNOSTIC':'1','CSS_AVATAR_OUT':str(out/'control/application')})
        control=read(out/'control/empty-control.json')['samples']
        gates['empty_control']=len(control)==6 and all(r['max_empty_callback_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in control)
        pytest('native',['tests/test_avatar_native_control.py'],{'CSS_AVATAR_OUT':str(out/'native/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_NATIVE_AFTER_ONLY':'1'})
        pytest('traces',['tests/test_avatar_cpu_attribution.py'],{'CSS_AVATAR_OUT':str(out/'traces/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_CPU_DIAGNOSTIC':'1','CSS_AVATAR_CPU_RUNS':'5'})
        for kind in ['fern','mushroom','succulent']:
            native=read(out/f'native/{kind}/native-control.json')
            rows=native['samples']
            gates[f'{kind}_native']=len(rows)==5 and native['after_only'] and all(not r['errors'] and frame_pass(r['scenario']['frame_p95_ms']) for r in rows)
            trace=read(out/f'traces/{kind}/summary.json');rows=trace['samples'];after=[r for r in rows if r['version']=='after']
            gates[f'{kind}_traces']=len(rows)==10 and len(after)==5 and all(r['owned_call_count'] and not r['errors'] and not r['trace_data_loss'] for r in rows) and all(r['max_owned_call_wall_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in after)
    else:
        before=root.parent/'avatar-2b-before'
        subprocess.run(['git','worktree','add','--detach',str(before),'1c964dc'],check=True)
        try:
            for name in ['test_avatar_baseline_browser.py','avatar_browser_fixture.py']:
                shutil.copy2(root/'tests'/name,before/'tests'/name)
            fs={str(path):subprocess.check_output(['stat','-f','-c','%T',str(path)],text=True).strip() for path in [root,before]}
            assert len(set(fs.values()))==1,'Before/current filesystem mismatch'
            (out/'filesystems.json').write_text(json.dumps(fs,indent=2))
            for name,cwd in [('before',before),('after',root)]:
                pytest(name,['tests/test_avatar_baseline_browser.py','-k','real_application_baseline'],{'CSS_AVATAR_OUT':str(out/name/'application'),'CSS_AVATAR_RUNS':'5','CSS_AVATAR_SECONDS':'30'},cwd=cwd)
                run('summarize-'+name,[python,'scripts/avatar_baseline/summarize.py',str(out/name/'application')])
            run('compare',[python,'scripts/avatar_baseline/compare.py','--before',str(out/'before/application'),'--after',str(out/'after/application')])
            comparison=read(out/'after/comparison.json');gates.update(comparison['gates'])
            for name in ['before','after']:
                gates[name+'_complete']=read(out/name/'application/summary.json')['full_duration_complete']
            # RSS is comparable only with the same renderer-process counts.
            for mobile in [False,True]:
                for cache in ['cold','warm']:
                    pair=[read(out/f'{arm}/application/{mobile}-{cache}.json') for arm in ['before','after']]
                    for scenario in pair[0][0]['scenarios']:
                        counts=[{r['scenarios'][scenario]['renderer_process_count'] for r in rows} for rows in pair]
                        gates[f'{mobile}-{cache}-{scenario}-matched_renderer_counts']=len(counts[0])==1 and counts[0]==counts[1] and min(counts[0])>0
            values=[r['scenarios']['home_interaction']['frame_p95_ms'] for f in ['True-cold','True-warm'] for r in read(out/f'after/application/{f}.json')]
            gates['mobile_interaction_p95_all_runs_le_33ms']=all(frame_pass(v) for v in values)
            gates['mobile_interaction_p95_medians_le_33ms']=all(frame_pass(g['scenarios']['home_interaction']['frame_p95_ms']['after']['median']) for g in comparison['groups'] if g['mobile'])
            for g in comparison['groups']:
                for scenario,metrics in g['scenarios'].items():
                    for metric,budget in [('lcp_ms',100),('interaction_duration_per_run_median_ms',20),('renderer_rss_sum_bytes',10*1048576),('js_heap_bytes',10*1048576)]:
                        if metric in metrics:gates[f"{g['mobile']}-{g['cache']}-{scenario}-{metric}"]=metrics[metric]['median_delta']<=budget
        finally:
            subprocess.run(['git','-C',str(before),'restore','tests/test_avatar_baseline_browser.py'],check=True)
            (before/'tests/avatar_browser_fixture.py').unlink(missing_ok=True)
            subprocess.run(['git','worktree','remove',str(before)],check=True)
except Exception as error:
    gates['harness_complete']=False
    meta['harness_error']=repr(error)
finally:
    result={**meta,'phase':a.phase,'runner_statuses':statuses,'gates':gates,'status':'passed' if gates and all(gates.values()) else 'failed'}
    (out/'assessment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
sys.exit(0 if result['status']=='passed' else 1)
