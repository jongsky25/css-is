from copy import deepcopy
import pytest
from scripts.avatar_baseline.control_phase_timing import Timing,validate_capture,process_stat,key_values,PHASES,EXPECTED_DOM,PROTOCOL
from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE


def capture():
    p={'protocol':PROTOCOL,'mode':'control','status':'captured','messages':[],
       'acceptance':False,'forced_gc':False,'back_forward_cache_disabled':True,
       'build_id':'1c5dca8527a61d07372e489142bee26af1bcaf71','browser_version':'156.0.8078.47',
       'selection_policy':'per-evaluate-selector-cache','begin_ns':1,'end_ns':10**12,'pid':3,
       'lifecycle_events':[{'index':i,'persisted':False} for i in range(11)],'stages':[]}
    def snapshot(t):
        return {'begin_ns':t,'end_ns':t+1,'processes':{k:{'start_ticks':i,'user_ticks':0,'system_ticks':0,'minor_faults':0,'major_faults':0} for i,k in enumerate(['python','browser','renderer','driver'])},
                'cgroup_cpu':{'throttled_usec':0,'nr_throttled':0,'usage_usec':0}}
    d={'protocol':PROTOCOL,'native_hooks_installed':False,'full_trace_enabled':False,
       'pids':dict(zip(['python','browser','renderer','driver'],[1,2,3,4])),
       'ticks_per_second':100,'initial':snapshot(0),'phases':[]};p['control_timing']=d
    t=10
    for i,mode in enumerate(SCHEDULE):
        s={'index':i,'fixture_mode':mode,'begin_ns':t,'dom_before_sha256':EXPECTED_DOM[mode],
           'dom_after_sha256':EXPECTED_DOM[mode],'censuses':[],'navigation_timing':{}}
        for j,group in enumerate(['avatar:0','avatar:1','other:0','other:1']):
            tag='path' if mode=='svg' else 'span' if mode=='dom' and group.startswith('other') else 'div'
            s['censuses'].append({'phase':f'census:{i}:{group}','result':{'count':32,'fixture_count':3000,
                'counts':[1]*32,'tags':[tag]*32,'selector_queries':(1 if j<2 else 2) if mode=='dom' else 1}})
        for name in PHASES:
            t+=5;duration=220_000_000 if name=='fixed_wait' else 1_000_000
            d['phases'].append({'index':i,'phase':name,'before':snapshot(t),'begin_ns':t+2,'end_ns':t+2+duration,'after':snapshot(t+3+duration)})
            t+=5+duration
        s['end_ns']=t+2;t+=10;p['stages'].append(s)
    return p


def test_complete_diagnostic_never_qualifies_timing():
    result=validate_capture(capture())
    assert len(result['stages'])==12 and result['throttle_ms']==0
    assert result['phase_ms']['fixed_wait']==2640
    assert 'No corrected or acceptance timing' in result['limitations']


@pytest.mark.parametrize('bad',['phase','missing','overlap','short_wait','pid','reset','injection','fixture','census','history','clock'])
def test_invalid_control_diagnostic_is_rejected(bad):
    p=capture();d=p['control_timing'];row=d['phases'][0]
    if bad=='phase':row['phase']='census'
    if bad=='missing':d['phases'].pop()
    if bad=='overlap':row['before']['end_ns']=row['end_ns']+1
    if bad=='short_wait':d['phases'][1]['end_ns']=d['phases'][1]['begin_ns']+1
    if bad=='pid':d['pids']['renderer']=10
    if bad=='reset':row['after']['processes']['renderer']['start_ticks']=99
    if bad=='injection':d['native_hooks_installed']=True
    if bad=='fixture':p['stages'][0]['dom_before_sha256']='changed'
    if bad=='census':p['stages'][0]['censuses'][0]['result']['counts'][0]=0
    if bad=='history':p['history']={'events':[{}]}
    if bad=='clock':d['ticks_per_second']=0
    with pytest.raises(ValueError):validate_capture(p)


def test_stat_parser_handles_spaces_and_parentheses_in_comm():
    fields=['R']+list(map(str,range(1,50)))
    parsed=process_stat('42 (a complicated ) name) '+' '.join(fields))
    assert parsed['start_ticks']==19 and parsed['user_ticks']==11
    assert key_values('usage_usec 4\nnr_throttled 2\n')=={'usage_usec':4,'nr_throttled':2}


def test_failing_operation_retains_brackets_and_snapshots(monkeypatch):
    t=Timing();monkeypatch.setattr(t,'snapshot',lambda:{'marker':True})
    def fail():raise RuntimeError('capture failed')
    with pytest.raises(RuntimeError):t.measure(0,'navigation',fail)
    row=t.data['phases'][0]
    assert row['before']==row['after']=={'marker':True} and row['begin_ns']<=row['end_ns']
