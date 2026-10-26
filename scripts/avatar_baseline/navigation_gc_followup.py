"""Post-hoc GC event extraction; does not revise the frozen phase comparisons."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path


def extract(root, assessment):
    output=[]
    for cohort in assessment['cohorts']:
        folder=root/f"{cohort['index']:02d}-{cohort['arm']}"
        path=folder/'navigation-trace.json.gz'
        events=json.load(gzip.open(path,'rt'))['traceEvents']
        markers={e['args']['sync_id']:e['ts'] for e in events if e.get('name')=='clock_sync'}
        lower,upper=markers['nav-10-before'],markers['nav-20-after']
        selected=[e for e in events if e.get('pid')==cohort['app_pid'] and lower<=e.get('ts',0)<=upper]
        cpp=[e for e in selected if 'cppgc' in e.get('cat','').lower()]
        names={'MajorGC','CppGC.MarkIncrementalStart','CppGC.MarkAtomicEpilogue',
               'CppGC.AtomicSweep','CppGC.ConcurrentSweep','CppGC.SweepFinish'}
        output.append({'slot':cohort['index'],'arm':cohort['arm'],
            'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'window_trace_us':[lower,upper],
            'cpp_event_name_counts':dict(collections.Counter(e['name'] for e in cpp)),
            'selected_gc_events':[e for e in selected if e['name'] in names],
            'navigation':cohort['navigation'][9:]})
    return {'acceptance':False,'post_hoc':True,'cohorts':output,
            'limits':'Event start inside navigation 10–20 marker window; not complete GC cycle accounting. A ConcurrentSweep duration end or Sweeping finished space event is not proof of whole-heap sweep completion. No source-effect inference or revision to frozen phase criteria.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('assessment',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.write_text(json.dumps(extract(args.root,json.loads(args.assessment.read_text())),indent=2)+'\n')
