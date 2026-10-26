"""Complete 2B verification on one fixed CI image; retain failures, no retries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from verification_result import Results, frame_pass, validate_samples, pytest_evidence

p=argparse.ArgumentParser();p.add_argument('phase',choices=['functional','control','focused','runtime','matrix']);p.add_argument('--output',type=Path,default=Path('avatar-verification'));a=p.parse_args()
root=Path.cwd();out=(a.output/a.phase).resolve();out.mkdir(parents=True,exist_ok=False)
python=sys.executable
base_env=dict(os.environ,CSS_TEST_NOW='2026-07-15T12:00:00',CSS_AVATAR_BASELINE='1',CSS_AVATAR_PIN_RENDERER='0')
statuses={}
results=Results()
def run(name,args,*,cwd=root,extra=None):
    env=dict(base_env,**(extra or {}));log=out/f'{name}.txt'
    with log.open('w') as f:
        statuses[name]=subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    print(name,statuses[name],flush=True)
    return statuses[name]
def read(path):return json.loads(path.read_text())
def pytest(name,files,extra=None,cwd=root,expected=None):
    code=run(name,[python,'-m','pytest',*files,'-s','--junitxml='+str(out/(name+'.xml'))],extra=extra,cwd=cwd)
    if code not in (0,1):
        results.errors[name]=f'pytest runner exited {code}'
    if expected is not None:
        def evidence():
            passed=pytest_evidence(out/(name+'.xml'),expected)
            if code != (0 if passed else 1):
                raise ValueError('Test exit code disagrees with JUnit evidence')
            return passed
        results.check(name+'_tests',evidence)
    return code
def run_control():
    results.check('control_runner',lambda: pytest('empty-control',['tests/test_avatar_throttle_control.py'],{'CSS_AVATAR_THROTTLE_DIAGNOSTIC':'1','CSS_AVATAR_OUT':str(out/'control/application')},expected=1)==0,environment=True)
    def control_check():
        rows=read(out/'control/empty-control.json')['samples']
        if {(r['cpu'],r['run']) for r in rows}!={(cpu,run) for cpu in [1,4] for run in range(3)} or len(rows)!=6:
            raise ValueError('Incomplete empty control cohort')
        return all(r['actions'] and r['scenario']['frame_count'] and r['max_empty_callback_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in rows)
    results.check('empty_control',control_check,environment=True)

# The user accepted a0.3ms overrun; preserve original values and50ms callback limit.
meta={'phase':a.phase}
try:
    meta={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          'python':sys.version,'platform':__import__('platform').platform(),'cpu_count':os.cpu_count(),'affinity':sorted(os.sched_getaffinity(0)),'chromium':subprocess.check_output(['chromium','--version'],text=True).strip(),
          'expected_chromium':os.getenv('CSS_AVATAR_CHROMIUM','154.0.8037.57'),'working_tree_status':subprocess.check_output(['git','status','--porcelain'],text=True),'frame_budget_ms':33.3,'original_frame_budget_ms':33,'callback_budget_ms':50,
          'frame_exception':'User accepted0.3ms frame overrun; no waiver for callbacks or larger stalls.',
          'source_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ['static/js/avatars.js','templates/_avatars.html','scripts/avatar_baseline/ci_verify.py','scripts/avatar_baseline/verification_result.py','tests/test_avatar_cpu_attribution.py']}}
    if meta['chromium'].split()[1] != meta['expected_chromium']:
        raise ValueError('Installed browser differs from explicit benchmark version')
    (out/'environment.json').write_text(json.dumps(meta,indent=2))
except Exception as error:
    results.errors['metadata']=repr(error)
gates=results.gates
try:
    if a.phase=='functional':
        files=['tests/test_avatar_motion_preference_browser.py','tests/test_avatar_chase_writes_browser.py','tests/test_avatar_geometry_browser.py','tests/test_avatar_pointer_browser.py','tests/test_avatar_static_preview_browser.py','tests/test_home_search_boot_browser.py']
        results.check('browser_regressions',lambda: pytest('browser-regressions',files,{'CSS_AVATAR_OUT':str(out/'functional/application')},expected=8)==0)
        results.check('svg_equivalence',lambda: run('svg-equivalence',[python,'scripts/avatar_baseline/check_lazy_equivalence.py','--out',str(out/'visual')])==0)
        results.check('native_visibility_touch_keyboard',lambda: pytest('native-behavior',['tests/test_avatar_baseline_browser.py','-k','native_visibility_and_touch'],{'CSS_AVATAR_OUT':str(out/'native/application')},expected=1)==0)
        results.check('persisted_plant_care',lambda: pytest('care',['tests/test_avatar_baseline_browser.py','-k','plant_care_live_surfaces'],{'CSS_AVATAR_OUT':str(out/'care/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_PLANTS':'fern,mushroom,succulent'},expected=1)==0)
    elif a.phase=='control':
        run_control()
    elif a.phase=='focused':
        run_control()
        results.check('native_runner',lambda: pytest('native',['tests/test_avatar_native_control.py'],{'CSS_AVATAR_OUT':str(out/'native/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_NATIVE_AFTER_ONLY':'1'},expected=3)==0)
        results.check('trace_runner',lambda: pytest('traces',['tests/test_avatar_cpu_attribution.py'],{'CSS_AVATAR_OUT':str(out/'traces/application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_CPU_DIAGNOSTIC':'1','CSS_AVATAR_CPU_RUNS':'5'},expected=3)==0)
        for kind in ['fern','mushroom','succulent']:
            def native_check():
                native=read(out/f'native/{kind}/native-control.json');rows=native['samples']
                validate_samples(rows,5)
                if not native['after_only'] or {(r['version'],r['run']) for r in rows}!={('after',n) for n in range(5)}:
                    raise ValueError('Incorrect native cohort')
                return all(not r['errors'] and frame_pass(r['scenario']['frame_p95_ms']) for r in rows)
            def trace_check():
                rows=read(out/f'traces/{kind}/summary.json')['samples'];validate_samples(rows,10)
                if {(r['version'],r['run']) for r in rows}!={(v,n) for v in ['before','after'] for n in range(5)} or any(not r['owned_call_count'] or r['trace_data_loss'] for r in rows):
                    raise ValueError('Incomplete/lost trace cohort')
                return all(not r['errors'] for r in rows) and all(r['max_owned_call_wall_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in rows if r['version']=='after')
            results.check(kind+'_native',native_check)
            results.check(kind+'_traces',trace_check)
    elif a.phase=='runtime':
        run_control()
        # Whole pre-2B checkout, not old SVG served by the current JavaScript.
        before=root.parent/'avatar-2b-runtime-before'
        subprocess.run(['git','worktree','add','--detach',str(before),'5b580d9'],check=True)
        copied=['test_avatar_baseline_browser.py','avatar_browser_fixture.py','test_avatar_native_control.py','test_avatar_cpu_attribution.py']
        existed={}
        try:
            for name in copied:
                path=before/'tests'/name;existed[name]=path.read_bytes() if path.exists() else None
                shutil.copy2(root/'tests'/name,path)
            for arm,cwd in [('before',before),('after',root)]:
                results.check(arm+'_runner',lambda: pytest('runtime-'+arm,['tests/test_avatar_cpu_attribution.py'],{'CSS_AVATAR_OUT':str(out/arm/'application'),'CSS_AVATAR_MATURE':'1','CSS_AVATAR_CPU_DIAGNOSTIC':'1','CSS_AVATAR_CPU_RUNS':'5','CSS_AVATAR_CPU_AFTER_ONLY':'1'},cwd=cwd,expected=3)==0)
            for kind in ['fern','mushroom','succulent']:
                def compare_runtime():
                    pair=[read(out/arm/kind/'summary.json') for arm in ['before','after']]
                    for data in pair:
                        validate_samples(data['samples'],5)
                        if not data.get('after_only') or {(r['version'],r['run']) for r in data['samples']}!={('after',n) for n in range(5)} or any(r['trace_data_loss'] or not r['owned_call_count'] for r in data['samples']):
                            raise ValueError('Incomplete whole-runtime trace')
                    if pair[0]['source_commit']==pair[1]['source_commit'] or pair[0]['runtime_sha256']==pair[1]['runtime_sha256']:
                        raise ValueError('Runtime control did not change source')
                    # Preserve all baseline failures, without waiving current limits.
                    return all(not r['errors'] and r['max_owned_call_wall_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in pair[1]['samples'])
                results.check(kind+'_runtime',compare_runtime)
        finally:
            for name,contents in existed.items():
                path=before/'tests'/name
                if contents is None:path.unlink(missing_ok=True)
                else:path.write_bytes(contents)
            subprocess.run(['git','worktree','remove',str(before)],check=True)
    else:
        run_control()
        before=root.parent/'avatar-2b-before'
        subprocess.run(['git','worktree','add','--detach',str(before),'1c964dc'],check=True)
        try:
            for name in ['test_avatar_baseline_browser.py','avatar_browser_fixture.py']:
                shutil.copy2(root/'tests'/name,before/'tests'/name)
            fs={str(path):subprocess.check_output(['stat','-f','-c','%T',str(path)],text=True).strip() for path in [root,before]}
            assert len(set(fs.values()))==1,'Before/current filesystem mismatch'
            (out/'filesystems.json').write_text(json.dumps(fs,indent=2))
            for name,cwd in [('before',before),('after',root)]:
                results.check(name+'_runner',lambda: pytest(name,['tests/test_avatar_baseline_browser.py','-k','real_application_baseline'],{'CSS_AVATAR_OUT':str(out/name/'application'),'CSS_AVATAR_RUNS':'5','CSS_AVATAR_SECONDS':'30'},cwd=cwd,expected=4)==0)
                results.check('summarize-'+name,lambda: run('summarize-'+name,[python,'scripts/avatar_baseline/summarize.py',str(out/name/'application')])==0,environment=True)
            results.check('comparison_runner',lambda: run('compare',[python,'scripts/avatar_baseline/compare.py','--before',str(out/'before/application'),'--after',str(out/'after/application')])==0,environment=True)
            comparison=read(out/'after/comparison.json');gates.update(comparison['gates'])
            for name in ['before','after']:
                results.environment[name+'_complete']=read(out/name/'application/summary.json')['full_duration_complete']
            # RSS is comparable only with the same renderer-process counts.
            for mobile in [False,True]:
                for cache in ['cold','warm']:
                    pair=[read(out/f'{arm}/application/{mobile}-{cache}.json') for arm in ['before','after']]
                    for scenario in pair[0][0]['scenarios']:
                        counts=[{r['scenarios'][scenario]['renderer_process_count'] for r in rows} for rows in pair]
                        results.environment[f'{mobile}-{cache}-{scenario}-matched_renderer_counts']=len(counts[0])==1 and counts[0]==counts[1] and min(counts[0])>0
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
    results.errors['phase']=repr(error)
finally:
    baseline_findings={name:results.gates.pop(name) for name in list(results.gates) if name in ('before_runner','runtime-before_tests','before_tests')}
    result={'baseline_findings':baseline_findings,**meta,'phase':a.phase,'runner_statuses':statuses,**results.as_dict()}
    (out/'assessment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
sys.exit(0 if result['status']=='passed' else 1)
