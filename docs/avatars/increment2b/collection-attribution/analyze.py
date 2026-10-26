import gzip,json,collections,hashlib
from pathlib import Path
root=Path('/workspace/scratch/collection-attribution');results=[]
for folder in sorted(root.glob('[0-3]-*')):
 es=json.load(gzip.open(folder/'collection-trace.json.gz','rt'))['traceEvents']
 records=json.loads((folder/'checkpoints.json').read_text())
 markers={e['args']['sync_id']:e['ts'] for e in es if e.get('name')=='clock_sync'}
 assert set(markers)=={r['checkpoint'] for r in records}
 commits=[e for e in es if e.get('name')=='CommitLoad']
 app_pids={e['pid'] for e in commits if e['args']['data'].get('url','').startswith('http://127.0.0.1:')}
 assert len(app_pids)==1,app_pids
 pid=next(iter(app_pids));last=0;points=[]
 relevant=[e for e in es if e.get('name') in ['MajorGC','MinorGC','CommitLoad','clock_sync'] or 'CppGC' in e.get('name','') or 'BlinkGC' in e.get('name','')]
 with gzip.open(folder/'collection-events.json.gz','wt') as f:json.dump(relevant,f)
 for r in records:
  ts=markers[r['checkpoint']];s=r['snapshot'];major=[e for e in es if e['pid']==pid and e.get('name')=='MajorGC' and last<e['ts']<=ts]
  detail=next(d for d in s['renderer_memory_detail'] if d['pid']==pid)
  points.append({'checkpoint':r['checkpoint'],'trace_timestamp_us':ts,'rss_bytes':s['renderer_rss_sum_bytes'],'app_renderer_rss_bytes':detail['status']['VmRSS'],'other_renderer_rss_bytes':s['renderer_rss_sum_bytes']-detail['status']['VmRSS'],'js_heap_bytes':s['js_heap_bytes'],'documents':s['dom_counters']['documents'],'nodes':s['dom_counters']['nodes'],'major_gc_since_previous':major})
  last=ts
 result={'cohort':folder.name,'app_pid':pid,'points':points,'gc_event_names':dict(collections.Counter(e['name'] for e in es if any(x in e.get('name','').lower() for x in ['cppgc','blinkgc']))),'trace_sha256':hashlib.sha256((folder/'collection-trace.json.gz').read_bytes()).hexdigest()}
 results.append(result)
 print(folder.name,'app',pid,'gc',[(p['checkpoint'],p['documents'],len(p['major_gc_since_previous'])) for p in points])
(root/'collection-summary.json').write_text(json.dumps({'acceptance':False,'cohorts':results},indent=2))
