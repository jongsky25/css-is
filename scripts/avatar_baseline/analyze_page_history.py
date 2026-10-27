"""Validate bounded native history and preserve calibration failures."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.avatar_baseline.run_page_history import REFS, HARNESS, BLOCKS
from scripts.avatar_baseline.run_navigation_light import adapt_fixture
from scripts.avatar_baseline.analyze_navigation_light import verify_backend
from scripts.avatar_baseline.analyze_paired_variance import source, expected_fixture, required_sources


def history_summary(history, begin, end):
    if history['dropped'] or history['offsets']!={'allocate':0x5ab0350,'pool':0x5ab0550}:
        raise ValueError('Dropped events or unexpected hook offsets')
    events=history['events'];seen={};allocated=set();reuses=0;unknown_pools=0;ambiguous=0;prep=[];kinds=Counter()
    for e in sorted(events,key=lambda e:e['returned_ns']):
        a,b,c=(e[k] for k in ['begin_ns','callback_ready_ns','returned_ns'])
        if not 0<a<=b<=c or e['kind'] not in ('allocate','pool'):
            raise ValueError('Invalid native event')
        page=int(e['page'],16);backend=int(e['backend'],16)
        if not backend:raise ValueError('Missing backend')
        if not page:
            if e['kind']=='pool':raise ValueError('Null pool page')
            continue  # allocation failure, kept in raw input
        key=(backend,page);previous=seen.get(key)
        if previous and previous['returned_ns']>b:
            ambiguous+=1
        elif e['kind']=='allocate':
            if key in allocated:raise ValueError('Duplicate active page allocation')
            if previous and previous['kind']=='pool':reuses+=1
            allocated.add(key)
        else:
            if key not in allocated:unknown_pools+=1
            allocated.discard(key)
        seen[key]=e
        if a<=end and c>=begin:
            kinds[e['kind']]+=1
            prep.append(max(0,min(b,end)-max(a,begin)))
    if not kinds['allocate'] or not kinds['pool']:raise ValueError('Missing page history coverage')
    return {'allocation_requests':kinds['allocate'],'pool_returns':kinds['pool'],
            'observed_reuses':reuses,'preexisting_or_unobserved_pool_returns':unknown_pools,
            'overlapping_call_order_ambiguities':ambiguous,
            'explicit_preparation_fraction':sum(prep)/(end-begin),
            'maximum_preparation_ms':max(prep,default=0)/1e6}


def timing_gate(cohorts):
    errors=[]
    if len(cohorts)!=4 or any(c.get('status')!='valid' for c in cohorts):return ['Require four intact slots']
    for c in cohorts:
        h=c.get('history',{})
        if h.get('explicit_preparation_fraction',0)>.05 or h.get('maximum_preparation_ms',0)>250:
            errors.append(f"Slot {c['index']}: explicit hook preparation exceeds 5% or 250ms")
    times=[c['navigation_ms'] for c in cohorts]
    if abs(times[3]-times[0])>times[0]*.2:errors.append('Control duration varies more than 20%')
    for a,b in [(0,1),(3,2)]:
        if times[b]>times[a]*1.2:errors.append(f'Probe/control duration exceeds 1.20: {a}/{b}')
    return errors


def audit(root,repo,ref):
    plan=json.loads((root/'experiment.json').read_text())
    phase=plan['phase'];blocks=[['current']*4] if phase=='calibration' else BLOCKS
    if phase not in ('calibration','comparison') or plan['protocol']!='native-page-history-v1' or plan['refs']!=REFS or plan['harness_commit']!=ref or plan['blocks']!=blocks or plan['acceptance'] is not False:
        raise ValueError('Plan identity mismatch')
    for name in HARNESS:
        if (root/'harness'/name).read_bytes()!=adapt_fixture(name,source(repo,ref,name)):raise ValueError('Harness mismatch')
    result={'acceptance':False,'harness_commit':ref,'status':'inconclusive','cohorts':[],'errors':[],'files_verified':0,'source_hashes_verified':0}
    for i,entry in enumerate(plan['cohorts']):
        b,pos=divmod(i,4);arm=blocks[b][pos];mode='control' if phase=='calibration' and pos in (0,3) else 'probe'
        row={'index':i,'arm':arm,'mode':mode,'status':'invalid'};result['cohorts'].append(row)
        try:
            if any(entry[k]!=v for k,v in dict(index=i,block=b,position=pos,arm=arm,mode=mode).items()):raise ValueError('Slot identity mismatch')
            folder=root/f'{i:02d}-{arm}';files=entry['files_sha256']
            if not {'page-history.json.gz','False-warm.json','environment.json','backend-source.json','runner.txt','junit.xml'}<=files.keys():raise ValueError('Missing evidence')
            for name,digest in files.items():
                if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError('File identity mismatch')
                result['files_verified']+=1
            result['source_hashes_verified']+=verify_backend(folder,repo,REFS[arm])
            env=json.loads((folder/'environment.json').read_text())
            if env['source_commit']!=REFS[arm] or env['chromium']!='156.0.8078.47' or set(env['source_sha256'])!=required_sources(repo,REFS[arm]):raise ValueError('Source environment mismatch')
            for name,digest in env['source_sha256'].items():
                data=adapt_fixture(name,source(repo,ref,name)) if name in HARNESS else source(repo,REFS[arm],name)
                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source hash mismatch')
                result['source_hashes_verified']+=1
            p=json.load(gzip.open(folder/'page-history.json.gz','rt'));native=p['native'];raw=json.loads((folder/'False-warm.json').read_text())
            if p['protocol']!='native-page-history-v1' or p['mode']!=mode or p['forced_gc'] is not False or p['acceptance'] is not False:raise ValueError('Probe protocol mismatch')
            for name,key,record in [(HARNESS[2],'probe_sha256',p),(HARNESS[3],'helper_sha256',native),(HARNESS[4],'hook_sha256',native)]:
                if hashlib.sha256(source(repo,ref,name)).hexdigest()!=record[key]:raise ValueError('Native probe identity mismatch')
                result['source_hashes_verified']+=1
            if entry['exit_code']!=0 or p['snapshots']!=13 or p['mount']!=20 or len(raw)!=1:raise ValueError('Incomplete workload')
            if [v['mount'] for v in p['checkpoints']]!=[1,5,10,15,20] or [v['mount'] for v in p['navigations']]!=list(range(1,21)):raise ValueError('Navigation schedule changed')
            for checkpoint,actual in zip(p['checkpoints'],raw[0]['navigation_trend'],strict=True):
                if actual!={'mount':checkpoint['mount'],**checkpoint['snapshot']}:raise ValueError('Snapshot changed')
            if native['build_id']!='1c5dca8527a61d07372e489142bee26af1bcaf71' or native['enabled']!=(mode=='probe') or native['frida_version']!='17.5.1':raise ValueError('Native build/mode mismatch')
            if any(m['type']=='error' for m in native['agent_messages']):raise ValueError('Agent error')
            begin,end=p['navigation_begin_ns'],p['navigation_end_ns']
            if not native['setup_end_ns']<=begin<end:raise ValueError('Setup overlaps workload')
            row['navigation_ms']=(end-begin)/1e6
            if mode=='probe':row['history']=history_summary(native['history'],begin,end)
            elif 'history' in native:raise ValueError('Instrumented control')
            row['status']='valid'
        except (KeyError,ValueError,OSError,TypeError) as exc:
            row['reason']=str(exc);result['errors'].append(f'Slot {i}: {exc}')
    if len(result['cohorts'])!=sum(map(len,blocks)):result['errors'].append('Incomplete fixed schedule')
    if phase=='calibration':
        result['gate_errors']=timing_gate(result['cohorts'])
        if not result['errors'] and not result['gate_errors']:result['status']='calibration_passed'
    else:
        result['gate_errors']=[f"Slot {c['index']}: hook preparation budget" for c in result['cohorts'] if c.get('history',{}).get('explicit_preparation_fraction',0)>.05 or c.get('history',{}).get('maximum_preparation_ms',0)>250]
        if not result['errors'] and not result['gate_errors']:result['status']='complete_history_diagnostic'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--ref',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[2];ref=subprocess.check_output(['git','rev-parse',a.ref],cwd=repo,text=True).strip()
    result=audit(a.root,repo,ref);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='cohorts'}))
    raise SystemExit(result['status'] not in ('calibration_passed','complete_history_diagnostic'))
