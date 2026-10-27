"""Offline accounting of archived stylesheet screen; never launches a browser."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

STATUS=('VmRSS','RssAnon','RssFile','RssShmem','VmSwap')
SMAPS=('Rss','Pss','Private_Dirty','Private_Clean','Shared_Dirty','Shared_Clean','Anonymous')


def point(record, tracked_pid):
    details=record['renderer_memory_detail']
    if len({d['pid'] for d in details})!=len(details):raise ValueError('Duplicate renderer PID')
    if len(details)!=record['renderer_process_count']:raise ValueError('Renderer count mismatch')
    tracked=next((d for d in details if d['pid']==tracked_pid),None)
    if tracked is None:raise ValueError('Tracked renderer disappeared; cannot attribute by rank')
    totals={k:sum(d['status'][k] for d in details) for k in STATUS}
    for d in details:
        if d['status']['VmRSS']!=sum(d['status'][k] for k in ['RssAnon','RssFile','RssShmem']):raise ValueError('Status components do not sum to VmRSS')
    return {'mount':record['mount'],'renderer_pids':[d['pid'] for d in details],
            'measured_rss':record['renderer_rss_sum_bytes'],'status_totals':totals,
            'status_vs_measured_residual':totals['VmRSS']-record['renderer_rss_sum_bytes'],
            'tracked_status':{k:tracked['status'][k] for k in STATUS},
            'other_status':{k:totals[k]-tracked['status'][k] for k in STATUS},
            'tracked_smaps':{k:tracked['smaps_rollup'][k] for k in SMAPS},
            'total_smaps':{k:sum(d['smaps_rollup'][k] for d in details) for k in SMAPS},
            'js_heap_bytes':record['js_heap_bytes'],'dom_counters':record['dom_counters'],
            'lcp_ms':record['lcp_ms'],'long_task_ms':sum(t['duration'] for t in record['long_tasks']),
            'long_task_count':len(record['long_tasks'])}


def analyze(rows):
    samples=[]
    for cohort,records in enumerate(rows):
        if len(records)!=2 or [r['run'] for r in records]!=[0,1]:raise ValueError('Incomplete cohort')
        for r in records:
            nav=r['navigation_trend']
            if [p['mount'] for p in nav]!=[1,5,10,15,20]:raise ValueError('Navigation protocol mismatch')
            pid=max(nav[0]['renderer_memory_detail'],key=lambda d:d['status']['VmRSS'])['pid']
            points=[point(p,pid) for p in nav]
            samples.append({'cohort':cohort,'run':r['run'],'tracked_pid':pid,
                            'tracking_rule':'largest VmRSS at navigation 1, same PID thereafter; not a proven page-to-PID binding',
                            'renderer_set_stable':all(set(p['renderer_pids'])==set(points[0]['renderer_pids']) for p in points),
                            'points':points})
    comparisons=[]
    for name,left,right in [('forward',0,1),('reverse',3,2),('current-repeat',0,3),('candidate-repeat',1,2)]:
        for mount in [1,5,10,15,20]:
            a=[next(p for p in s['points'] if p['mount']==mount) for s in samples if s['cohort']==left]
            b=[next(p for p in s['points'] if p['mount']==mount) for s in samples if s['cohort']==right]
            delta=lambda field:statistics.median(p[field] for p in b)-statistics.median(p[field] for p in a)
            categories={section:{k:statistics.median(p[section][k] for p in b)-statistics.median(p[section][k] for p in a) for k in a[0][section]} for section in ['status_totals','tracked_status','other_status','tracked_smaps','total_smaps']}
            comparisons.append({'name':name,'mount':mount,'measured_rss_delta':delta('measured_rss'),
                                'js_heap_delta':delta('js_heap_bytes'),'category_deltas':categories})
    return {'acceptance':False,'new_browser_runs':0,'samples':samples,'comparisons':comparisons,
            'limits':'RSS/status/smaps/JS observations are sequential, not atomic. Smaps and JS heap overlap status categories and must not be summed or subtracted to revise acceptance. Two-sample medians are descriptive; no exclusion or causal attribution to GC, a specific allocator, asset, or app component.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text());data=args.archive.read_bytes()
    if hashlib.sha256(data).hexdigest()!=manifest['archive_sha256']:raise ValueError('Archive identity mismatch')
    with zipfile.ZipFile(args.archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['members_sha256']):raise ValueError('Archive member mismatch')
        for name,digest in manifest['members_sha256'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Member identity mismatch')
        rows=[json.loads(z.read(f'screen/{i}-{arm}/False-warm.json')) for i,arm in enumerate(['current','candidate','candidate','current'])]
        experiment=json.loads(z.read('screen/experiment.json'))
    result=analyze(rows);result['provenance']={'archive_sha256':manifest['archive_sha256'],'members_verified':len(manifest['members_sha256']),'harness_commit':experiment['harness_commit'],'refs':experiment['refs']}
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Verified',len(manifest['members_sha256']),'archive members;',len(result['samples']),'samples;',sum(len(s['points']) for s in result['samples']),'navigation observations')


if __name__=='__main__':main()
