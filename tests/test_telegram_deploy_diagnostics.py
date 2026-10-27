"""Read-only live worker observations using the existing deploy identity."""
import json
import sqlite3

import pytest

import deploy_hf as deploy
import pull_backup


def test_predeploy_snapshot_summary_is_read_only_and_excludes_private_fields(tmp_path):
    path = tmp_path / 'private-backup.db'
    with sqlite3.connect(path) as conn:
        for table in ('telegram_update', 'telegram_delivery', 'telegram_link_challenge'):
            conn.execute('CREATE TABLE ' + table + '(state TEXT, payload TEXT)')
            conn.execute('INSERT INTO ' + table + ' VALUES (?,?)', ('queued', 'private-code and staff message'))
            conn.execute('INSERT INTO ' + table + ' VALUES (?,?)', ('private-state', 'private-token'))
    before = path.read_bytes()
    result = deploy.telegram_snapshot_summary(path)
    assert path.read_bytes() == before
    assert result == {'telegram_update': {'queued': 1}, 'telegram_delivery': {'queued': 1}, 'telegram_link_challenge': {}}
    assert 'private' not in json.dumps(result)
    assert deploy.telegram_snapshot_summary(tmp_path / 'missing.db') == {'available': False}
    assert not (tmp_path / 'missing.db').exists()


def page(**fields):
    worker = {'state': 'failed', 'stage': 'delivery', 'error': 'worker_error',
              'scheduler_disabled': False, 'stale': False, 'bot_configured': True,
              'switches': {'inbound': True, 'delivery': True, 'link': True},
              'updates': {'queued': 4}, 'deliveries': {'failed': 1}, **fields}
    value = {'version': '8.81', 'commit': 'abcdef1', 'worker': worker, 'password': 'private-password'}
    return '<p>Private staff information</p><script type="application/json" id="telegram-diagnostics">' + json.dumps(value) + '</script>'


def test_only_allowlisted_typed_metadata_leaves_the_admin_page():
    result = deploy.telegram_ops_summary(page(token='secret-token', chat_id=123, text='private-message',
                       updates={'queued': 4, 'private-name': 999}, deliveries={'failed': 1, 'accepted': True}))
    assert result['updates'] == {'queued': 4} and result['deliveries'] == {'failed': 1}
    assert result['state'] == 'failed' and result['stage'] == 'delivery'
    assert not any(secret in json.dumps(result) for secret in
                   ('secret-token', 'private-name', 'private-message', 'private-password', 'Private staff', 'chat_id'))
    result = deploy.telegram_ops_summary(page(state='secret-state', stage='private-stage', error='secret-error'))
    assert not {'state', 'stage', 'error'} & result.keys()


def test_report_reads_only_ops_with_existing_credentials_and_bounded_samples(monkeypatch, capsys):
    monkeypatch.setenv('CSS_ADMIN_USER', 'private-user')
    monkeypatch.setenv('CSS_ADMIN_PASS', 'private-password')
    reads, sleeps, logins = [], [], []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 2 * 1024 * 1024 + 1
            return page().encode()
    class Opener:
        def open(self, request, timeout):
            reads.append(request.full_url)
            assert request.get_method() == 'GET' and timeout == 30
            return Response()
    opener = Opener()
    monkeypatch.setattr(pull_backup, '_opener', lambda: (opener, None))
    monkeypatch.setattr(pull_backup, 'login', lambda *args: logins.append(args))
    monkeypatch.setattr(deploy.time, 'sleep', sleeps.append)
    deploy.report_live_telegram_status()
    output = capsys.readouterr().out
    assert len(logins) == 1 and reads == [deploy.LIVE_BASE + '/ops'] * 3
    assert sleeps == [35, 35] and output.count('Telegram diagnostics:') == 3
    assert '"state": "failed"' in output
    assert 'private-user' not in output and 'private-password' not in output and 'Private staff' not in output


@pytest.mark.parametrize('failure', [ValueError('secret-cookie'), SystemExit('private-password')])
def test_login_failure_does_not_print_exception_or_credentials(monkeypatch, capsys, failure):
    monkeypatch.setenv('CSS_ADMIN_USER', 'private-user')
    monkeypatch.setenv('CSS_ADMIN_PASS', 'private-password')
    monkeypatch.setattr(pull_backup, '_opener', lambda: (None, None))
    def fail(*args): raise failure
    monkeypatch.setattr(pull_backup, 'login', fail)
    deploy.report_live_telegram_status()
    assert capsys.readouterr().out == 'Telegram diagnostics: unavailable (login, response or network check failed).\n'


def test_missing_credentials_skip_report_without_network(monkeypatch, capsys):
    monkeypatch.delenv('CSS_ADMIN_PASS', raising=False)
    monkeypatch.setattr(pull_backup, '_opener', lambda: pytest.fail('Unexpected login'))
    deploy.report_live_telegram_status()
    assert 'credentials not configured' in capsys.readouterr().out
