import copy
import pytest
from scripts.avatar_baseline.native_handle_buffer import analyze, validate_header, OFFSETS
from scripts.avatar_baseline.element_membership_lifecycle import BUILD


def fixture():
    def e(number,kind,begin,end,**values):
        return dict(id=number,kind=kind,begin_ns=begin,ready_ns=begin,end_ns=end,thread=1,
                    a0='0x0',a1='0x0',value='0x0',caller_offset=123,**values)
    events=[e(1,'per_ctor',10,90),e(2,'global_create',20,21),
            e(3,'global_create',95,96),e(4,'global_weak_field',110,111),
            e(5,'gc_epilogue',200,201),e(6,'global_release',210,211)]
    events[1].update(value='0x100',caller_offset=0xfd4bb86)
    events[2].update(value='0x200',caller_offset=0x1234)
    events[3]['a1']='0x100';events[5]['a0']='0x200'
    h=dict(protocol='native-handle-buffer-v1',pid=123,offsets=OFFSETS,record_size=72,
           capacity=50000,limit=50000,dropped=0,pending=0,clock_domain='CLOCK_MONOTONIC',
           toolchain='internal',storage=dict(canary_verified=True,state_bytes=7200100,allocated_bytes=7200256),
           snapshot_end_ns=999,events=events,per_event_javascript=False,runtime_subscription_added=False,
           snapshot_requested=False,gc_requested=False)
    journal=dict(native=h,export_begin_ns=990,export_end_ns=1000,messages=[],
                 clock_samples=[dict(begin_ns=1,native_ns=2,end_ns=3)]*20)
    capture=dict(pid=123,build_id=BUILD,stages=[dict(index=0,begin_ns=1,end_ns=170),dict(index=1,begin_ns=171,end_ns=300)])
    return journal,capture


def test_unscoped_birth_has_caller_and_weak_candidates_are_preserved():
    journal,capture=fixture();a=analyze(journal,capture)
    point=a['gc_epilogues'][0]
    assert point['old_unreleased_handles']==[2,3]
    assert point['old_without_observed_weakening']==[3]
    assert point['old_unreleased_by_caller']=={str(0xfd4bb86):1,str(0x1234):1}
    assert a['generations'][1]['role']=='unscoped'
    assert a['generations'][0]['role']=='V8PerContextData::context_'
    assert a['instrument_qualified'] is False


def test_released_slot_can_be_reused_without_inheriting_previous_birth():
    journal,capture=fixture();h=journal['native']
    e=copy.deepcopy(h['events'][2]);e.update(id=7,begin_ns=220,ready_ns=220,end_ns=221)
    h['events'].append(e)
    point=copy.deepcopy(h['events'][4]);point.update(id=8,begin_ns=240,ready_ns=240,end_ns=241)
    h['events'].append(point)
    a=analyze(journal,capture)
    assert a['generations'][-1]['creation']==7
    assert a['gc_epilogues'][-1]['old_unreleased_handles']==[2]


@pytest.mark.parametrize('mutation',['drop','pending','clock','size','canary','offset','sequence','overlap','caller'])
def test_fail_closed_on_incomplete_or_ambiguous_native_evidence(mutation):
    journal,capture=fixture();journal=copy.deepcopy(journal);h=journal['native']
    if mutation=='drop':h['dropped']=1
    if mutation=='pending':h['pending']=1
    if mutation=='clock':h['events'][0]['ready_ns']=999
    if mutation=='size':h['record_size']=80
    if mutation=='canary':h['storage']['canary_verified']=False
    if mutation=='offset':h['offsets']['global_create']+=1
    if mutation=='sequence':h['events'][1]['id']=99
    if mutation=='overlap':h['events'][2]['value']='0x100'
    if mutation=='caller':h['events'][1]['caller_offset']=0x123
    with pytest.raises(ValueError):analyze(journal,capture)


def test_preexisting_transition_remains_explicitly_unknown():
    journal,capture=fixture();journal['native']['events'][5]['a0']='0x999'
    assert analyze(journal,capture)['unknown_preexisting_transitions']=={'global_release':1}
