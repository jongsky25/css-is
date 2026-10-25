"""Regression tests for false acceptance and skipped independent verification."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest
from scripts.avatar_baseline.verification_result import Results, frame_pass, pytest_evidence, validate_samples


def test_missing_evidence_does_not_skip_next_check(tmp_path):
    result = Results()
    result.check('missing', lambda: json.loads((tmp_path/'missing.json').read_text()))
    result.check('next', lambda: True)
    assert result.gates['next']
    assert result.status == 'inconclusive'


def test_invalid_control_is_not_an_application_regression():
    result = Results()
    result.check('callback', lambda: False)
    assert result.status == 'application_regression'
    result.check('empty_control', lambda: False, environment=True)
    assert result.status == 'inconclusive'
    assert result.gates['callback'] is False


@pytest.mark.parametrize('body', ['', '<testcase><skipped/></testcase>', '<testcase><error/></testcase>'])
def test_missing_skipped_or_errored_tests_cannot_pass(tmp_path, body):
    path = tmp_path/'test.xml';path.write_text('<testsuite>'+body+'</testsuite>')
    with pytest.raises(ValueError):
        pytest_evidence(path, 1)


def test_test_failure_is_not_ignored(tmp_path):
    path = tmp_path/'test.xml';path.write_text('<testsuite><testcase><failure/></testcase></testsuite>')
    assert pytest_evidence(path, 1) is False


def test_duplicate_samples_cannot_satisfy_count():
    row = {'run':0,'version':'after','seconds':30,'actions':20,'scenario':{'frame_count':100}}
    with pytest.raises(ValueError):
        validate_samples([row,row], 2)


@pytest.mark.parametrize('value,passed', [(33.3,True),(33.300000000001,True),(33.4,False),(None,False),(float('nan'),False)])
def test_only_approved_frame_exception(value, passed):
    from tests.avatar_browser_fixture import accepted_frame
    assert frame_pass(value) is passed
    assert accepted_frame(value) is passed


def test_focused_driver_continues_after_missing_control(tmp_path, monkeypatch):
    script=Path(__file__).resolve().parents[1]/'scripts/avatar_baseline/ci_verify.py'
    monkeypatch.syspath_prepend(str(script.parent))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys,'argv',[str(script),'focused'])
    calls=[]
    monkeypatch.setattr(subprocess,'check_output',lambda *a,**kw:'fixture\n')
    def fake_run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(subprocess,'run',fake_run)
    with pytest.raises(SystemExit) as done:
        runpy.run_path(str(script),run_name='__main__')
    assert done.value.code==1
    assert any('tests/test_avatar_native_control.py' in call for call in calls)
    assert any('tests/test_avatar_cpu_attribution.py' in call for call in calls)
    result=json.loads((tmp_path/'avatar-verification/focused/assessment.json').read_text())
    assert result['status']=='inconclusive'
    assert 'empty_control' in result['harness_errors']
    assert all(kind+'_traces' in result['harness_errors'] for kind in ['fern','mushroom','succulent'])
