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


@pytest.mark.parametrize('batch_kinds', [None, 'dog,rabbit,bird,turtle'])
def test_focused_driver_continues_after_missing_control(tmp_path, monkeypatch, batch_kinds):
    if batch_kinds is None:
        monkeypatch.delenv('CSS_AVATAR_BATCH_KINDS', raising=False)
    else:
        monkeypatch.setenv('CSS_AVATAR_BATCH_KINDS', batch_kinds)
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
    assert all(kind+'_traces' in result['harness_errors'] for kind in (batch_kinds or 'fern,mushroom,succulent').split(','))


def test_complete_assessment_rejects_missing_phases(tmp_path):
    from scripts.avatar_baseline.assess_complete import assess
    verdict=assess(tmp_path)
    assert verdict['status']=='inconclusive'
    assert all(phase in verdict['harness_errors'] for phase in ['functional','focused','runtime','matrix'])


def test_green_phase_labels_cannot_replace_raw_evidence(tmp_path):
    from scripts.avatar_baseline.assess_complete import assess, PHASES
    for phase in PHASES:
        directory=tmp_path/phase;directory.mkdir()
        (directory/'assessment.json').write_text(json.dumps({'status':'passed','gates':{'test':True},
            'source_commit':'current','chromium':'Chromium 156','expected_chromium':'156',
            'source_sha256':{'static/js/avatars.js':'current-js','templates/_avatars.html':'current-svg'}}))
    verdict=assess(tmp_path)
    assert verdict['gates']['functional'] is True
    assert verdict['status']=='inconclusive'
    assert 'fern_runtime_raw' in verdict['harness_errors']


def test_mixed_source_phases_cannot_pass(tmp_path):
    from scripts.avatar_baseline.assess_complete import assess, PHASES
    for phase in PHASES:
        directory=tmp_path/phase;directory.mkdir()
        (directory/'assessment.json').write_text(json.dumps({'status':'passed','gates':{'test':True},
            'source_commit':phase,'chromium':'Chromium 156','expected_chromium':'156',
            'source_sha256':{'static/js/avatars.js':'current-js','templates/_avatars.html':'current-svg'}}))
    verdict=assess(tmp_path)
    assert verdict['status']=='inconclusive'
    assert 'same_source_and_browser' in verdict['harness_errors']


def test_historical_art_renders_matching_growth_callers(tmp_path):
    from itertools import count
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from tests.avatar_browser_fixture import historical_art_loader
    root = Path(__file__).resolve().parents[1]
    current = FileSystemLoader(root / 'templates')
    stages = [dict(stage=n, name=str(n), current=n == 1, reached=n == 1,
                   points_at=n * 10) for n in range(1, 7)]
    how = dict(points=[], care=dict(verb='water', badge='Cared for', blurb='A test'))
    for historical in [True, False]:
        loader = historical_art_loader(current, tmp_path / 'old') if historical else current
        env = Environment(loader=loader, autoescape=True, undefined=StrictUndefined)
        ids = count(1)
        env.globals.update(avatar_uid=lambda: 'compat-' + str(next(ids)),
            avatar_family=lambda kind: 'plant', avatar_is_swimmer=lambda kind: False,
            avatar_month=lambda: 7, avatar_outfit=lambda: 'default',
            avatar_care_verb=lambda kind: 'water')
        macro = env.get_template('_avatars.html').module.avatar_svg
        assert ('static_preview' in macro.arguments) is not historical
        html = str(env.get_template('_growth.html').module.growth('fern', stages, how, None))
        assert html.count('data-avatar-kind="fern"') == 6
