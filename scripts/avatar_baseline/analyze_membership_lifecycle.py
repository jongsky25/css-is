"""Document disposition versus natural collection; never upgrades membership qualification."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.avatar_baseline.analyze_element_membership import inspect, validate_identity, OFFSETS
from scripts.avatar_baseline.analyze_reader_retention import clock_bounds, mapped, selected_events, position

PROTOCOL = 'native-membership-lifecycle-v6'
SUPPORTED = {f'native-membership-lifecycle-v{i}' for i in [1,2,3,4,5,6]}
EXTRA_OFFSETS = {'shutdown': 0x100208d0, 'destroy': 0x5aa4490, 'release': 0x5ab09d0}
SOURCES = ['scripts/avatar_baseline/element_membership_lifecycle.py',
           'scripts/avatar_baseline/native/element_membership_lifecycle.js',
           'scripts/avatar_baseline/analyze_membership_lifecycle.py',
           'scripts/avatar_baseline/run_membership_lifecycle.py',
           'scripts/avatar_baseline/analyze_element_membership.py',
           'scripts/avatar_baseline/analyze_reader_retention.py']


def lifecycle_events(events):
    if len(events) != 11 or sorted(e['index'] for e in events) != list(range(11)):
        raise ValueError('Incomplete document pagehide history')
    if any(e['persisted'] is not False for e in events):
        raise ValueError('Document persisted in history cache')


def census_costs(p):
    if p['protocol'] not in ['native-membership-lifecycle-v5','native-membership-lifecycle-v6']:
        return [c['end_ns']-c['begin_ns'] for s in p['stages'] for c in s['censuses']]
    if p.get('census_transport') != 'one-evaluate-four-fixed-groups':
        raise ValueError('Wrong batched census transport')
    costs = []
    for s in p['stages']:
        lo, hi = s['batch_census_interval_ns']
        if len(s['censuses']) != 4 or any([c['begin_ns'],c['end_ns']] != [lo,hi] for c in s['censuses']):
            raise ValueError('Batched census interval mismatch')
        if not s['begin_ns'] <= lo <= hi <= s['end_ns']:
            raise ValueError('Batch outside measured stage')
        costs.append(hi-lo)
    return costs


def analyze(p, trace=None):
    if p['protocol'] not in SUPPORTED or p['back_forward_cache_disabled'] is not True:
        raise ValueError('Wrong lifecycle protocol or BFCache launch flag')
    expected_transport = 'same-origin-beacon' if p['protocol'] in ['native-membership-lifecycle-v4', 'native-membership-lifecycle-v5', PROTOCOL] else 'cdp-runtime-binding'
    if p['protocol'] in ['native-membership-lifecycle-v3', 'native-membership-lifecycle-v4', 'native-membership-lifecycle-v5', PROTOCOL] and p.get('lifecycle_transport') != expected_transport:
        raise ValueError('Wrong lifecycle event transport')
    lifecycle_events(p['lifecycle_events'])
    native = p.get('history'); begin, end = p['begin_ns'], p['end_ns']
    if any(not begin <= e['received_ns'] <= end for e in p['lifecycle_events']):
        raise ValueError('Pagehide delivery outside measured window')
    adapted = deepcopy(p); adapted['protocol'] = 'native-element-membership-v3' if p['protocol'] == 'native-membership-lifecycle-v6' else 'native-element-membership-v2'
    if native:
        if native['offsets'] != {**OFFSETS, **EXTRA_OFFSETS}:
            raise ValueError('Unexpected lifecycle hooks')
        for e in native['events']:
            if e['kind'] not in native['offsets'] or not 0 < e['begin_ns'] <= e['callback_ready_ns'] <= e['returned_ns']:
                raise ValueError('Malformed lifecycle native event')
        adapted['history']['offsets'] = OFFSETS
        adapted['history']['events'] = [e for e in native['events'] if e['kind'] in OFFSETS
            and begin <= e['begin_ns'] <= e['returned_ns'] <= end]
    membership = inspect(adapted)
    # Preserve the original failing qualification independently of this attribution diagnostic.
    result = {'mode': p['mode'], 'duration_ms': membership['duration_ms'],
              'membership_status': membership['status'], 'membership_errors': membership['errors'],
              'membership_qualification_waived': False, 'errors': [], 'stages': []}
    for stage in p['stages']:
        for name in ['heap', 'dom']:
            lo, hi = stage[name]['interval_ns']
            if not stage['begin_ns'] <= lo <= hi <= stage['end_ns']:
                raise ValueError('Counter interval outside stage')
        result['stages'].append({'index': stage['index'], 'documents': stage['dom']['value']['documents'],
            'nodes': stage['dom']['value']['nodes'], 'used_heap_bytes': stage['heap']['value']['usedSize']})
    costs = census_costs(p)
    costs += [s[k]['interval_ns'][1]-s[k]['interval_ns'][0] for s in p['stages'] for k in ['heap', 'dom']]
    costs += [p.get('trace_setup_ns', 0)]
    if native:
        costs += [e['callback_ready_ns']-e['begin_ns'] for e in native['events']
                  if begin <= e['begin_ns'] <= e['returned_ns'] <= end]
    # Deliberately conservative: census intervals include geometry calls and RPCs;
    # hook preparation inside them is counted again rather than subtracted.
    result['observation_fraction_bound'] = sum(costs)/(end-begin)
    result['maximum_observation_ms'] = max(costs)/1e6
    if result['observation_fraction_bound'] > .05 or result['maximum_observation_ms'] > 250:
        result['errors'].append('Observation bound exceeds 5% or 250ms')
    if p['mode'] == 'control':
        result['status'] = 'valid_control'
        return result
    if p['trace_completion'].get('dataLossOccurred') or not end < p['transfer_begin_ns'] <= p['transfer_end_ns']:
        raise ValueError('Trace loss or transfer inside measurement')
    events = trace['traceEvents']
    if any(e.get('args', {}).get('forced') or e.get('args', {}).get('dumps') for e in events):
        raise ValueError('Forced collection or memory dump')
    clock = clock_bounds(p, events); gc = selected_events(events, p['pid'])
    markers = [e for e in events if e.get('pid') == p['pid'] and e.get('name') == 'TimeStamp'
               and e.get('args', {}).get('data', {}).get('message', '').startswith('membership-pagehide:')]
    expected = {f'membership-pagehide:{i}:false' for i in range(11)}
    if len(markers) != 11 or {e['args']['data']['message'] for e in markers} != expected:
        raise ValueError('Missing/extra native-timeline pagehide markers')
    shutdown_trace = [e for e in events if e.get('pid') == p['pid'] and e.get('name') == 'Document::shutdown']
    measured = [e for e in native['events'] if begin <= e['begin_ns'] <= e['returned_ns'] <= end]
    counts = Counter(e['kind'] for e in measured)
    for s in p['stages']:
        selected = [e for e in measured if e['kind'] == 'shutdown' and e['phase'] == f'navigation:{s["index"]}']
        if not selected: result['errors'].append(f'No native shutdown entry at navigation {s["index"]}')
    if len(shutdown_trace) < 12:
        result['errors'].append('Native shutdown trace coverage incomplete')
    summaries = []
    for stage in p['stages']:
        components = {}
        for name in ['heap', 'dom']:
            bounds = mapped(stage[name]['interval_ns'], clock)
            covered = clock['coverage_us'][0] <= bounds[0] <= bounds[1] <= clock['coverage_us'][1]
            components[name] = {'bounds_us': bounds, 'fully_covered': covered,
                               'gc_overlap': [e for e in gc if position(e, bounds) == 'overlap_or_uncertain']}
            if not covered and stage['index'] != 11:
                result['errors'].append(f'Counter trace coverage incomplete: {stage["index"]}/{name}')
        summaries.append({'index': stage['index'], 'components': components})
    allowed_membership_errors = ['No labelled page generation observed returning to pool']
    if any(e not in allowed_membership_errors for e in membership['errors']):
        result['errors'].append('Live membership coverage failed independently of reclamation')
    result.update(status='valid_lifecycle_capture', native_event_counts=dict(counts),
                  native_events_outside_window=len(native['events'])-len(measured),
                  pagehide_markers=markers, shutdown_trace_events=shutdown_trace,
                  gc_events=gc, gc_event_counts=dict(Counter(e['name'] for e in gc)),
                  counter_order=summaries, clock=clock,
                  matched_receivers=membership['matched_receiver_records'],
                  receiver_records=membership['receiver_records'],
                  mixed_generations=membership['mixed_group_generations'])
    return result


def audit(root, repo, ref):
    plan = json.loads((root/'experiment.json').read_text())
    if plan['protocol'] not in SUPPORTED or plan['harness_commit'] != ref or plan['acceptance'] is not False or plan['order'] != ['control','probe','probe','control'] or len(plan['cohorts']) != 4:
        raise ValueError('Invalid frozen lifecycle schedule')
    result = {'acceptance': False, 'application_qualified': False, 'status': 'diagnostic_failed',
              'errors': [], 'cohorts': [], 'files_verified': 0, 'source_hashes_verified': 0}
    for name in SOURCES:
        if (root/'harness'/name).read_bytes() != subprocess.check_output(['git','show',ref+':'+name],cwd=repo):
            raise ValueError('Archived harness mismatch')
        result['source_hashes_verified'] += 1
    for index, entry in enumerate(plan['cohorts']):
        row = {'index': index}; result['cohorts'].append(row)
        try:
            mode = plan['order'][index]; folder = root/f'{index}-{mode}'
            if entry['index'] != index or entry['mode'] != mode or entry['exit_code']:
                raise ValueError('Failed/mismatched cohort')
            required = {'identity.json','capture.json.gz','runner.txt'} | ({'trace.json.gz'} if mode == 'probe' else set())
            if not required <= entry['files_sha256'].keys(): raise ValueError('Missing evidence')
            for name, sha in entry['files_sha256'].items():
                if Path(name).name != name or hashlib.sha256((folder/name).read_bytes()).hexdigest() != sha:
                    raise ValueError('Evidence identity mismatch')
                result['files_verified'] += 1
            p = json.load(gzip.open(folder/'capture.json.gz','rt'))
            if p['harness_commit'] != ref or p['mode'] != mode or p['protocol'] != plan['protocol']: raise ValueError('Capture source/mode mismatch')
            for name, key in [(SOURCES[0],'runner_sha256'),(SOURCES[1],'hook_sha256')]:
                raw = subprocess.check_output(['git','show',ref+':'+name],cwd=repo)
                if hashlib.sha256(raw).hexdigest() != p[key]: raise ValueError('Runtime probe mismatch')
                result['source_hashes_verified'] += 1
            validate_identity(json.loads((folder/'identity.json').read_text()),p)
            row.update(analyze(p, json.load(gzip.open(folder/'trace.json.gz','rt')) if mode == 'probe' else None))
            result['errors'].extend(f'Slot {index}: {e}' for e in row['errors'])
        except (ValueError, KeyError, TypeError, OSError) as error:
            row.update(status='invalid',error=repr(error)); result['errors'].append(f'Slot {index}: {error}')
    if all('duration_ms' in c for c in result['cohorts']):
        times = [c['duration_ms'] for c in result['cohorts']]
        if abs(times[3]-times[0]) > times[0]*.2: result['errors'].append('Controls vary more than 20%')
        for a,b in [(0,1),(3,2)]:
            if times[b] > times[a]*1.2: result['errors'].append(f'Probe/control exceeds 1.20: {a}/{b}')
    if not result['errors']: result['status'] = 'complete_lifecycle_diagnostic'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--ref',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    ref=subprocess.check_output(['git','rev-parse',a.ref],text=True).strip()
    result=audit(a.root,Path(__file__).resolve().parents[2],ref);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cohorts'}))
