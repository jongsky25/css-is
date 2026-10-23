"""Offline A22 evaluation runner, minimized evidence and fail-closed report gate.

pytest loads this plugin through pytest.ini; recording is enabled only by
--ai-evaluation-report. No runtime app import or provider call occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'evaluations/ai/cases-v1.json'
REFERENCE = ROOT / 'evaluations/ai/reference-v1.json'
CATEGORIES = ('facts', 'authority', 'freshness', 'injection', 'resilience')
REPORT_KEYS = {'schema_version', 'suite_id', 'suite_version', 'contract_version', 'mode', 'reference_clock',
               'python_version', 'manifest_sha256', 'reference_sha256', 'source_sha256', 'git_commit',
               'application_version', 'status', 'pytest_exitstatus', 'errors', 'cases'}
PROVENANCE = ('app.py', 'ai_core.py', 'ai_facts.py', 'auth.py', 'storage.py',
              'calendar_answers.py', 'office_answers.py', 'rooms.py', 'ratelimit.py',
              'version.py', 'ai_report_drafts.py', 'css_is_engine.py', 'dashboard_insights.py',
              'tests/test_ai_evaluation.py', 'tests/test_ai_report_evaluation.py',
              'tests/test_ai_triage_evaluation.py', 'tests/test_ai_feedback_triage_browser.py',
              'tests/test_ai_verbatim_evaluation.py', 'tests/test_ai_verbatim_browser.py',
              'templates/feedback_detail.html', 'static/js/activity_ai.js', 'scripts/ai_evaluation.py',
              'evaluations/ai/cases-v1.json', 'evaluations/ai/reference-v1.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_suite():
    suite = json.loads(MANIFEST.read_text())
    if (suite['schema_version'] != 1 or suite['suite_id'] != 'existing-ai-answers'
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', suite['suite_version'])
            or suite['contract_version'] != 1 or tuple(suite['categories']) != CATEGORIES
            or len(suite['cases']) < 25):
        raise ValueError('Invalid evaluation manifest.')
    ids = set()
    for case in suite['cases']:
        if (not re.fullmatch(r'[a-z][a-z0-9-]{1,60}', case['id']) or case['id'] in ids
                or case['category'] not in CATEGORIES or not isinstance(case['question'], str)
                or not case['question'].strip() or not isinstance(case['expect'], dict)):
            raise ValueError('Invalid or duplicate evaluation case.')
        ids.add(case['id'])
    if {c['category'] for c in suite['cases']} != set(CATEGORIES):
        raise ValueError('An evaluation category is missing.')
    return suite


def provenance():
    from scripts.check_release import metadata
    h = hashlib.sha256()
    for name in PROVENANCE:
        h.update(name.encode() + b'\0' + (ROOT / name).read_bytes() + b'\0')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('The evaluation requires a source commit.')
    return {'manifest_sha256': digest(MANIFEST), 'reference_sha256': digest(REFERENCE),
            'source_sha256': h.hexdigest(), 'git_commit': commit,
            'application_version': metadata((ROOT / 'version.py').read_text())['APP_VERSION']}


def report_for(suite, results, *, exitstatus, errors=(), binding=None):
    expected = {case['id']: case for case in suite['cases']}
    problems = list(errors)
    if set(results) != set(expected):
        problems.append('case_coverage_incomplete')
    rows = []
    for identifier, case in expected.items():
        result = results.get(identifier, {'status': 'incomplete', 'duration_ms': 0})
        rows.append({'id': identifier, 'category': case['category'], **result})
    if exitstatus != 0:
        problems.append('pytest_unsuccessful')
    ok = not problems and all(row['status'] == 'passed' for row in rows)
    return {'schema_version': 1, 'suite_id': suite['suite_id'], 'suite_version': suite['suite_version'],
            'contract_version': suite['contract_version'], 'mode': 'offline-provider-fixtures',
            'reference_clock': suite['reference_clock'], 'python_version': platform.python_version(),
            **(binding or provenance()), 'status': 'passed' if ok else 'failed',
            'pytest_exitstatus': int(exitstatus), 'errors': sorted(set(problems)), 'cases': rows}


def validate_report(report):
    suite = load_suite()
    if (not isinstance(report, dict) or set(report) != REPORT_KEYS
            or type(report.get('schema_version')) is not int or report.get('schema_version') != 1
            or report.get('suite_id') != suite['suite_id']
            or report.get('suite_version') != suite['suite_version']
            or type(report.get('contract_version')) is not int or report.get('contract_version') != suite['contract_version']
            or report.get('mode') != 'offline-provider-fixtures'
            or report.get('reference_clock') != suite['reference_clock']
            or report.get('status') != 'passed' or type(report.get('pytest_exitstatus')) is not int
            or report.get('pytest_exitstatus') != 0
            or report.get('errors') != []):
        raise ValueError('Evaluation did not pass with the current contract.')
    if not isinstance(report.get('python_version'), str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', report['python_version']):
        raise ValueError('Evaluation runtime evidence is invalid.')
    if any(report.get(k) != v for k, v in provenance().items()):
        raise ValueError('Evaluation evidence is stale or belongs to another source revision.')
    rows = report.get('cases')
    expected = {case['id']: case['category'] for case in suite['cases']}
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('Evaluation coverage is incomplete.')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'category', 'status', 'duration_ms'}
                or row['id'] not in expected or row['id'] in seen or row['category'] != expected[row['id']]
                or row['status'] != 'passed' or type(row['duration_ms']) not in (int, float)
                or not math.isfinite(row['duration_ms']) or row['duration_ms'] < 0):
            raise ValueError('An evaluation case failed, was skipped, or has invalid evidence.')
        seen.add(row['id'])
    return len(rows)


def markdown(report):
    lines = [f"# AI evaluation — {report['suite_version']}", '',
             f"Result: **{report['status']}** · Application {report['application_version']}",
             f"Source commit: `{report['git_commit']}`", '',
             'Offline simulated provider responses; this is not a real-model accuracy or latency score.', '',
             '| Category | Passed | Total |', '|---|---:|---:|']
    for category in CATEGORIES:
        rows = [r for r in report['cases'] if r['category'] == category]
        lines.append(f"| {category} | {sum(r['status'] == 'passed' for r in rows)} | {len(rows)} |")
    lines += ['', '| Case | Result | Test time (ms) |', '|---|---|---:|']
    lines += [f"| {r['id']} | {r['status']} | {r['duration_ms']:.1f} |" for r in report['cases']]
    return '\n'.join(lines) + '\n'


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as target:
        temporary = Path(target.name)
        target.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def pytest_addoption(parser):
    parser.addoption('--ai-evaluation-report', help='Write minimized A22 JSON and Markdown reports')


def pytest_configure(config):
    config.addinivalue_line('markers', 'ai_evaluation(case_id): versioned A22 scenario')
    path = config.getoption('--ai-evaluation-report')
    if path:
        config.pluginmanager.register(Recorder(Path(path).resolve()), 'a22-recorder')


class Recorder:
    def __init__(self, path):
        if path.suffix != '.json' or path in (MANIFEST, REFERENCE):
            raise ValueError('Choose a separate .json report path.')
        self.path, self.suite, self.binding = path, load_suite(), provenance()
        self.nodes, self.phases, self.durations, self.errors = {}, {}, {}, []
        # Never leave a previous passing artifact behind after a failed rerun.
        path.unlink(missing_ok=True)
        path.with_suffix('.md').unlink(missing_ok=True)

    def pytest_collection_modifyitems(self, items):
        seen = set()
        for item in items:
            markers = list(item.iter_markers('ai_evaluation'))
            if not markers:
                continue
            if len(markers) != 1 or len(markers[0].args) != 1:
                self.errors.append('invalid_case_marker')
                continue
            identifier = markers[0].args[0]
            if identifier in seen or identifier not in {c['id'] for c in self.suite['cases']}:
                self.errors.append('duplicate_or_unknown_case')
                continue
            seen.add(identifier)
            self.nodes[item.nodeid] = identifier

    def pytest_runtest_logreport(self, report):
        identifier = self.nodes.get(report.nodeid)
        if identifier is not None:
            outcome = 'failed' if getattr(report, 'wasxfail', False) else report.outcome
            self.phases.setdefault(identifier, []).append((report.when, outcome))
            self.durations[identifier] = self.durations.get(identifier, 0) + report.duration

    def pytest_sessionfinish(self, session, exitstatus):
        results = {}
        for identifier, phases in self.phases.items():
            passed = sorted(phases) == [('call', 'passed'), ('setup', 'passed'), ('teardown', 'passed')]
            status = ('passed' if passed else 'failed' if any(p[1] == 'failed' for p in phases)
                      else 'skipped' if any(p[1] == 'skipped' for p in phases) else 'incomplete')
            results[identifier] = {'status': status,
                                   'duration_ms': round(self.durations[identifier] * 1000, 3)}
        if self.binding != provenance():
            self.errors.append('source_changed_during_evaluation')
        report = report_for(self.suite, results, exitstatus=exitstatus, errors=self.errors, binding=self.binding)
        atomic_write(self.path, json.dumps(report, indent=2, allow_nan=False) + '\n')
        atomic_write(self.path.with_suffix('.md'), markdown(report))
        if report['status'] != 'passed' and session.exitstatus == 0:
            session.exitstatus = 1


def check_contract(base):
    """Changes to the reviewed cases/reference require a new suite version."""
    suite = load_suite()
    base = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', base + '^{commit}'],
                                   cwd=ROOT, text=True).strip()
    paths = ('evaluations/ai/cases-v1.json', 'evaluations/ai/reference-v1.json')
    present = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', base, '--', *paths],
                                      cwd=ROOT, text=True).splitlines()
    if not present:
        return suite['suite_version']  # First introduction of the evaluation.
    if set(present) != set(paths):
        raise ValueError('The previous evaluation contract is incomplete.')
    old = [subprocess.check_output(['git', 'show', base + ':' + name], cwd=ROOT) for name in paths]
    if any(before != (ROOT / name).read_bytes() for before, name in zip(old, paths)):
        previous = json.loads(old[0])['suite_version']
        if tuple(map(int, suite['suite_version'].split('.'))) <= tuple(map(int, previous.split('.'))):
            raise ValueError('Changed evaluation cases/reference require a suite version increase.')
    return suite['suite_version']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--shuffle-seed', type=int)
    commands.add_parser('check').add_argument('report', type=Path)
    commands.add_parser('contract').add_argument('--base', required=True)
    args = parser.parse_args()
    # Running as a script puts scripts/, rather than ROOT, on sys.path.
    sys.path.insert(0, str(ROOT))
    try:
        if args.command == 'contract':
            print(f'AI evaluation contract OK: {check_contract(args.base)}')
            return
        if args.command == 'run':
            output = args.output.resolve()
            suite = load_suite()
            env = dict(os.environ, CSS_TEST_NOW=suite['reference_clock'])
            command = [sys.executable, '-m', 'pytest', '-p', 'scripts.ai_evaluation', '-o', 'addopts=',
                       '-q', 'tests/test_ai_evaluation.py', 'tests/test_ai_report_evaluation.py',
                       'tests/test_ai_triage_evaluation.py', 'tests/test_ai_verbatim_evaluation.py',
                       '--ai-evaluation-report=' + str(output)]
            if args.shuffle_seed is not None:
                command.append('--shuffle-seed=' + str(args.shuffle_seed))
            code = subprocess.call(command, cwd=ROOT, env=env)
            if code:
                raise ValueError('Evaluation execution failed; inspect its test results.')
        else:
            output = args.report
        count = validate_report(json.loads(output.read_text()))
        print(f'AI evaluation gate OK: {count} cases, all categories passed; offline fixtures only')
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        parser.exit(1, 'AI evaluation gate failed: evidence is missing, unsuccessful, incomplete or stale.\n')


if __name__ == '__main__':
    main()
