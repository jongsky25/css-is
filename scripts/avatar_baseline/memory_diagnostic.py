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
summary = {'acceptance': False, 'purpose': 'Attribute RSS variance without GC, cache flushing, or budget changes', 'cohorts': []}
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
            cohort['samples'] = [{
                'run': r['run'],
                'rss_bytes': r['scenarios']['picker_growth']['renderer_rss_sum_bytes'],
                'heap_bytes': r['scenarios']['picker_growth']['js_heap_bytes'],
                'details': r['scenarios']['picker_growth']['renderer_memory_detail'],
                'dom': r['scenarios']['picker_growth']['dom_counters'],
            } for r in rows]
            cohort['rss_median_bytes'] = statistics.median(r['rss_bytes'] for r in cohort['samples'])
        summary['cohorts'].append(cohort)
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
        print('MEMORY_COHORT=' + json.dumps(cohort, separators=(',', ':')), flush=True)
finally:
    subprocess.run(['git', '-C', str(before), 'restore', 'tests/test_avatar_baseline_browser.py'], check=True)
    (before / 'tests/avatar_browser_fixture.py').unlink(missing_ok=True)
    subprocess.run(['git', 'worktree', 'remove', str(before)], check=True)
if len(summary['cohorts']) != 4 or any(c['exit_code'] for c in summary['cohorts']):
    sys.exit(1)
