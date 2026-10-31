"""Opt-in configuration is pinned to a verified service and fresh backup."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy_hf as deploy

URL = 'https://office-connect-telegram.onrender.com'
COMMIT = 'a'*40
TRAILERS = 'Telegram-Outbound-URL: '+URL+'\nTelegram-Outbound-Commit: '+COMMIT


def test_merge_trailers_are_explicit_and_never_taken_from_earlier_paragraphs():
    assert deploy.outbound_release_config('Ordinary release') is None
    assert deploy.outbound_release_config(TRAILERS+'\n\nNormal ending') is None
    assert deploy.outbound_release_config('Merge repair\n\n'+TRAILERS) == (URL, COMMIT)
    for text in (TRAILERS+'\nTelegram-Outbound-URL: '+URL,
                 TRAILERS.replace(URL, URL+'?token=private'),
                 TRAILERS.replace(COMMIT, 'invalid'),
                 TRAILERS.replace('https://', 'http://'),
                 TRAILERS.replace('.onrender.com', '.evil.example')):
        with pytest.raises(ValueError):
            deploy.outbound_release_config(text)


def test_trailers_only_apply_in_explicit_canonical_main_deployment(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'jongsky25/css-is')
    monkeypatch.delenv('CSS_TELEGRAM_OUTBOUND_SETUP', raising=False)
    monkeypatch.setattr(deploy.subprocess, 'check_output', lambda *args, **kwargs: TRAILERS)
    assert deploy.requested_outbound_service() is None
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_SETUP', '1')
    assert deploy.requested_outbound_service() == (URL, COMMIT)
    monkeypatch.setenv('GITHUB_REF', 'refs/pull/1/merge')
    assert deploy.requested_outbound_service() is None


def setup(monkeypatch, *, old_url=None, bad_network=False, bad_commit=False, backup_fails=False):
    events = []
    def read(url):
        events.append(url)
        if url.endswith('/health'):
            return {'ok': True, 'protocol': 1, 'source': deploy.LIVE_BASE,
                    'commit': 'b'*40 if bad_commit else COMMIT}
        return {'state': 'failed' if bad_network else 'reached', 'http_status': 302}
    def backup():
        events.append('backup')
        if backup_fails:
            raise SystemExit('Backup failed')
    class API:
        def get_space_variables(self, repo):
            assert repo == deploy.REPO_ID
            events.append('variables')
            return {'CSS_TELEGRAM_OUTBOUND_URL': SimpleNamespace(value=old_url)}
        def add_space_variable(self, repo, **kwargs):
            assert repo == deploy.REPO_ID
            assert kwargs == {'key': 'CSS_TELEGRAM_OUTBOUND_URL', 'value': URL}
            events.append('configure')
    monkeypatch.setattr(deploy, '_outbound_public_read', read)
    monkeypatch.setattr(deploy, 'secure_predeploy_backup', backup)
    return API(), events


def test_service_commit_network_and_backup_precede_the_only_environment_write(monkeypatch):
    api, events = setup(monkeypatch)
    deploy.prepare_outbound_service(api, (URL, COMMIT), True)
    assert events == [URL+'/health', URL+'/connection', 'backup', 'variables', 'configure', 'backup']


@pytest.mark.parametrize('failure', ['bad_network', 'bad_commit', 'backup_fails'])
def test_preflight_or_backup_failure_never_changes_hosting(monkeypatch, failure):
    api, events = setup(monkeypatch, **{failure: True})
    with pytest.raises(SystemExit):
        deploy.prepare_outbound_service(api, (URL, COMMIT), True)
    assert 'configure' not in events and 'variables' not in events


def test_same_configuration_is_idempotent_and_override_is_refused(monkeypatch):
    api, events = setup(monkeypatch, old_url=URL)
    deploy.prepare_outbound_service(api, (URL, COMMIT), True)
    assert 'backup' in events and 'configure' not in events
    events.clear()
    monkeypatch.setenv('CSS_DEPLOY_SKIP_BACKUP', '1')
    with pytest.raises(SystemExit):
        deploy.prepare_outbound_service(api, (URL, COMMIT), True)
    assert not events


def test_second_backup_failure_stops_before_the_code_upload_restart(monkeypatch):
    api, events = setup(monkeypatch)
    def backup():
        events.append('backup')
        if events.count('backup') == 2:
            raise SystemExit('Post-configuration backup unavailable')
    monkeypatch.setattr(deploy, 'secure_predeploy_backup', backup)
    with pytest.raises(SystemExit, match='Post-configuration backup unavailable'):
        deploy.prepare_outbound_service(api, (URL, COMMIT), True)
    assert events[-2:] == ['configure', 'backup']


def test_service_lock_is_an_exact_subset_of_audited_application_versions():
    root = Path(deploy.__file__).parent
    def pins(name):
        return dict(re.findall(r'^([a-zA-Z0-9_.-]+)==([^\s;\\]+)', (root/name).read_text(), re.M))
    service = pins('requirements-telegram-outbound.txt')
    runtime = pins('requirements.txt')
    assert service and all(runtime.get(name) == version for name, version in service.items())
    docker = (root/'Dockerfile.telegram-outbound').read_text()
    assert '--require-hashes' in docker and '--only-binary=:all:' in docker
    assert 'app.py' not in docker and 'css_is.db' not in docker
