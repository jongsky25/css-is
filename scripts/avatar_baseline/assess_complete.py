"""Audit a complete hosted artifact without rerunning or replacing measurements."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from .verification_result import Results, frame_pass, read_json, validate_samples
except ImportError:
    from verification_result import Results, frame_pass, read_json, validate_samples

try:
    from .memory_audit import audit_memory
except ImportError:
    from memory_audit import audit_memory

PHASES = ('functional', 'focused', 'runtime', 'matrix')


def assess(root):
    root = Path(root)
    result = Results()
    phases = {}
    for phase in PHASES:
        def check_phase():
            data = read_json(root/phase/'assessment.json')
            phases[phase] = data
            if data['status'] == 'inconclusive' or data.get('harness_errors') or not data['gates']:
                raise ValueError(f'{phase} is incomplete or inconclusive')
            if not all(data.get('environment_checks', {}).values()):
                raise ValueError(f'{phase} has invalid environment controls')
            return data['status'] == 'passed' and all(data['gates'].values())
        result.check(phase, check_phase)

    def source_consistency():
        if set(phases) != set(PHASES):
            raise ValueError('Missing phase assessments')
        for key in ['source_commit', 'chromium', 'expected_chromium']:
            if len({data[key] for data in phases.values()}) != 1:
                raise ValueError(f'Phases disagree on {key}')
        for source in ['static/js/avatars.js', 'templates/_avatars.html']:
            if len({data['source_sha256'][source] for data in phases.values()}) != 1:
                raise ValueError(f'Phases disagree on {source}')
        return True
    result.check('same_source_and_browser', source_consistency, environment=True)

    for phase in ['focused','runtime','matrix']:
        def control():
            rows=read_json(root/phase/'control/empty-control.json')['samples']
            if len(rows)!=6 or {(r['cpu'],r['run']) for r in rows}!={(cpu,n) for cpu in [1,4] for n in range(3)}:
                raise ValueError('Incomplete control cohort')
            return all(r['actions'] and r['scenario']['frame_count'] and r['max_empty_callback_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in rows)
        result.check(phase+'_control_raw',control,environment=True)

    for kind in ['fern', 'mushroom', 'succulent']:
        def focused():
            native = read_json(root/'focused/native'/kind/'native-control.json')
            trace = read_json(root/'focused/traces'/kind/'summary.json')
            validate_samples(native['samples'], 5)
            validate_samples(trace['samples'], 10)
            if not native['after_only'] or {(r['version'],r['run']) for r in native['samples']} != {('after',n) for n in range(5)}:
                raise ValueError('Native sample identities mismatch')
            if {(r['version'],r['run']) for r in trace['samples']} != {(v,n) for v in ['before','after'] for n in range(5)}:
                raise ValueError('Focused trace sample identities mismatch')
            for data in [native, trace]:
                if data['source_commit'] != phases['focused']['source_commit']:
                    raise ValueError('Stale focused source')
            if trace['runtime_sha256'] != phases['focused']['source_sha256']['static/js/avatars.js']:
                raise ValueError('Focused runtime hash mismatch')
            if any(r['trace_data_loss'] or not r['owned_call_count'] for r in trace['samples']):
                raise ValueError('Lost or empty trace')
            return (all(not r['errors'] and frame_pass(r['scenario']['frame_p95_ms']) for r in native['samples'])
                    and all(not r['errors'] for r in trace['samples'])
                    and all(r['max_owned_call_wall_ms'] <= 50 and frame_pass(r['scenario']['frame_p95_ms']) for r in trace['samples'] if r['version']=='after'))
        result.check(kind+'_focused_raw', focused)

        def runtime():
            pair = [read_json(root/'runtime'/arm/kind/'summary.json') for arm in ['before','after']]
            for data in pair:
                validate_samples(data['samples'],5)
                if not data['after_only'] or {(r['version'],r['run']) for r in data['samples']} != {('after',n) for n in range(5)}:
                    raise ValueError('Whole-runtime sample identities mismatch')
                if any(r['trace_data_loss'] or not r['owned_call_count'] for r in data['samples']):
                    raise ValueError('Lost or empty whole-runtime trace')
            if not pair[0]['source_commit'].startswith('5b580d9') or pair[0]['source_commit']==pair[1]['source_commit'] or pair[0]['runtime_sha256']==pair[1]['runtime_sha256']:
                raise ValueError('Whole-runtime control reused current source')
            if pair[1]['source_commit']!=phases['runtime']['source_commit'] or pair[1]['runtime_sha256']!=phases['runtime']['source_sha256']['static/js/avatars.js']:
                raise ValueError('Stale whole-runtime current source')
            return all(not r['errors'] and r['max_owned_call_wall_ms']<=50 and frame_pass(r['scenario']['frame_p95_ms']) for r in pair[1]['samples'])
        result.check(kind+'_runtime_raw',runtime)

    def matrix():
        environments=[read_json(root/'matrix'/arm/'application/environment.json') for arm in ['before','after']]
        expected=phases['matrix']['expected_chromium']
        if any(e['chromium']!=expected for e in environments):
            raise ValueError('Baseline/current browser mismatch')
        if not environments[0]['source_commit'].startswith('1c964dc') or environments[0]['source_sha256']['static/js/avatars.js']==environments[1]['source_sha256']['static/js/avatars.js']:
            raise ValueError('Matrix baseline reused current JavaScript')
        if environments[1]['source_commit']!=phases['matrix']['source_commit']:
            raise ValueError('Stale matrix current source')
        for arm in ['before','after']:
            for mobile in [False,True]:
                for cache in ['cold','warm']:
                    rows=read_json(root/'matrix'/arm/'application'/f'{mobile}-{cache}.json')
                    if len(rows)!=5 or {r['run'] for r in rows}!=set(range(5)):
                        raise ValueError('Incomplete matrix group')
                    if any(r['seconds']<30 or r['chromium']!=expected or r['mobile']!=mobile or r['cache']!=cache or r['cpu_rate']!=(4 if mobile else 1) for r in rows):
                        raise ValueError('Matrix protocol mismatch')
        return True
    result.check('matrix_protocol',matrix,environment=True)
    memory=audit_memory(root/'matrix/before/application',root/'matrix/after/application')
    result.check('complete_memory_cohorts',lambda: memory['status']!='inconclusive',environment=True)
    result.check('all_scenario_and_navigation_memory',lambda: memory['status']=='passed')
    return {**result.as_dict(), 'full_memory_audit':memory, 'phase_statuses':{p:d['status'] for p,d in phases.items()},
            'source_commit':phases.get('functional',{}).get('source_commit'),
            'artifact_assessment_sha256':{p:hashlib.sha256((root/p/'assessment.json').read_bytes()).hexdigest() for p in phases},
            'scope':'Increment2B; pre-existing offscreen motion, timer activity and listener retention remain separately tracked release blockers.',
            'release_ready':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    verdict=assess(args.directory)
    (args.directory/'overall-assessment.json').write_text(json.dumps(verdict,indent=2)+'\n')
    print(json.dumps(verdict,indent=2))
    raise SystemExit(0 if verdict['status']=='passed' else 1)
