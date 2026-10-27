"""Recover exact Blink type histograms omitted by the earlier family summary.

Endpoint allocated-object inventory only, not resident bytes or retaining paths.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import zipfile

from scripts.avatar_baseline.analyze_reader_retention import run as verify_comparison

PREFIX = 'blink_objects/blink_gc/main/'


def scalar(attrs, name, units):
    value = attrs.get(name)
    if not value or value.get('type') != 'scalar' or value.get('units') != units:
        raise ValueError('Missing or invalid scalar: '+name)
    if not re.fullmatch(r'[0-9a-fA-F]+', value['value']):
        raise ValueError('Invalid hexadecimal scalar')
    return int(value['value'], 16)


def type_name(label):
    match = re.fullmatch(r'(.+) \(0x([0-9a-fA-F]+)\)', label)
    if not match:
        raise ValueError('Missing type identity')
    return match[1]


def extract(allocators):
    global_types = {}
    page_types = defaultdict(lambda: {'bytes': 0, 'count': 0})
    for path, info in allocators.items():
        attrs = info.get('attrs', {})
        if path.startswith(PREFIX):
            label = path[len(PREFIX):]
            type_name(label)
            global_types[label] = {'bytes': scalar(attrs, 'allocated_objects_size', 'bytes'),
                                   'count': scalar(attrs, 'object_count', 'objects')}
        elif path.startswith('blink_gc/main/heap/') and '/types/' in path:
            label = path.split('/types/', 1)[1]
            type_name(label)
            page_types[label]['bytes'] += scalar(attrs, 'allocated_objects_size', 'bytes')
            page_types[label]['count'] += scalar(attrs, 'object_count', 'objects')
    if not global_types:
        raise ValueError('No object type inventory')
    if set(page_types) - set(global_types):
        raise ValueError('Page type absent from global inventory')
    for label, value in global_types.items():
        if value != page_types.get(label, {'bytes': 0, 'count': 0}):
            raise ValueError('Page/global type mismatch: '+label)
    heap = allocators['blink_gc/main/heap']['attrs']
    size = scalar(heap, 'allocated_objects_size', 'bytes')
    if sum(v['bytes'] for v in global_types.values()) != size:
        raise ValueError('Type inventory does not reconcile to heap objects')
    merged = defaultdict(lambda: {'allocated_bytes': 0, 'object_count': 0, 'labels': []})
    for label,v in global_types.items():
        row = merged[type_name(label)]
        row['allocated_bytes'] += v['bytes']
        row['object_count'] += v['count']
        row['labels'].append(label)
    return {'allocated_objects_bytes': size,
        'heap_committed_bytes': scalar(heap,'committed_size','bytes'),
        'heap_size_bytes': scalar(heap,'size','bytes'),
        'pooled_bytes': scalar(heap,'pooled_size','bytes'),
        'raw_type_count': len(global_types), 'named_type_count': len(merged),
        'types': dict(sorted(merged.items())),
        'type_page_and_heap_totals_match': True}


def bounded_allocators(events, pid, dump_id, dump_ts):
    allocators = {}
    for e in events:
        if e.get('pid') != pid or e.get('ph') != 'v' or e.get('id') != dump_id or e.get('ts') != dump_ts:
            continue
        fragment = e.get('args',{}).get('dumps',{}).get('allocators',{})
        if allocators.keys() & fragment.keys():
            raise ValueError('Overlapping dump fragments')
        allocators.update(fragment)
    if not allocators:
        raise ValueError('Missing identified dump')
    return allocators


def compare(left, right):
    names = left['types'].keys() | right['types'].keys()
    rows = []
    for name in names:
        a,b = left['types'].get(name,{}),right['types'].get(name,{})
        rows.append({'type': name,
            'allocated_bytes_delta': b.get('allocated_bytes',0)-a.get('allocated_bytes',0),
            'object_count_delta': b.get('object_count',0)-a.get('object_count',0)})
    rows.sort(key=lambda x:(-x['allocated_bytes_delta'],x['type']))
    total = right['allocated_objects_bytes']-left['allocated_objects_bytes']
    if sum(v['allocated_bytes_delta'] for v in rows) != total:
        raise ValueError('Type difference reconciliation failed')
    return {'left': left['index'], 'right': right['index'],
        'allocated_objects_delta_bytes': total,
        'pooled_delta_bytes': right['pooled_bytes']-left['pooled_bytes'],
        'heap_size_delta_bytes': right['heap_size_bytes']-left['heap_size_bytes'],
        'type_differences': rows}


def run(root):
    # Re-audit frozen identities/captures; do not trust a self-described dump PID.
    checked = verify_comparison(root)
    results = []
    with zipfile.ZipFile(root/'comparison-evidence.zip') as z:
        for slot in checked['cohorts']:
            prefix = f"{slot['index']:02d}-{slot['arm']}/"
            raw = z.read(prefix+'trace-2.json.gz')
            events = json.loads(gzip.decompress(raw))['traceEvents']
            endpoint = slot['endpoint']
            allocators = bounded_allocators(events,slot['pid'],endpoint['trace_id'],endpoint['trace_ts'])
            row = extract(allocators)
            row.update(index=slot['index'], arm=slot['arm'], app_pid=slot['pid'],
                       trace_sha256=hashlib.sha256(raw).hexdigest(),
                       dump_id=endpoint['trace_id'],dump_ts=endpoint['trace_ts'])
            results.append(row)
    pairs = [(0,1),(3,2),(5,4),(6,7),(0,3),(1,2),(5,6),(4,7)]
    return {'acceptance': False,'new_browser_measurements': 0,
        'archive_sha256': checked['archive_sha256'], 'archive_members_verified': checked['archive_members_verified'],
        'cohorts': results,'comparisons': [compare(results[a],results[b]) for a,b in pairs],
        'limits': 'Detailed endpoint dumps finish pending sweeping. Types are allocated objects, possibly garbage, not reachable owners or RSS. Page/type/global views overlap; only global type rows are summed. Pooled pages have no current object-type assignment. Type IDs vary across processes; identical names are merged, raw labels retained. No source effect inferred from unstable controls.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = run(args.root)
    with gzip.open(args.out,'wt') as f: json.dump(result,f)
    print(json.dumps({'cohorts':len(result['cohorts']),'all_type_totals_reconciled':True,
                      'new_browser_measurements':0}))
