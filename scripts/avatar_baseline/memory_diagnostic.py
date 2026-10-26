"""Retain two opposite-order warm desktop cohorts; diagnostic, never acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

root = Path.cwd()
out = root / 'avatar-verification' / 'memory-diagnostic'
out.mkdir(parents=True, exist_ok=False)
before = root.parent / 'avatar-memory-original'
subprocess.run(['git', 'worktree', 'add', '--detach', str(before), '1c964dc'], check=True)
summary = {'acceptance': False, 'purpose': 'Reproduce every warm desktop scenario and navigation checkpoint in both execution orders; unchanged final 2B product; no GC, extra cache flushing, sample filtering or budget changes', 'cohorts': []}
try:
    for name in ['test_avatar_baseline_browser.py', 'avatar_browser_fixture.py']:
        shutil.copy2(root / 'tests' / name, before / 'tests' / name)
    for index, arm in enumerate(['before', 'after', 'after', 'before']):
        cwd = before if arm == 'before' else root
        dest = out / f'{index}-{arm}'
        dest.mkdir()
        env = dict(os.environ, CSS_TEST_NOW='2026-07-15T12:00:00',
                   CSS_AVATAR_BASELINE='1', CSS_AVATAR_PIN_RENDERER='0',
                   CSS_AVATAR_MEMORY_DIAGNOSTIC='1', CSS_AVATAR_RUNS='5',
                   CSS_AVATAR_SECONDS='30', CSS_AVATAR_OUT=str(dest / 'application'))
        with (dest / 'runner.txt').open('w') as log:
            code = subprocess.run([sys.executable, '-m', 'pytest',
                'tests/test_avatar_baseline_browser.py::test_real_application_baseline[warm-desktop]',
                '-s', '--junitxml=' + str(dest / 'junit.xml')], cwd=cwd, env=env,
                stdout=log, stderr=subprocess.STDOUT).returncode
        cohort = {'index': index, 'arm': arm, 'exit_code': code}
        raw = dest / 'application/False-warm.json'
        if raw.exists():
            rows = json.loads(raw.read_text())
            cohort['raw_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
            cohort['browser_versions'] = sorted({r['chromium'] for r in rows})
            cohort['checkpoints'] = {}
            for scenario in [*rows[0]['scenarios'], *('navigation_'+str(m) for m in (1,5,10,15,20))]:
                def point(r):
                    if scenario.startswith('navigation_'):
                        return next(n for n in r['navigation_trend'] if n['mount']==int(scenario.split('_')[1]))
                    return r['scenarios'][scenario]
                points = [point(r) for r in rows]
                cohort['checkpoints'][scenario] = {
                    'rss_median_bytes': statistics.median(p['renderer_rss_sum_bytes'] for p in points),
                    'heap_median_bytes': statistics.median(p['js_heap_bytes'] for p in points),
                    'renderer_counts': [p['renderer_process_count'] for p in points],
                    'rss_samples_bytes': [p['renderer_rss_sum_bytes'] for p in points],
                    'dom_samples': [p['dom_counters'] for p in points],
                }
        summary['cohorts'].append(cohort)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
        print('MEMORY_COHORT=' + json.dumps(cohort, separators=(',', ':')), flush=True)
    summary['pairs'] = []
    for old_index,new_index in [(0,1),(3,2)]:
        old,new = summary['cohorts'][old_index],summary['cohorts'][new_index]
        if not old.get('checkpoints') or not new.get('checkpoints'): continue
        comparisons = {}
        for key in old['checkpoints']:
            a,b = old['checkpoints'][key],new['checkpoints'][key]
            delta = b['rss_median_bytes']-a['rss_median_bytes']
            comparisons[key] = {'rss_delta_bytes':delta,'within_10_mib':delta<=10*1024*1024,
                'before_renderer_counts':a['renderer_counts'],'after_renderer_counts':b['renderer_counts']}
        summary['pairs'].append({'before_index':old_index,'after_index':new_index,'comparisons':comparisons})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
finally:
    subprocess.run(['git', '-C', str(before), 'restore', 'tests/test_avatar_baseline_browser.py'], check=True)
    (before / 'tests/avatar_browser_fixture.py').unlink(missing_ok=True)
    subprocess.run(['git', 'worktree', 'remove', str(before)], check=True)
if len(summary['cohorts']) != 4 or any(c['exit_code'] for c in summary['cohorts']):
    sys.exit(1)
