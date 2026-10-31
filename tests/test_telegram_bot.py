"""Private help webhook, crash recovery and provider boundaries; synthetic identities only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from threading import Event

from fastapi import FastAPI
import pytest
from starlette.testclient import TestClient

import backups
import request_security
import storage as st
import telegram_bot as bot
import telegram_transport as transport
from tests.test_work import workspace
from tests.test_telegram_storage import connection

TOKEN = '123456:' + 'A' * 35
SECRET = 'synthetic_webhook_secret_' + 'x' * 32
NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
HEADERS = {'x-telegram-bot-api-secret-token': SECRET}


def update(number=1, sender=101, text='/start'):
    return {'update_id': number, 'message': {'message_id': 1, 'from': {'id': sender, 'is_bot': False},
        'chat': {'id': sender, 'type': 'private'}, 'text': text}}


@pytest.fixture
def setup(workspace, monkeypatch):
    c, users, _, path = workspace
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('CSS_TELEGRAM_INBOUND_ENABLED', '1')
    monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED', '1')
    # These cases exercise the existing asynchronous Bot API worker. The
    # webhook transport has separate end-to-end cases with this override removed.
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT', 'direct')
    monkeypatch.setattr(bot, 'now_utc', lambda: NOW)
    app = FastAPI()
    app.include_router(bot.make_router(lambda: st.connect(path)))
    with TestClient(app) as client:
        yield c, users, path, client


def submit(client, value=None, **kwargs):
    return client.post(bot.PATH, json=update() if value is None else value, headers=HEADERS, **kwargs)


def test_secret_before_body_and_default_off(setup, monkeypatch):
    c, _, _, client = setup
    assert client.post(bot.PATH, content=b'x' * 70000).status_code == 403
    assert c.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 0
    monkeypatch.delenv('CSS_TELEGRAM_INBOUND_ENABLED')
    assert submit(client).status_code == 503
    monkeypatch.setenv('CSS_TELEGRAM_INBOUND_ENABLED', '1')
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET', 'short')
    assert submit(client).status_code == 503
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.delenv('CSS_TELEGRAM_BOT_TOKEN')
    assert submit(client).status_code == 503


@pytest.mark.parametrize('value', [[], {}, {'update_id': True}, {'update_id': -1},
    {'update_id': 2**63}, {'update_id': 1, 'message': {}},
    {'update_id': 1, 'callback_query': {'from': {'id': 101}, 'data': 'x'*65}}])
def test_malformed_rejected(setup, value):
    c, _, _, client = setup
    assert submit(client, value).status_code == 400
    assert c.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 0


def test_size_unicode_and_content_bounds(setup):
    _, _, _, client = setup
    for payload in (update(text='x'*4097), update(sender=True)):
        assert submit(client, payload).status_code == 400
    for content, expected in ((b'{', 400), (b'\xff', 400), (b' '*65537, 413)):
        assert client.post(bot.PATH, content=content, headers={**HEADERS, 'content-type': 'application/json'}).status_code == expected
    assert client.post(bot.PATH, content=b'{}', headers=HEADERS).status_code == 400


def test_durable_duplicate_once_and_no_business_content(setup, monkeypatch):
    c, _, path, client = setup
    value = update(text='/start private-forwarded-link-argument')
    assert submit(client, value).status_code == 200
    other = st.connect(path)
    assert other.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 1
    other.close()
    assert submit(client, value).status_code == 200
    assert bot.process_updates(c, NOW) == 1
    assert bot.process_updates(c, NOW) == 0
    assert c.execute('SELECT payload_json FROM telegram_update').fetchone() == (None,)
    assert 'private-forwarded' not in '\n'.join(c.iterdump())
    sent = []
    monkeypatch.setattr(transport, 'send', lambda *args: sent.append(args) or ('accepted', 12, None))
    assert bot.deliver(c, NOW) == 1
    assert bot.deliver(c, NOW) == 0
    assert sent == [(TOKEN, 101, bot.HELP)]
    assert submit(client, value).status_code == 200
    assert bot.process_updates(c, NOW) == 0
    assert c.execute('SELECT count(*) FROM telegram_operation').fetchone()[0] == 0
    assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0] == 0


def test_unsupported_groups_callbacks_and_edited_messages_ignored(setup):
    c, _, _, client = setup
    group = update();group['message']['chat'] = {'id': -100, 'type': 'supergroup'}
    values = [group, update(text='private content'), {'update_id': 3, 'edited_message': update()['message']},
              {'update_id': 4, 'callback_query': {'from': {'id': 101}, 'data': 'not-implemented'}}]
    for number, value in enumerate(values):
        value['update_id'] = number
        assert submit(client, value).status_code == 200
    assert bot.process_updates(c, NOW) == 0
    assert c.execute("SELECT count(*) FROM telegram_update WHERE state='ignored' AND payload_json IS NULL").fetchone()[0] == 4
    assert c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0] == 0


def test_rates_are_durable_duplicates_still_acknowledged(setup):
    c, _, path, client = setup
    for i in range(20):
        assert submit(client, update(i)).status_code == 200
    assert submit(client, update(20)).status_code == 429
    assert submit(client, update(0)).status_code == 200
    # Different senders consume the instance-wide remaining quota.
    for i in range(20,120):
        assert submit(client, update(i, sender=1000+i)).status_code == 200
    assert submit(client, update(121, sender=9000)).status_code == 429
    fresh = st.connect(path)
    assert bot.receive(fresh, bot.normalize(update(122)), b'{}', transport.config(), NOW) == 429
    fresh.close()
    assert c.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 120


def test_database_failure_never_acknowledges(setup, monkeypatch):
    c, _, _, client = setup
    def failed(*args):
        raise sqlite3.OperationalError('synthetic failure')
    monkeypatch.setattr(bot, 'receive', failed)
    assert submit(client).status_code == 503
    assert c.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 0


def test_enqueue_rollback_and_restart(setup, monkeypatch):
    c, _, path, client = setup
    assert submit(client).status_code == 200
    c.execute("CREATE TRIGGER stop_delivery BEFORE INSERT ON telegram_delivery BEGIN SELECT RAISE(ABORT,'fixture'); END")
    c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        bot.process_updates(c, NOW)
    assert c.execute('SELECT state FROM telegram_update').fetchone() == ('queued',)
    c.execute('DROP TRIGGER stop_delivery');c.commit()
    restarted = st.connect(path)
    assert bot.process_updates(restarted, NOW) == 1
    restarted.close()
    monkeypatch.setattr(transport, 'send', lambda *args: ('accepted', 7, None))
    restarted = st.connect(path)
    assert bot.deliver(restarted, NOW) == 1
    restarted.close()


@pytest.mark.parametrize('change', ['disconnect', 'deactivate', 'pause', 'rotate_token', 'restore'])
def test_revocation_or_config_change_before_send(setup, monkeypatch, change):
    c, users, path, client = setup
    cid, _ = connection(c, users[0]);c.commit()
    assert submit(client).status_code == 200
    assert bot.process_updates(c, NOW) == 1
    if change == 'disconnect':
        c.execute("UPDATE telegram_connection SET state='revoked',revoked_at=? WHERE id=?", (bot.stamp(NOW), cid));c.commit()
    elif change == 'deactivate':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],));c.commit()
    elif change == 'pause':
        monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED', '0')
    elif change == 'rotate_token':
        monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', '123456:'+'B'*35)
    else:
        backups.clear_restored_sessions(path)
    monkeypatch.setattr(transport, 'send', lambda *args: pytest.fail('Ineligible send'))
    assert bot.deliver(c, NOW) == 0
    assert c.execute('SELECT state FROM telegram_delivery').fetchone()[0] in ('cancelled', 'queued')


def test_retry_limits_expiry_and_uncertain_never_resends(setup, monkeypatch):
    c, _, _, client = setup
    submit(client);bot.process_updates(c, NOW)
    attempts = []
    monkeypatch.setattr(transport, 'send', lambda *args: attempts.append(1) or ('retry_wait', None, 60))
    assert bot.deliver(c, NOW) == 1
    assert bot.deliver(c, NOW) == 0
    for i in range(1,5):
        assert bot.deliver(c, NOW+timedelta(seconds=61*i)) == 1
    assert c.execute('SELECT state,attempts FROM telegram_delivery').fetchone() == ('failed', 5)
    submit(client, update(2));bot.process_updates(c, NOW)
    monkeypatch.setattr(transport, 'send', lambda *args: ('uncertain', None, None))
    assert bot.deliver(c, NOW) == 1
    assert bot.deliver(c, NOW+timedelta(hours=1)) == 0
    submit(client, update(3));bot.process_updates(c, NOW)
    assert bot.deliver(c, NOW+timedelta(days=2)) == 0
    assert c.execute("SELECT count(*) FROM telegram_delivery WHERE state='cancelled'").fetchone()[0] == 1


def test_interrupted_send_and_restore_fence_finalizer(setup, monkeypatch):
    c, _, path, client = setup
    submit(client);bot.process_updates(c, NOW)
    c.execute("UPDATE telegram_delivery SET state='sending',claim_token='old',lease_until=?", (bot.stamp(NOW-timedelta(seconds=1)),));c.commit()
    monkeypatch.setattr(transport, 'send', lambda *args: pytest.fail('Uncertain delivery replay'))
    assert bot.deliver(c, NOW) == 0
    assert c.execute('SELECT state FROM telegram_delivery').fetchone() == ('uncertain',)
    submit(client, update(2));bot.process_updates(c, NOW)
    def restore_during_send(*args):
        backups.clear_restored_sessions(path)
        return 'accepted', 99, None
    monkeypatch.setattr(transport, 'send', restore_during_send)
    assert bot.deliver(c, NOW) == 1
    assert c.execute("SELECT state,provider_message_id FROM telegram_delivery ORDER BY id DESC LIMIT 1").fetchone() == ('uncertain', None)


def test_concurrent_workers_send_once(setup, monkeypatch):
    c, _, path, client = setup
    submit(client);bot.process_updates(c, NOW)
    entered, release = Event(), Event()
    def send(*args):
        entered.set()
        assert release.wait(5)
        return 'accepted', 9, None
    monkeypatch.setattr(transport, 'send', send)
    def drain():
        other = st.connect(path)
        try:
            return bot.deliver(other, NOW)
        finally:
            other.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(drain)
        assert entered.wait(5)
        second = executor.submit(drain)
        try:
            assert second.result(timeout=5) == 0
        finally:
            release.set()
        assert first.result(timeout=5) == 1


def test_bounded_ticks_and_retention_leave_tombstones(setup, monkeypatch):
    c, _, _, client = setup
    for i in range(25):
        assert submit(client, update(i, sender=1000+i)).status_code == 200
    assert bot.process_updates(c, NOW) == 20
    assert bot.process_updates(c, NOW) == 5
    monkeypatch.setattr(transport, 'send', lambda *args: ('accepted', 9, None))
    assert bot.deliver(c, NOW) == 20
    assert bot.deliver(c, NOW) == 5
    bot.cleanup(c, NOW+timedelta(days=181))
    assert c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0] == 5
    assert c.execute('SELECT count(*) FROM telegram_update WHERE sender_id IS NULL').fetchone()[0] == 20
    assert submit(client, update(0)).status_code == 200
    assert bot.process_updates(c, NOW) == 0


def test_real_app_auth_and_origin_boundary(workspace, monkeypatch):
    import app
    _, _, _, path = workspace
    monkeypatch.setattr(app, 'DB', path)
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('CSS_TELEGRAM_INBOUND_ENABLED', '1')
    monkeypatch.setattr(transport, 'send', lambda *args: pytest.fail('Unexpected scheduler send'))
    with TestClient(app.app) as client:
        client.headers.pop('origin', None)
        assert submit(client).status_code == 200
        assert client.post(bot.PATH, json=update(2)).status_code == 403
        assert not request_security.csrf_exempt('POST', bot.PATH + '/child')
        assert not request_security.csrf_exempt('GET', bot.PATH)
        assert client.post('/calendar/new', data={}).status_code in (303,401,403)
        monkeypatch.setenv('CSS_TELEGRAM_INBOUND_ENABLED', '0')
        monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED', '0')
        assert app._telegram_tick() == (0,0)


def test_concurrent_duplicate_receipts_and_preprocess_revocation(setup):
    c, users, path, client = setup
    value = update()
    def accept():
        other = st.connect(path)
        try:
            return bot.receive(other, bot.normalize(value), json.dumps(value).encode(), transport.config(), NOW)
        finally:
            other.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: accept(), range(2))) == [200,200]
    assert c.execute('SELECT count(*) FROM telegram_update').fetchone()[0] == 1
    # Linking after intake cannot silently give an unlinked receipt account authority.
    cid, _ = connection(c, users[0]);c.commit()
    assert bot.process_updates(c, NOW) == 1
    assert c.execute('SELECT state FROM telegram_update').fetchone() == ('cancelled',)
    submit(client, update(2))
    c.execute("UPDATE telegram_connection SET state='revoked',revoked_at=? WHERE id=?", (bot.stamp(NOW),cid));c.commit()
    assert bot.process_updates(c, NOW) == 1
    assert c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0] == 0


def test_permanent_rejection_stops_queued_destination_until_fresh_command(setup, monkeypatch):
    c, _, _, client = setup
    submit(client);submit(client, update(2));bot.process_updates(c, NOW)
    calls = []
    monkeypatch.setattr(transport, 'send', lambda *args: calls.append(1) or ('failed', None, None))
    assert bot.deliver(c, NOW) == 1
    assert c.execute('SELECT state FROM telegram_delivery ORDER BY id').fetchall() == [('failed',),('cancelled',)]
    assert calls == [1]
    # Only a fresh, authenticated private command can schedule another attempt.
    monkeypatch.setattr(bot, 'now_utc', lambda: NOW+timedelta(minutes=1))
    assert submit(client, update(3)).status_code == 200
    bot.process_updates(c, NOW+timedelta(minutes=1))
    assert bot.deliver(c, NOW+timedelta(minutes=1)) == 1
