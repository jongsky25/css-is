"""Summarize actual HTTP baseline without dropping outliers or failed gates."""
import argparse
import json
import statistics
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',default='docs/avatars/application');a=p.parse_args()
root=Path(a.directory); rows=[]
for file in sorted(root.glob('*.json')):
    if file.name=='summary.json':continue
    value=json.loads(file.read_text())
    if isinstance(value,list):rows.extend(value)
summary={'samples':len(rows),'groups':[],'failures':{},'limits':[
    'Event Timing reports events >=16 ms only; absent entries do not prove zero input latency.',
    'Long tasks are page-wide and not attributed to avatar script without a trace.',
    'Renderer RSS sums OS renderer-process resident pages; shared pages may be counted more than once. It is not private memory/PSS.',
    'Hidden verification is reported per sample; false means browser did not hide the document.',
    'Warm means prior navigation in the same context; resource timings distinguish actual cache hits.',
    'Compression is a local controlled GZip proxy around the unmodified ASGI application.',
]}
def stats(values):
    values=[v for v in values if v is not None]
    return {'median':statistics.median(values),'worst':max(values),'n':len(values)} if values else None
for mobile in [False,True]:
 for cache in ['cold','warm']:
    group=[r for r in rows if r['mobile']==mobile and r['cache']==cache]
    if not group:continue
    scenarios={}
    for name in group[0]['scenarios']:
        data=[r['scenarios'][name] for r in group]
        scenarios[name]={metric:stats([v[metric] for v in data]) for metric in ['lcp_ms','frame_p95_ms','js_heap_bytes','nodes','avatar_animations','renderer_rss_sum_bytes','renderer_process_count']}
        scenarios[name]['long_tasks_over_50_ms']=[t for v in data for t in v['long_tasks'] if t['duration']>50]
        scenarios[name]['interaction_duration_per_run_median_ms']=stats([statistics.median([e['duration'] for e in v['events'] if e['interaction']]) for v in data if any(e['interaction'] for e in v['events'])])
        scenarios[name]['interaction_duration_ms']=stats([e['duration'] for v in data for e in v['events'] if e['interaction']])
        scenarios[name]['interaction_input_delay_ms']=stats([e['processing'] for v in data for e in v['events'] if e['interaction']])
    summary['groups'].append({'mobile':mobile,'cache':cache,'runs':len(group),'scenarios':scenarios,
        'home_encoded_bytes':stats([r['home_document']['encoded'] for r in group]),
        'picker_encoded_bytes':stats([r['picker_document']['encoded'] for r in group]),
        'heap_navigation_change_bytes':stats([r['navigation_trend'][-1]['js_heap_bytes']-r['navigation_trend'][0]['js_heap_bytes'] for r in group])})
summary['full_duration_complete'] = len(rows)==20 and all(r['seconds']>=30 for r in rows) and all(sum(r['mobile']==m and r['cache']==c for r in rows)==5 for m in [False,True] for c in ['cold','warm'])
visibility_file=root/'native-visibility-touch.json'
summary['native_visibility_verified'] = json.loads(visibility_file.read_text())['hidden_end']['hidden'] if visibility_file.exists() else False
summary['failures']={
    'javascript_errors':[e for r in rows for e in r['errors']],
    'external_attempts':[e for r in rows for e in r['external_attempts']],
    'hidden_not_verified':sum(not r['hidden_verified'] for r in rows),
    'offscreen_animating':sum(r['scenarios']['offscreen']['avatar_animations']>0 for r in rows),
    'reduced_motion_animating':sum(r['scenarios']['reduced_motion']['avatar_animations']>0 for r in rows),
    'mobile_interaction_frame_gate_misses':sum(r['mobile'] and r['scenarios']['home_interaction']['frame_p95_ms']>33 for r in rows),
}
(root/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps({'samples':len(rows),'failures':summary['failures']},indent=2))
