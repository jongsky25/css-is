"""Validate known DOM receivers and join them to bounded normal-page generations."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from scripts.avatar_baseline.mixed_membership_fixture import SCHEDULE as MIXED_SCHEDULE, MODES as MIXED_MODES, tag as mixed_tag
import subprocess
from scripts.avatar_baseline.element_membership_capability import BUILD, COUNT, STAGES
from scripts.avatar_baseline.run_element_membership import SOURCES

OFFSETS = {'allocate': 0x5ab0350, 'pool': 0x5ab0550, 'receiver': 0x100b1880}
PAGE_SIZE = 131072


def generations(events):
    active = {}; spans = []; unknown_returns = 0
    for e in sorted((e for e in events if e['kind'] != 'receiver'), key=lambda e: e['returned_ns']):
        base = int(e['address'], 16); key = (e['backend'], base)
        if base == 0 or base % PAGE_SIZE:
            raise ValueError('Invalid normal page base')
        if e['kind'] == 'allocate':
            if key in active:
                raise ValueError('Overlapping page generations')
            span = {'base': base, 'backend': e['backend'], 'generation': len(spans),
                    'begin_ns': e['returned_ns'], 'end_ns': None, 'labels': []}
            active[key] = span; spans.append(span)
        else:
            span = active.pop(key, None)
            if span is None:
                unknown_returns += 1
            elif e['begin_ns'] < span['begin_ns']:
                raise ValueError('Ambiguous page return ordering')
            else:
                span['end_ns'] = e['begin_ns']
    return spans, unknown_returns


def join_receivers(events, spans):
    by_base = defaultdict(list)
    for span in spans: by_base[span['base']].append(span)
    rows = []
    for e in events:
        if e['kind'] != 'receiver': continue
        address = int(e['address'], 16); base = address & ~(PAGE_SIZE-1)
        if not address: raise ValueError('Null receiver')
        matching = [s for s in by_base[base] if s['begin_ns'] <= e['begin_ns']
                    and (s['end_ns'] is None or e['returned_ns'] < s['end_ns'])]
        if len(matching) > 1: raise ValueError('Ambiguous receiver page generation')
        span = matching[0] if matching else None
        if span: span['labels'].append(e['phase'])
        rows.append({'phase': e['phase'], 'address': e['address'], 'base': hex(base),
                     'begin_ns': e['begin_ns'], 'end_ns': e['returned_ns'],
                     'generation': span['generation'] if span else None,
                     'coverage': 'observed_request' if span else 'preexisting_or_unobserved'})
    return rows


def validate_absent_query(p, events=()):
    if (p.get('observable') != 'absent-attribute-node-ns' or
        p.get('attribute_namespace') != 'urn:css-is:membership:absent' or
        p.get('attribute_local_name') != 'absent'):
        raise ValueError('Wrong absent-attribute observable')
    if any(e.get('attribute_absent') is not True for e in events if e['kind']=='receiver'):
        raise ValueError('Native attribute getter did not return null')


def inspect(p):
    protocol = p['protocol']
    count = COUNT if protocol == 'native-element-membership-v1' else 32 if protocol in ['native-element-membership-v3','native-element-membership-v4','native-element-membership-v5'] else 128
    if (p['status'] != 'captured' or protocol not in ['native-element-membership-v1', 'native-element-membership-v2', 'native-element-membership-v3', 'native-element-membership-v4', 'native-element-membership-v5']
        or p['acceptance'] is not False or p['forced_gc'] is not False or p['build_id'] != BUILD
        or p['browser_version'] != '156.0.8078.47' or p['frida_version'] != '17.5.1'
        or p['count_per_group'] != count or p['stage_count'] != STAGES
        or (protocol in ['native-element-membership-v2', 'native-element-membership-v3', 'native-element-membership-v4'] and p.get('fixture_count_per_group') != 4096)):
        raise ValueError('Invalid capability identity or incomplete capture')
    if protocol in ['native-element-membership-v4','native-element-membership-v5']: validate_absent_query(p)
    mixed=protocol=='native-element-membership-v5'
    if mixed and (p.get('fixture_count_per_group')!=3000 or p.get('fixture_profile')!='legacy-dom-svg-style-3000-v1' or p.get('fixture_schedule')!=MIXED_SCHEDULE):
        raise ValueError('Wrong mixed fixture profile')
    if [s['index'] for s in p['stages']] != list(range(STAGES)) or p['end_ns'] <= p['begin_ns']:
        raise ValueError('Incomplete fixed schedule')
    for s in p['stages']:
        if s['dom_before_sha256'] != s['dom_after_sha256']:
            raise ValueError('DOM changed during census')
        if mixed and s.get('fixture_mode')!=MIXED_SCHEDULE[s['index']]: raise ValueError('Wrong mixed fixture schedule')
        expected = [f'census:{s["index"]}:{g}:{r}' for g in ['avatar', 'other'] for r in [0, 1]]
        if [c['phase'] for c in s['censuses']] != expected:
            raise ValueError('Census schedule mismatch')
        for c in s['censuses']:
            if c['result']['count'] != count or len(c['result']['counts']) != count:
                raise ValueError('Incomplete known-element census')
            if protocol in ['native-element-membership-v2', 'native-element-membership-v3', 'native-element-membership-v4'] and c['result'].get('fixture_count') != 4096:
                raise ValueError('Wrong fixed fixture size')
            if mixed and (c['result'].get('fixture_count')!=3000 or c['result'].get('tags')!=[mixed_tag(s['fixture_mode'],c['phase'].split(':')[2])]*count):
                raise ValueError('Wrong mixed census size or element type')
            if any(v != 1 for v in c['result']['counts']):
                raise ValueError('Unexpected geometry result')
            if not p['begin_ns'] <= s['begin_ns'] <= c['begin_ns'] <= c['end_ns'] <= s['end_ns'] <= p['end_ns']:
                raise ValueError('Invalid census interval')
    result = {'status': 'valid_control' if p['mode'] == 'control' else 'capability_failed',
              'mode': p['mode'], 'duration_ms': (p['end_ns']-p['begin_ns'])/1e6, 'errors': []}
    if p['mode'] == 'control':
        if 'history' in p: raise ValueError('Injected control')
        return result
    if p['mode'] != 'probe': raise ValueError('Invalid mode')
    h = p['history']; events = h['events']
    expected_offsets = {**OFFSETS, 'receiver': 0x100cce80} if protocol in ['native-element-membership-v4','native-element-membership-v5'] else OFFSETS
    if h['offsets'] != expected_offsets or h['page_size'] != PAGE_SIZE or h['dropped']:
        raise ValueError('Wrong native hook or dropped events')
    if any(m.get('type') == 'error' for m in p['messages']):
        raise ValueError('Native agent error')
    for e in events:
        if e['kind'] not in OFFSETS or not 0 < e['begin_ns'] <= e['callback_ready_ns'] <= e['returned_ns']:
            raise ValueError('Malformed native event')
    if protocol in ['native-element-membership-v4','native-element-membership-v5']: validate_absent_query(p, events)
    spans, unknown = generations(events); rows = join_receivers(events, spans)
    by_phase = defaultdict(list)
    for e in rows: by_phase[e['phase']].append(e)
    expected_phases = {c['phase']: c for s in p['stages'] for c in s['censuses']}
    if set(by_phase) != set(expected_phases):
        raise ValueError('Missing or extra receiver phase')
    for label, census in expected_phases.items():
        selected = by_phase[label]
        if len(selected) != count or len({e['address'] for e in selected}) != count:
            raise ValueError('Known-element/native-receiver count mismatch')
        if any(not census['begin_ns'] <= e['begin_ns'] <= e['end_ns'] <= census['end_ns'] for e in selected):
            raise ValueError('Receiver outside census')
        if not any(e['generation'] is not None for e in selected):
            result['errors'].append('No observed-request membership: ' + label)
    for index in range(STAGES):
        groups = []
        for group in ['avatar', 'other']:
            first = [e['address'] for e in by_phase[f'census:{index}:{group}:0']]
            second = [e['address'] for e in by_phase[f'census:{index}:{group}:1']]
            if first != second: raise ValueError('Repeat receiver identities differ')
            groups.append(set(first))
        if groups[0] & groups[1]: raise ValueError('Disjoint DOM groups share receiver identity')
    matched = sum(e['generation'] is not None for e in rows)
    returned = [s for s in spans if s['labels'] and s['end_ns'] is not None]
    mixed = [s for s in spans if {label.split(':')[2] for label in s['labels']} == {'avatar', 'other'}]
    prep = [e['callback_ready_ns'] - e['begin_ns'] for e in events
            if p['begin_ns'] <= e['begin_ns'] <= p['end_ns']]
    fraction = sum(prep)/(p['end_ns']-p['begin_ns'])
    maximum = max(prep, default=0)/1e6
    if matched < len(rows)*.9: result['errors'].append('Observed-request receiver coverage below 90%')
    if not returned: result['errors'].append('No labelled page generation observed returning to pool')
    if not mixed: result['errors'].append('No mixed-group page generation demonstrated')
    if protocol=='native-element-membership-v5':
        returned_modes={MIXED_SCHEDULE[int(label.split(':')[1])] for span in returned for label in span['labels']}
        for mode in MIXED_MODES:
            if mode not in returned_modes: result['errors'].append('No labelled page return for mixed mode: '+mode)
    if fraction > .05 or maximum > 250: result['errors'].append('Callback preparation exceeds 5% or 250ms')
    result.update(status='capability_passed' if not result['errors'] else 'capability_failed',
                  receiver_records=len(rows), matched_receiver_records=matched, matched_fraction=matched/len(rows),
                  page_generations=len(spans), labelled_returned_generations=len(returned),
                  mixed_group_generations=len(mixed), unknown_returns=unknown,
                  preparation_fraction=fraction, max_preparation_ms=maximum,
                  receivers=rows, generations=spans)
    return result


def validate_identity(trace, capture):
    pids = {e['pid'] for e in trace['traceEvents'] if e.get('name') == 'CommitLoad'
            and e.get('args', {}).get('data', {}).get('url', '').startswith('http://127.0.0.1:')
            and e['args']['data']['url'].endswith('/empty')}
    if pids != {capture['pid']}:
        raise ValueError('Independent renderer identity mismatch')
    if capture['mode'] == 'probe':
        ready = [m['payload'] for m in capture['messages'] if m.get('payload', {}).get('ready')]
        if len(ready) != 1 or ready[0]['pid'] != capture['pid']:
            raise ValueError('Native receiver process mismatch')


def audit(root, repo, ref):
    plan = json.loads((root / 'experiment.json').read_text())
    if (plan['protocol'] not in ['native-element-membership-v1', 'native-element-membership-v2', 'native-element-membership-v3', 'native-element-membership-v4', 'native-element-membership-v5'] or plan['harness_commit'] != ref
        or plan['order'] != ['control', 'probe', 'probe', 'control'] or plan['acceptance'] is not False):
        raise ValueError('Invalid frozen calibration')
    result = {'acceptance': False, 'status': 'calibration_failed', 'cohorts': [], 'errors': [], 'files_verified': 0, 'source_hashes_verified': 0}
    if len(plan['cohorts']) != 4: raise ValueError('Incomplete calibration schedule')
    for name in SOURCES:
        raw = subprocess.check_output(['git', 'show', ref + ':' + name], cwd=repo)
        if (root / 'harness' / name).read_bytes() != raw: raise ValueError('Archived harness mismatch')
        result['source_hashes_verified'] += 1
    runner = 'scripts/avatar_baseline/element_membership_capability.py'
    hook = 'scripts/avatar_baseline/native/element_membership.js'
    for index, entry in enumerate(plan['cohorts']):
        row = {'index': index}; result['cohorts'].append(row)
        try:
            if entry['index'] != index or entry['mode'] != plan['order'][index] or entry['exit_code']:
                raise ValueError('Failed/invalid slot')
            folder = root / f'{index}-{entry["mode"]}'
            if not {'capture.json.gz', 'identity.json', 'runner.txt'} <= entry['files_sha256'].keys():
                raise ValueError('Missing evidence files')
            for name, sha in entry['files_sha256'].items():
                if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != sha:
                    raise ValueError('Evidence identity mismatch')
                result['files_verified'] += 1
            p = json.load(gzip.open(folder / 'capture.json.gz', 'rt'))
            if p['harness_commit'] != ref or p['mode'] != entry['mode'] or p['protocol'] != plan['protocol']:
                raise ValueError('Frozen source or mode mismatch')
            for name, key in [(runner, 'runner_sha256'), (hook, 'hook_sha256')]:
                raw = subprocess.check_output(['git', 'show', ref + ':' + name], cwd=repo)
                if hashlib.sha256(raw).hexdigest() != p[key]: raise ValueError('Runtime probe identity mismatch')
                result['source_hashes_verified'] += 1
            trace = json.loads((folder / 'identity.json').read_text())
            validate_identity(trace, p)
            row.update(inspect(p))
            if row['errors']: result['errors'].extend(f'Slot {index}: {e}' for e in row['errors'])
        except (ValueError, OSError, KeyError, TypeError) as e:
            row.update(status='invalid', error=repr(e)); result['errors'].append(f'Slot {index}: {e}')
    if any(c.get('status') not in ['valid_control', 'capability_passed'] for c in result['cohorts']):
        result['errors'].append('Four intact qualified slots required')
    if all('duration_ms' in c for c in result['cohorts']):
        times = [c['duration_ms'] for c in result['cohorts']]
        if abs(times[3]-times[0]) > times[0]*.2: result['errors'].append('Control duration varies more than 20%')
        for control, probe in [(0, 1), (3, 2)]:
            if times[probe] > times[control]*1.2: result['errors'].append(f'Probe/control exceeds 1.20: {control}/{probe}')
    if not result['errors']: result['status'] = 'calibration_passed'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--ref', required=True)
    p.add_argument('--out', type=Path, required=True); a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    ref = subprocess.check_output(['git', 'rev-parse', a.ref], cwd=repo, text=True).strip()
    result = audit(a.root, repo, ref); a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k,v in result.items() if k != 'cohorts'}))
