"""Independent source, coverage and overhead audit for component-order calibration."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.avatar_baseline.run_snapshot_order import HARNESS, BACKEND, BUILD, digest
from scripts.avatar_baseline.analyze_cat_gradients import REFS
from scripts.avatar_baseline.memory_audit import SCENARIOS
from scripts.avatar_baseline.analyze_paired_variance import required_sources, source
from scripts.avatar_baseline.analyze_source_isolation import points
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds, mapped, selected_events, position


def validate_calls(snapshot):
    calls = snapshot['calls']
    details = snapshot['snapshot']['renderer_memory_detail']
    expected = ['page.evaluate', 'cdp:SystemInfo.getProcessInfo']
    expected += [f"/proc/{r['pid']}/status" for r in details]
    for r in details:
        expected += [f"/proc/{r['pid']}/status", f"/proc/{r['pid']}/smaps_rollup"]
    expected += ['cdp:Runtime.getHeapUsage', 'cdp:Memory.getDOMCounters', 'cdp:Runtime.evaluate']
    if [c['call'] for c in calls] != expected:
        raise ValueError('Missing, reordered or additional snapshot calls')
    lower, upper = snapshot['interval_ns']
    for c in calls:
        if c.get('error_type') or not lower <= c['begin_ns'] <= c['end_ns'] <= upper:
            raise ValueError('Invalid component bracket')
        lower = c['end_ns']


def inspect(folder, p, rows):
    points(rows, 1)
    snapshots = p['snapshots']; nav = p['navigations']; probe = p['mode'] == 'probe'
    if p['protocol'] != 'snapshot-order-v1' or p['acceptance'] is not False or p['forced_gc'] is not False:
        raise ValueError('Invalid capture protocol')
    if len(snapshots) != 13 or [n['mount'] for n in nav] != list(range(1, 21)):
        raise ValueError('Incomplete workload')
    for i, s in enumerate(snapshots):
        if s['index'] != i or s['interval_ns'][0] > s['interval_ns'][1]:
            raise ValueError('Invalid snapshot index or bracket')
        if probe:
            validate_calls(s)
        elif s['calls']:
            raise ValueError('Instrumented control')
    expected_scenarios = list(SCENARIOS)
    actual_scenarios = rows[0]['scenarios']
    if set(expected_scenarios) != set(actual_scenarios):
        raise ValueError('Unexpected scenario inventory')
    for s, key in zip(snapshots[:8], expected_scenarios, strict=True):
        if s['snapshot'] != actual_scenarios[key]:
            raise ValueError('Scenario snapshot rewritten')
    for sealed, actual in zip(snapshots[8:], rows[0]['navigation_trend'], strict=True):
        if actual != {'mount': sealed['mount'], **sealed['snapshot']}:
            raise ValueError('Navigation snapshot rewritten')
    start, end = p['navigation_begin_ns'], p['navigation_end_ns']
    if not start < end or [s['mount'] for s in snapshots[8:]] != [1, 5, 10, 15, 20]:
        raise ValueError('Invalid navigation window/checkpoints')
    for n in nav:
        if not start <= n['begin_ns'] <= n['goto_end_ns'] <= end:
            raise ValueError('Navigation outside measurement')
    for s in snapshots[8:]:
        if not start <= s['interval_ns'][0] <= s['interval_ns'][1] <= end:
            raise ValueError('Snapshot outside measurement')
    pauses = [s['interval_ns'][1] - s['interval_ns'][0] for s in snapshots[8:]]
    # Conservative bound includes underlying snapshot work, not just instrumentation.
    setup = p.get('trace_setup_ns', 0)
    result = {'mode': p['mode'], 'navigation_ms': (end-start)/1e6,
              'observation_fraction_bound': (sum(pauses)+setup)/(end-start),
              'max_observation_ms': max([setup, *pauses])/1e6, 'checkpoints': []}
    if not probe:
        return result
    if p['completion'].get('dataLossOccurred') or not end < p['transfer_begin_ns'] <= p['transfer_end_ns']:
        raise ValueError('Trace loss or transfer during workload')
    events = json.load(gzip.open(folder / 'trace.json.gz', 'rt'))['traceEvents']
    if any(e.get('args', {}).get('forced') or e.get('args', {}).get('dumps') for e in events):
        raise ValueError('Forced GC or memory dump')
    pids = {e['pid'] for e in events if e.get('name') == 'CommitLoad'
            and e.get('args', {}).get('data', {}).get('url', '').startswith('http://127.0.0.1:')}
    if len(pids) != 1:
        raise ValueError('Ambiguous app renderer')
    pid = next(iter(pids)); clock = clock_bounds(p, events); gc = selected_events(events, pid)
    if not any(e['name'] == 'MajorGC' for e in gc) or not any('Sweep' in e['name'] for e in gc):
        raise ValueError('Natural collection/sweeping coverage absent')
    result.update(app_pid=pid, event_count=len(events), gc_event_count=len(gc), clock=clock)
    for s in snapshots[8:]:
        if sum(d['pid'] == pid for d in s['snapshot']['renderer_memory_detail']) != 1:
            raise ValueError('App PID missing from checkpoint')
        components = []
        for c in s['calls']:
            bounds = mapped([c['begin_ns'], c['end_ns']], clock)
            covered = clock['coverage_us'][0] <= bounds[0] <= bounds[1] <= clock['coverage_us'][1]
            components.append({**c, 'trace_bounds_us': bounds, 'covered': covered,
                               'gc_overlap': [e for e in gc if position(e, bounds) == 'overlap_or_uncertain']})
        result['checkpoints'].append({'mount': s['mount'], 'components': components})
    if any(not c['covered'] for s in result['checkpoints'] if s['mount'] in (5, 10) for c in s['components']):
        raise ValueError('Failing-checkpoint trace coverage incomplete')
    return result


def gate(cohorts):
    errors = []
    if len(cohorts) != 4 or any(c.get('error') for c in cohorts):
        return ['Four intact calibration slots required']
    for i, c in enumerate(cohorts):
        if c['observation_fraction_bound'] > .05 or c['max_observation_ms'] > 250:
            errors.append(f'Slot {i}: observation bound exceeds 5% or 250ms')
    durations = [c['navigation_ms'] for c in cohorts]
    if abs(durations[3] - durations[0]) > durations[0] * .2:
        errors.append('Controls vary more than 20%')
    for control, probe in [(0, 1), (3, 2)]:
        if durations[probe] > durations[control] * 1.2:
            errors.append(f'Probe/control exceeds 1.20: {control}/{probe}')
    return errors


def audit(root, repo):
    result = {'acceptance': False, 'status': 'inconclusive', 'errors': [], 'cohorts': [],
              'source_hashes_verified': 0, 'files_verified': 0}
    try:
        plan = json.loads((root / 'experiment.json').read_text()); head = plan['harness_commit']
        if (plan['protocol'] != 'snapshot-order-v1' or plan['phase'] != 'calibration' or plan['acceptance'] is not False
            or plan['source_commit'] != REFS['current'] or plan['build_id'] != BUILD or plan['seconds'] != 30
            or plan['order'] != ['control', 'probe', 'probe', 'control'] or len(plan['cohorts']) != 4):
            raise ValueError('Invalid frozen schedule')
        for name in HARNESS:
            if (root / 'harness' / name).read_bytes() != source(repo, head, name):
                raise ValueError('Harness identity mismatch')
        for index, row in enumerate(plan['cohorts']):
            if row['index'] != index or row['mode'] != plan['order'][index]:
                raise ValueError('Invalid cohort identity')
            folder = root / f"{index}-{row['mode']}"
            try:
                required = {'environment.json', 'backend-source.json', 'runner.txt', 'junit.xml',
                            'False-warm.json', 'order-provenance.json'}
                if row['mode'] == 'probe':
                    required.add('trace.json.gz')
                if row['exit_code'] or not required <= row['files_sha256'].keys():
                    raise ValueError('Failed or incomplete cohort')
                for name, value in row['files_sha256'].items():
                    if Path(name).name != name or digest(folder / name) != value:
                        raise ValueError('Evidence hash mismatch')
                    result['files_verified'] += 1
                env = json.loads((folder / 'environment.json').read_text())
                if env['source_commit'] != REFS['current'] or env['chromium'] != '156.0.8078.47':
                    raise ValueError('Source/browser mismatch')
                expected = required_sources(repo, REFS['current'])
                if set(env['source_sha256']) != expected:
                    raise ValueError('Incomplete source inventory')
                backend = json.loads((folder / 'backend-source.json').read_text())
                if set(backend) != set(BACKEND):
                    raise ValueError('Incomplete backend inventory')
                for name, value in {**env['source_sha256'], **backend}.items():
                    ref = head if name in HARNESS else REFS['current']
                    if hashlib.sha256(source(repo, ref, name)).hexdigest() != value:
                        raise ValueError('Source hash mismatch: ' + name)
                    result['source_hashes_verified'] += 1
                p = json.loads((folder / 'order-provenance.json').read_text())
                if p['mode'] != row['mode']:
                    raise ValueError('Mode mismatch')
                inspected = inspect(folder, p, json.loads((folder / 'False-warm.json').read_text()))
                result['cohorts'].append({'index': index, **inspected})
            except (ValueError, OSError, KeyError, TypeError) as error:
                result['cohorts'].append({'index': index, 'error': repr(error)})
        result['errors'] = gate(result['cohorts'])
        result['status'] = 'calibration_failed' if result['errors'] else 'calibration_passed'
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        result['errors'].append(repr(error))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path); parser.add_argument('--out', required=True, type=Path)
    a = parser.parse_args(); result = audit(a.root, Path(__file__).resolve().parents[2])
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cohorts'}))
