"""Fixed counter/GC-trace comparison without browser injection; not acceptance."""
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
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page
from scripts.avatar_baseline import element_membership_lifecycle as baseline
from scripts.avatar_baseline.hosted_native_calibration import SOURCES as BASE_SOURCES
from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE, document, tag
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds, mapped, selected_events
from scripts.avatar_baseline.runner_isolation_inventory import inventory

PROTOCOL='uninjected-gc-contrast-v1'
FIXTURES='docs/avatars/increment2b/uninjected-gc-contrast/fixture-hashes.json'
ORDER=['counter-only','trace-only','trace-only','counter-only']
TRACE_CONFIG={'excludedCategories':['*'],'includedCategories':['devtools.timeline','blink','cppgc',
    'disabled-by-default-cppgc','disabled-by-default-v8.gc'],'traceBufferSizeInKb':65536,
    'recordMode':'recordUntilFull','memoryDumpConfig':{}}
SOURCES=list(dict.fromkeys([*BASE_SOURCES,'scripts/avatar_baseline/uninjected_gc_contrast.py',FIXTURES]))


def analyze(p,meta,mode,fixtures,trace=None):
    if (mode not in ORDER or p['status']!='captured' or p['mode']!='control'
        or p['protocol']!=baseline.PROTOCOL or p['build_id']!=baseline.BUILD
        or p['browser_version']!='156.0.8078.47' or p['playwright_version']!='1.62.0'
        or p['acceptance'] is not False or p['forced_gc'] is not False
        or p['back_forward_cache_disabled'] is not True or p['messages']
        or p['runner_sha256']!=hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest()
        or any(k in p for k in ['history','native_export_interval_ns'])
        or meta['protocol']!=PROTOCOL or meta['mode']!=mode
        or meta['identity_pid']!=p['pid'] or meta['frida_attempts']
        or 'attach' not in meta['frida_guarded_apis']):
        raise ValueError('Invalid uninjected capture identity/guard')
    if [s['index'] for s in p['stages']]!=list(range(12)) or [s['fixture_mode'] for s in p['stages']]!=SCHEDULE:
        raise ValueError('Incomplete contrast workload')
    if len(p['lifecycle_events'])!=11 or sorted(e['index'] for e in p['lifecycle_events'])!=list(range(11)) or any(e['persisted'] is not False or not p['begin_ns']<=e['received_ns']<=p['end_ns'] for e in p['lifecycle_events']):
        raise ValueError('Incomplete/BFCache lifecycle evidence')
    for s in p['stages']:
        if not p['begin_ns']<=s['begin_ns']<=s['end_ns']<=p['end_ns']:
            raise ValueError('Stage outside measured window')
        expected=fixtures[s['fixture_mode']]
        if hashlib.sha256(document(s['fixture_mode'])).hexdigest()!=expected['raw_document_sha256'] or s['dom_before_sha256']!=expected['outer_html_sha256'] or s['dom_after_sha256']!=expected['outer_html_sha256']:
            raise ValueError('Fixture/observable DOM changed')
        labels=[f'census:{s["index"]}:{group}:{repeat}' for group in ['avatar','other'] for repeat in [0,1]]
        if [q['phase'] for q in s['censuses']]!=labels:raise ValueError('Changed census order')
        for q in s['censuses']:
            r=q['result'];group=q['phase'].split(':')[2]
            if r['count']!=32 or r['fixture_count']!=3000 or r['counts']!=[1]*32 or r['tags']!=[tag(s['fixture_mode'],group)]*32:
                raise ValueError('Changed receiver sample/observable')
            if [q['begin_ns'],q['end_ns']]!=s['batch_census_interval_ns'] or not s['begin_ns']<=q['begin_ns']<=q['end_ns']<=s['end_ns']:
                raise ValueError('Census outside original batch/stage')
        for key in ['heap','dom']:
            lo,hi=s[key]['interval_ns']
            if not s['begin_ns']<=lo<=hi<=s['end_ns']:raise ValueError('Counter outside stage')
    counts=Counter((c['session'],c['method']) for c in meta['commands'])
    allowed={'browser':{'SystemInfo.getProcessInfo','Tracing.start','Tracing.end','Tracing.recordClockSyncMarker','IO.read','IO.close'},
             'page':{'Runtime.getHeapUsage','Memory.getDOMCounters'}}
    if any(c['method'] not in allowed[c['session']] for c in meta['commands']):raise ValueError('Unexpected diagnostic CDP command')
    if counts[('page','Runtime.getHeapUsage')]!=12 or counts[('page','Memory.getDOMCounters')]!=12:
        raise ValueError('Counter command schedule changed')
    epochs=2 if mode=='trace-only' else 1
    if counts[('browser','Tracing.start')]!=epochs or counts[('browser','Tracing.end')]!=epochs:
        raise ValueError('Trace/identity epoch count changed')
    result={'status':'uninjected_contrast_capture_analyzed','acceptance':False,'instrument_qualified':False,
        'mode':mode,'duration_ms':(p['end_ns']-p['begin_ns'])/1e6,
        'command_counts':{f'{session}:{method}':n for (session,method),n in counts.items()},
        'stage_counters':[{'index':s['index'],**s['dom']['value'],'heap':s['heap']['value']['usedSize']} for s in p['stages']]}
    if mode=='counter-only':
        if trace is not None or meta.get('trace_started') or counts[('browser','Tracing.recordClockSyncMarker')]:raise ValueError('Measurement trace added to baseline slot')
        return result
    if (trace is None or meta['trace_config']!=TRACE_CONFIG or not meta.get('trace_finished') or meta['trace_completion'].get('dataLossOccurred')
        or not p['end_ns']<=meta['after']['begin_ns']<=meta['transfer_begin_ns']<=meta['transfer_end_ns']
        or counts[('browser','Tracing.recordClockSyncMarker')]!=2):
        raise ValueError('Missing/lost trace or transfer inside measurement')
    events=trace['traceEvents']
    if any(e.get('args',{}).get('forced') or e.get('args',{}).get('dumps') for e in events):raise ValueError('Forced collection or memory dump')
    clock=clock_bounds(meta,events);gc=selected_events(events,p['pid']);major=[e for e in gc if e['name']=='MajorGC']
    stats=[]
    for e in events:
        if e.get('pid')==p['pid'] and e['name']=='V8.GCTraceGCNVP':
            value=json.loads(e['args']['value'])
            if value.get('gc')=='mc':
                stats.append({'trace_ts_us':e['ts'],**{k:value.get(k) for k in ['reason','collector_reason','stack','mark.js_global_proxies','end_object_size','start_global_consumed_size','end_global_consumed_size']}})
    counters=[]
    for s in p['stages']:
        point={'stage':s['index'],'components':{}}
        for name in ['heap','dom']:
            bounds=mapped(s[name]['interval_ns'],clock)
            covered=clock['coverage_us'][0]<=bounds[0]<=bounds[1]<=clock['coverage_us'][1]
            point['components'][name]={'bounds_us':bounds,'fully_trace_covered':covered,
                'major_gc_definitely_before':[i for i,e in enumerate(major) if e['ts']+e['dur']<bounds[0]],
                'major_gc_overlap_or_uncertain':[i for i,e in enumerate(major) if e['ts']<=bounds[1] and e['ts']+e['dur']>=bounds[0]]}
        counters.append(point)
    result.update(clock=clock,natural_major_gc=major,major_statistics=stats,counter_trace_order=counters,
                  gc_event_counts=dict(Counter(e['name'] for e in gc)),trace_setup_ms=(meta['trace_setup_interval_ns'][1]-meta['trace_setup_interval_ns'][0])/1e6,
                  limits='Two trace slots are descriptive evidence, not a causal estimate or root graph. Coverage/clock uncertainty is preserved. No injected membership, qualification or memory acceptance.')
    return result


def capture(out,mode):
    out.mkdir(parents=True)
    data={'protocol':PROTOCOL,'mode':mode,'commands':[],'frida_attempts':[],'frida_guarded_apis':[],'trace_started':False}
    for name in ['attach','spawn','inject_library_blob','inject_library_file']:
        if hasattr(baseline.frida,name):
            def forbidden(*args,api=name,**kwargs):
                data['frida_attempts'].append(api);raise RuntimeError('Frida forbidden in uninjected contrast')
            setattr(baseline.frida,name,forbidden);data['frida_guarded_apis'].append(name)
    original_browser,original_page,original_goto=Browser.new_browser_cdp_session,BrowserContext.new_cdp_session,Page.goto
    cdp=None;done=[];current_page=None
    def wrap(session,name):
        send=session.send
        def record(method,params=None):
            lo=time.monotonic_ns();value=send(method,params);hi=time.monotonic_ns()
            data['commands'].append({'session':name,'method':method,'begin_ns':lo,'end_ns':hi})
            return value
        session.send=record
        return session
    def marker(name):
        lo=time.monotonic_ns();cdp.send('Tracing.recordClockSyncMarker',{'syncId':name});hi=time.monotonic_ns()
        return {'name':name,'begin_ns':lo,'end_ns':hi}
    def browser_session(browser,*args,**kwargs):
        nonlocal cdp
        cdp=wrap(original_browser(browser,*args,**kwargs),'browser')
        cdp.on('Tracing.tracingComplete',lambda event:done.append(event))
        send,detach=cdp.send,cdp.detach
        identity=[]
        def record(method,params=None):
            value=send(method,params)
            if method=='IO.read' and 'identity_pid' not in data:
                identity.append(value['data'])
                if value.get('eof'):
                    events=json.loads(''.join(identity))['traceEvents']
                    pids={e['pid'] for e in events if e.get('name')=='CommitLoad' and e.get('args',{}).get('data',{}).get('url','').endswith('/empty')}
                    if len(pids)!=1:raise ValueError('Ambiguous uninjected PID')
                    data['identity_pid']=pids.pop()
            return value
        def finish():
            if data['trace_started'] and not data.get('trace_finished'):
                data['after']=marker('uninjected-after');count=len(done);cdp.send('Tracing.end')
                deadline=time.monotonic()+15
                while len(done)==count:
                    if time.monotonic()>deadline:raise TimeoutError('Uninjected trace completion')
                    current_page.wait_for_timeout(10)  # Deferred; measured workload already ended.
                data['trace_completion']=done[-1];handle=done[-1]['stream'];parts=[]
                data['transfer_begin_ns']=time.monotonic_ns()
                while True:
                    value=cdp.send('IO.read',{'handle':handle});parts.append(value['data'])
                    if value.get('eof'):break
                cdp.send('IO.close',{'handle':handle});data['transfer_end_ns']=time.monotonic_ns()
                with gzip.open(out/'gc-trace.json.gz','wt') as stream:stream.write(''.join(parts))
                data['trace_finished']=True
            return detach()
        cdp.send=record;cdp.detach=finish
        return cdp
    def page_session(context,*args,**kwargs):return wrap(original_page(context,*args,**kwargs),'page')
    def goto(page,url,*args,**kwargs):
        nonlocal current_page
        if mode=='trace-only' and urlsplit(url).path=='/fixture/0':
            if data['trace_started']:raise ValueError('Duplicate contrast trace start')
            current_page=page;lo=time.monotonic_ns()
            cdp.send('Tracing.start',{'transferMode':'ReturnAsStream','traceConfig':TRACE_CONFIG})
            data['trace_started']=True;data['trace_config']=TRACE_CONFIG
            data['before']=marker('uninjected-before');data['trace_setup_interval_ns']=[lo,time.monotonic_ns()]
        return original_goto(page,url,*args,**kwargs)
    Browser.new_browser_cdp_session=browser_session;BrowserContext.new_cdp_session=page_session;Page.goto=goto
    try:return baseline.run(out/'capture','control')
    finally:
        with gzip.open(out/'contrast.json.gz','wt') as stream:json.dump(data,stream)


def run(out):
    out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[2]
    ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    result={'protocol':PROTOCOL,'harness_commit':ref,'order':ORDER,'acceptance':False,
        'instrument_qualified':False,'application_qualified':False,'cohorts':[],'errors':[]}
    try:
        for name in SOURCES:
            raw=(repo/name).read_bytes()
            if raw!=subprocess.check_output(['git','show',ref+':'+name],cwd=repo):raise ValueError('Unfrozen contrast source')
            dest=out/'harness'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        if platform.machine()!='x86_64' or platform.python_version()!='3.12.14' or importlib.metadata.version('playwright')!='1.62.0':raise ValueError('Wrong contrast toolchain')
        caps=int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:')),16)
        if caps&(1<<19):raise ValueError('Unexpected SYS_PTRACE capability')
        result['sys_ptrace_effective']=False
        (out/'runner-inventory.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        fixtures=json.loads((repo/FIXTURES).read_text())
        for index,mode in enumerate(ORDER):
            folder=out/f'{index}-{mode}';folder.mkdir();row={'index':index,'mode':mode};result['cohorts'].append(row)
            with (folder/'runner.txt').open('w') as stream:
                row['exit_code']=subprocess.run([sys.executable,'-m','scripts.avatar_baseline.uninjected_gc_contrast','--capture','--mode',mode,'--out',str(folder/'slot')],cwd=repo,stdout=stream,stderr=subprocess.STDOUT).returncode
            try:
                if row['exit_code']:raise ValueError('Uninjected workload failed')
                p=json.load(gzip.open(folder/'slot/capture/capture.json.gz','rt'));meta=json.load(gzip.open(folder/'slot/contrast.json.gz','rt'))
                if p['harness_commit']!=ref:raise ValueError('Wrong contrast capture source')
                tracefile=folder/'slot/gc-trace.json.gz';trace=json.load(gzip.open(tracefile,'rt')) if tracefile.exists() else None
                row['analysis']=analyze(p,meta,mode,fixtures,trace)
            except Exception as error:row['error']=repr(error);result['errors'].append(f'Slot {index}: {error}')
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception as error:result['errors'].append(repr(error))
    result['status']='diagnostic_failed' if result['errors'] else 'diagnostic_complete'
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Uninjected counter/GC-trace comparison','',result['status'],'',
        'Diagnostic only. No native/application qualification, memory acceptance or deployment.','']
    for row in result['cohorts']:
        a=row.get('analysis',{});c=a.get('stage_counters',[])
        lines.append(f"- Slot {row['index']} {row['mode']}: "+str(row.get('error',[(s['index'],s['documents'],s['nodes']) for s in c if s['index'] in [6,11]])))
    lines.extend(result['errors']);summary='\n'.join(lines)+'\n';(out/'SUMMARY.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:stream.write(summary)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n');print(summary)
    return bool(result['errors'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--capture',action='store_true');parser.add_argument('--mode',choices=['counter-only','trace-only'])
    args=parser.parse_args();raise SystemExit(capture(args.out.resolve(),args.mode) if args.capture else run(args.out.resolve()))
