import threading
import pytest
from scripts.avatar_baseline.analyze_cpu_profiles import trace_cpu, js_summary, python_summary


def event(start,duration,name,pid=42,tid=42):
    return {'ph':'X','pid':pid,'tid':tid,'tts':start,'tdur':duration,'name':name}


def test_native_nested_cpu_is_not_double_counted():
    result=trace_cpu([event(0,10000,'RunTask'),event(1000,4000,'FunctionCall'),event(2000,1000,'Layout'),event(0,50000,'worker',tid=43)],42)
    assert result['recorded_cpu_coverage_ms']==10
    assert result['innermost_recorded_cpu_ms']=={'RunTask':6,'FunctionCall':3,'Layout':1}
    assert result['inclusive_cpu_ms_not_additive']['RunTask']==10


def test_native_disjoint_and_crossing_intervals_preserved():
    r=trace_cpu([event(0,2000,'a'),event(1000,2000,'b'),event(4000,1000,'c')],42)
    assert r['recorded_cpu_coverage_ms']==4
    assert sum(r['innermost_recorded_cpu_ms'].values())==4


def test_wall_only_event_is_not_invented_cpu():
    r=trace_cpu([{'ph':'X','pid':42,'tid':42,'dur':9000,'name':'Layout'}],42)
    assert r['recorded_cpu_coverage_ms']==0
    assert r['events_without_thread_cpu']=={'Layout':1}


def js_fixture():
    return {'startTime':0,'endTime':5000,'nodes':[{'id':1,'callFrame':{'functionName':'(idle)'}},{'id':2,'callFrame':{'functionName':'render','url':'http://localhost/avatars.js'}}],
            'samples':[1,2,2],'timeDeltas':[1000,2000,1000]}


def test_js_idle_and_elapsed_sample_weights_remain_explicit():
    r=js_summary(js_fixture())
    assert r['sampled_elapsed_ms']==4 and r['profile_ms']==5
    assert r['leaf_functions'][0]['sampled_elapsed_ms']==3
    assert r['leaf_functions'][1]['callFrame']['functionName']=='(idle)'


@pytest.mark.parametrize('change',[
    lambda p:p['samples'].append(2),lambda p:p['samples'].__setitem__(0,99),
    lambda p:p['timeDeltas'].__setitem__(0,float('nan')),lambda p:p['nodes'].append(p['nodes'][0]),
    lambda p:p['timeDeltas'].__setitem__(0,50000)])
def test_invalid_js_profile_rejected(change):
    p=js_fixture();change(p)
    with pytest.raises(ValueError):js_summary(p)


def python_fixture():
    return {'yappi_version':'1.7.3','python_clock':'cpu','python_all_threads':True,'acceptance':False,
            'functions':[{'index':1,'module':'app.py','name':'render','lineno':10,'ncall':2,'nactualcall':2,'ttot':.1,'tsub':.05,'children':[]}],
            'threads':[{'ttot':.06},{'ttot':.04}]}


def test_python_clock_and_additive_self_cpu():
    p=python_fixture();r=python_summary(p)
    assert r['self_cpu_ms']==50 and r['thread_cpu_ms']==100
    p['python_clock']='wall'
    with pytest.raises(ValueError,match='clock'):python_summary(p)


def test_python_unknown_child_and_bad_duration_rejected():
    p=python_fixture();p['functions'][0]['children']=[{'index':9}]
    with pytest.raises(ValueError,match='child'):python_summary(p)
    p=python_fixture();p['functions'][0]['tsub']=1
    with pytest.raises(ValueError,match='duration'):python_summary(p)


def test_python_profiles_thread_started_before_profiler():
    pytest.importorskip('yappi')
    from tests.avatar_cpu_probe import CpuProfiles
    ready=threading.Event();go=threading.Event();done=threading.Event()
    def existing_thread_work():
        return sum(i*i for i in range(20000))
    def worker():
        ready.set();go.wait();existing_thread_work();done.set()
    class CDP:
        def send(self,name,params=None):
            return {'profile':js_fixture()} if name=='Profiler.stop' else {}
    thread=threading.Thread(target=worker);thread.start();assert ready.wait(5)
    probe=CpuProfiles(CDP())
    try:
        probe.start();go.set();assert done.wait(5);result=probe.stop()
    finally:
        go.set();thread.join(5)
        if probe.started:probe.stop()
    assert any(f['name']=='existing_thread_work' and f['ncall']==1 for f in result['functions'])
    assert len(result['threads'])>=2 and result['python_clock']=='cpu'


def test_native_post_workload_tail_is_not_charged_to_navigation():
    a={**event(0,100,'inside'),'ts':1000,'dur':100}
    b={**event(100,500,'tail'),'ts':1200,'dur':500}
    c={**event(0,50,'boundary'),'ts':900,'dur':200}
    r=trace_cpu([a,b,c],42,[1000,1300])
    assert r['recorded_cpu_coverage_ms']==.1
    assert r['boundary_or_outside_events']==2


def test_merged_python_child_is_joined_by_full_function_identity():
    p=python_fixture();p['functions'][0]['children']=[{'index':99,'module':'app.py','name':'render','lineno':10}]
    result=python_summary(p)
    assert result['renumbered_child_edges']==1
    assert result['resolved_child_edges'][0]['resolved_child_index']==1


def test_python_frame_open_at_boundary_is_retained():
    p=python_fixture();p['functions'][0].update(nactualcall=0,ttot=0,tsub=.05)
    r=python_summary(p)
    assert r['open_call_frames']==[1] and r['self_cpu_ms']==50


def test_signed_js_deltas_retained_without_negative_function_weights():
    p=js_fixture();p['timeDeltas'][1]=-100
    r=js_summary(p)
    assert r['negative_delta_count']==1 and not r['elapsed_weights_available']
    assert r['sample_count']==3 and all(f['sampled_elapsed_ms'] is None for f in r['leaf_functions'])


def test_trace_v8_nodes_and_samples_survive_context_changes():
    from scripts.avatar_baseline.analyze_cpu_profiles import trace_js_profiles
    def e(name,data,ts=0):return {'name':name,'pid':42,'tid':42 if name=='Profile' else 99,'id':'0x1','ts':ts,'args':{'data':data}}
    events=[e('Profile',{'startTime':0}),
            e('ProfileChunk',{'cpuProfile':{'nodes':[{'id':1,'callFrame':{'functionName':'first'}}],'samples':[1]},'timeDeltas':[100]},1),
            e('ProfileChunk',{'cpuProfile':{'nodes':[{'id':2,'callFrame':{'functionName':'second'}}],'samples':[2,2]},'timeDeltas':[200,-10]},2)]
    r=trace_js_profiles([events],42,[{'mount':1,'low_us':50,'high_us':150},{'mount':2,'low_us':250,'high_us':350}])
    assert not r['missing_mounts'] and r['samples_by_mount']=={1:1,2:2}
    assert r['negative_deltas_retained']==1
    assert {f['function'] for f in r['leaf_functions']}=={'first','second'}
    missing=trace_js_profiles([events],42,[{'mount':3,'low_us':400,'high_us':500}])
    assert missing['missing_mounts']==[3] and missing['outside_navigation_intervals']==3


def test_trace_v8_unknown_node_fails():
    from scripts.avatar_baseline.analyze_cpu_profiles import trace_js_profiles
    events=[{'name':'Profile','pid':42,'tid':42,'id':'1','ts':0,'args':{'data':{'startTime':0}}},
            {'name':'ProfileChunk','pid':42,'tid':42,'id':'1','ts':1,'args':{'data':{'cpuProfile':{'samples':[9]},'timeDeltas':[1]}}}]
    with pytest.raises(ValueError,match='Unknown V8'):trace_js_profiles([events],42,[])
