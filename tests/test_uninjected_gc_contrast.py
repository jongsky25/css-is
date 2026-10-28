import copy
import hashlib
import json
from pathlib import Path
import pytest
from scripts.avatar_baseline import uninjected_gc_contrast as contrast
from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE,tag


def fixture(mode='counter-only'):
    fixtures=json.loads((Path(__file__).resolve().parents[1]/contrast.FIXTURES).read_text())
    p=dict(status='captured',mode='control',protocol=contrast.baseline.PROTOCOL,
        build_id=contrast.baseline.BUILD,browser_version='156.0.8078.47',playwright_version='1.62.0',
        acceptance=False,forced_gc=False,back_forward_cache_disabled=True,messages=[],pid=123,
        runner_sha256=hashlib.sha256(Path(contrast.baseline.__file__).read_bytes()).hexdigest(),
        begin_ns=1000000,end_ns=250000000,lifecycle_events=[dict(index=i,persisted=False,received_ns=10000000+i*10000000) for i in range(11)],stages=[])
    for i,kind in enumerate(SCHEDULE):
        begin=2000000+i*20000000;end=begin+15000000
        qs=[dict(phase=f'census:{i}:{group}:{repeat}',begin_ns=begin+1000000,end_ns=begin+2000000,
            result=dict(count=32,fixture_count=3000,counts=[1]*32,tags=[tag(kind,group)]*32)) for group in ['avatar','other'] for repeat in [0,1]]
        p['stages'].append(dict(index=i,fixture_mode=kind,begin_ns=begin,end_ns=end,
            dom_before_sha256=fixtures[kind]['outer_html_sha256'],dom_after_sha256=fixtures[kind]['outer_html_sha256'],
            censuses=qs,batch_census_interval_ns=[begin+1000000,begin+2000000],
            heap=dict(interval_ns=[begin+3000000,begin+4000000],value=dict(usedSize=1234)),
            dom=dict(interval_ns=[begin+5000000,begin+6000000],value=dict(documents=1,nodes=9007,jsEventListeners=1))))
    commands=[dict(session='page',method=method) for i in range(12) for method in ['Runtime.getHeapUsage','Memory.getDOMCounters']]
    commands += [dict(session='browser',method=method) for method in ['Tracing.start','Tracing.end']]
    meta=dict(protocol=contrast.PROTOCOL,mode=mode,identity_pid=123,frida_attempts=[],frida_guarded_apis=['attach'],commands=commands,trace_started=False)
    trace=None
    if mode=='trace-only':
        commands.extend(dict(session='browser',method=method) for method in ['Tracing.start','Tracing.end','Tracing.recordClockSyncMarker','Tracing.recordClockSyncMarker'])
        meta.update(trace_started=True,trace_finished=True,trace_config=contrast.TRACE_CONFIG,trace_completion={},
            trace_setup_interval_ns=[2000000,3000000],before=dict(name='before',begin_ns=2000000,end_ns=2001000),
            after=dict(name='after',begin_ns=251000000,end_ns=251001000),transfer_begin_ns=252000000,transfer_end_ns=253000000)
        trace=dict(traceEvents=[dict(name='clock_sync',ts=2000,args=dict(sync_id='before')),
            dict(name='clock_sync',ts=251000,args=dict(sync_id='after')),
            dict(name='MajorGC',pid=123,ts=130000,dur=200,ph='X',args=dict(type='natural')),
            dict(name='V8.GCTraceGCNVP',pid=123,ts=130200,args=dict(value=json.dumps({'gc':'mc','mark.js_global_proxies':11,'end_object_size':2501964})))])
    return p,meta,fixtures,trace


def test_counter_only_has_no_measurement_trace_or_native_qualification():
    p,m,f,t=fixture();result=contrast.analyze(p,m,'counter-only',f,t)
    assert result['instrument_qualified'] is False and 'natural_major_gc' not in result
    assert len(result['stage_counters'])==12


def test_trace_only_preserves_natural_gc_stats_and_clock_coverage():
    p,m,f,t=fixture('trace-only');result=contrast.analyze(p,m,'trace-only',f,t)
    assert len(result['natural_major_gc'])==1
    assert result['major_statistics'][0]['mark.js_global_proxies']==11
    assert all(v['fully_trace_covered'] for s in result['counter_trace_order'] for v in s['components'].values())


@pytest.mark.parametrize('mutation',['attach','history','pid','source','fixture','samples','batch','schedule','counter','lifecycle','query','extra_trace'])
def test_reject_changed_baseline_or_injection(mutation):
    p,m,f,t=fixture()
    if mutation=='attach':m['frida_attempts']=['attach']
    if mutation=='history':p['history']={}
    if mutation=='pid':m['identity_pid']=999
    if mutation=='source':p['runner_sha256']='wrong'
    if mutation=='fixture':p['stages'][0]['dom_after_sha256']='wrong'
    if mutation=='samples':p['stages'][0]['censuses'][0]['result']['counts'][0]=0
    if mutation=='batch':p['stages'][0]['censuses'][0]['begin_ns']=0
    if mutation=='schedule':p['stages'].pop()
    if mutation=='counter':m['commands'].pop(0)
    if mutation=='lifecycle':p['lifecycle_events'][0]['persisted']=True
    if mutation=='query':m['commands'].append(dict(session='page',method='HeapProfiler.takeHeapSnapshot'))
    if mutation=='extra_trace':m['trace_started']=True
    with pytest.raises(ValueError):contrast.analyze(p,m,'counter-only',f,t)


@pytest.mark.parametrize('mutation',['forced','dump','loss','transfer','config','anchor'])
def test_reject_untrustworthy_trace(mutation):
    p,m,f,t=fixture('trace-only');m=copy.deepcopy(m)
    if mutation=='forced':t['traceEvents'][2]['args']['forced']=True
    if mutation=='dump':t['traceEvents'][2]['args']['dumps']={"heap":1}
    if mutation=='loss':m['trace_completion']['dataLossOccurred']=True
    if mutation=='transfer':m['transfer_begin_ns']=1
    if mutation=='config':m['trace_config']['includedCategories']=['*']
    if mutation=='anchor':t['traceEvents'][0]['args']['sync_id']='wrong'
    with pytest.raises(ValueError):contrast.analyze(p,m,'trace-only',f,t)
