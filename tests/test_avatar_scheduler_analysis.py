import copy
import pytest
from scripts.avatar_baseline.analyze_scheduler import scheduler_observation
from scripts.avatar_baseline.analyze_navigation_light import calibration_gate
from tests.avatar_scheduler_probe import parse_stat


def sample(t, count):
    return {'begin_ns':t,'end_ns':t+10,'reader_cpu_ns':1,'errors':[],
            'cgroup_cpu':{'usage_usec':count*10,'nr_periods':count,'nr_throttled':count,'throttled_usec':count*2},
            'tasks':[{'pid':42,'stat':{'state':'R','start_ticks':123,'user_ticks':count,'system_ticks':count,
                                     'minor_faults':count,'major_faults':0},
                      'schedstat':{'runtime_ns':count*100,'wait_ns':count*20,'timeslices':count}}]}


def fixture():
    return {'scheduler_environment':{'main_pid':42},'navigation_begin_ns':1000,'navigation_end_ns':21000,
            'scheduler_edges':[sample(900,0),sample(21100,21)],
            'samples':[{'scheduler':sample(1800+i*1000,i+1)} for i in range(20)],
            'navigation_intervals':[{'mount':i+1,'begin_ns':1000+i*1000,'goto_end_ns':1300+i*1000,'wait_end_ns':1500+i*1000} for i in range(20)]}


def test_scheduler_brackets_preserve_all_intervals():
    r=scheduler_observation(fixture())
    assert r['cgroup_delta']['nr_throttled']==21
    assert r['tasks'][0]['schedstat_delta']['wait_ns']==420
    assert len(r['navigation'])==20 and len(r['sample_steps'])==21
    assert all(n['bracket_ns'][0] <= n['begin_ns'] <= n['wait_end_ns'] <= n['bracket_ns'][1] for n in r['navigation'])


@pytest.mark.parametrize('change,match',[
    (lambda p:p['samples'][1]['scheduler']['cgroup_cpu'].update(nr_throttled=0),'counter reset'),
    (lambda p:p['samples'][1]['scheduler']['tasks'][0]['stat'].update(start_ticks=999),'PID reused'),
    (lambda p:p['samples'][1]['scheduler'].update(begin_ns=0),'Overlapping'),
    (lambda p:p['samples'][1]['scheduler'].update(errors=['unavailable']),'Missing cgroup'),
    (lambda p:p['navigation_intervals'].pop(),'Missing navigation'),
    (lambda p:p['scheduler_edges'][1].update(begin_ns=0),'bracket'),
    (lambda p:p['samples'][1]['scheduler'].update(reader_cpu_ns=9999),'reader CPU'),
])
def test_invalid_scheduler_evidence_rejected(change,match):
    p=fixture();change(p)
    with pytest.raises(ValueError,match=match):scheduler_observation(p)


def test_exited_task_is_reported_not_invented():
    p=fixture();p['samples'][1]['scheduler']['tasks'][0]={'pid':42,'error':'exited'}
    r=scheduler_observation(p)
    assert r['task_read_errors']==[{'pid':42,'error':'exited'}]


def test_comm_with_parentheses_and_spaces_is_parsed():
    fields=['R']+[str(i) for i in range(1,40)]
    p=parse_stat('42 (name ) with space) '+' '.join(fields))
    assert p['user_ticks']==11 and p['system_ticks']==12 and p['start_ticks']==19


def test_new_reader_budget_does_not_relax_prior_gates():
    c=[{'index':i,'status':'valid_capture','navigation_ms':1000,'overhead_fraction':0,'max_rotation_ms':0,
        'scheduler':{'reader_cpu_fraction':.001}} for i in range(4)]
    assert not calibration_gate(c)
    c[2]['scheduler']['reader_cpu_fraction']=.011
    assert any('reader CPU' in e for e in calibration_gate(c))


def test_missing_main_thread_edge_fails_integrity():
    p=fixture();p['scheduler_edges'][0]['tasks']=[]
    with pytest.raises(ValueError,match='Missing main-thread'):scheduler_observation(p)
