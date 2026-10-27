"""All global-handle births/transitions in a C buffer; diagnostic only."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
from http.server import ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

import frida
from playwright.sync_api import Browser, sync_playwright
from scripts.avatar_baseline import element_membership_lifecycle as baseline
from scripts.avatar_baseline.context_handle_journal import OFFSETS, ROLES
from scripts.avatar_baseline.hosted_native_calibration import SOURCES as BASE_SOURCES
from scripts.avatar_baseline.mixed_membership_fixture import Handler
from scripts.avatar_baseline.runner_isolation_inventory import inventory
from tests import avatar_page_history_probe as identity_helper

AGENT='scripts/avatar_baseline/native/handle_buffer.js'
PROTOCOL='native-handle-buffer-diagnostic-v1'
PREFIX='globalThis.HANDLE_BUFFER_SELFTEST=true;\n'
SOURCES=list(dict.fromkeys([*BASE_SOURCES,AGENT,'scripts/avatar_baseline/native_handle_buffer.py',
    'scripts/avatar_baseline/context_handle_journal.py']))


def validate_header(history, export, live=True):
    if (history['protocol']!='native-handle-buffer-v1' or history['offsets']!=OFFSETS
        or history['record_size']!=72 or history['capacity']!=50000 or history['pending']
        or history['clock_domain']!='CLOCK_MONOTONIC' or history['toolchain']!='internal'
        or not history['storage']['canary_verified']
        or history['storage']['state_bytes']>history['storage']['allocated_bytes']
        or any(history[k] is not False for k in ['per_event_javascript','runtime_subscription_added','snapshot_requested','gc_requested'])
        or not export[0]<=history['snapshot_end_ns']<=export[1]):
        raise ValueError('Invalid native handle buffer ABI/storage/export')
    if live and (history['dropped'] or history['limit']!=50000
                 or [e['id'] for e in history['events']]!=list(range(1,len(history['events'])+1))):
        raise ValueError('Incomplete native handle records')
    for e in history['events']:
        if not 0<e['begin_ns']<=e['ready_ns']<=e['end_ns']<=history['snapshot_end_ns'] or e['thread']<=0:
            raise ValueError('Invalid native callback clock/thread interval')
        if live and e['kind'] not in OFFSETS:raise ValueError('Unexpected native callback')


def validate_proof(proof):
    if proof.get('error') or any(m.get('type')=='error' for m in proof['messages']):
        raise ValueError('Native buffer preflight failed')
    if proof['identity']['build_id']!=baseline.BUILD or proof['frida_version']!='17.5.1':
        raise ValueError('Wrong preflight browser/Frida')
    if len(proof['clock_samples'])!=20 or any(not s['begin_ns']<=s['native_ns']<=s['end_ns'] for s in proof['clock_samples']):
        raise ValueError('Native clock samples incomplete or mismatched')
    for label,count,drops,limit,iterations in [('concurrency',1024,0,50000,256),('overflow',32,36,32,17)]:
        value=proof[label];h=value['history'];validate_header(h,[value['begin_ns'],value['end_ns']],False)
        if len(h['events'])!=count or h['dropped']!=drops or h['limit']!=limit:
            raise ValueError('Native concurrency/overflow counts changed')
        addresses=set();workers=set();threads=set()
        for e in h['events']:
            token=int(e['a0'],16);worker=token>>32;seq=token&0xffffffff
            if e['kind']!='__selftest' or not 1<=worker<=4 or not 1<=seq<=iterations or token in addresses or int(e['a1'],16)!=(token^0x5a5a) or int(e['value'],16)!=token or int(e['caller'],16)!=worker:
                raise ValueError('Native immutable argument/return/caller copy failed')
            addresses.add(token);workers.add(worker);threads.add(e['thread'])
        if label=='concurrency' and (workers!={1,2,3,4} or len(threads)!=4):
            raise ValueError('Native concurrency thread coverage incomplete')
    return {'status':'native_buffer_selftest_passed','acceptance':False,'clock_samples':20,
            'threads':4,'immutable_records':1024,'overflow_stored':32,'overflow_dropped':36}


def proof(out):
    out.mkdir(parents=True,exist_ok=False)
    p={'messages':[],'clock_samples':[],'frida_version':frida.__version__}
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.lifecycle_events=[]
    threading.Thread(target=server.serve_forever,daemon=True).start();session=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(baseline.BROWSER),args=['--no-sandbox'])
            if browser.version!='156.0.8078.47':raise ValueError('Wrong proof browser')
            page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/empty')
            p['identity']=identity_helper.PageHistory(page,False).finish()
            session=frida.attach(p['identity']['pid']);script=session.create_script(PREFIX+Path(AGENT).read_text())
            script.on('message',lambda m,d:p['messages'].append(m));script.load()
            if not any(m.get('payload',{}).get('selftest_ready') for m in p['messages']):raise ValueError('Native preflight not ready')
            for _ in range(20):
                lo=time.monotonic_ns();value=script.exports_sync.clock();hi=time.monotonic_ns()
                p['clock_samples'].append({'begin_ns':lo,'native_ns':value,'end_ns':hi})
            for name,it,limit in [('concurrency',256,50000),('overflow',17,32)]:
                lo=time.monotonic_ns();history=script.exports_sync.selftest(4,it,limit);hi=time.monotonic_ns()
                p[name]={'begin_ns':lo,'end_ns':hi,'history':history}
            script.unload();session.detach();session=None;browser.close()
    except Exception as error:p['error']=repr(error)
    finally:
        if session:
            try:session.detach()
            except Exception:pass
        server.shutdown();server.server_close()
        with gzip.open(out/'capture.json.gz','wt') as stream:json.dump(p,stream)
    checked=validate_proof(p)
    (out/'assessment.json').write_text(json.dumps(checked,indent=2)+'\n')
    return checked


def analyze(journal,capture):
    h=journal['native'];validate_header(h,[journal['export_begin_ns'],journal['export_end_ns']])
    if h['pid']!=capture['pid'] or capture['build_id']!=baseline.BUILD:
        raise ValueError('Native buffer renderer identity mismatch')
    if len(journal['clock_samples'])!=20 or any(not s['begin_ns']<=s['native_ns']<=s['end_ns'] for s in journal['clock_samples']):
        raise ValueError('Live native buffer clock mismatch')
    if any(m.get('type')=='error' for m in journal['messages']):raise ValueError('Native handle agent error')
    events=h['events'];owners=defaultdict(list);parent={};first={};owner_kinds=set(OFFSETS)-{'global_create','global_release','global_weak_direct','global_weak_field','gc_epilogue'}
    for e in sorted(events,key=lambda e:(e['begin_ns'],e['id'])):
        stack=owners[e['thread']]
        while stack and stack[-1]['end_ns']<=e['begin_ns']:stack.pop()
        if e['kind']=='global_create':
            scope=next((v for v in reversed(stack) if v['kind'] in ROLES),None)
            if scope:
                if e['end_ns']>scope['end_ns']:raise ValueError('Constructor scope overlap')
                parent[e['id']]=scope;first.setdefault(scope['id'],e['id'])
        if e['kind'] in owner_kinds:stack.append(e)
    def stage(point):
        matches=[s['index'] for s in capture['stages'] if s['begin_ns']<=point<=s['end_ns']]
        return matches[0] if len(matches)==1 else None
    generations=[];active={};unknown=Counter();samples=[];callsite_witness=False
    actions=[(e['end_ns'],e['id'],'event',e) for e in events if e['kind'].startswith('global_')]
    actions += [(e['begin_ns'],e['id'],'gc',e) for e in events if e['kind']=='gc_epilogue']
    for point,serial,action,e in sorted(actions):
        if action=='gc':
            index=stage(point);strong=[v for v in active.values() if v['state']=='strong']
            old=[v for v in active.values() if index is not None and v['created_stage'] is not None and v['created_stage']<index]
            samples.append({'event':e['id'],'stage':index,'begin_ns':point,
                'known_context_handles_without_observed_weakening':[v['creation'] for v in strong if v['role'] in ROLES.values()],
                'old_unreleased_handles':[v['creation'] for v in old],
                'old_without_observed_weakening':[v['creation'] for v in old if v['state']=='strong'],
                'old_unreleased_by_role':dict(Counter(v['role'] for v in old)),
                'old_unreleased_by_caller':dict(Counter(str(v['caller_offset']) for v in old))})
            continue
        if e['kind']=='global_create':
            slot=e['value']
            if int(slot,16)==0 or slot in active:raise ValueError('Overlapping/null global handle generation')
            scope=parent.get(e['id']);is_context=scope is not None and first[scope['id']]==e['id']
            role=ROLES[scope['kind']] if is_context else 'other-scoped' if scope else 'unscoped'
            if role=='V8PerContextData::context_' and e['caller_offset']==0xfd4bb86:callsite_witness=True
            value={'creation':e['id'],'slot':slot,'created_stage':stage(e['begin_ns']),
                'role':role,'owner_event':scope['id'] if scope else None,'caller_offset':e['caller_offset'],
                'state':'strong','transitions':[]}
            generations.append(value);active[slot]=value
        else:
            slot=e['a1'] if e['kind']=='global_weak_field' else e['a0']
            generation=active.get(slot)
            if generation is None:unknown[e['kind']]+=1;continue
            generation['transitions'].append(e['id'])
            if e['kind']=='global_release':generation['state']='released';del active[slot]
            else:generation['state']='weak'
    if not callsite_witness or not samples:raise ValueError('Missing known caller/GC positive witness')
    return {'status':'native_handle_diagnostic_analyzed','acceptance':False,'instrument_qualified':False,
        'event_counts':dict(Counter(e['kind'] for e in events)), 'generations':generations,
        'unknown_preexisting_transitions':dict(unknown),'gc_epilogues':samples,
        'known_callsite_witness':True,
        'limits':'Observed entry paths only; inlined transitions and weakness restoration may be unobserved. Unreleased handles are candidates, not proven strong roots. Previously weakened candidates remain included. Pre-attach roots and target types are unknown. Callers identify creation paths, not exclusive ownership or bytes. No identity across moving GC.'}


def capture(out,mode):
    out.mkdir(parents=True)
    data={'protocol':PROTOCOL,'messages':[],'clock_samples':[]}
    original_cdp,original_close=Browser.new_browser_cdp_session,Browser.close
    session=None;script=None;loaded=False
    def initialize(pid):
        nonlocal session,script,loaded
        session=frida.attach(pid);script=session.create_script(Path(AGENT).read_text())
        script.on('message',lambda m,d:data['messages'].append(m));script.load()
        if not any(m.get('payload',{}).get('handle_buffer_ready') for m in data['messages']):raise ValueError('Native handle buffer not ready')
        for _ in range(20):
            lo=time.monotonic_ns();value=script.exports_sync.clock();hi=time.monotonic_ns()
            data['clock_samples'].append({'begin_ns':lo,'native_ns':value,'end_ns':hi})
        loaded=True
    def new_cdp(browser,*args,**kwargs):
        cdp=original_cdp(browser,*args,**kwargs);send=cdp.send;parts=[];pid=None
        def record(method,params=None):
            nonlocal pid
            value=send(method,params)
            if not loaded and method=='IO.read':
                parts.append(value['data'])
                if value.get('eof'):
                    trace=json.loads(''.join(parts))
                    pids={e['pid'] for e in trace['traceEvents'] if e.get('name')=='CommitLoad' and e.get('args',{}).get('data',{}).get('url','').endswith('/empty')}
                    if len(pids)!=1:raise ValueError('Ambiguous native handle PID')
                    pid=pids.pop()
            if not loaded and method=='IO.close' and pid is not None:initialize(pid)
            return value
        cdp.send=record;return cdp
    def close(browser,*args,**kwargs):
        nonlocal script,session
        if script is not None:
            data['export_begin_ns']=time.monotonic_ns();data['native']=script.exports_sync.result();data['export_end_ns']=time.monotonic_ns()
            script.unload();session.detach();script=None;session=None
        return original_close(browser,*args,**kwargs)
    Browser.new_browser_cdp_session=new_cdp;Browser.close=close
    try:return baseline.run(out/'capture',mode)
    finally:
        if script is not None:
            try:
                data['export_begin_ns']=time.monotonic_ns();data['native']=script.exports_sync.result();data['export_end_ns']=time.monotonic_ns()
            except Exception as error:data['export_error']=repr(error)
        with gzip.open(out/'native-handles.json.gz','wt') as stream:json.dump(data,stream)


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    result={'protocol':PROTOCOL,'harness_commit':ref,'acceptance':False,'instrument_qualified':False,
        'application_qualified':False,'order':['buffer-only','buffer+membership','buffer+membership','buffer-only'], 'cohorts':[],'errors':[]}
    try:
        for name in SOURCES:
            raw=(repo/name).read_bytes()
            if raw!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Unfrozen handle buffer source')
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        if platform.machine()!='x86_64' or platform.python_version()!='3.12.14' or {n:importlib.metadata.version(n) for n in ['playwright','frida']}!={'playwright':'1.62.0','frida':'17.5.1'}:raise ValueError('Wrong native handle toolchain')
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        result['preflight']=proof(out/'native-preflight')
        for index,mode in enumerate(['control','probe','probe','control']):
            folder=out/f'{index}-{mode}';folder.mkdir();row={'index':index,'mode':result['order'][index]};result['cohorts'].append(row)
            with (folder/'runner.txt').open('w') as stream:
                row['exit_code']=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.native_handle_buffer','--capture','--mode',mode,'--out',str(folder/'slot')],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
            try:
                if row['exit_code']:raise ValueError('Native handle capture failed')
                p=json.load(gzip.open(folder/'slot/capture/capture.json.gz','rt'))
                if p['status']!='captured' or p['harness_commit']!=ref or p['forced_gc'] is not False or len(p['stages'])!=12:raise ValueError('Invalid native handle workload')
                journal=json.load(gzip.open(folder/'slot/native-handles.json.gz','rt'));row['analysis']=analyze(journal,p)
                row['stage_counters']=[{'index':s['index'],**s['dom']['value'],'heap':s['heap']['value']['usedSize']} for s in p['stages']]
                if mode=='probe':
                    from scripts.avatar_baseline.analyze_reader_retention import selected_events
                    trace=json.load(gzip.open(folder/'slot/capture/trace.json.gz','rt'))['traceEvents'];gc=selected_events(trace,p['pid'])
                    if any(e.get('args',{}).get('dumps') for e in trace):raise ValueError('Unexpected memory dump')
                    row['natural_major_gc_count']=sum(e['name']=='MajorGC' for e in gc)
            except Exception as error:row['error']=repr(error);result['errors'].append(f'Slot {index}: {error}')
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception as error:result['errors'].append(repr(error))
    result['status']='diagnostic_failed' if result['errors'] else 'diagnostic_complete'
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Native-buffer handle/caller diagnostic','',result['status'],'',
        'Diagnostic only. No native/application qualification or memory acceptance.','']
    for row in result['cohorts']:lines.append(f"- Slot {row['index']} {row['mode']}: "+str(row.get('error',[(s['stage'],len(s['old_unreleased_handles'])) for s in row.get('analysis',{}).get('gc_epilogues',[])])))
    lines.extend(result['errors']);summary='\n'.join(lines)+'\n';(out/'SUMMARY.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(summary)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n');print(summary)
    return bool(result['errors'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--capture',action='store_true');parser.add_argument('--mode',choices=['control','probe'])
    args=parser.parse_args();raise SystemExit(capture(args.out.resolve(),args.mode) if args.capture else run(args.out.resolve()))
