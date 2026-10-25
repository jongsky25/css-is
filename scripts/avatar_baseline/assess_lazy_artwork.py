"""Assess the fresh lazy-template cohort, retaining all earlier failures."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

root = Path('docs/avatars/increment2b')
out = root / 'lcp-unblock'
read = lambda p: json.loads(p.read_text())
comparison = read(out / 'comparison.json')
summary = read(out / 'application/summary.json')
assert comparison['complete'] and summary['full_duration_complete']
rows = [r for p in sorted((out / 'application').glob('*.json')) if p.stem in ['False-cold', 'False-warm', 'True-cold', 'True-warm'] for r in read(p)]
assert len(rows) == 20
assert all(r['seconds'] == 30 and r['chromium'] == '154.0.8037.57' and r['cpu_rate'] == (4 if r['mobile'] else 1) for r in rows)
control = read(root / 'reproduced-overlay-control/application/False-cold.json')
current = [r for r in rows if not r['mobile'] and r['cache'] == 'cold']
assert len(current) == len(control) == 5
old_values = [r['scenarios']['home_idle']['lcp_ms'] for r in control]
new_values = [r['scenarios']['home_idle']['lcp_ms'] for r in current]
env = read(out / 'application/environment.json')
before_env = read(root / 'reproduced-overlay-control/application/environment.json')
for key in ['chromium', 'playwright', 'python', 'platform', 'fixture_date_local', 'random_seed']:
    assert env[key] == before_env[key], key
assert subprocess.check_output(['stat', '-f', '-c', '%T', '.'], text=True).strip() == 'overlayfs'
for name, digest in env['source_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
assert read(out / 'artwork-equivalence.json')['svg_equivalence_checks'] == 1734
# The application fixture's only post-a607092 change is provenance metadata;
# instrumentation and scenario behavior remain identical.
secondary = {}
for group in comparison['groups']:
    for name, metrics in group['scenarios'].items():
        if name in ['home_idle', 'home_interaction']:
            continue
        for metric, budget in [('lcp_ms', 100), ('interaction_duration_per_run_median_ms', 20), ('renderer_rss_sum_bytes', 10*1048576), ('js_heap_bytes', 10*1048576)]:
            if metric in metrics:
                delta = metrics[metric]['median_delta']
                secondary[f"{group['mobile']}-{group['cache']}-{name}-{metric}"] = {'delta': delta, 'budget': budget, 'passed': delta <= budget}
matched = {'reference_commit': before_env['source_commit'], 'current_commit': env['source_commit'],
           'control_values_ms': old_values, 'current_values_ms': new_values,
           'control_median_ms': statistics.median(old_values), 'current_median_ms': statistics.median(new_values),
           'control_worst_ms': max(old_values), 'current_worst_ms': max(new_values),
           'median_delta_ms': statistics.median(new_values) - statistics.median(old_values), 'budget_ms': 100}
matched['passed'] = matched['median_delta_ms'] <= matched['budget_ms']
batch = read(out / 'batch-diagnostic/summary.json')
assert batch['groups']['batched']['runtime_sha256'] == env['source_sha256']['static/js/avatars.js']
callback_checks = {}
for kind in ['fern', 'mushroom', 'succulent']:
    trace = read(out / f'targeted/{kind}/long-task-attribution.json')
    after = next(r for r in trace if r['version'] == 'after')
    assert after['kind'] == kind and after['mature_fixture'] and after['cpu_rate'] == 4 and after['seconds'] == 30
    calls = [c['duration_ms'] for t in after['trace_long_tasks'] for c in t['calls'] if c['file'].startswith(('avatars.js', 'avatar-audio.js'))]
    callback_checks[kind] = {'max_recorded_avatar_callback_ms': max(calls, default=0), 'passed': max(calls, default=0) <= 50}
native = read(out / 'application/native-visibility-touch.json')
assert native['hidden_end']['hidden']
passed = all(comparison['gates'].values()) and matched['passed'] and all(s['passed'] for s in secondary.values()) and all(s['passed'] for s in callback_checks.values())
result = {'status': 'complete' if passed else 'blocked', 'primary_samples': 20,
          'source_commit': env['source_commit'], 'comparison': 'lcp-unblock/comparison.json',
          'historical_gates': comparison['gates'], 'same_filesystem_control': matched,
          'secondary_scenario_gates': secondary, 'secondary_gates_passed': all(s['passed'] for s in secondary.values()),
          'preserved_failed_cohort': 'assessment-blocked.json',
          'artwork_equivalence': 'lcp-unblock/artwork-equivalence.json',
          'native_hidden_verified': True, 'avatar_callback_checks': callback_checks,
          'preserved_stopped_attempt': 'lcp-unblock/pre-frame-fix/STOPPED.json',
          'limits': ['Lazy loading removes measured compilation work; it does not establish that all prior run-to-run variation was caused by template compilation.',
                     'Original 20 failed samples and both original-source controls remain preserved; no sample replacement or threshold adjustment.',
                     'Existing offscreen motion, chase/idle/roam timers, animated picker thumbnails and remount listeners remain separate release blockers.'],
          'next_step': '3A: dog, rabbit, bird and turtle' if passed else 'Continue investigating the failing gate before 3A.'}
(out / 'assessment.json').write_text(json.dumps(result, indent=2))
print(json.dumps({'status': result['status'], 'historical_gates': comparison['gates'], 'matched_cold_desktop': matched, 'secondary_passed': result['secondary_gates_passed']}, indent=2))
