"""Fail-closed audit of light capture, overhead calibration, and fixed comparisons."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

from scripts.avatar_baseline.analyze_paired_variance import REFS, expected_fixture, required_sources, slot_points, source
from scripts.avatar_baseline.analyze_navigation_residency import join_dump

PROBE = 'tests/test_avatar_navigation_light_browser.py'
HARNESS = ['tests/test_avatar_baseline_browser.py', 'tests/avatar_browser_fixture.py', PROBE]
BLOCKS = [['original', 'current', 'current', 'original'], ['current', 'original', 'original', 'current']]
BUDGET = 10 * 2**20


def calibration_gate(cohorts):
    errors = []
    if len(cohorts) != 4 or any(c['status'] != 'valid_capture' for c in cohorts):
        return ['Require four intact calibration captures']
    for c in cohorts:
        if c['overhead_fraction'] > .05 or c['max_rotation_ms'] > 250:
            errors.append(f"Slot {c['index']}: explicit trace overhead exceeds 5% or 250ms")
    durations = [c['navigation_ms'] for c in cohorts]
    for control, traced in [(0, 1), (3, 2)]:
        if durations[traced] > durations[control] * 1.2:
            errors.append(f'Trace/control navigation duration exceeds 1.20: {control}/{traced}')
    if abs(durations[3] - durations[0]) > durations[0] * .2:
        errors.append('Control navigation duration varies more than 20%')
    return errors


def clocks(events, names):
    found = [e for e in events if e.get('name') == 'clock_sync']
    if len(found) != len(names) or {e['args']['sync_id'] for e in found} != set(names):
        raise ValueError('Missing or duplicate clock marker')
    return {e['args']['sync_id']: e['ts'] for e in found}


def inspect_capture(folder, provenance, raw):
    p = provenance
    mode = p['mode']
    if p['protocol'] not in ('navigation-light-v3', 'navigation-light-v4') or p['acceptance'] is not False or p['forced_gc'] is not False:
        raise ValueError('Invalid capture protocol')
    if p['snapshots'] != 13 or p['mount'] != 20 or [c['mount'] for c in p['checkpoints']] != [1, 5, 10, 15, 20]:
        raise ValueError('Incomplete navigation')
    if len(raw) != 1:
        raise ValueError('Expected one workload')
    for sealed, actual in zip(p['checkpoints'], raw[0]['navigation_trend'], strict=True):
        if actual != {'mount': sealed['mount'], **sealed['snapshot']}:
            raise ValueError('Measured snapshot rewritten')
        if sealed['interval_ns'][1] > p['navigation_end_ns']:
            raise ValueError('Checkpoint outside measurement')
    nav_segments = 4 if p['protocol'] == 'navigation-light-v3' else 2
    expected_rotations = [0, 5, 10, 15] if nav_segments == 4 else [0, 10]
    if [r['mount'] for r in p['rotations']] != expected_rotations:
        raise ValueError('Invalid rotation schedule')
    for r in p['rotations']:
        if not p['navigation_begin_ns'] <= r['begin_ns'] <= r['end_ns'] <= p['navigation_end_ns']:
            raise ValueError('Rotation outside measurement')
    total = p['navigation_end_ns'] - p['navigation_begin_ns']
    if total <= 0:
        raise ValueError('Invalid navigation duration')
    rotations = [r['end_ns'] - r['begin_ns'] for r in p['rotations']]
    result = {'navigation_ms': total / 1e6, 'overhead_fraction': sum(rotations) / total,
              'max_rotation_ms': max(rotations) / 1e6, 'trace_segments': [], 'endpoint': None}
    if len(p['segments']) != (nav_segments + 1 if mode == 'trace' else 0):
        raise ValueError('Incorrect segment count')
    if any(s['completion'].get('dataLossOccurred') for s in p['segments']):
        raise ValueError('Trace data loss; sample retained, not replaced')
    all_events = []
    anchors = []
    pids = set()
    windows = []
    endpoint_events = None
    for index, segment in enumerate(p['segments']):
        if segment['number'] != index or segment['trace_file'] != f'trace-{index}.json.gz':
            raise ValueError('Segment identity mismatch')
        events = json.load(gzip.open(folder / segment['trace_file'], 'rt'))['traceEvents']
        if any(e.get('args', {}).get('forced') for e in events):
            raise ValueError('Forced collection flag')
        names = [f'segment-{index}-{side}' for side in ['before', 'after']]
        if index == nav_segments:
            names += ['endpoint-before', 'endpoint-after']
        markers = clocks(events, names)
        if markers[names[1]] <= markers[names[0]]:
            raise ValueError('Nonchronological trace')
        if index < nav_segments:
            if any(e.get('args', {}).get('dumps') for e in events):
                raise ValueError('Allocator dump inside measured workload')
            pids.update(e['pid'] for e in events if e.get('name') == 'CommitLoad' and
                        e.get('args', {}).get('data', {}).get('url', '').startswith('http://127.0.0.1:'))
            all_events.extend(events)
            windows.append([markers[names[0]], markers[names[1]]])
            for side in ['before', 'after']:
                host = segment[side]
                if host['end_ns'] < host['begin_ns']:
                    raise ValueError('Invalid marker host interval')
                anchors.append({'host_us': (host['begin_ns'] + host['end_ns']) / 2000,
                                'trace_us': markers[host['name']],
                                'uncertainty_us': (host['end_ns'] - host['begin_ns']) / 2000})
        else:
            if not p['navigation_end_ns'] < segment['start_ns'] < p['endpoint_before']['begin_ns'] <= p['endpoint_before']['end_ns'] < p['endpoint_after']['begin_ns'] <= p['endpoint_after']['end_ns']:
                raise ValueError('Endpoint dump precedes sealed measurements')
            if not p['endpoint_request']['success']:
                raise ValueError('Endpoint request failed')
            endpoint_events = (events, markers)
        result['trace_segments'].append({'index': index, 'event_count': len(events),
            'bytes': (folder / segment['trace_file']).stat().st_size, 'data_loss': False})
    if mode == 'trace':
        if len(pids) != 1:
            raise ValueError('Ambiguous app renderer')
        pid = next(iter(pids))
        events, markers = endpoint_events
        result['endpoint'] = join_dump(events, pid, markers['endpoint-before'], markers['endpoint-after'])
    else:
        # No tracing means no authoritative page/PID association. Keep all PIDs.
        pid = None
    result['app_pid'] = pid
    samples = p['samples']
    if len(samples) < 2:
        raise ValueError('Missing status samples')
    for i, s in enumerate(samples):
        if s['end_ns'] < s['begin_ns'] or (i and s['begin_ns'] <= samples[i-1]['end_ns']):
            raise ValueError('Invalid status intervals')
    result['status_sample_count'] = len(samples)
    gaps = [(b['begin_ns'] - a['begin_ns']) / 1e6 for a, b in zip(samples, samples[1:])]
    result['max_poll_gap_ms'] = max(gaps)
    result['median_poll_gap_ms'] = statistics.median(gaps)
    result['rss_drops_at_least_5_mib'] = []
    result['minimum_anonymous_step_bytes'] = None
    if pid is not None:
        for checkpoint in p['checkpoints']:
            if len([d for d in checkpoint['snapshot']['renderer_memory_detail'] if d['pid'] == pid]) != 1:
                raise ValueError('App PID absent from checkpoint')
        previous = None
        anon = []
        for s in samples:
            rows = [d for d in s['renderers'] if d['pid'] == pid]
            if len(rows) != 1:
                raise ValueError('App PID absent or duplicated in status poll')
            host = (s['begin_ns'] + s['end_ns']) / 2000
            anchor = min(anchors, key=lambda a: abs(a['host_us'] - host))
            estimate = anchor['trace_us'] + host - anchor['host_us']
            uncertainty = anchor['uncertainty_us'] + (s['end_ns'] - s['begin_ns']) / 2000
            point = {'trace_us': estimate, 'uncertainty_us': uncertainty, 'status': rows[0]['status'],
                     'begin_ns': s['begin_ns'], 'end_ns': s['end_ns']}
            if previous:
                delta = {k: point['status'][k] - previous['status'][k] for k in point['status']}
                anon.append(delta['RssAnon'])
                if delta['VmRSS'] <= -5 * 2**20:
                    low = previous['trace_us'] - previous['uncertainty_us']
                    high = estimate + uncertainty
                    # No correlation across a trace rotation gap.
                    covered = any(a <= low <= high <= b for a, b in windows)
                    gc = [e for e in all_events if e.get('pid') == pid and
                          ('gc' in e.get('cat', '').lower() or e.get('name') in ('MajorGC', 'MinorGC')) and
                          e.get('ts', 0) <= high and e.get('ts', 0) + e.get('dur', 0) >= low] if covered else []
                    result['rss_drops_at_least_5_mib'].append({'status_deltas': delta,
                        'host_interval_ns': [previous['begin_ns'], point['end_ns']],
                        'trace_interval_us': [low, high], 'trace_coverage': covered,
                        'overlapping_gc_events': gc})
            previous = point
        result['minimum_anonymous_step_bytes'] = min(anon)
    return result


def comparisons(cohorts, phase):
    pairs = [('calibration-forward', 0, 1), ('calibration-reverse', 3, 2),
             ('calibration-control', 0, 3), ('calibration-trace-repeat', 1, 2)] if phase == 'calibration' else [
             ('source-forward-0', 0, 1), ('source-reverse-0', 3, 2),
             ('original-control-0', 0, 3), ('current-control-0', 1, 2),
             ('source-reverse-1', 5, 4), ('source-forward-1', 6, 7),
             ('original-control-1', 5, 6), ('current-control-1', 4, 7)]
    output = []
    for name, left, right in pairs:
        a, b = cohorts[left], cohorts[right]
        row = {'name': name, 'left': left, 'right': right, 'acceptance': False, 'metrics': []}
        if a['status'] != 'valid_capture' or b['status'] != 'valid_capture':
            row['status'] = 'unavailable_invalid_capture'
        else:
            row['status'] = 'descriptive_only'
            for checkpoint in a['points']:
                for metric in ['renderer_rss_sum_bytes', 'js_heap_bytes']:
                    x = a['points'][checkpoint][metric]['samples'][0]
                    y = b['points'][checkpoint][metric]['samples'][0]
                    delta = y - x
                    row['metrics'].append({'checkpoint': checkpoint, 'metric': metric, 'delta_bytes': delta,
                        'renderer_counts_match': a['points'][checkpoint]['renderer_counts'] == b['points'][checkpoint]['renderer_counts'],
                        'within_10_mib': (delta <= BUDGET if name.startswith('source-') else abs(delta) <= BUDGET)})
        output.append(row)
    return output


def audit(root, repo, ref):
    result = {'status': 'inconclusive', 'acceptance': False, 'harness_commit': ref,
              'errors': [], 'cohorts': [], 'files_verified': 0, 'source_hashes_verified': 0}
    plan = json.loads((root / 'experiment.json').read_text())
    phase = plan['phase']
    blocks = [['current'] * 4] if phase == 'calibration' else BLOCKS
    if (phase not in ('calibration', 'comparison') or plan['protocol'] not in ('navigation-light-v3', 'navigation-light-v4') or
        plan['harness_commit'] != ref or plan['refs'] != REFS or plan['blocks'] != blocks or
        plan['acceptance'] is not False or plan['seconds'] != 30 or plan['samples_per_slot'] != 1 or
        plan['fixture_adapter'] != 'sample-ordinal-v1' or plan['browser'] != '156.0.8078.47' or
        plan['budget_bytes'] != BUDGET or len(plan['cohorts']) != 4 * len(blocks)):
        raise ValueError('Protocol identity mismatch')
    result['phase'] = phase
    result['protocol'] = plan['protocol']
    for name in HARNESS:
        if (root / 'harness' / name).read_bytes() != expected_fixture(repo, ref, name):
            raise ValueError('Harness identity mismatch')
    for i, entry in enumerate(plan['cohorts']):
        block, pos = divmod(i, 4)
        arm = blocks[block][pos]
        mode = 'control' if phase == 'calibration' and pos in (0, 3) else 'trace'
        row = {'index': i, 'arm': arm, 'mode': mode, 'status': 'invalid_capture'}
        result['cohorts'].append(row)
        try:
            if any(entry[k] != v for k, v in dict(index=i, block=block, position=pos, arm=arm, mode=mode).items()):
                raise ValueError('Slot identity mismatch')
            folder = root / f'{i:02d}-{arm}'
            required = {'environment.json', 'runner.txt', 'junit.xml', 'light-provenance.json', 'False-warm.json'}
            if mode == 'trace':
                required.update(f'trace-{n}.json.gz' for n in range(5 if plan['protocol'] == 'navigation-light-v3' else 3))
            if not required <= entry['files_sha256'].keys():
                raise ValueError('Missing required files')
            for name, digest in entry['files_sha256'].items():
                if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                    raise ValueError('Artifact hash mismatch')
                result['files_verified'] += 1
            env = json.loads((folder / 'environment.json').read_text())
            if env['source_commit'] != REFS[arm] or env['chromium'] != '156.0.8078.47' or set(env['source_sha256']) != required_sources(repo, REFS[arm]):
                raise ValueError('Source environment mismatch')
            for name, digest in env['source_sha256'].items():
                data = expected_fixture(repo, ref, name) if name in HARNESS else source(repo, REFS[arm], name)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError('Source hash mismatch')
                result['source_hashes_verified'] += 1
            p = json.loads((folder / 'light-provenance.json').read_text())
            if p['protocol'] != plan['protocol'] or p['mode'] != mode or p['probe_sha256'] != hashlib.sha256(source(repo, ref, PROBE)).hexdigest():
                raise ValueError('Probe hash mismatch')
            result['source_hashes_verified'] += 1
            raw_path = folder / 'False-warm.json'
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != entry['raw_sha256']:
                raise ValueError('Raw identity mismatch')
            raw = json.loads(raw_path.read_text())
            details = inspect_capture(folder, p, raw)
            if entry['exit_code'] != 0:
                raise ValueError('Workload failed; retained without replacement')
            row.update(details, points=slot_points(raw, block), status='valid_capture')
        except (OSError, ValueError, KeyError, TypeError) as error:
            row['reason'] = str(error)
            result['errors'].append(f'Slot {i}: {error}')
    result['comparisons'] = comparisons(result['cohorts'], phase)
    if phase == 'calibration':
        result['gate_errors'] = calibration_gate(result['cohorts'])
        if not result['errors'] and not result['gate_errors']:
            result['status'] = 'calibration_passed'
    elif not result['errors']:
        # Instrumentation limits remain checked for every comparison slot.
        result['gate_errors'] = [f"Slot {c['index']}: overhead exceeds calibration limits" for c in result['cohorts']
                                 if c['overhead_fraction'] > .05 or c['max_rotation_ms'] > 250]
        result['status'] = 'complete_diagnostic' if not result['gate_errors'] else 'overhead_gate_failed'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--harness-ref', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    ref = subprocess.check_output(['git', 'rev-parse', args.harness_ref], cwd=repo, text=True).strip()
    result = audit(args.root, repo, ref)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result.get(k) for k in ['status', 'errors', 'gate_errors', 'files_verified', 'source_hashes_verified']}))
    sys.exit(result['status'] not in ('calibration_passed', 'complete_diagnostic'))
