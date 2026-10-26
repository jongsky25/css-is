"""Offline timing analysis of the four frozen residency cohorts; no new samples."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

from scripts.avatar_baseline.analyze_residency import summarize


def completed_major(events, pid, start, end):
    """Use event END, never its start, when assigning a completed collection."""
    result = []
    for e in events:
        if e.get('pid') != pid or e.get('name') != 'MajorGC':
            continue
        if e.get('ph') != 'X' or e.get('dur', -1) < 0:
            raise ValueError('Unsupported MajorGC duration format')
        finish = e['ts'] + e['dur']
        if start < finish <= end:
            result.append({**e, 'end_timestamp_us': finish})
    return sorted(result, key=lambda e: e['end_timestamp_us'])


def analyze(events, records):
    base = summarize(events, records)
    pid = base['app_pid']
    output = []
    previous = None
    for index, point in enumerate(base['records']):
        end = point['trace_timestamp_us']
        start = previous['trace_timestamp_us'] if previous else 0
        completed = completed_major(events, pid, start, end)
        history = completed_major(events, pid, 0, end)
        latest = history[-1] if history else None
        if point['checkpoint'].startswith('navigation_'):
            heap = point['app_allocator_bytes']['blink_gc/main/heap']
            output.append({
                'checkpoint': point['checkpoint'],
                'interval_start_checkpoint': previous['checkpoint'],
                'interval_ms': (end-start)/1000,
                'completed_major_gc': completed,
                'ms_since_last_completed_major_gc': (end-latest['end_timestamp_us'])/1000 if latest else None,
                'documents': point['documents'], 'nodes': point['nodes'],
                'document_delta': point['documents']-previous['documents'],
                'rss_bytes': point['rss_bytes'],
                'rss_delta_bytes': point['rss_bytes']-previous['rss_bytes'],
                'app_renderer_rss_bytes': point['app_renderer_rss_bytes'],
                'js_heap_bytes': point['js_heap_bytes'],
                'blink_heap_attributes_bytes': heap,
                'dump_delay_after_marker_ms': (point['dump_timestamp_us']-end)/1000,
                'major_gc_completing_between_marker_and_dump': completed_major(events,pid,end,point['dump_timestamp_us']),
                'post_dump_documents': records[index]['after_dump_snapshot']['dom_counters']['documents'],
                'post_dump_rss_bytes': point['after_dump_rss_bytes'],
            })
        previous = point
    return {'app_pid': pid, 'navigation': output}


def run(root):
    manifest = json.loads((root/'manifest.json').read_text())
    expected = ['0-original.zip','1-current.zip','2-current.zip','3-original.zip']
    if sorted(a['name'] for a in manifest['archives']) != expected:
        raise ValueError('Incomplete cohort manifest')
    results = []
    checked = 0
    for archive in manifest['archives']:
        raw = (root/archive['name']).read_bytes()
        if len(raw) != archive['bytes'] or hashlib.sha256(raw).hexdigest() != archive['sha256']:
            raise ValueError('Archive identity mismatch')
        with zipfile.ZipFile(root/archive['name']) as z:
            if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(archive['files']):
                raise ValueError('Archive inventory mismatch')
            for name, digest in archive['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest() != digest:
                    raise ValueError('Member identity mismatch')
                checked += 1
            provenance = json.loads(z.read('provenance.json'))
            if provenance['trace_completion'].get('dataLossOccurred') or not provenance['native_allocator_dumps']:
                raise ValueError('Invalid trace provenance')
            events = json.loads(gzip.decompress(z.read('collection-trace.json.gz')))['traceEvents']
            records = json.loads(z.read('checkpoints.json'))
            if len(records) != 13:
                raise ValueError('Incomplete checkpoints')
            result = analyze(events, records)
            result.update(cohort=archive['name'][:-4], archive_sha256=archive['sha256'])
            results.append(result)
    return {'acceptance': False, 'new_measurements': 0, 'verified_archive_members': checked,
            'cohorts': results,
            'limits': 'Historical instrumented cohorts only. GC completion refers to a V8 MajorGC duration, not whole Blink sweep completion. Snapshots, markers and dumps are sequential. Allocated objects may include garbage; heap capacity is not RSS. No allocator subtraction or acceptance substitution.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.write_text(json.dumps(run(args.root), indent=2)+'\n')
