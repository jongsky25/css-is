"""Join allocator dumps to natural collection without changing RSS accounting."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

if __package__:
    from .analyze_collection import summarize as summarize_collection
else:
    from analyze_collection import summarize as summarize_collection


def guid(value):
    # Trace IDs and CDP dumpGuid are hexadecimal, with optional 0x prefix.
    return int(str(value),16)


def allocator_family(name):
    return "/" not in name or (name.startswith(("blink_gc/","malloc/","partition_alloc/partitions/","v8/"))
        and name.count("/")<=3 and "__" not in name)


def summarize(events, records):
    collection=summarize_collection(events,records)
    app_pid=collection['app_pid']
    dumps={}
    for event in events:
        if event.get('ph')=='v' and event.get('args',{}).get('dumps',{}).get('allocators'):
            key=guid(event['id']);pid=event['pid']
            group=dumps.setdefault(key,{})
            allocators=event['args']['dumps']['allocators']
            if pid in group:
                prior=group[pid]
                if prior['ts']!=event['ts'] or prior.get('name')!=event.get('name'):
                    raise ValueError('Conflicting allocator fragments for PID and GUID')
                previous=prior['args']['dumps']['allocators']
                if set(previous)&set(allocators):
                    raise ValueError('Duplicate allocator entries for PID and GUID')
                previous.update(allocators)
            else:
                group[pid]={**event,'args':{'dumps':{'allocators':dict(allocators)}}}
    output=[];seen=set();used=set()
    for index,(record,point) in enumerate(zip(records,collection['points'])):
        request=record['dump_request']
        if request.get('success') is not True:raise ValueError('Unsuccessful dump request')
        key=guid(request['dumpGuid'])
        if key in seen:raise ValueError('Duplicate requested dump GUID')
        seen.add(key)
        # Chromium's JSON exporter renumbers dump IDs independently of CDP GUIDs.
        # Join by a unique app dump inside the clock interval, never by ordinal.
        end=collection['points'][index+1]['trace_timestamp_us'] if index+1<len(records) else float('inf')
        candidates=[(dump_id,group) for dump_id,group in dumps.items() if app_pid in group
            and point['trace_timestamp_us'] <= group[app_pid]['ts'] < end]
        if len(candidates)!=1:raise ValueError('Missing or ambiguous allocator dump in checkpoint interval')
        trace_id,group=candidates[0]
        if trace_id in used:raise ValueError('Allocator dump reused across checkpoints')
        used.add(trace_id);event=group[app_pid]
        allocations={}
        for name,data in event['args']['dumps']['allocators'].items():
            # Retain allocator families and partition totals, not their overlapping bucket children.
            if not allocator_family(name):continue
            attrs={k:int(v['value'],16) for k,v in data.get('attrs',{}).items() if v.get('units')=='bytes'}
            if attrs:allocations[name]=attrs
        sweeping=[e for e in events if e['pid']==app_pid and e.get('ts',0)<=event['ts']
            and 'cppgc' in e.get('cat','').lower() and 'sweep' in e.get('name','').lower()]
        latest=sorted(sweeping,key=lambda e:e['ts'])[-20:]
        output.append({**point,'dump_guid':request['dumpGuid'],'trace_dump_id':hex(trace_id),
            'dump_join':'unique app-renderer dump in checkpoint clock interval','dump_timestamp_us':event['ts'],
            'after_dump_rss_bytes':record['after_dump_snapshot']['renderer_rss_sum_bytes'],
            'app_allocator_bytes':allocations,'preceding_sweep_events':latest,
            'renderer_pids_in_dump':sorted(group),
            'observed_renderer_pids':[d['pid'] for d in record['snapshot']['renderer_memory_detail']]})
    return {'acceptance':False,'app_pid':app_pid,'cpp_gc_event_count':collection['cpp_gc_event_count'],
        'forced_collection_events':collection['forced_collection_events'],'records':output,
        'interpretation':'Raw allocator attributes overlap and have distinct meanings. Allocated objects can include pending garbage. Reserved/committed capacity is not RSS. Never sum allocator families or subtract them from RSS. Preceding sweep events do not establish completion of the entire heap sweep.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    results=[]
    folders=sorted(args.root.glob('[0-3]-*'))
    if [p.name for p in folders] != ['0-original','1-current','2-current','3-original']:
        raise ValueError('Incomplete counterbalanced diagnostic')
    for folder in folders:
        trace=folder/'collection-trace.json.gz'
        events=json.load(gzip.open(trace,'rt'))['traceEvents']
        records=json.loads((folder/'checkpoints.json').read_text())
        if len(records)!=13:
            raise ValueError('Incomplete checkpoint set')
        provenance=json.loads((folder/'provenance.json').read_text())
        if not provenance.get('native_allocator_dumps') or provenance['trace_completion'].get('dataLossOccurred'):
            raise ValueError('Missing native dumps or trace data loss')
        result=summarize(events,records)
        if not result['cpp_gc_event_count']:
            raise ValueError('No C++ collection events captured')
        result.update(cohort=folder.name,trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
        results.append(result)
        retained=[]
        for e in events:
            if e.get('ph')=='v' and e.get('args',{}).get('dumps',{}).get('allocators'):
                retained.append({**{k:v for k,v in e.items() if k!='args'},'args':{'dumps':{'allocators':e['args']['dumps']['allocators']}}})
            elif e.get('name') in ['clock_sync','CommitLoad','MajorGC','MinorGC'] or 'cppgc' in e.get('cat','').lower():retained.append(e)
        with gzip.open(folder/'residency-events.json.gz','wt') as stream:json.dump({'traceEvents':retained},stream)
        print(folder.name,'matched dumps',len(result['records']),flush=True)
    (args.root/'residency-summary.json').write_text(json.dumps({'acceptance':False,'cohorts':results},indent=2)+'\n')


if __name__=='__main__':main()
