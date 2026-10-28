"""Offline chronology of the retained failed native prerequisite; no capture."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from scripts.avatar_baseline.analyze_membership_lifecycle import audit
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds, mapped, selected_events
from scripts.avatar_baseline.analyze_element_membership import generations, join_receivers

ARTIFACT='docs/avatars/increment2b/application-observer-calibration/attempt-v5-failure-evidence.zip'
SHA='5e066d46a033ae2fdc8f68ea3d06f6c37e1bf248e8f29185f4bfb8f235df5b6b'
REF='9e47c14dbf1dea37b70fc19fc0f8925c2199bca1'
PHASES={'CppGC.MarkIncrementalStart','CppGC.MarkVisitRoots','CppGC.MarkVisitStack',
    'CppGC.MarkVisitCrossThreadPersistents','CppGC.AtomicMark','CppGC.AtomicWeak',
    'CppGC.WeakContainerCallbacksProcessing','CppGC.CustomCallbacksProcessing',
    'CppGC.ConcurrentSweep','CppGC.SweepFinalizeEmptyPages',
    'V8.GC_MC_MARK_RETAIN_MAPS','V8.GC_MC_MARK_WEAK_CLOSURE_EPHEMERON_MARKING',
    'V8.GC_MC_CLEAR_WEAK_GLOBAL_HANDLES','V8.GC_CONSERVATIVE_STACK_SCANNING'}


def relation(bounds,point):
    if len(bounds)!=2 or not bounds[0]<=bounds[1]:raise ValueError('Invalid mapped interval')
    if bounds[1]<point:return 'definitely_before'
    if bounds[0]>point:return 'definitely_after'
    return 'overlap_or_uncertain'


def pair_statistics(major,statistics):
    result=[]
    for stat in statistics:
        matches=[i for i,event in enumerate(major) if event['tid']==stat['tid'] and event['ts']<=stat['ts']<=event['ts']+event['dur']]
        if len(matches)!=1:raise ValueError('Ambiguous major-GC statistics interval')
        result.append({'major_index':matches[0],**stat})
    if sorted(s['major_index'] for s in result)!=list(range(len(major))):
        raise ValueError('Incomplete major-GC statistics')
    return result


def chronology(p,trace):
    events=trace['traceEvents'];clock=clock_bounds(p,events);gc=selected_events(events,p['pid'])
    major=[e for e in gc if e['name']=='MajorGC']
    if not major or p['trace_completion'].get('dataLossOccurred'):raise ValueError('Missing/lost natural GC trace')
    if any(e.get('args',{}).get('forced') or e.get('args',{}).get('dumps') for e in events):raise ValueError('Forced collection or dump')
    statistics=[]
    for e in events:
        if e.get('pid')==p['pid'] and e['name']=='V8.GCTraceGCNVP':
            value=json.loads(e['args']['value'])
            if value['gc']=='mc':statistics.append({'ts':e['ts'],'tid':e['tid'],'values':value})
    stats=pair_statistics(major,statistics)
    starts=[e for e in gc if e['name']=='CppGC.MarkIncrementalStart']
    if not starts:raise ValueError('Missing incremental marking start')
    first=starts[0]['ts']
    native=p['history']['events'];inside=[e for e in native if p['begin_ns']<=e['begin_ns']<=e['returned_ns']<=p['end_ns']]
    spans,unknown=generations([e for e in inside if e['kind'] in ['allocate','pool']])
    joins=join_receivers(inside,spans)
    labelled=[s for s in spans if s['labels']];returns=[s for s in labelled if s['end_ns'] is not None]
    base=mapped([p['begin_ns'],p['begin_ns']],clock)[0]
    shutdown=[]
    for e in inside:
        if e['kind']=='shutdown':
            bounds=mapped([e['begin_ns'],e['returned_ns']],clock)
            shutdown.append({'phase':e['phase'],'document_address':e['address'],'bounds_us':bounds,
                'relative_to_first_mark':relation(bounds,first),'before_mark_margin_ms':(first-bounds[1])/1000})
    pagehide=[e for e in events if e.get('pid')==p['pid'] and e['name']=='TimeStamp'
        and e.get('args',{}).get('data',{}).get('message','').startswith('membership-pagehide:')]
    beacons=[{'index':e['index'],'bounds_us':mapped([e['received_ns'],e['received_ns']],clock)} for e in p['lifecycle_events']]
    for e in beacons:e['relative_to_first_mark']=relation(e['bounds_us'],first)
    phases=[{'name':e['name'],'ts':e['ts'],'dur':e.get('dur',0),'tid':e['tid'],
             'epoch':e.get('args',{}).get('epoch'),'from_window_lower_bound_ms':(e['ts']-base)/1000}
        for e in events if e.get('pid')==p['pid'] and e['name'] in PHASES]
    epochs=defaultdict(list)
    for e in phases:
        if e['epoch'] is not None:epochs[str(e['epoch'])].append(e)
    epoch_rows=[]
    for epoch,es in epochs.items():
        sweeps=[e for e in es if 'Sweep' in e['name']]
        epoch_rows.append({'epoch':epoch,'observed_phase_counts':dict(Counter(e['name'] for e in es)),
            'first_observed_us':min(e['ts'] for e in es),'last_observed_end_us':max(e['ts']+e['dur'] for e in es),
            'last_observed_selected_sweep_end_us':max((e['ts']+e['dur'] for e in sweeps),default=None),
            'whole_sweep_completion_known':False})
    stages=[]
    for s in p['stages']:
        row={'index':s['index'],'mode':s['fixture_mode'],'host_interval_ns':[s['begin_ns'],s['end_ns']],
             **s['dom']['value'],'used_heap_bytes':s['heap']['value']['usedSize']}
        row['counter_bounds_us']={k:mapped(s[k]['interval_ns'],clock) for k in ['heap','dom']}
        row['counter_trace_coverage']={k:clock['coverage_us'][0]<=v[0]<=v[1]<=clock['coverage_us'][1] for k,v in row['counter_bounds_us'].items()}
        stages.append(row)
    return {'clock':clock,'major_gc':major,'major_statistics':stats,'selected_gc_phases':phases,
        'cppgc_epochs':epoch_rows,'first_incremental_mark_us':first,
        'shutdown_calls':shutdown,'pagehide_markers':pagehide,'beacon_receipts':beacons,'stages':stages,
        'native_event_counts':dict(Counter(e['kind'] for e in inside)),
        'receiver_records':len(joins),'matched_receivers':sum(e['generation'] is not None for e in joins),
        'labelled_generations':len(labelled),'labelled_returned_generations':len(returns),
        'unknown_pool_returns':unknown,
        'labelled_returns':[{'generation':s['generation'],'base':hex(s['base']),
            'labels':sorted(set(s['labels'])),'return_ns':s['end_ns'],
            'return_bounds_us':mapped([s['end_ns'],s['end_ns']],clock)} for s in returns],
        'disposal_event_name_counts':{name:sum(e.get('pid')==p['pid'] and e['name']==name for e in events)
            for name in ['LocalWindowProxy::DisposeContext','ScriptState::DisposePerContextData','V8.GCNotifyContextDisposed']},
        'missing_root_evidence':{'local_window_proxy_disposal_arguments':False,
            'script_state_dispose_calls':False,'context_disposal_notifications':False,
            'strong_retainer_paths':False,'v8_object_identities':False},
        'limits':'Shutdown addresses are not Element receiver ownership. Marked proxies are visited-object counts, not roots or context IDs. A phase scope is not proof of completed whole sweeping or object reclamation.'}


def run(artifact,repo):
    if hashlib.sha256(artifact.read_bytes()).hexdigest()!=SHA:raise ValueError('Original artifact changed')
    with tempfile.TemporaryDirectory(prefix='original-gc-audit-') as temp:
        root=Path(temp)
        with zipfile.ZipFile(artifact) as archive:
            if any(Path(n).is_absolute() or '..' in Path(n).parts for n in archive.namelist()):raise ValueError('Unsafe original archive')
            archive.extractall(root)
        result=root/'result';manifest=json.loads((result/'files-sha256.json').read_text())
        if len(manifest)!=145:raise ValueError('Original manifest scope changed')
        for name,sha in manifest.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or hashlib.sha256((result/name).read_bytes()).hexdigest()!=sha:
                raise ValueError('Original evidence hash mismatch')
        native=json.loads((result/'native-qualification/result.json').read_text())
        checked=audit(result/'native-qualification/calibration',repo,REF)
        if native['harness_commit']!=REF or checked!=native['calibration_audit'] or checked['instrument_qualified_for_application_calibration'] is not False:
            raise ValueError('Original failed native audit changed')
        if (result/'application').exists():raise ValueError('Unexpected application workload')
        cohorts=[]
        for index,mode in enumerate(['control','probe','probe','control']):
            folder=result/f'native-qualification/calibration/{index}-{mode}'
            p=json.load(gzip.open(folder/'capture.json.gz','rt'))
            original=checked['cohorts'][index]
            row={'index':index,'mode':mode,'original_audit':{k:original[k] for k in
                ['status','membership_status','membership_errors','errors','duration_ms',
                 'observation_fraction_bound','maximum_observation_ms','matched_receivers'] if k in original}}
            if mode=='probe':row['chronology']=chronology(p,json.load(gzip.open(folder/'trace.json.gz','rt')))
            else:row['counters']=[{'index':s['index'],**s['dom']['value'],'used_heap_bytes':s['heap']['value']['usedSize']} for s in p['stages']]
            cohorts.append(row)
        return {'protocol':'original-gc-offline-audit-v1','status':'offline_audit_complete',
            'audit_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'original_run':40532187252,'artifact_sha256':SHA,
            'internal_hashes_verified':145,'original_native_audit_identical':True,
            'original_native_audit_sha256':hashlib.sha256(json.dumps(checked,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'original_errors':checked['errors'],
            'acceptance':False,'instrument_qualified':False,'application_qualified':False,'new_measurements':0,
            'cohorts':cohorts}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--artifact',type=Path,default=Path(ARTIFACT))
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    result=run(args.artifact.resolve(),Path(__file__).resolve().parents[2]);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cohorts'}))
