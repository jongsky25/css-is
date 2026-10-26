"""Align natural GC with diagnostic checkpoints; never acceptance accounting."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path


def summarize(events, records):
    forced_flags = [e['args']['forced'] for e in events if 'forced' in e.get('args', {})]
    if any(forced_flags):
        raise ValueError('Forced collection invalidates natural-collection diagnosis')
    clocks = [e for e in events if e.get('name') == 'clock_sync']
    markers = {e['args']['sync_id']: e['ts'] for e in clocks}
    labels = [r['checkpoint'] for r in records]
    if len(markers) != len(clocks) or len(set(labels)) != len(labels) or set(markers) != set(labels):
        raise ValueError('Missing or duplicate checkpoint clock markers')
    commits = [e for e in events if e.get('name') == 'CommitLoad']
    app_pids = {e['pid'] for e in commits if e['args']['data'].get('url', '').startswith('http://127.0.0.1:')}
    if len(app_pids) != 1:
        raise ValueError('Expected one app renderer; role mapping needs explicit review')
    pid = next(iter(app_pids)); last = 0; points = []
    for record in records:
        ts = markers[record['checkpoint']]
        if ts <= last:
            raise ValueError('Nonchronological checkpoints')
        snap = record['snapshot']
        detail = next(d for d in snap['renderer_memory_detail'] if d['pid'] == pid)
        interval = [e for e in events if e['pid'] == pid and last < e.get('ts', 0) <= ts]
        major = [e for e in interval if e.get('name') == 'MajorGC']
        cpp = [e for e in interval if 'cppgc' in e.get('cat', '').lower()]
        points.append({'checkpoint':record['checkpoint'], 'trace_timestamp_us':ts,
            'rss_bytes':snap['renderer_rss_sum_bytes'], 'app_renderer_rss_bytes':detail['status']['VmRSS'],
            'other_renderer_rss_bytes':snap['renderer_rss_sum_bytes'] - detail['status']['VmRSS'],
            'js_heap_bytes':snap['js_heap_bytes'], 'documents':snap['dom_counters']['documents'],
            'nodes':snap['dom_counters']['nodes'], 'major_gc_since_previous':major,
            'cpp_gc_events_since_previous':dict(collections.Counter(e['name'] for e in cpp))})
        last = ts
    return {'app_pid':pid, 'points':points, 'forced_collection_events':sum(forced_flags),
        'explicit_natural_collection_flags':len(forced_flags),
        'cpp_gc_event_count':sum('cppgc' in e.get('cat', '').lower() for e in events)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path)
    args = parser.parse_args(); results = []
    for folder in sorted(args.root.glob('[0-3]-*')):
        trace = folder / 'collection-trace.json.gz'
        events = json.load(gzip.open(trace, 'rt'))['traceEvents']
        records = json.loads((folder / 'checkpoints.json').read_text())
        result = summarize(events, records)
        result.update(cohort=folder.name, trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
        results.append(result)
        retained = [e for e in events if e.get('name') in ('MajorGC','MinorGC','CommitLoad','clock_sync') or 'cppgc' in e.get('cat','').lower()]
        with gzip.open(folder / 'collection-events.json.gz', 'wt') as stream:
            json.dump(retained, stream)
        print(folder.name, 'cppgc events', result['cpp_gc_event_count'])
    (args.root / 'collection-summary.json').write_text(json.dumps({'acceptance':False,'cohorts':results},indent=2)+'\n')


if __name__ == '__main__':
    main()
