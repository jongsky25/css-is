"""Offline GC/retention timing for every slot of the frozen reader comparison.

No new browser measurements, inferred whole-sweep completions, or RSS subtraction.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import zipfile
import tempfile

from scripts.avatar_baseline.analyze_navigation_light import audit


def clock_bounds(segment, events):
    markers = {}
    for side in ('before', 'after'):
        host = segment[side]
        matching = [e for e in events if e.get('name') == 'clock_sync' and e.get('args', {}).get('sync_id') == host['name']]
        if len(matching) != 1 or host['end_ns'] < host['begin_ns']:
            raise ValueError('Invalid clock anchor')
        markers[side] = matching[0]['ts']
    # Envelope of both anchor request bounds, rather than exact midpoint clocks.
    low = min(markers[s] - segment[s]['end_ns']/1000 for s in markers)
    high = max(markers[s] - segment[s]['begin_ns']/1000 for s in markers)
    return {'offset_us': [low, high], 'coverage_us': [markers['before'], markers['after']]}


def mapped(interval, clock):
    if len(interval) != 2 or interval[1] < interval[0]:
        raise ValueError('Invalid host interval')
    return [interval[0]/1000 + clock['offset_us'][0],
            interval[1]/1000 + clock['offset_us'][1]]


def position(event, bounds):
    end = event['ts'] + event['dur']
    if end < bounds[0]:
        return 'before'
    if event['ts'] > bounds[1]:
        return 'after'
    return 'overlap_or_uncertain'


def selected_events(events, pid):
    selected = []
    for e in events:
        if e.get('pid') != pid or not (e.get('name') == 'MajorGC' or e.get('name', '').startswith('CppGC.')):
            continue
        if e.get('ph') == 'I':
            e = {**e, 'dur': 0, 'instant_event': True}
        elif e.get('ph') != 'X' or e.get('dur', -1) < 0:
            raise ValueError('Unsupported GC interval')
        if e.get('args', {}).get('forced'):
            raise ValueError('Forced collection')
        selected.append(e)
    return selected


def union_duration(events):
    """Wall-time union per thread, no nested event double counting."""
    threads = defaultdict(list)
    for e in events:
        threads[e['tid']].append((e['ts'], e['ts'] + e['dur']))
    result = {}
    for tid, intervals in threads.items():
        total = 0
        end = float('-inf')
        for a,b in sorted(intervals):
            total += max(0, b - max(a, end))
            end = max(end, b)
        result[str(tid)] = total
    return result


def analyze_slot(provenance, traces, pid):
    segments = []
    for index, events in enumerate(traces[:2]):
        s = provenance['segments'][index]
        if s['completion'].get('dataLossOccurred'):
            raise ValueError('Lost trace data')
        clock = clock_bounds(s, events)
        selected = selected_events(events, pid)
        epochs = defaultdict(list)
        for e in selected:
            if e['name'].startswith('CppGC.'):
                epochs[str(e['args'].get('epoch', 'unlabelled'))].append(e)
        summaries = []
        for epoch, es in epochs.items():
            sweep = [e for e in es if 'Sweep' in e['name']]
            summaries.append({'epoch': epoch, 'first_observed_us': min(e['ts'] for e in es),
                'last_observed_end_us': max(e['ts'] + e['dur'] for e in es),
                'events': dict(Counter(e['name'] for e in es)),
                'sweep_union_wall_us_by_thread': union_duration(sweep),
                'last_observed_sweep_end_us': max((e['ts']+e['dur'] for e in sweep), default=None),
                'whole_sweep_completion_known': False})
        segments.append({'index': index, **clock, 'epochs': summaries,
                         'major_gc': [e for e in selected if e['name'] == 'MajorGC'], '_events': selected})
    checkpoints = []
    for point in provenance['checkpoints']:
        # Assign by the fixed mount schedule; do not bridge trace rotation gaps.
        seg = segments[0 if point['mount'] <= 10 else 1]
        bounds = mapped(point['interval_ns'], seg)
        covered = seg['coverage_us'][0] <= bounds[0] <= bounds[1] <= seg['coverage_us'][1]
        before = [e for e in seg['major_gc'] if position(e, bounds) == 'before']
        latest = max(before, key=lambda e: e['ts'] + e['dur'], default=None)
        eend = latest['ts'] + latest['dur'] if latest else None
        snapshot = point['snapshot']
        statuses = [r['status'] for r in snapshot['renderer_memory_detail'] if r['pid'] == pid]
        if len(statuses) != 1:
            raise ValueError('App renderer identity missing')
        checkpoints.append({'mount': point['mount'], 'trace_bounds_us': bounds,
            'segment': seg['index'], 'fully_inside_trace': covered,
            'rss_bytes': snapshot['renderer_rss_sum_bytes'], 'app_status': statuses[0],
            'js_heap_bytes': snapshot['js_heap_bytes'], 'live_nodes': snapshot['nodes'],
            'dom_counters': snapshot['dom_counters'],
            'last_completed_major_gc_in_segment': latest,
            'ms_since_major_end_bounds': [(v-eend)/1000 for v in bounds] if eend is not None else None,
            'gc_overlapping_checkpoint_bounds': [e for e in seg['_events'] if position(e, bounds) == 'overlap_or_uncertain'],
            'cpp_sweep_events_after_checkpoint': sum('Sweep' in e['name'] and position(e, bounds) == 'after' for e in seg['_events'])})
    # Keep EVERY adjacent status interval. RSS drops may primarily be shared
    # pages; separately expose anonymous deltas and exact sweep event overlap.
    steps = []
    for a,b in zip(provenance['samples'], provenance['samples'][1:]):
        rows = [[r for r in p['renderers'] if r['pid'] == pid] for p in (a,b)]
        if any(len(r) != 1 for r in rows):
            raise ValueError('Status renderer identity missing')
        delta = {k: rows[1][0]['status'][k] - rows[0][0]['status'][k] for k in rows[0][0]['status']}
        matches = []
        for seg in segments:
            bounds = mapped([a['begin_ns'], b['end_ns']], seg)
            if seg['coverage_us'][0] <= bounds[0] <= bounds[1] <= seg['coverage_us'][1]:
                events = [e for e in seg['_events'] if position(e,bounds) == 'overlap_or_uncertain']
                matches.append({'segment': seg['index'], 'trace_bounds_us': bounds,
                    'major_gc_count': sum(e['name'] == 'MajorGC' for e in events),
                    'cpp_sweep_counts': dict(Counter(e['name'] for e in events if 'Sweep' in e['name'])),
                    'cpp_epochs': sorted({e['args']['epoch'] for e in events if 'epoch' in e.get('args', {})})})
        if len(matches) > 1:
            raise ValueError('Ambiguous segment coverage')
        steps.append({'host_bounds_ns': [a['begin_ns'], b['end_ns']], 'delta_bytes': delta,
                      'covered': bool(matches), 'overlap': matches[0] if matches else None})
    for seg in segments:
        del seg['_events']
    return {'pid': pid, 'segments': segments, 'checkpoints': checkpoints, 'status_steps': steps}


def run(root):
    archive = root / 'comparison-evidence.zip'
    manifest = json.loads((root / 'comparison-manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archive_sha256']:
        raise ValueError('Archive mismatch')
    assessment = json.loads((root / 'comparison.json').read_text())
    if assessment['status'] != 'complete_diagnostic' or assessment['errors'] or assessment['gate_errors']:
        raise ValueError('Requires qualified complete capture')
    results = []
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest['members_sha256']):
            raise ValueError('Archive inventory mismatch')
        for name in names:
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Unsafe archive member')
            if hashlib.sha256(z.read(name)).hexdigest() != manifest['members_sha256'][name]:
                raise ValueError('Member mismatch')
        with tempfile.TemporaryDirectory(prefix='reader-retention-audit-') as d:
            z.extractall(d)
            checked = audit(Path(d), Path(__file__).resolve().parents[2],
                '586f81c0af4071c6c976bf2978810e200814cb96', expected_refs={
                    'original': '1c964dcba2fa19de1eab077b00e0e5748d742554',
                    'current': 'cf363bfe547d5e23619eee28cdaf68bd4b6d7753'})
            if json.loads(json.dumps(checked)) != assessment:
                raise ValueError('Independent comparison audit differs')
        for slot in assessment['cohorts']:
            prefix = f"{slot['index']:02d}-{slot['arm']}/"
            p = json.loads(z.read(prefix+'light-provenance.json'))
            traces = [json.loads(gzip.decompress(z.read(prefix+f'trace-{i}.json.gz')))['traceEvents'] for i in range(2)]
            pids = {e['pid'] for es in traces for e in es if e.get('name') == 'CommitLoad' and e.get('args',{}).get('data',{}).get('url','').startswith('http://127.0.0.1:')}
            if pids != {slot['app_pid']}:
                raise ValueError('Trace renderer mismatch')
            result = analyze_slot(p,traces,slot['app_pid'])
            result.update(index=slot['index'], arm=slot['arm'], endpoint=slot['endpoint'])
            results.append(result)
    return {'acceptance': False, 'new_measurements': 0, 'archive_sha256': manifest['archive_sha256'],
        'assessment_sha256': hashlib.sha256((root/'comparison.json').read_bytes()).hexdigest(),
        'archive_members_verified': len(names), 'cohorts': results,
        'limits': 'Clock envelope assumes unit-rate monotonic clocks between anchors. Snapshot components are sequential within the bracket. No GC history across trace gaps; last observed sweep is not whole-epoch completion. Status/event overlap is correlation, not byte ownership. Endpoint dump is after workload, not checkpoint allocation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root)
    with gzip.open(args.out, 'wt') as f:
        json.dump(result, f)
    print(json.dumps({'slots': len(result['cohorts']), 'members_verified': result['archive_members_verified'], 'new_measurements': 0}))
