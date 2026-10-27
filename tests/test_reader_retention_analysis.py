import pytest
from scripts.avatar_baseline.analyze_reader_retention import (
    clock_bounds, mapped, position, selected_events, union_duration,
)


def event(**kw):
    return dict({'name': 'CppGC.IncrementalSweep', 'pid': 7, 'tid': 8,
                 'ph': 'X', 'ts': 100, 'dur': 20, 'args': {'epoch': 2, 'forced': False}}, **kw)


def test_snapshot_boundary_ambiguity_and_completion_uses_end():
    assert position(event(), [110, 130]) == 'overlap_or_uncertain'
    assert position(event(), [121, 130]) == 'before'
    assert position(event(), [80, 99]) == 'after'
    assert position(event(), [120, 130]) == 'overlap_or_uncertain'


def test_anchor_envelope_retains_both_request_uncertainties():
    segment = {'before': {'name': 'a', 'begin_ns': 1000, 'end_ns': 3000},
               'after': {'name': 'b', 'begin_ns': 10000, 'end_ns': 14000}}
    events = [{'name': 'clock_sync', 'ts': 102, 'args': {'sync_id': 'a'}},
              {'name': 'clock_sync', 'ts': 114, 'args': {'sync_id': 'b'}}]
    clock = clock_bounds(segment, events)
    assert clock['offset_us'] == [99, 104]
    assert mapped([4000, 5000], clock) == [103, 109]
    with pytest.raises(ValueError, match='anchor'):
        clock_bounds(segment, events + [events[0]])


def test_instant_events_are_not_fabricated_durations():
    instant = event(ph='I'); del instant['dur']
    result = selected_events([instant], 7)
    assert result[0]['dur'] == 0 and result[0]['instant_event'] is True
    assert 'dur' not in instant
    bad = event(); del bad['dur']
    with pytest.raises(ValueError, match='interval'):
        selected_events([bad], 7)


def test_forced_gc_rejected_and_other_pids_and_non_gc_events_excluded():
    assert selected_events([event(pid=9), event(name='IsLoading')], 7) == []
    with pytest.raises(ValueError, match='Forced'):
        selected_events([event(args={'forced': True})], 7)


def test_nested_sweep_duration_is_not_summed_and_threads_stay_separate():
    assert union_duration([event(), event(ts=105, dur=5), event(ts=115, dur=10),
                           event(tid=9, ts=105, dur=5)]) == {'8': 25, '9': 5}


@pytest.mark.parametrize('bounds', [[3,2], [1], []])
def test_invalid_intervals_rejected(bounds):
    with pytest.raises(ValueError, match='interval'):
        mapped(bounds, {'offset_us': [0,1]})


def test_no_status_correlation_across_rotation_gap():
    from scripts.avatar_baseline.analyze_reader_retention import analyze_slot
    def seg(n,a,b):
        return {'before': {'name': f'{n}a', 'begin_ns': a*1000, 'end_ns': a*1000},
                'after': {'name': f'{n}b', 'begin_ns': b*1000, 'end_ns': b*1000},
                'completion': {'dataLossOccurred': False}}
    segments = [seg(0,0,100),seg(1,200,300)]
    traces = [[{'name': 'clock_sync', 'ts': t,
                'args': {'sync_id': segments[i][side]['name']}}
               for side,t in [('before',a),('after',b)]]
              for i,(a,b) in enumerate([(0,100),(200,300)])]
    traces[1].append(event(ts=205,dur=10))
    def sample(t,rss):
        return {'begin_ns': t*1000, 'end_ns': (t+1)*1000,
                'renderers': [{'pid': 7, 'status': {'VmRSS': rss, 'RssAnon': rss}}]}
    result = analyze_slot({'segments': segments, 'checkpoints': [],
                           'samples': [sample(90,20),sample(220,10)]}, traces, 7)
    assert result['status_steps'][0]['covered'] is False
    assert result['status_steps'][0]['overlap'] is None
    assert result['segments'][1]['epochs'][0]['whole_sweep_completion_known'] is False
