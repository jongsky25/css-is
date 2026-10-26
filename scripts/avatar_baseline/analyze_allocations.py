"""Summarize diagnostic native memory dumps without reinterpreting RSS gates."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def summarize(folder):
    path = Path(folder)
    trace_path = path/'memory-trace.json.gz'
    events = json.load(gzip.open(trace_path,'rt'))['traceEvents']
    requests = json.loads((path/'allocation-requests.json').read_text())
    groups = {}
    for event in events:
        if event.get('ph') == 'v' and event.get('args',{}).get('dumps',{}).get('allocators'):
            groups.setdefault(event['id'],[]).append(event)
    ordered = sorted(groups.values(), key=lambda events:min(e['ts'] for e in events))
    assert len(ordered) == len(requests), (len(ordered),len(requests))
    # Preserve the exact allocator fields consumed below, without unrelated VM maps.
    renderer_pids={p['pid'] for request in requests for p in request['snapshot']['renderer_memory_detail']}
    retained=[]
    for group in ordered:
        for event in group:
            if event['pid'] not in renderer_pids:continue
            copy={k:v for k,v in event.items() if k!='args'}
            copy['args']={'dumps':{'allocators':event['args']['dumps']['allocators']}}
            retained.append(copy)
    with gzip.open(path/'allocator-dumps.json.gz','wt') as stream:
        json.dump({'traceEvents':retained},stream,separators=(',',':'))
    records=[]
    for request, group in zip(requests,ordered):
        pids={p['pid'] for p in request['snapshot']['renderer_memory_detail']}
        allocators={}
        for event in group:
            if event['pid'] not in pids:continue
            for key,value in event['args']['dumps']['allocators'].items():
                # Stable allocator families only; full raw dumps remain in the trace.
                if key.count('/') > 3 or '__' in key or any(token in key for token in
                    ('tile_manager_', 'provider_', 'cache_', 'image_', 'resource_', 'segment_')):
                    continue
                fields=value.get('attrs',{})
                sizes={k:int(v['value'],16) for k,v in fields.items() if v.get('units')=='bytes'}
                if sizes:allocators.setdefault(key,[]).append({'pid':event['pid'],**sizes})
        records.append({'checkpoint':request['checkpoint'],'run':request['run'],
                        'trace_dump_id':group[0]['id'],'request_dump_id':request['request']['dumpGuid'],
                        'rss_bytes':request['snapshot']['renderer_rss_sum_bytes'],
                        'dom':request['snapshot']['dom_counters'],'allocators':allocators})
    return {'acceptance':False,'method':'Detailed allocation dumps in chronological request order. Renderer PIDs from the preceding RSS snapshot. Allocator categories overlap; never sum categories or subtract from RSS.',
            'trace_sha256':hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            'allocator_dump_sha256':hashlib.sha256((path/'allocator-dumps.json.gz').read_bytes()).hexdigest(),
            'full_trace_local_path':str(trace_path.resolve()),'records':records}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args()
    result=summarize(args.folder)
    (Path(args.folder)/'allocation-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'checkpoints':len(result['records']),'trace_sha256':result['trace_sha256']}))
