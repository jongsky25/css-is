"""Compact all-slot findings; preserves the complete analysis separately."""
import gzip
import json
from pathlib import Path

root = Path(__file__).resolve().parent
p = json.load(gzip.open(root/'analysis.json.gz', 'rt'))
s = {'acceptance': False, 'new_measurements': 0,
     'members_verified': p['archive_members_verified'], 'slots': []}
for c in p['cohorts']:
    steps = c['status_steps']
    drops = [x for x in steps if x['delta_bytes']['RssAnon'] <= -5*2**20]
    s['slots'].append({'index': c['index'], 'arm': c['arm'],
        'majors': sum(len(v['major_gc']) for v in c['segments']),
        'live_nodes': sorted({x['live_nodes'] for x in c['checkpoints']}),
        'documents': [x['dom_counters']['documents'] for x in c['checkpoints']],
        'major_overlapping_mounts': [x['mount'] for x in c['checkpoints'] if any(e['name']=='MajorGC' for e in x['gc_overlapping_checkpoint_bounds'])],
        'bounds_crossing_trace_edge': [x['mount'] for x in c['checkpoints'] if not x['fully_inside_trace']],
        'anonymous_drops_at_least_5_mib': len(drops),
        'drops_with_sweep_overlap': sum(bool(x['overlap'] and x['overlap']['cpp_sweep_counts']) for x in drops),
        'uncovered_status_intervals': sum(not x['covered'] for x in steps),
        'status_intervals': len(steps),
        'endpoint_blink_heap_mib': {k:v/2**20 for k,v in c['endpoint']['allocators']['blink_gc/main/heap'].items()}})
a,b = p['cohorts'][4],p['cohorts'][7]
pt = a['checkpoints'][3]
major = a['segments'][1]['major_gc'][0]
epoch = a['segments'][1]['epochs'][0]
s['slot4_navigation15'] = {'snapshot_trace_bounds_us': pt['trace_bounds_us'],
    'major_start_us': major['ts'], 'major_end_us': major['ts']+major['dur'],
    'last_observed_sweep_end_us': epoch['last_observed_sweep_end_us'],
    'sweep_after_snapshot_upper_bound_ms': (epoch['last_observed_sweep_end_us']-pt['trace_bounds_us'][1])/1000,
    'major_heap_before_mib': major['args']['usedHeapSizeBefore']/2**20,
    'major_heap_after_mib': major['args']['usedHeapSizeAfter']/2**20,
    'snapshot_js_heap_mib': pt['js_heap_bytes']/2**20}
s['slot4_minus7_navigation15_app_status_mib'] = {
    k:(a['checkpoints'][3]['app_status'][k]-b['checkpoints'][3]['app_status'][k])/2**20
    for k in ['VmRSS','RssAnon','RssFile','RssShmem']}
(root/'summary.json').write_text(json.dumps(s, indent=2)+'\n')
