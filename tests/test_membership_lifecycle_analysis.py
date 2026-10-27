from copy import deepcopy
import pytest
from scripts.avatar_baseline import analyze_membership_lifecycle as analysis


def test_pagehide_completeness_and_no_persisted_document():
    events = [{'index': i, 'persisted': False} for i in range(11)]
    analysis.lifecycle_events(events)
    for bad in [events[:-1], [*events[:-1], events[0]]]:
        with pytest.raises(ValueError, match='history'): analysis.lifecycle_events(bad)
    bad = deepcopy(events); bad[0]['persisted'] = True
    with pytest.raises(ValueError, match='persisted'): analysis.lifecycle_events(bad)


def specimen(monkeypatch):
    membership = {'status': 'capability_failed', 'duration_ms': 10,
                  'errors': ['No labelled page generation observed returning to pool'],
                  'matched_receiver_records': 6144, 'receiver_records': 6144, 'mixed_group_generations': 12}
    monkeypatch.setattr(analysis, 'inspect', lambda p: membership)
    p = {'protocol': 'native-membership-lifecycle-v9', 'back_forward_cache_disabled': True, 'lifecycle_transport': 'same-origin-beacon', 'census_transport': 'navigation-armed-four-fixed-groups',
         'begin_ns': 0, 'end_ns': 10000000, 'pid': 7, 'mode': 'probe',
         'lifecycle_events': [{'index': i, 'persisted': False, 'received_ns': 100000+i*500000} for i in range(11)],
         'stages': [], 'history': {'offsets': {**analysis.receiver_offsets(analysis.PROTOCOL), **analysis.EXTRA_OFFSETS}, 'events': []},
         'before': {'name': 'before', 'begin_ns': 1000, 'end_ns': 2000},
         'after': {'name': 'after', 'begin_ns': 10001000, 'end_ns': 10002000},
         'trace_completion': {'dataLossOccurred': False}, 'transfer_begin_ns': 10003000, 'transfer_end_ns': 10004000}
    trace = {'traceEvents': [{'name': 'clock_sync', 'ts': 1, 'args': {'sync_id': 'before'}},
                             {'name': 'clock_sync', 'ts': 10001, 'args': {'sync_id': 'after'}}]}
    for i in range(12):
        offset = i*500000
        p['stages'].append({'index': i, 'begin_ns': offset+2000, 'end_ns': offset+5000, 'censuses': [{'begin_ns': offset+2100, 'end_ns': offset+2200} for _ in range(4)], 'batch_census_interval_ns': [offset+2100,offset+2200],
            'heap': {'value': {'usedSize': 1000}, 'interval_ns': [offset+3000, offset+3500]},
            'dom': {'value': {'documents': i+1, 'nodes': 100}, 'interval_ns': [offset+3600, offset+4000]}})
        p['history']['events'].append({'kind': 'shutdown', 'begin_ns': offset+4000,
            'callback_ready_ns': offset+4001, 'returned_ns': offset+4002, 'phase': f'navigation:{i}'})
        trace['traceEvents'].append({'pid': 7, 'name': 'Document::shutdown', 'ts': offset/1000+4, 'ph': 'X', 'dur': 1})
    for i in range(11):
        trace['traceEvents'].append({'pid': 7, 'name': 'TimeStamp', 'ts': 100+i*500,
                                    'args': {'data': {'message': f'membership-pagehide:{i}:false'}}})
    return p, trace, membership


def test_absent_gc_can_be_observed_without_waiving_reclamation(monkeypatch):
    p, trace, _ = specimen(monkeypatch)
    p['protocol']='native-membership-lifecycle-v7'
    p['census_transport']='one-evaluate-four-fixed-groups'
    result = analysis.analyze(p, trace)
    assert not result['errors'] and result['gc_events'] == []
    assert result['membership_status'] == 'capability_failed'
    assert result['membership_qualification_waived'] is False
    assert result['membership_errors'] == ['No labelled page generation observed returning to pool']


@pytest.mark.parametrize('failure', ['flag', 'lost', 'forced', 'marker', 'native_shutdown'])
def test_lifecycle_integrity_failures_remain_visible(monkeypatch, failure):
    p, trace, _ = specimen(monkeypatch)
    if failure == 'flag': p['back_forward_cache_disabled'] = False
    if failure == 'lost': p['trace_completion']['dataLossOccurred'] = True
    if failure == 'forced': trace['traceEvents'].append({'args': {'forced': True}})
    if failure == 'marker': trace['traceEvents'].pop()
    if failure == 'native_shutdown':
        p['history']['events'].pop()
        assert analysis.analyze(p, trace)['errors']
    else:
        with pytest.raises(ValueError): analysis.analyze(p, trace)


def test_other_membership_failure_is_not_excused(monkeypatch):
    p, trace, membership = specimen(monkeypatch)
    membership['errors'].append('Observed-request receiver coverage below 90%')
    assert 'Live membership coverage failed independently of reclamation' in analysis.analyze(p, trace)['errors']


def test_batch_is_counted_once_and_mismatch_cannot_reduce_cost(monkeypatch):
    p, _, _ = specimen(monkeypatch)
    assert analysis.census_costs(p) == [100]*12
    bad = deepcopy(p); bad['stages'][0]['censuses'][0]['end_ns'] -= 1
    with pytest.raises(ValueError, match='mismatch'): analysis.census_costs(bad)
    bad = deepcopy(p); bad['stages'][0]['batch_census_interval_ns'][1] += 50000
    with pytest.raises(ValueError): analysis.census_costs(bad)
    old = deepcopy(p); old['protocol'] = 'native-membership-lifecycle-v4'
    assert len(analysis.census_costs(old)) == 48


def test_mixed_protocol_requires_natural_collection_even_with_returning_pages(monkeypatch):
    p, trace, membership=specimen(monkeypatch)
    membership.update(status='capability_passed',errors=[])
    result=analysis.analyze(p,trace)
    assert 'Missing natural major/sweep coverage in mixed fixture' in result['errors']
    trace['traceEvents'] += [
        {'pid':7,'tid':7,'name':'MajorGC','ts':100,'dur':5,'ph':'X','args':{}},
        {'pid':7,'tid':7,'name':'CppGC.IncrementalSweep','ts':106,'dur':5,'ph':'X','args':{}}]
    assert not analysis.analyze(p,trace)['errors']


def test_local_selector_reuse_counts_are_verified():
    p={'selection_policy':'per-evaluate-selector-cache','stages':[
      {'fixture_mode':'dom','censuses':[{'result':{'selector_queries':n}} for n in [1,1,2,2]]},
      {'fixture_mode':'svg','censuses':[{'result':{'selector_queries':1}} for _ in range(4)]}]}
    analysis.validate_selector_reuse(p)
    bad=deepcopy(p);bad['stages'][1]['censuses'][-1]['result']['selector_queries']=4
    with pytest.raises(ValueError,match='query count'):analysis.validate_selector_reuse(bad)
    bad=deepcopy(p);bad['selection_policy']='persistent-global-cache'
    with pytest.raises(ValueError,match='policy'):analysis.validate_selector_reuse(bad)


def test_deferred_pointer_descriptor_is_required_for_its_version(monkeypatch):
    from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE
    p,trace,membership=specimen(monkeypatch)
    p['protocol']='native-membership-lifecycle-v11';p['selection_policy']='per-evaluate-selector-cache'
    for stage,mode in zip(p['stages'],SCHEDULE):
        stage['fixture_mode']=mode
        for c,n in zip(stage['censuses'],[1,1,2,2] if mode=='dom' else [1,1,1,1]):c['result']={'selector_queries':n}
    with pytest.raises(ValueError,match='encoding'):analysis.analyze(p,trace)
    p['history']['address_encoding']='deferred-native-pointer-v1'
    membership.update(status='capability_passed',errors=[])
    trace['traceEvents'] += [
        {'pid':7,'tid':7,'name':'MajorGC','ts':100,'dur':5,'ph':'X','args':{}},
        {'pid':7,'tid':7,'name':'CppGC.IncrementalSweep','ts':106,'dur':5,'ph':'X','args':{}}]
    assert not analysis.analyze(p,trace)['errors']
