"""Independent checks, private status, deduplication and delivery-test safety."""
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.error

import pytest
import yaml

import backups as bk
import storage as st
from scripts import operational_monitor as m


def payload(**changes):
    return {'schema': 1, 'version': '9.58', 'checks': {
        'durability': 'ok', 'scheduled_backups': 'ok', 'audit': 'ok', **changes}}


GOOD = {'uptime': True, 'backup': True, 'audit': True, 'monitor': True}


class FakeGitHub:
    def __init__(self):
        self.rows, self.calls = [], []

    def label(self):
        pass

    def incidents(self):
        return [r for r in self.rows if r['state'] == 'open']

    def api(self, path, payload=None, method=None):
        self.calls.append((path, payload, method))
        if path == '/issues':
            row = dict(payload, number=len(self.rows) + 1, state='open',
                       user={'login': 'github-actions[bot]'})
            self.rows.append(row)
            return row
        row = self.rows[int(path.rsplit('/', 1)[1]) - 1]
        row.update(payload)
        return row


def test_one_incident_per_confirmed_failure_and_recovery():
    github = FakeGitHub()
    failed = dict(GOOD, uptime=False, backup=None, audit=None)
    assert m.reconcile(github, failed, failed, 'https://github.com/run') == ['uptime:opened']
    assert m.reconcile(github, failed, failed, 'https://github.com/run') == []
    assert m.reconcile(github, failed, GOOD, 'https://github.com/run') == []
    assert github.rows[0]['state'] == 'open'
    assert m.reconcile(github, GOOD, GOOD, 'https://github.com/run') == ['uptime:recovered']
    assert github.rows[0]['state'] == 'closed'
    assert m.reconcile(github, failed, failed, 'https://github.com/run') == ['uptime:opened']


def test_startup_unknown_holds_existing_backup_incident():
    github = FakeGitHub()
    failed = dict(GOOD, backup=False)
    m.reconcile(github, failed, failed, 'https://github.com/run')
    starting = m.status_checks(payload(durability='starting'))
    assert starting['backup'] is None
    m.reconcile(github, starting, starting, 'https://github.com/run')
    assert github.rows[0]['state'] == 'open'
    assert m.status_checks(payload(durability='starting', scheduled_backups='failed'))['backup'] is False


@pytest.mark.parametrize('change', [
    {'durability': 'failed'}, {'durability': 'stale'}, {'durability': 'unconfigured'},
    {'scheduled_backups': 'failed'}, {'scheduled_backups': 'overdue'},
    {'scheduled_backups': 'disabled'}, {'scheduled_backups': 'unknown'},
])
def test_all_backup_failure_states_are_actionable(change):
    assert m.status_checks(payload(**change))['backup'] is False


def test_audit_failure_not_ignored_during_deploy_grace():
    github = FakeGitHub()
    value = dict(GOOD, uptime=False, audit=False, monitor=False)
    changed = m.reconcile(github, value, value, 'https://github.com/run',
                          maintenance=True, rolling_out=True)
    assert changed == ['audit:opened']
    assert github.rows[0]['assignees'] == ['jongsky25']


def test_delivery_test_is_marked_and_never_claims_production_outage():
    github = FakeGitHub()
    assert m.reconcile(github, GOOD, GOOD, 'https://github.com/run', test=True) == ['test:opened']
    assert m.marker('test') in github.rows[0]['body']
    assert 'not a production incident' in github.rows[0]['body']
    assert m.reconcile(github, GOOD, GOOD, 'https://github.com/run', test=True) == []
    assert len(github.rows) == 1


def test_foreign_issue_cannot_suppress_a_real_alert():
    github = FakeGitHub()
    github.rows.append({'number': 1, 'state': 'open', 'body': m.marker('audit'),
                        'user': {'login': 'someone-else'}})
    failed = dict(GOOD, audit=False)
    assert m.reconcile(github, failed, failed, 'https://github.com/run') == ['audit:opened']


@pytest.mark.parametrize('value', [None, [], {'schema': True},
    {'schema': 1, 'version': '9.58', 'checks': {'audit': 'ok'}},
    payload(audit='unknown'), payload(durability=True)])
def test_invalid_monitor_payload_is_not_healthy(value):
    with pytest.raises(m.CheckUnavailable):
        m.status_checks(value)


def test_response_size_is_bounded():
    with pytest.raises(m.CheckUnavailable):
        m.read_json(io.BytesIO(b' ' * (m.LIMIT + 1)))


class Response(io.BytesIO):
    status = 200
    headers = {}

    def __init__(self, value):
        super().__init__(json.dumps(value).encode())


def test_outage_does_not_try_admin_login(monkeypatch):
    probe = m.Probe('private-user', 'private-password')
    calls = []
    def fail(path, fields=None):
        calls.append(path)
        raise OSError('private-provider-error')
    monkeypatch.setattr(probe, 'request', fail)
    assert probe.sample() == {'uptime': False, 'backup': None, 'audit': None, 'monitor': None}
    assert calls == ['/health']


def test_rejected_login_is_config_failure_and_never_retried(monkeypatch):
    probe = m.Probe('private-user', 'private-password')
    calls = []
    def request(path, fields=None):
        calls.append(path)
        if path == '/health':
            return Response({'status': 'ok', 'db': 'ok', 'monitoring_protocol': 1})
        raise urllib.error.HTTPError(m.BASE + path, 401, 'private-error', {}, None)
    monkeypatch.setattr(probe, 'request', request)
    for _ in range(2):
        assert probe.sample() == dict(GOOD, backup=None, audit=None, monitor=False)
    assert calls.count('/login') == 1


def test_private_probe_reuses_then_revokes_session(monkeypatch):
    probe = m.Probe('private-user', 'private-password')
    calls = []
    def request(path, fields=None):
        calls.append(path)
        if path == '/health':
            return Response({'status': 'ok', 'db': 'ok', 'monitoring_protocol': 1})
        if path == '/login':
            assert fields['existing_account_only'] == '1'
            raise urllib.error.HTTPError(m.BASE + path, 303, 'redirect',
                                          {'Location': '/admin/monitoring-status'}, None)
        return Response(payload())
    monkeypatch.setattr(probe, 'request', request)
    assert probe.sample() == GOOD and probe.sample() == GOOD
    probe.close()
    assert calls.count('/login') == 1 and calls[-1] == '/logout'


def test_redirects_never_forward_credentials():
    assert m.NoRedirect().redirect_request(None, None, None, None, None, None) is None


def test_legacy_app_never_receives_monitor_credentials(monkeypatch):
    probe = m.Probe('private-user', 'private-password')
    calls = []
    def request(path, fields=None):
        calls.append(path)
        return Response({'status': 'ok', 'db': 'ok'})
    monkeypatch.setattr(probe, 'request', request)
    assert probe.sample() == dict(GOOD, backup=None, audit=None, monitor=False)
    assert calls == ['/health']


def test_existing_account_only_never_enters_first_admin_setup(app_mod, client, db_path, monkeypatch):
    from tests.conftest import PW
    conn = st.connect(db_path)
    before = conn.execute('SELECT COUNT(*) FROM admin_user').fetchone()[0]
    conn.close()
    monkeypatch.setattr(st, 'count_admin_users', lambda conn: 0)
    monkeypatch.setattr(st, 'create_admin_user', lambda *args, **kwargs: pytest.fail('must not create an account'))
    response = client.post('/login', data={'username': 'synthetic@example.invalid',
        'password': PW, 'existing_account_only': '1'}, follow_redirects=False)
    assert response.status_code == 401
    conn = st.connect(db_path)
    assert conn.execute('SELECT COUNT(*) FROM admin_user').fetchone()[0] == before
    conn.close()


def test_maintenance_grace_is_bounded_and_excludes_verification(monkeypatch):
    github = m.GitHub('private-token')
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    job = {'name': 'deploy', 'status': 'in_progress',
           'started_at': (now - timedelta(minutes=5)).isoformat()}
    monkeypatch.setattr(github, 'api', lambda path: {'workflow_runs': [{'id': 1}]}
                        if 'workflows' in path else {'jobs': [job]})
    assert github.maintenance(now)
    job['name'] = 'verification / Python 3.11 (normal)'
    assert not github.maintenance(now)
    job['name'] = 'deploy'
    job['started_at'] = (now - timedelta(minutes=11)).isoformat()
    assert not github.maintenance(now)


def test_rollout_grace_matches_source_and_expires(monkeypatch):
    github = m.GitHub('private-token')
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    sha = 'a' * 40
    run = {'head_sha': sha, 'status': 'in_progress',
           'created_at': (now - timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(github, 'api', lambda path: {'workflow_runs': [run]})
    assert github.rolling_out(sha, now)
    run['status'] = 'completed'
    assert not github.rolling_out(sha, now)
    run['status'], run['head_sha'] = 'in_progress', 'b' * 40
    assert not github.rolling_out(sha, now)
    run['head_sha'], run['created_at'] = sha, (now - timedelta(minutes=91)).isoformat()
    assert not github.rolling_out(sha, now)


@pytest.mark.parametrize('freq,hours', [('h6', 6), ('h12', 12), ('daily', 24), ('weekly', 168)])
def test_backup_deadline_grace_and_failure_are_schedule_aware(monkeypatch, freq, hours):
    last = datetime(2026, 10, 26, 2)
    cfg = {'enabled': True, 'freq': freq, 'time': '02:00', 'weekday': 0,
           'last_backup_at': last.isoformat(), 'last_backup_status': 'OK — private snapshot path'}
    monkeypatch.setattr(bk, 'read_config', lambda conn: cfg)
    assert bk.monitoring_status(None, last + timedelta(hours=hours, minutes=14)) == 'ok'
    assert bk.monitoring_status(None, last + timedelta(hours=hours, minutes=16)) == 'overdue'
    cfg['last_backup_status'] = 'FAILED at private path — private provider error'
    assert bk.monitoring_status(None, last + timedelta(minutes=1)) == 'failed'


def test_missing_future_and_aware_backup_dates_are_unknown(monkeypatch):
    now = datetime(2026, 11, 1)
    cfg = {'enabled': True, 'last_backup_status': ''}
    monkeypatch.setattr(bk, 'read_config', lambda conn: cfg)
    for stamp in ['', 'invalid', '2026-11-01T00:00:00+08:00', '2026-11-02T00:00:00']:
        cfg['last_backup_at'] = stamp
        assert bk.monitoring_status(None, now) == 'unknown'
    cfg['enabled'] = False
    assert bk.monitoring_status(None, now) == 'disabled'


def test_private_status_access_and_content(app_mod, admin, viewer, client, monkeypatch):
    assert client.get('/admin/monitoring-status', follow_redirects=False).status_code == 303
    assert viewer.get('/admin/monitoring-status').status_code == 403
    monkeypatch.setattr(app_mod, '_persist_health_view', lambda: {'tone': 'good', 'down': False,
                       'text': 'private-path and private provider error'})
    monkeypatch.setattr(bk, 'monitoring_status', lambda conn: 'ok')
    monkeypatch.setattr(st, 'audit_health', lambda conn: {'ok': True, 'raw_ok': False,
                                                          'acknowledged': True})
    response = admin.get('/admin/monitoring-status')
    assert response.status_code == 200 and response.json()['checks'] == payload()['checks']
    assert 'no-store' in response.headers['cache-control']
    assert 'private-' not in response.text and 'raw_ok' not in response.text
    monkeypatch.setattr(st, 'audit_health', lambda conn: {'ok': False})
    assert admin.get('/admin/monitoring-status').json()['checks']['audit'] == 'failed'


def test_never_ticked_saver_only_has_bounded_startup_grace(app_mod, admin, monkeypatch):
    monkeypatch.setattr(app_mod, '_persist_health_view', lambda: {'tone': 'neutral', 'down': False})
    monkeypatch.setattr(app_mod.mon, 'health', lambda *args, **kwargs: {'uptime_s': 120})
    assert admin.get('/admin/monitoring-status').json()['checks']['durability'] == 'starting'
    monkeypatch.setattr(app_mod.mon, 'health', lambda *args, **kwargs: {'uptime_s': 301})
    assert admin.get('/admin/monitoring-status').json()['checks']['durability'] == 'stale'


def test_workflow_never_runs_production_credentials_on_pr_or_other_branch():
    value = yaml.load(Path('.github/workflows/operational-monitor.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(value['on']) == {'schedule', 'workflow_dispatch'}
    assert value['on']['schedule'][0]['cron'] == '2-59/5 * * * *'
    job = value['jobs']['check']
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert "github.repository == 'jongsky25/css-is'" in job['if']
    assert value['permissions'] == {'contents': 'read', 'actions': 'read', 'issues': 'write'}
    assert job['timeout-minutes'] == '5'
    assert value['concurrency']['cancel-in-progress'] == 'false'


def test_actual_synthetic_app_login_probe_and_logout(app_mod, monkeypatch):
    from starlette.testclient import TestClient
    from tests.conftest import PW
    monkeypatch.setattr(app_mod, '_persist_health_view', lambda: {'tone': 'good', 'down': False})
    monkeypatch.setattr(bk, 'monitoring_status', lambda conn: 'ok')
    probe = m.Probe('admin@test.local', PW)
    with TestClient(app_mod.app, base_url=m.BASE) as client:
        class Transport:
            def open(self, request, timeout):
                response = client.request(request.get_method(), request.full_url,
                    content=request.data, headers=dict(request.header_items()), follow_redirects=False)
                if response.status_code != 200:
                    raise urllib.error.HTTPError(request.full_url, response.status_code,
                                                  'synthetic status', response.headers, None)
                return io.BytesIO(response.content)
        probe.opener = Transport()
        assert probe.sample() == GOOD
        assert probe.sample() == GOOD
        assert client.get('/admin/monitoring-status', follow_redirects=False).status_code == 200
        probe.close()
        assert client.get('/admin/monitoring-status', follow_redirects=False).status_code == 303


def test_cli_refuses_non_main_before_reading_secrets_or_sending(monkeypatch):
    monkeypatch.setattr('sys.argv', ['operational_monitor.py'])
    monkeypatch.setenv('GITHUB_REPOSITORY', m.REPO)
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/untrusted')
    monkeypatch.setattr(m, 'GitHub', lambda *args: pytest.fail('must not initialize delivery'))
    with pytest.raises(m.CheckUnavailable):
        m.main()
