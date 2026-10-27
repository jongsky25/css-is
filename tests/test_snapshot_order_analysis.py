from copy import deepcopy
from pathlib import Path
import pytest
from scripts.avatar_baseline.analyze_snapshot_order import validate_calls, gate
from tests.avatar_snapshot_timing import SnapshotTiming


def specimen():
    names = ['page.evaluate', 'cdp:SystemInfo.getProcessInfo', '/proc/7/status',
             '/proc/7/status', '/proc/7/smaps_rollup', 'cdp:Runtime.getHeapUsage',
             'cdp:Memory.getDOMCounters', 'cdp:Runtime.evaluate']
    return {'snapshot': {'renderer_memory_detail': [{'pid': 7}]}, 'interval_ns': [0, 100],
            'calls': [{'call': n, 'begin_ns': 2*i, 'end_ns': 2*i+1} for i,n in enumerate(names)]}


def test_component_coverage_rejects_missing_or_reordered_reads():
    s = specimen(); validate_calls(s)
    for i in range(len(s['calls'])):
        bad = deepcopy(s); bad['calls'].pop(i)
        with pytest.raises(ValueError, match='snapshot calls'):
            validate_calls(bad)
    bad = deepcopy(s); bad['calls'][2:4] = reversed(bad['calls'][2:4])
    # Equal call names remain ordered by their brackets.
    with pytest.raises(ValueError, match='bracket'):
        validate_calls(bad)


@pytest.mark.parametrize('mutation', ['outside', 'overlap', 'exception'])
def test_component_coverage_rejects_invalid_bounds_and_errors(mutation):
    s = specimen()
    if mutation == 'outside': s['calls'][-1]['end_ns'] = 101
    if mutation == 'overlap': s['calls'][1]['begin_ns'] = 0
    if mutation == 'exception': s['calls'][0]['error_type'] = 'RuntimeError'
    with pytest.raises(ValueError, match='bracket'):
        validate_calls(s)


def test_calibration_checks_both_pairs_controls_and_all_observation_costs():
    rows = [{'navigation_ms': 1000, 'observation_fraction_bound': .01, 'max_observation_ms': 10} for _ in range(4)]
    assert not gate(rows)
    for index in range(4):
        bad = deepcopy(rows); bad[index]['observation_fraction_bound'] = .051
        assert gate(bad)
        bad = deepcopy(rows); bad[index]['max_observation_ms'] = 251
        assert gate(bad)
    for index in [1, 2, 3]:
        bad = deepcopy(rows); bad[index]['navigation_ms'] = 1201
        assert gate(bad)
    assert gate(rows[:3])
    assert gate([{'error': 'failed'}, *rows[1:]])


def test_wrapper_preserves_result_arguments_exceptions_and_call_count(monkeypatch, tmp_path):
    class Page:
        def evaluate(self, expression):
            return expression
    class Session:
        def __init__(self): self.requests = []
        def send(self, method, args=None):
            self.requests.append((method, args))
            if method == 'fail': raise LookupError('preserved')
            return {'original': args}
    timing = SnapshotTiming(monkeypatch, Page, Session)
    page = Page(); session = Session()
    assert session.send('outside') == {'original': None}
    def capture():
        assert page.evaluate('expression') == 'expression'
        assert session.send('Runtime.getHeapUsage', {'x': 1}) == {'original': {'x': 1}}
        Path('/proc/self/status').read_text()
        with pytest.raises(LookupError): session.send('fail')
        return object()
    value, p = timing.capture(capture)
    assert value is not None
    assert [c['call'] for c in p['calls']] == ['page.evaluate', 'cdp:Runtime.getHeapUsage', '/proc/self/status', 'cdp:fail']
    assert p['calls'][-1]['error_type'] == 'LookupError'
    assert session.requests == [('outside', None), ('Runtime.getHeapUsage', {'x': 1}), ('fail', None)]
    assert timing.active is None
    with pytest.raises(ValueError):
        timing.capture(lambda: (_ for _ in ()).throw(ValueError('same')))
    assert timing.active is None
