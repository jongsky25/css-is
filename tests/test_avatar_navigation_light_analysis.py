import copy
import gzip
import json
import pytest
from scripts.avatar_baseline.analyze_navigation_light import calibration_gate, inspect_capture


def fixture(tmp_path, version=3):
    snap = {'renderer_memory_detail': [{'pid': 42, 'status': {'VmRSS': 100}}]}
    p = {'protocol': f'navigation-light-v{version}', 'acceptance': False, 'forced_gc': False, 'mode': 'trace',
         'snapshots': 13, 'mount': 20, 'navigation_begin_ns': 0, 'navigation_end_ns': 20_000_000_000,
         'checkpoints': [{'mount': m, 'snapshot': copy.deepcopy(snap), 'interval_ns': [m*10**8, m*10**8+10]} for m in [1,5,10,15,20]],
         'rotations': [{'mount': m, 'begin_ns': m*10**9, 'end_ns': m*10**9+100} for m in ([0,5,10,15] if version == 3 else [0,10])],
         'segments': [], 'samples': [], 'endpoint_request': {'success': True}}
    segments = 4 if version == 3 else 2
    span = 20_000_000 // segments
    for i in range(segments+1):
        start = i*span + (1_000_000 if i == segments else 10)
        end = start+span-100_000
        markers = [(f'segment-{i}-before', start), (f'segment-{i}-after', end)]
        if i == segments:
            markers += [('endpoint-before', start+10), ('endpoint-after', end-10)]
        events = [{'name': 'clock_sync', 'ts': t, 'args': {'sync_id': n}} for n,t in markers]
        if i < segments:
            events.append({'name': 'CommitLoad', 'pid': 42, 'args': {'data': {'url': 'http://127.0.0.1:123/'}}})
        else:
            events.append({'ph': 'v', 'pid': 42, 'ts': start+20, 'id': 'renumbered', 'args': {'dumps': {'allocators': {'blink_gc/main': {'attrs': {'size': {'units': 'bytes', 'value': '1000'}}}}}}})
        with gzip.open(tmp_path/f'trace-{i}.json.gz', 'wt') as f:
            json.dump({'traceEvents': events}, f)
        segment = {'number': i, 'start_ns': start*1000-10, 'trace_file': f'trace-{i}.json.gz', 'completion': {'dataLossOccurred': False}}
        for side,t in [('before',start),('after',end)]:
            segment[side] = {'name': f'segment-{i}-{side}', 'begin_ns': t*1000-1, 'end_ns': t*1000+1}
        p['segments'].append(segment)
        if i == segments:
            p['endpoint_before'] = {'begin_ns': (start+10)*1000-1, 'end_ns': (start+10)*1000+1}
            p['endpoint_after'] = {'begin_ns': (end-10)*1000-1, 'end_ns': (end-10)*1000+1}
    for m in range(1,20):
        value = (100 if m%2 else 90)*2**20
        p['samples'].append({'begin_ns': m*10**9, 'end_ns': m*10**9+100,
            'renderers': [{'pid': 42, 'status': {'VmRSS': value, 'RssAnon': value, 'RssFile': 0, 'RssShmem': 0, 'VmSwap': 0}}]})
    raw = [{'navigation_trend': [{'mount': c['mount'], **copy.deepcopy(c['snapshot'])} for c in p['checkpoints']]}]
    return p, raw


def test_sealed_capture_and_post_workload_dump(tmp_path):
    p, raw = fixture(tmp_path)
    result = inspect_capture(tmp_path,p,raw)
    assert result['endpoint']['allocators']['blink_gc/main']['size'] == 4096
    assert len(result['rss_drops_at_least_5_mib']) == 9
    assert any(not d['trace_coverage'] for d in result['rss_drops_at_least_5_mib'])
    assert all(not d['overlapping_gc_events'] for d in result['rss_drops_at_least_5_mib'])


@pytest.mark.parametrize('mutation,match', [
    (lambda p,r: p['segments'][1]['completion'].update(dataLossOccurred=True), 'Trace data loss'),
    (lambda p,r: r[0]['navigation_trend'][0].update(extra=1), 'rewritten'),
    (lambda p,r: p['segments'][4].update(start_ns=0), 'precedes'),
    (lambda p,r: p['samples'][2].update(begin_ns=0), 'status intervals'),
    (lambda p,r: p['checkpoints'].pop(), 'Incomplete'),
    (lambda p,r: p['samples'][2]['renderers'][0].update(pid=99), 'App PID'),
])
def test_invalid_capture_rejected(tmp_path,mutation,match):
    p,raw = fixture(tmp_path)
    mutation(p,raw)
    with pytest.raises(ValueError,match=match):
        inspect_capture(tmp_path,p,raw)


def test_dump_in_navigation_rejected(tmp_path):
    p,raw=fixture(tmp_path)
    path=tmp_path/'trace-0.json.gz'
    events=json.load(gzip.open(path,'rt'))
    events['traceEvents'].append({'args':{'dumps':{'allocators':{}}}})
    with gzip.open(path,'wt') as f:json.dump(events,f)
    with pytest.raises(ValueError,match='inside measured'):inspect_capture(tmp_path,p,raw)


def cohorts():
    return [{'index': i, 'status': 'valid_capture', 'navigation_ms': 10_000,
             'overhead_fraction': .01, 'max_rotation_ms': 30} for i in range(4)]


def test_calibration_requires_both_orders_and_intact_controls():
    c=cohorts()
    assert calibration_gate(c)==[]
    c[2]['navigation_ms']=12_001
    assert calibration_gate(c)
    c=cohorts();c[3]['status']='invalid_capture'
    assert calibration_gate(c)


@pytest.mark.parametrize('key,value',[('overhead_fraction',.051),('max_rotation_ms',251)])
def test_explicit_probe_overhead_limit(key,value):
    c=cohorts();c[1][key]=value
    assert calibration_gate(c)


def test_control_variance_cannot_be_ignored():
    c=cohorts();c[3]['navigation_ms']=12_001
    assert 'Control navigation duration varies more than 20%' in calibration_gate(c)


def test_v4_two_segments_preserve_all_samples(tmp_path):
    p,raw=fixture(tmp_path,version=4)
    result=inspect_capture(tmp_path,p,raw)
    assert len(result['trace_segments'])==3
    assert len(result['rss_drops_at_least_5_mib'])==9
    assert result['endpoint']['allocators']['blink_gc/main']['size']==4096
