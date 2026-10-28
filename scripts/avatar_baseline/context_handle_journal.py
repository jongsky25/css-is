"""Snapshot-free context/handle lifecycle diagnostic; never calibration."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from playwright.sync_api import Browser, BrowserContext
from scripts.avatar_baseline import element_membership_lifecycle as baseline
from scripts.avatar_baseline.hosted_native_calibration import SOURCES as BASE_SOURCES
from scripts.avatar_baseline.runner_isolation_inventory import inventory

PROTOCOL = 'context-handle-diagnostic-v1'
AGENT = 'scripts/avatar_baseline/native/context_journal.js'
SOURCES = list(dict.fromkeys([*BASE_SOURCES, AGENT,
    'scripts/avatar_baseline/context_handle_journal.py']))
ROLES = {'state_ctor':'ScriptState::context_', 'per_ctor':'V8PerContextData::context_',
         'holder_set':'gin::ContextHolder::context_', 'extension_ctor':'extensions::ScriptContext::v8_context_'}
OFFSETS = {'state_ctor':0xfd46290,'state_dispose':0xfd46800,'state_dtor':0xfd46690,
    'state_dissociate':0xfd46990,'per_ctor':0xfd4bac0,'per_dtor':0xfd4bc10,
    'extension_ctor':0xad479b0,'extension_invalidate':0xad48db0,'extension_dtor':0xad48610,
    'holder_set':0xd32f710,'holder_dtor':0xd32f660,'global_create':0x5142d10,
    'global_release':0x5143060,'global_weak_direct':0x5143150,
    'global_weak_field':0x51431a0,'gc_epilogue':0x51184b0}


def analyze(journal, capture):
    native = journal['native']
    if (native['protocol']!='context-handle-journal-v1' or native['pid']!=capture['pid']
        or native['offsets']!=OFFSETS or capture['build_id']!=baseline.BUILD
        or native['clock_domain']!='CLOCK_MONOTONIC' or native['dropped'] or native['pending']
        or native['snapshot_requested'] is not False or native['gc_requested'] is not False):
        raise ValueError('Invalid context journal identity or completeness')
    for sample in journal['clock_samples']:
        if not sample['begin_ns']<=sample['native_ns']<=sample['end_ns']:
            raise ValueError('Context journal clock mismatch')
    if len(journal['clock_samples'])!=20:
        raise ValueError('Incomplete context clock proof')
    if any(m.get('type')=='error' for m in journal['messages']):
        raise ValueError('Context journal agent error')
    events = native['events']
    if [e['id'] for e in events]!=list(range(1,len(events)+1)):
        raise ValueError('Context event sequence incomplete')
    by_id = {e['id']:e for e in events}
    creates, transitions, first = {}, {}, {}
    for event in events:
        if event['kind'] not in OFFSETS:
            raise ValueError('Unknown context event kind')
        if not 0<event['begin_ns']<=event['end_ns']<=journal['export_end_ns'] or event['thread']<=0:
            raise ValueError('Invalid context event interval')
        parent = by_id.get(event['parent'])
        if event['parent'] and (not parent or parent['thread']!=event['thread']
                or not parent['begin_ns']<=event['begin_ns']<=event['end_ns']<=parent['end_ns']):
            raise ValueError('Invalid context owner nesting')
        if event['kind']=='global_create':
            if not parent or parent['kind'] not in ROLES or event.get('overlap_with') or int(event['slot'],16)==0:
                raise ValueError('Ambiguous context global handle creation')
            creates[event['id']] = event
            transitions[event['id']] = []
            first.setdefault(parent['id'], event['id'])
    for event in events:
        if event['kind'] in ['global_release','global_weak_direct','global_weak_field']:
            created = creates.get(event['creation'])
            if not created or created['slot']!=event['slot'] or created['end_ns']>event['begin_ns']:
                raise ValueError('Handle transition has no matching generation')
            transitions[created['id']].append(event)
    active={}
    for event in sorted((e for e in events if e['kind'].startswith('global_')),key=lambda e:e['end_ns']):
        slot=event['slot']
        if event['kind']=='global_create':
            if slot in active:raise ValueError('Overlapping global handle generations')
            active[slot]=event['id']
        else:
            if active.get(slot)!=event['creation']:raise ValueError('Transition on inactive handle generation')
            if event['kind']=='global_release':del active[slot]
    rows=[]
    for event in creates.values():
        owner = by_id[event['parent']]
        # Only the FIRST Create in each source-audited owner initializer is its
        # context handle. Other handles remain raw evidence, without this label.
        if first[owner['id']]!=event['id']:
            continue
        stages=[s['index'] for s in capture['stages'] if s['begin_ns']<=owner['begin_ns']<=s['end_ns']]
        rows.append({'creation':event['id'],'slot':event['slot'],'owner_event':owner['id'],
                     'owner_address':owner['owner'],'role':ROLES[owner['kind']],
                     'created_stage':stages[0] if len(stages)==1 else None,
                     'begin_ns':event['begin_ns'],'ready_ns':event['end_ns'],
                     'transitions':sorted(transitions[event['id']],key=lambda e:e['end_ns'])})
    samples=[]
    for event in events:
        if event['kind']!='gc_epilogue':
            continue
        point=event['begin_ns']
        strong=[]
        for row in rows:
            if row['ready_ns']>point:
                continue
            state='strong'
            for transition in row['transitions']:
                if transition['end_ns']<=point:
                    state='released' if transition['kind']=='global_release' else 'weak'
            if state=='strong':strong.append({k:row[k] for k in ['creation','owner_event','role','created_stage','owner_address']})
        stages=[s['index'] for s in capture['stages'] if s['begin_ns']<=point<=s['end_ns']]
        stage=stages[0] if len(stages)==1 else None
        samples.append({'event':event['id'],'begin_ns':point,'stage':stage,'known_strong_context_handles':strong,
                        'old_known_strong_context_handles':[r for r in strong if r['created_stage'] is not None and stage is not None and r['created_stage']<stage]})
    counts=Counter(e['kind'] for e in events)
    if not samples or not all(counts[k] for k in ['state_ctor','state_dispose','per_ctor','extension_invalidate','global_create','global_release','global_weak_field']):
        raise ValueError('Missing context/cleanup/GC witness')
    return {'status':'context_diagnostic_analyzed','acceptance':False,'instrument_qualified':False,
            'event_counts':dict(counts),'context_handles':rows,'gc_epilogues':samples,
            'cdp_event_counts':dict(Counter(e['kind'] for e in journal['cdp_events'])),
            'limits':'Known owner initializers only; pre-attach/other roots are unobserved. Constructor argument cells and object values are not stable identities across GC. Hook overhead is unqualified.'}


def capture(out, mode):
    import frida  # Optional: required only when explicitly running this diagnostic.
    out.mkdir(parents=True)
    data={'protocol':PROTOCOL,'messages':[],'clock_samples':[],'cdp_events':[],
          'snapshot_requested':False,'gc_requested':False}
    new_browser_cdp, new_page_cdp, close = Browser.new_browser_cdp_session, BrowserContext.new_cdp_session, Browser.close
    session=None
    script=None
    loaded=False
    def initialize(pid):
        nonlocal session,script,loaded
        session=frida.attach(pid)
        script=session.create_script(Path(AGENT).read_text())
        script.on('message',lambda message,binary:data['messages'].append(message))
        script.load()
        for _ in range(20):
            lo=time.monotonic_ns();value=script.exports_sync.clock();hi=time.monotonic_ns()
            data['clock_samples'].append({'begin_ns':lo,'native_ns':value,'end_ns':hi})
        data['pid']=pid
        loaded=True
    def browser_cdp(browser,*args,**kwargs):
        cdp=new_browser_cdp(browser,*args,**kwargs)
        send=cdp.send
        chunks=[]
        identity=None
        def record(method,params=None):
            nonlocal identity
            result=send(method,params)
            if not loaded and method=='IO.read':
                chunks.append(result['data'])
                if result.get('eof'):
                    trace=json.loads(''.join(chunks))
                    pids={e['pid'] for e in trace['traceEvents'] if e.get('name')=='CommitLoad' and e.get('args',{}).get('data',{}).get('url','').endswith('/empty')}
                    if len(pids)!=1:raise ValueError('Ambiguous journal renderer identity')
                    identity=pids.pop()
            if not loaded and method=='IO.close' and identity is not None:
                initialize(identity)
            return result
        cdp.send=record
        return cdp
    def page_cdp(context,page):
        cdp=new_page_cdp(context,page)
        for name in ['executionContextCreated','executionContextDestroyed','executionContextsCleared']:
            def record(event,kind=name):
                # Persist only synthetic context metadata, never remote objects.
                value=event.get('context',{})
                data['cdp_events'].append({'kind':kind,'received_ns':time.monotonic_ns(),
                    'id':value.get('id',event.get('executionContextId')),
                    'unique_id':value.get('uniqueId',event.get('executionContextUniqueId')),
                    'name':value.get('name'),'origin':value.get('origin'),'aux_data':value.get('auxData')})
            cdp.on('Runtime.'+name,record)
        cdp.send('Runtime.enable')
        return cdp
    def finish(browser,*args,**kwargs):
        nonlocal script,session
        if script is not None:
            data['export_begin_ns']=time.monotonic_ns()
            data['native']=script.exports_sync.result()
            data['export_end_ns']=time.monotonic_ns()
            script.unload();session.detach();script=None;session=None
        return close(browser,*args,**kwargs)
    Browser.new_browser_cdp_session=browser_cdp
    BrowserContext.new_cdp_session=page_cdp
    Browser.close=finish
    try:
        return baseline.run(out/'capture',mode)
    finally:
        if script is not None:
            try:
                data['export_begin_ns']=time.monotonic_ns();data['native']=script.exports_sync.result();data['export_end_ns']=time.monotonic_ns()
            except Exception as error:data['export_error']=repr(error)
        with gzip.open(out/'context-journal.json.gz','wt') as stream:json.dump(data,stream)


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    result={'protocol':PROTOCOL,'harness_commit':ref,'acceptance':False,'instrument_qualified':False,
            'application_qualified':False,'order':['journal-only','journal+membership','journal+membership','journal-only'],
            'cohorts':[],'errors':[]}
    try:
        for name in SOURCES:
            raw=(repo/name).read_bytes()
            if raw!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Unfrozen journal source: '+name)
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        if platform.machine()!='x86_64' or platform.python_version()!='3.12.14' or {n:importlib.metadata.version(n) for n in ['playwright','frida']}!={'playwright':'1.62.0','frida':'17.5.1'}:raise ValueError('Wrong journal toolchain')
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        for index,mode in enumerate(['control','probe','probe','control']):
            folder=out/f'{index}-{mode}';folder.mkdir()
            row={'index':index,'mode':result['order'][index]};result['cohorts'].append(row)
            with (folder/'runner.txt').open('w') as stream:
                row['exit_code']=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.context_handle_journal',
                    '--capture','--mode',mode,'--out',str(folder/'slot')],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
            try:
                if row['exit_code']:raise ValueError('Context capture failed')
                p=json.load(gzip.open(folder/'slot/capture/capture.json.gz','rt'))
                if p['status']!='captured' or p['harness_commit']!=ref or p['forced_gc'] is not False or len(p['stages'])!=12:raise ValueError('Incomplete journal workload')
                journal=json.load(gzip.open(folder/'slot/context-journal.json.gz','rt'))
                row['analysis']=analyze(journal,p)
                row['stage_counters']=[{'index':s['index'],**s['dom']['value'],'heap':s['heap']['value']['usedSize']} for s in p['stages']]
                if mode=='probe':
                    from scripts.avatar_baseline.analyze_reader_retention import selected_events
                    trace=json.load(gzip.open(folder/'slot/capture/trace.json.gz','rt'))['traceEvents']
                    gc=selected_events(trace,p['pid'])
                    row['natural_major_gc_count']=sum(e['name']=='MajorGC' for e in gc)
            except Exception as error:row['error']=repr(error);result['errors'].append(f'Slot {index}: {error}')
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception as error:result['errors'].append(repr(error))
    result['status']='diagnostic_failed' if result['errors'] else 'diagnostic_complete'
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Snapshot-free context handle diagnostic','',result['status'],'',
           'Diagnostic only: no instrument/application qualification or memory acceptance.','']
    for row in result['cohorts']:
        lines.append(f"- Slot {row['index']} {row['mode']}: "+str(row.get('error',[(p['stage'],len(p['old_known_strong_context_handles'])) for p in row.get('analysis',{}).get('gc_epilogues',[])])))
    summary='\n'.join(lines)+'\n';(out/'SUMMARY.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(summary)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(summary)
    return bool(result['errors'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--capture',action='store_true');parser.add_argument('--mode',choices=['control','probe'])
    args=parser.parse_args()
    raise SystemExit(capture(args.out.resolve(),args.mode) if args.capture else run(args.out.resolve()))
