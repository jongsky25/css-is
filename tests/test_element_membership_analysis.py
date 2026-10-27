from copy import deepcopy
import pytest
from scripts.avatar_baseline import analyze_element_membership as analysis


def event(kind, address, begin, end=None, **kwargs):
    return {'kind': kind, 'address': hex(address), 'backend': '0x10' if kind != 'receiver' else None,
            'begin_ns': begin, 'callback_ready_ns': begin+1, 'returned_ns': end or begin+2,
            'phase': 'navigation:0', **kwargs}


def test_receiver_join_respects_pool_return_and_address_reuse():
    events = [event('allocate', 0x20000, 10), event('pool', 0x20000, 100),
              event('allocate', 0x20000, 200),
              event('receiver', 0x20010, 50, phase='old'),
              event('receiver', 0x20010, 150, phase='gap'),
              event('receiver', 0x20010, 250, phase='new')]
    spans, unknown = analysis.generations(events)
    rows = analysis.join_receivers(events, spans)
    assert unknown == 0
    assert [r['generation'] for r in rows] == [0, None, 1]
    assert spans[0]['labels'] == ['old'] and spans[1]['labels'] == ['new']


def test_unknown_pool_return_and_unobserved_page_are_explicit():
    spans, unknown = analysis.generations([event('pool', 0x20000, 10)])
    rows = analysis.join_receivers([event('receiver', 0x40010, 50)], spans)
    assert unknown == 1 and rows[0]['coverage'] == 'preexisting_or_unobserved'


def test_ambiguous_page_lifetimes_and_non_page_address_rejected():
    with pytest.raises(ValueError, match='Overlapping'):
        analysis.generations([event('allocate', 0x20000, 10), event('allocate', 0x20000, 20)])
    with pytest.raises(ValueError, match='base'):
        analysis.generations([event('allocate', 0x20010, 10)])
    spans = [{'base': 0x20000, 'begin_ns': 1, 'end_ns': None, 'labels': [], 'generation': i} for i in [0, 1]]
    with pytest.raises(ValueError, match='Ambiguous'):
        analysis.join_receivers([event('receiver', 0x20010, 50)], spans)


def specimen(monkeypatch):
    monkeypatch.setattr(analysis, 'COUNT', 2); monkeypatch.setattr(analysis, 'STAGES', 1)
    events = [event('allocate', 0x20000, 10)]
    censuses = []
    for i, (group, repeat) in enumerate((g,r) for g in ['avatar','other'] for r in [0,1]):
        label = f'census:0:{group}:{repeat}'; start = 50+i*20
        censuses.append({'phase': label, 'begin_ns': start, 'end_ns': start+19,
                         'result': {'count': 2, 'counts': [1,1]}})
        for node in range(2):
            address = 0x20010 + node*16 + (64 if group == 'other' else 0)
            events.append(event('receiver', address, start+2+node*3, phase=label))
    events.append(event('pool', 0x20000, 200))
    return {'status': 'captured', 'protocol': 'native-element-membership-v1', 'acceptance': False,
            'forced_gc': False, 'build_id': analysis.BUILD, 'browser_version': '156.0.8078.47',
            'frida_version': '17.5.1', 'count_per_group': 2, 'stage_count': 1, 'mode': 'probe',
            'begin_ns': 1, 'end_ns': 300, 'messages': [],
            'stages': [{'index': 0, 'begin_ns': 20, 'end_ns': 180, 'censuses': censuses,
                        'dom_before_sha256': 'same', 'dom_after_sha256': 'same'}],
            'history': {'offsets': analysis.OFFSETS, 'page_size': analysis.PAGE_SIZE, 'dropped': 0, 'events': events}}


def test_known_disjoint_receivers_repeat_and_mixed_page_does_not_mean_exclusive_owner(monkeypatch):
    p = specimen(monkeypatch)
    # Expand the time window so the explicit callback cost stays below 5%.
    p['end_ns'] = 1000
    result = analysis.inspect(p)
    assert result['status'] == 'capability_passed'
    assert result['mixed_group_generations'] == 1
    assert result['labelled_returned_generations'] == 1
    assert result['matched_fraction'] == 1


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'different_repeat', 'dom', 'dropped', 'outside'])
def test_known_fixture_coverage_fails_closed(monkeypatch, failure):
    p = specimen(monkeypatch); events = p['history']['events']
    if failure == 'missing': events.pop(1)
    if failure == 'duplicate': events[2]['address'] = events[1]['address']
    if failure == 'different_repeat': events[3]['address'] = '0x200a0'
    if failure == 'dom': p['stages'][0]['dom_after_sha256'] = 'changed'
    if failure == 'dropped': p['history']['dropped'] = 1
    if failure == 'outside': events[1]['begin_ns'] = 1
    with pytest.raises(ValueError): analysis.inspect(p)


def test_missing_reclamation_or_request_coverage_is_failure_not_extrapolated(monkeypatch):
    p = specimen(monkeypatch); p['end_ns'] = 1000
    p['history']['events'] = [e for e in p['history']['events'] if e['kind'] != 'pool']
    result = analysis.inspect(p)
    assert result['status'] == 'capability_failed'
    assert any('returning to pool' in e for e in result['errors'])
    p['history']['events'] = [e for e in p['history']['events'] if e['kind'] != 'allocate']
    result = analysis.inspect(p)
    assert result['matched_fraction'] == 0
    assert any('below 90%' in e for e in result['errors'])
