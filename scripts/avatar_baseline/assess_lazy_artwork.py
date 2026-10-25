"""Assess the fresh lazy-template cohort, retaining all earlier failures."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

root = Path('docs/avatars/increment2b')
out = root / 'lcp-unblock'
read = lambda p: json.loads(p.read_text())
# Focused validation is a prerequisite; retain a failing cohort without running
# or borrowing a primary matrix from a different source revision.
focused = {}
for kind in ['fern', 'mushroom', 'succulent']:
    data = read(out / f'native-control/{kind}/native-control.json')
    assert data['after_only'] and data['kind'] == kind and len(data['samples']) == 5
    checks = []
    for row in data['samples']:
        assert row['version'] == 'after' and row['mature'] and row['cpu'] == 4 and row['seconds'] == 30
        scripts = [s for l in row['native_long_animation_frames'] for s in l['scripts'] if '/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']]
        maximum = max((s['duration'] for s in scripts), default=0)
        checks.append({'run': row['run'], 'frame_p95_ms': row['scenario']['frame_p95_ms'], 'max_reported_owned_script_ms': maximum,
                       'over_budget_scripts': [s for s in scripts if s['duration'] > 50],
                       'passed': not row['errors'] and row['scenario']['frame_p95_ms'] <= 33 and maximum <= 50})
    focused[kind] = {'source_commit': data['source_commit'], 'samples': checks, 'passed': all(r['passed'] for r in checks)}
if not all(c['passed'] for c in focused.values()):
    env = read(out / 'native-control/application/environment.json')
    assert all(c['source_commit'] == env['source_commit'] for c in focused.values())
    for name, digest in env['source_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    native = read(out / 'native-functional/application/native-visibility-touch.json')
    assert native['hidden_end']['hidden'] and native['hidden_end']['frame_count'] == 0
    assert native['touch_drag_changed_style'] and not native['picker_animations']
    care = read(out / 'care/live-plant-care.json')
    assert [r['kind'] for r in care['results']] == ['fern', 'mushroom', 'succulent']
    assert all(r['care_persisted'] and r['wet_soil_visible'] for r in care['results'])
    for path in ['native-functional/application/environment.json', 'care/application/environment.json']:
        evidence_env = read(out / path)
        assert evidence_env['source_commit'] == env['source_commit'] and evidence_env['source_sha256'] == env['source_sha256']
    result = {'status': 'blocked', 'source_commit': env['source_commit'], 'primary_samples': 0,
              'native_hidden_touch_keyboard': 'lcp-unblock/native-functional/application/native-visibility-touch.json',
              'care_verification': 'lcp-unblock/care/live-plant-care.json',
              'static_picker_verified': True,
              'reason': 'Final-source focused native frame/callback prerequisite failed. Full20 matrix intentionally not started.',
              'avatar_callback_checks': focused, 'budgets': {'frame_p95_ms': 33, 'owned_callback_ms': 50},
              'previous_primary_matrix': 'lcp-unblock/pre-motion-fix/application/summary.json',
              'previous_primary_source': '00d76bc', 'previous_primary_applies_to_final_source': False,
              'visual_equivalence': 'lcp-unblock/artwork-equivalence.json',
              'tests': 'lcp-unblock/validation-tests.txt', 'functional': 'lcp-unblock/static-functional/tests.txt',
              'limits': ['Native LoAF attributes wall duration to scripts in long frames; zero means no owned script reported, not zero CPU.',
                         'Several over-budget scripts report zero forced layout. This does not establish scheduling or GC as the cause; the failures remain unresolved.',
                         'All cohorts retained; no thresholds relaxed or favorable samples substituted.'],
              'next_step': 'Resolve or isolate the focused native callback/frame failures before rerunning the original20 matrix; do not start3A.'}
    (out / 'assessment.json').write_text(json.dumps(result, indent=2))
    (root / 'assessment.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(0)
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
callback_checks = {}
for kind in ['fern', 'mushroom', 'succulent']:
    data = read(out / f'native-control/{kind}/native-control.json')
    assert data['source_commit'] == env['source_commit'] and data['after_only'] and data['kind'] == kind
    samples = data['samples']
    assert len(samples) == 5
    checks = []
    for row in samples:
        assert row['kind'] == kind and row['mature'] and row['cpu'] == 4 and row['seconds'] == 30 and row['version'] == 'after'
        calls = [s['duration'] for l in row['native_long_animation_frames'] for s in l['scripts'] if '/static/js/avatars.js' in s['sourceURL'] or '/static/js/avatar-audio.js' in s['sourceURL']]
        checks.append({'run': row['run'], 'frame_p95_ms': row['scenario']['frame_p95_ms'], 'max_reported_owned_script_ms': max(calls, default=0),
                       'passed': not row['errors'] and row['scenario']['frame_p95_ms'] <= 33 and max(calls, default=0) <= 50})
    callback_checks[kind] = {'samples': checks, 'passed': all(r['passed'] for r in checks),
        'method': 'Native LoAF, no API wrappers, tracing, callback clocks or stacks. Zero means no owned script reported in a long frame, not zero CPU.'}
native = read(out / 'application/native-visibility-touch.json')
assert native['hidden_end']['hidden'] and native['hidden_end']['frame_count'] == 0
assert native['touch_drag_changed_style'] and not native['picker_animations']
care = read(out / 'live-plant-care.json')
assert len(care['results']) == 3 and all(r['care_persisted'] and r['wet_soil_visible'] for r in care['results'])
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
                     'Existing selected-companion offscreen motion, chase/idle/roam timers and remount listeners remain separate release blockers; static picker policy is verified.',
                     'Native controls on 00d76bc exposed a new mushroom chase callback60.4ms (41.6ms forced layout). That genuine failure and all failed instrumented traces remain in pre-motion-fix/.'],
          'next_step': '3A: dog, rabbit, bird and turtle' if passed else 'Continue investigating the failing gate before 3A.'}
(out / 'assessment.json').write_text(json.dumps(result, indent=2))
print(json.dumps({'status': result['status'], 'historical_gates': comparison['gates'], 'matched_cold_desktop': matched, 'secondary_passed': result['secondary_gates_passed']}, indent=2))
