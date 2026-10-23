"""Evaluation evidence must not turn a partial, skipped or stale run green."""
import copy
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import ai_evaluation as evaluation


@pytest.fixture
def evidence():
    suite = evaluation.load_suite()
    results = {c['id']: {'status': 'passed', 'duration_ms': 1.25} for c in suite['cases']}
    return evaluation.report_for(suite, results, exitstatus=0)


def test_complete_report_is_minimized_and_covers_every_category(evidence):
    assert evaluation.validate_report(evidence) == len(evaluation.load_suite()['cases'])
    public = json.dumps(evidence) + evaluation.markdown(evidence)
    for private in ('EVAL-ONLY-VIEWER', 'EVAL-PRIVATE-REMARK', 'EVAL-PRIVATE-PERSON', 'offline-evaluation-key'):
        assert private not in public
    assert {row['category'] for row in evidence['cases']} == set(evaluation.CATEGORIES)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'failed', 'skipped', 'incomplete',
    'negative_time', 'nan_time', 'bool_time', 'stale_source', 'stale_manifest', 'stale_commit',
    'failed_session', 'collection_error', 'raw_prompt', 'wrong_category', 'bool_exitstatus', 'bool_schema'])
def test_reject_unsuccessful_incomplete_stale_or_unminimized_evidence(evidence, fault):
    bad = copy.deepcopy(evidence)
    if fault == 'missing': bad['cases'].pop()
    elif fault == 'duplicate': bad['cases'][-1] = dict(bad['cases'][0])
    elif fault in ('failed', 'skipped', 'incomplete'): bad['cases'][0]['status'] = fault
    elif fault == 'negative_time': bad['cases'][0]['duration_ms'] = -1
    elif fault == 'nan_time': bad['cases'][0]['duration_ms'] = float('nan')
    elif fault == 'bool_time': bad['cases'][0]['duration_ms'] = True
    elif fault == 'stale_source': bad['source_sha256'] = '0' * 64
    elif fault == 'stale_manifest': bad['manifest_sha256'] = '0' * 64
    elif fault == 'stale_commit': bad['git_commit'] = '0' * 40
    elif fault == 'failed_session': bad['pytest_exitstatus'] = 1
    elif fault == 'collection_error': bad['errors'] = ['case_coverage_incomplete']
    elif fault == 'raw_prompt': bad['question'] = 'This must not enter public evidence'
    elif fault == 'wrong_category': bad['cases'][0]['category'] = 'other'
    elif fault == 'bool_exitstatus': bad['pytest_exitstatus'] = False
    elif fault == 'bool_schema': bad['schema_version'] = True
    with pytest.raises(ValueError): evaluation.validate_report(bad)


@pytest.mark.parametrize('phase,outcome,xfail', [
    ('setup', 'failed', False), ('call', 'failed', False), ('teardown', 'failed', False),
    ('setup', 'skipped', False), ('call', 'skipped', True), ('call', 'passed', True)])
def test_recorder_fails_on_fixture_errors_skips_and_expected_failures(tmp_path, phase, outcome, xfail):
    recorder = evaluation.Recorder(tmp_path / 'report.json')
    recorder.phases = {c['id']: [('setup', 'passed'), ('call', 'passed'), ('teardown', 'passed')]
                       for c in recorder.suite['cases']}
    recorder.durations = {identifier: .001 for identifier in recorder.phases}
    identifier = recorder.suite['cases'][0]['id']
    recorder.nodes = {'synthetic-node': identifier}
    recorder.phases[identifier] = [(when, result) for when, result in recorder.phases[identifier] if when != phase]
    recorder.pytest_runtest_logreport(SimpleNamespace(nodeid='synthetic-node', when=phase,
        outcome=outcome, duration=.001, wasxfail='expected failure' if xfail else False))
    session = SimpleNamespace(exitstatus=0)
    recorder.pytest_sessionfinish(session, 0)
    report = json.loads((tmp_path / 'report.json').read_text())
    assert session.exitstatus == 1 and report['status'] == 'failed'
    with pytest.raises(ValueError): evaluation.validate_report(report)


def test_partial_real_pytest_run_cannot_reuse_old_passing_report(tmp_path, evidence):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps(evidence))
    result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'scripts.ai_evaluation', '-o', 'addopts=',
                             '-q', 'tests/test_ai_evaluation.py', '-k', 'facts-total',
                             '--ai-evaluation-report=' + str(path)], cwd=evaluation.ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout[-1000:]
    partial = json.loads(path.read_text())
    assert partial['status'] == 'failed' and 'case_coverage_incomplete' in partial['errors']
    assert sum(row['status'] == 'passed' for row in partial['cases']) == 1
    with pytest.raises(ValueError): evaluation.validate_report(partial)


def test_changed_cases_require_contract_version_increase(tmp_path, monkeypatch):
    cases, reference = evaluation.MANIFEST.read_bytes(), evaluation.REFERENCE.read_bytes()
    folder = tmp_path / 'evaluations/ai'; folder.mkdir(parents=True)
    manifest, data = folder / 'cases-v1.json', folder / 'reference-v1.json'
    manifest.write_bytes(cases); data.write_bytes(reference)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, stderr=subprocess.DEVNULL, text=True).strip()
    git('init', '-q'); git('add', '.')
    git('-c', 'user.name=Evaluation', '-c', 'user.email=evaluation@test.local', 'commit', '-qm', 'Synthetic contract')
    base = git('rev-parse', 'HEAD')
    monkeypatch.setattr(evaluation, 'ROOT', tmp_path)
    monkeypatch.setattr(evaluation, 'MANIFEST', manifest)
    monkeypatch.setattr(evaluation, 'REFERENCE', data)
    assert evaluation.check_contract(base) == '1.8.0'
    data.write_bytes(reference + b'\n')
    with pytest.raises(ValueError, match='version increase'): evaluation.check_contract(base)
    current = json.loads(cases); current['suite_version'] = '1.8.1'
    manifest.write_text(json.dumps(current))
    assert evaluation.check_contract(base) == '1.8.1'
