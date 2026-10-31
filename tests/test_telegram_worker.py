"""Exercise webhook-to-reply scheduling without contacting Telegram."""
from datetime import timedelta
import json
import sqlite3

import pytest

import telegram_bot as bot
from tests.test_telegram_bot import setup, submit, update, NOW, TOKEN, SECRET
from tests.test_telegram_transport import response
from tests.test_work import workspace


@pytest.fixture(autouse=True)
def worker_state(monkeypatch):
    monkeypatch.setattr(bot, '_WORKER', {'state': 'not_started', 'started_at': None, 'finished_at': None,
                                       'stage': None, 'error': None, 'processed': 0, 'sent': 0})
    monkeypatch.setattr(bot, '_WORKER_STARTED', None)


@pytest.mark.parametrize('command', ['/start', '/help'])
def test_complete_tick_replies_to_unlinked_private_commands(setup, monkeypatch, command):
    conn, _, _, client = setup
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '1')
    monkeypatch.setenv('CSS_BASE_URL', 'https://office.example')
    sent = []
    monkeypatch.setattr(bot.transport, 'send', lambda *args: sent.append(args) or ('accepted', 7, None))
    assert submit(client, update(text=command)).status_code == 200
    assert bot.tick(conn, NOW + timedelta(seconds=61)) == (1, 1)
    assert len(sent) == 1
    if command == '/start':
        assert 'https://office.example/account/telegram' in sent[0][2]
    else:
        assert 'Office Connect private commands' in sent[0][2]
    assert bot.tick(conn, NOW + timedelta(seconds=122)) == (0, 0)


def test_app_worker_uses_real_transport_and_reports_acceptance(setup, monkeypatch):
    import app
    conn, _, path, client = setup
    monkeypatch.setattr(app, 'DB', path)
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '1')
    monkeypatch.setenv('CSS_BASE_URL', 'https://office.example')
    calls = []
    response(monkeypatch, 200, {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101}}}, calls)
    assert submit(client).status_code == 200
    assert app._telegram_tick() == (1, 1)
    assert len(calls) == 1 and 'account/telegram' in calls[0][1]['json']['text']
    status = bot.worker_status(conn)
    assert status['state'] == 'finished' and status['deliveries'] == {'accepted': 1}
    assert app._telegram_tick() == (0, 0)


@pytest.mark.parametrize('stage', ['updates', 'change_routes', 'change_notices', 'reminders', 'delivery', 'cleanup'])
def test_failure_stage_is_visible_without_logging_private_error_text(setup, monkeypatch, caplog, stage):
    import telegram_changes
    conn, _, _, _ = setup
    target, name = {
        'updates': (bot, 'process_updates'), 'change_routes': (telegram_changes, 'prepare_routes'),
        'change_notices': (bot.notices, 'enqueue'), 'reminders': (bot.reminders, 'enqueue'),
        'delivery': (bot, 'deliver'), 'cleanup': (bot, 'cleanup'),
    }[stage]
    private = TOKEN + SECRET + ' private SQL and message contents'
    def fail(*args):
        raise sqlite3.OperationalError(private)
    monkeypatch.setattr(target, name, fail)
    with pytest.raises(sqlite3.OperationalError):
        bot.tick(conn, NOW)
    status = bot.worker_status(conn)
    assert status['state'] == 'failed' and status['stage'] == stage
    assert status['error'] == 'database_error'
    assert 'stage=' + stage in caplog.text and 'database_error' in caplog.text
    assert private not in caplog.text and TOKEN not in caplog.text and SECRET not in caplog.text
    assert 'private SQL' not in json.dumps(status)


def test_connection_failure_is_reported_before_tick(setup, monkeypatch, caplog):
    import app
    conn, _, _, _ = setup
    def fail(*args):
        raise sqlite3.OperationalError(TOKEN)
    monkeypatch.setattr(app.st, 'connect', fail)
    with pytest.raises(sqlite3.OperationalError):
        app._telegram_tick()
    status = bot.worker_status(conn)
    assert status['state'] == 'failed' and status['stage'] == 'connect'
    assert TOKEN not in caplog.text


def test_status_is_read_only_and_distinguishes_disabled_and_stalled_workers(setup, monkeypatch):
    conn, _, _, client = setup
    assert submit(client).status_code == 200
    before = conn.total_changes
    monkeypatch.setenv('CSS_NO_SCHEDULER', '1')
    status = bot.worker_status(conn)
    assert conn.total_changes == before and not conn.in_transaction
    assert status['updates'] == {'queued': 1} and status['deliveries'] == {}
    assert status['scheduler_disabled'] and status['state'] == 'not_started'
    assert TOKEN not in json.dumps(status) and SECRET not in json.dumps(status)
    monkeypatch.setattr(bot, '_WORKER_STARTED', bot.time.monotonic() - 181)
    assert bot.worker_status(conn)['stale']


def test_ops_panel_is_admin_only_and_shows_safe_worker_failure(admin, viewer, monkeypatch):
    monkeypatch.setenv('CSS_NO_SCHEDULER', '0')
    monkeypatch.setattr(bot, '_WORKER', {'state': 'failed', 'started_at': None, 'finished_at': None,
                                       'stage': 'updates', 'error': 'database_error', 'processed': 0, 'sent': 0})
    page = admin.get('/ops')
    assert page.status_code == 200 and 'id="telegram-health"' in page.text
    assert 'failed during updates (database_error)' in page.text
    assert '0 accepted by Telegram' in page.text
    assert viewer.get('/ops').status_code == 403


def test_rejection_logs_status_without_provider_body_or_retries(setup, monkeypatch, caplog):
    conn, _, _, client = setup
    response(monkeypatch, 401, {'ok': False, 'description': TOKEN + SECRET})
    assert submit(client).status_code == 200
    assert bot.tick(conn, NOW) == (1, 1)
    assert bot.worker_status(conn)['deliveries'] == {'failed': 1}
    assert 'Telegram delivery rejected: HTTP 401' in caplog.text
    assert TOKEN not in caplog.text and SECRET not in caplog.text
    assert bot.tick(conn, NOW + timedelta(seconds=61)) == (0, 0)
